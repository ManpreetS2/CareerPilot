import {
  ApiError,
  BackendUnreachableError,
  getActiveTabUrl,
  getAutofillData,
  getPanelData,
  isJobPageUrl,
  NotLoggedInError,
  originPattern,
  type PanelData,
} from "./api";
import { fillFormInPage } from "./fillForm";
import { escapeHtml, materialsBadge, matchBadge, scoutedTimeAgo, sourceBadge, statusBadge } from "./render";

const WEB_APP_URL = "http://localhost:5173";

const app = document.getElementById("app")!;
// Guards against a fast tab switch firing a second load while the first
// one's still awaiting the network — the response for the stale URL is
// simply dropped instead of racing with the newer one to paint the panel.
let requestToken = 0;

function renderLoading() {
  app.innerHTML = `<p class="text-ink-500">Checking this page…</p>`;
}

/** Shown for pages that could never be a job posting (chrome:// internals,
 * the New Tab page, file://). Deliberately not the "not tracked yet" state,
 * which would imply CareerPilot could track this page if you asked it to. */
function renderIdle() {
  app.innerHTML = `
    <div class="card p-4">
      <p class="font-semibold">No job page open</p>
      <p class="mt-1 text-ink-500">Open a job posting in this tab and the panel will check it automatically.</p>
    </div>`;
}

function renderError(message: string, kind: "login" | "retry" = "retry") {
  app.innerHTML = `
    <div class="card p-4">
      <p class="text-danger-600 dark:text-rose-300">${escapeHtml(message)}</p>
      ${
        kind === "login"
          ? `<a class="btn-secondary mt-3" href="${WEB_APP_URL}/login" target="_blank" rel="noreferrer">Open CareerPilot to log in</a>`
          : `<button id="retry-btn" type="button" class="btn-secondary mt-3">Try again</button>`
      }
    </div>`;
  // Without this the only way out of an error state is switching tabs and
  // back, since the panel has no other trigger of its own.
  document.getElementById("retry-btn")?.addEventListener("click", () => void refresh());
}

function renderNotTracked() {
  app.innerHTML = `
    <div class="card p-4">
      <p class="font-semibold">This page isn't tracked in CareerPilot yet</p>
      <p class="mt-1 text-ink-500">Add it from the Jobs page to see its fit score and evidence here.</p>
      <a class="btn-primary mt-3" href="${WEB_APP_URL}/jobs" target="_blank" rel="noreferrer">Open Jobs in CareerPilot</a>
    </div>`;
}

function evidenceList(label: string, skills: string[]): string {
  if (skills.length === 0) return "";
  return `<div class="mt-2"><p class="text-xs font-semibold uppercase tracking-wide text-ink-500">${label}</p>
    <div class="mt-1 flex flex-wrap gap-1.5">
      ${skills.map((s) => `<span class="rounded-lg bg-ink-100 px-2 py-0.5 text-xs text-ink-700 dark:bg-ink-800 dark:text-ink-100">${escapeHtml(s)}</span>`).join("")}
    </div></div>`;
}

function assistedApplyCard(data: PanelData, job: { id?: string | null }): string {
  const heading = `<p class="text-xs font-semibold uppercase tracking-wide text-ink-500">Assisted apply</p>`;

  // Assisted apply only exists for Greenhouse and Lever (the backend's
  // detect_ats_platform decides, and sends the verdict in panel-data).
  // Rendering a button here on, say, a Remotive posting would offer an
  // action that can only ever fail — say why instead.
  if (data.platform === "unsupported") {
    return `
    <div class="card mt-3 p-4">
      ${heading}
      <p class="mt-1 text-ink-500">Only Greenhouse and Lever application pages can be filled. Open this job's real application page to use it.</p>
    </div>`;
  }

  // Filling needs an approved application package. Showing the button
  // anyway would mean clicking it just to be told no, with the panel unable
  // to say what to do about it — so surface the backend's own reason and
  // link straight to where it gets resolved.
  if (!data.apply_ready) {
    return `
    <div class="card mt-3 p-4">
      ${heading}
      <p class="mt-1 text-ink-500">${escapeHtml(data.apply_blocked_reason ?? "This application isn't ready to fill yet.")}</p>
      <a class="btn-secondary mt-2" href="${WEB_APP_URL}/applications/${encodeURIComponent(job.id ?? "")}" target="_blank" rel="noreferrer">Prepare it in CareerPilot</a>
    </div>`;
  }

  // An overridden package is about to be typed into a real employer's
  // application form. This is the last point before that happens, so the
  // warning belongs here and not only back in the web app.
  const unverifiedNotice = data.materials_unverified
    ? `<p class="mt-2 rounded-lg bg-amber-100 px-2.5 py-2 text-xs font-semibold text-warn-600 dark:bg-amber-950/40 dark:text-amber-200">These materials were kept without evidence checks. Read them before you submit — they may claim experience your resume doesn't show.</p>`
    : "";

  return `
    <div class="card mt-3 p-4">
      ${heading}
      <p class="mt-1 text-ink-500">Fills what it can confidently map into the real form on this page. Never submits — you review and submit yourself.</p>
      ${unverifiedNotice}
      <button id="fill-btn" type="button" class="btn-primary mt-2">Fill this page</button>
      <div id="fill-status" role="status" class="mt-2"></div>
    </div>`;
}

function renderTracked(data: PanelData, url: string) {
  const job = data.job!;
  const seenAgo = scoutedTimeAgo(job.date_scraped);
  const score = data.score;

  app.innerHTML = `
    <div class="card p-4">
      <p class="text-xs text-ink-500">${escapeHtml(job.company)}</p>
      <h1 class="font-semibold leading-snug">${escapeHtml(job.title)}</h1>
      <div class="mt-2 flex flex-wrap items-center gap-1.5">
        ${statusBadge(job.status)}
        ${sourceBadge(job.source)}
        ${seenAgo ? `<span class="text-xs text-ink-500">${escapeHtml(seenAgo)}</span>` : ""}
      </div>
    </div>

    <div class="card mt-3 p-4">
      <p class="text-xs font-semibold uppercase tracking-wide text-ink-500">Fit score</p>
      <div class="mt-2">${matchBadge(score?.overall_score, score?.recommendation, score?.score_kind)}</div>
      ${
        score
          ? `${evidenceList("Matched", score.matched_skills)}${evidenceList("Missing", score.missing_skills)}`
          : `<p class="mt-2 text-ink-500">Not scored yet.</p><a class="btn-secondary mt-2" href="${WEB_APP_URL}/jobs/${encodeURIComponent(job.id ?? "")}" target="_blank" rel="noreferrer">Calculate in CareerPilot</a>`
      }
    </div>

    <div class="card mt-3 p-4">
      <p class="text-xs font-semibold uppercase tracking-wide text-ink-500">Application materials</p>
      <div class="mt-2">${materialsBadge(data.materials_status)}</div>
      ${
        data.materials_status === "current"
          ? ""
          : `<a class="btn-secondary mt-2" href="${WEB_APP_URL}/applications/${encodeURIComponent(job.id ?? "")}" target="_blank" rel="noreferrer">Open in CareerPilot</a>`
      }
    </div>

    ${assistedApplyCard(data, job)}`;

  document.getElementById("fill-btn")?.addEventListener("click", () => void runFill(url));
}

/** chrome.scripting.executeScript needs access to the page's own origin.
 * "activeTab" grants that only for the tab that was active at the moment
 * the user invoked the extension — opening the side panel from the toolbar.
 * The whole point of a panel is that it stays open while you move between
 * tabs, and those later tabs are NOT covered by that grant, so the fill
 * would fail on exactly the tabs the panel exists to serve. Asking for the
 * one origin being filled, from the click itself, keeps page access
 * per-site and consent-driven instead of a standing allowlist in the
 * manifest.
 *
 * chrome.permissions.request must be reached while the click's user gesture
 * is still live, so nothing may be awaited ahead of it — notably not a
 * chrome.permissions.contains check, which would consume the gesture to
 * answer a question that doesn't need asking: requesting an origin that is
 * already granted resolves true immediately and shows no prompt. */
function ensurePageAccess(url: string): Promise<boolean> {
  const pattern = originPattern(url);
  if (!pattern) return Promise.resolve(false);
  return chrome.permissions.request({ origins: [pattern] });
}

async function runFill(url: string) {
  const button = document.getElementById("fill-btn") as HTMLButtonElement | null;
  const statusEl = document.getElementById("fill-status");
  if (!button || !statusEl) return;
  button.disabled = true;
  // Synchronous DOM writes only before ensurePageAccess — see its comment
  // on why nothing may be awaited ahead of the permission request.
  statusEl.textContent = "Checking page access…";

  try {
    if (!(await ensurePageAccess(url))) {
      statusEl.textContent = "CareerPilot needs permission to fill this site's form. Click Fill this page again to allow it.";
      return;
    }

    statusEl.textContent = "Looking up this application…";
    const autofill = await getAutofillData(url);
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) throw new Error("Could not read the current tab.");
    // The panel renders one job but fills whatever tab is active when the
    // button is clicked. If those have drifted apart — a tab switch the
    // panel hasn't caught up with yet — filling would write this job's
    // answers into a different company's form. Refuse and resync instead.
    if (tab.url !== url) {
      statusEl.textContent = "This tab changed — rechecking it now.";
      void refresh();
      return;
    }

    statusEl.textContent = "Filling the form…";
    const injection = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: fillFormInPage,
      args: [autofill],
    });
    const result = injection?.[0]?.result;
    if (!result) {
      statusEl.textContent = "No result returned from the page.";
      return;
    }
    const parts: string[] = [];
    if (result.filled.length > 0) {
      parts.push(
        `<p class="mt-2 text-xs font-semibold uppercase tracking-wide text-ink-500">Filled automatically</p><ul class="mt-1 list-disc pl-4">${result.filled
          .map((f) => `<li>${escapeHtml(f.name)}</li>`)
          .join("")}</ul>`,
      );
    }
    if (result.flagged.length > 0) {
      parts.push(
        `<p class="mt-2 text-xs font-semibold uppercase tracking-wide text-warn-600">Needs your input</p><ul class="mt-1 list-disc pl-4">${result.flagged
          .map((f) => `<li>${escapeHtml(f.name)} — ${escapeHtml(f.reason)}</li>`)
          .join("")}</ul>`,
      );
    }
    statusEl.innerHTML = parts.join("") || "Nothing on this page matched.";
  } catch (err) {
    if (err instanceof NotLoggedInError) {
      renderError(err.message, "login");
      return;
    }
    statusEl.textContent = err instanceof Error ? err.message : String(err);
  } finally {
    button.disabled = false;
  }
}

async function loadForUrl(url: string) {
  const token = ++requestToken;
  if (!isJobPageUrl(url)) {
    renderIdle();
    return;
  }
  renderLoading();
  try {
    const data = await getPanelData(url);
    if (token !== requestToken) return; // a newer tab switch has already superseded this
    if (!data.tracked) {
      renderNotTracked();
      return;
    }
    renderTracked(data, url);
  } catch (err) {
    if (token !== requestToken) return;
    if (err instanceof NotLoggedInError) {
      renderError(err.message, "login");
    } else if (err instanceof BackendUnreachableError || err instanceof ApiError) {
      renderError(err.message);
    } else {
      renderError(err instanceof Error ? err.message : String(err));
    }
  }
}

/** Re-reads the active tab from scratch, rather than reusing whatever URL
 * the panel last rendered — used on first open, by the retry button, and by
 * the wrong-tab guard, none of which can trust the rendered URL. */
async function refresh() {
  const url = await getActiveTabUrl();
  if (url) {
    await loadForUrl(url);
  } else {
    renderError("Could not read the current tab.");
  }
}

chrome.runtime.onMessage.addListener((message: { type?: string; url?: string }) => {
  // Reloads even when the URL is unchanged. Coming back to a tab is the
  // main way stored data goes stale: you follow "Calculate in CareerPilot",
  // score the job in the web app, return here — and without a re-fetch the
  // panel would still be insisting the job was never scored.
  if (message?.type === "TAB_CHANGED" && message.url) {
    void loadForUrl(message.url);
  }
});

void refresh();
