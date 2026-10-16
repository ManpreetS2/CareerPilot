/** Guards chrome.scripting injections against tab switches and navigations.
 *
 * Fill downloads a resume and may retry attach after the form fill. Between
 * those awaits the user can switch tabs or the page can navigate; injecting
 * into a stale tabId would type answers into the wrong application. Every
 * attach/fill/verify call must re-check tab id, URL, active focus, and the
 * main-frame document id captured when Fill started.
 */

export class InjectionAbortedError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "InjectionAbortedError";
  }
}

export type InjectionTarget = {
  tabId: number;
  url: string;
  /** Chrome document id for the main frame at Fill start; required for
   * document-navigation guards when the API provides it. */
  documentId?: string;
};

type ScriptingResult<T> = { result?: T; documentId?: string };

function tabsGet(tabId: number): Promise<chrome.tabs.Tab> {
  return new Promise((resolve, reject) => {
    try {
      const maybe = chrome.tabs.get(tabId) as unknown;
      if (maybe && typeof (maybe as Promise<chrome.tabs.Tab>).then === "function") {
        (maybe as Promise<chrome.tabs.Tab>)
          .then((tab) => {
            if (!tab) {
              reject(new InjectionAbortedError("The original tab is gone — fill aborted."));
              return;
            }
            resolve(tab);
          })
          .catch(() => reject(new InjectionAbortedError("The original tab is gone — fill aborted.")));
        return;
      }
    } catch {
      // Fall through to callback form.
    }
    chrome.tabs.get(tabId, (tab) => {
      const err = chrome.runtime?.lastError;
      if (err || !tab) {
        reject(new InjectionAbortedError("The original tab is gone — fill aborted."));
        return;
      }
      resolve(tab);
    });
  });
}

/** Named so tests (and Chrome's serialized func.name) can distinguish the
 * document-id probe from attach/fill/verify injections. Must stay a function
 * declaration — an object-literal `func: () => true` is often named "func". */
function probeInjectionDocument(): boolean {
  return true;
}

/** Snapshot the active tab before any async download/fill work. */
export async function captureInjectionTarget(expectedUrl: string): Promise<InjectionTarget> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) throw new Error("Could not read the current tab.");
  if (tab.url !== expectedUrl) {
    throw new InjectionAbortedError("This tab changed — rechecking it now.");
  }
  if (tab.status === "loading") {
    throw new InjectionAbortedError("This tab is still navigating — fill aborted.");
  }

  // Probe once so later injections can pin the same document id. A full
  // navigation replaces the document id even when the URL string matches.
  const probe = (await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: probeInjectionDocument,
  })) as ScriptingResult<boolean>[];
  const documentId = probe?.[0]?.documentId;

  return { tabId: tab.id, url: expectedUrl, documentId };
}

/** Re-validate immediately before (and after) every page injection. */
export async function assertInjectionTarget(target: InjectionTarget): Promise<void> {
  const tab = await tabsGet(target.tabId);
  const [active] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!active?.id || active.id !== target.tabId) {
    throw new InjectionAbortedError("You switched tabs — fill aborted.");
  }
  if (tab.url !== target.url) {
    throw new InjectionAbortedError("This tab navigated — fill aborted.");
  }
  if (tab.status === "loading") {
    throw new InjectionAbortedError("This tab is still navigating — fill aborted.");
  }
}

/** executeScript with tab/URL/document guards before and after the call. */
export async function executeScriptOnTarget<Args extends unknown[], Result>(
  target: InjectionTarget,
  func: (...args: Args) => Result,
  args: Args,
): Promise<Result | undefined> {
  await assertInjectionTarget(target);

  const scriptTarget: chrome.scripting.InjectionTarget = { tabId: target.tabId };
  if (target.documentId) {
    scriptTarget.documentIds = [target.documentId];
  }

  let injection: ScriptingResult<Result>[];
  try {
    injection = (await chrome.scripting.executeScript({
      target: scriptTarget,
      func,
      args,
    })) as ScriptingResult<Result>[];
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    if (/document|frame|tab|navigat|no matching/i.test(message)) {
      throw new InjectionAbortedError("This page reloaded or navigated — fill aborted.");
    }
    throw err;
  }

  const resultDoc = injection?.[0]?.documentId;
  if (target.documentId && resultDoc && resultDoc !== target.documentId) {
    throw new InjectionAbortedError("This page reloaded or navigated — fill aborted.");
  }

  await assertInjectionTarget(target);
  return injection?.[0]?.result;
}
