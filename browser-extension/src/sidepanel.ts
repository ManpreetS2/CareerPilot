import { ApiError, getActiveTabUrl, getAutofillData, getPanelData, NotLoggedInError, type PanelData } from "./api";
import { fillFormInPage } from "./fillForm";
import { escapeHtml, materialsBadge, matchBadge, scoutedTimeAgo, sourceBadge, statusBadge } from "./render";

const WEB_APP_URL = "http://localhost:5173";

const app = document.getElementById("app")!;
let currentUrl: string | null = null;
// Guards against a fast tab switch firing a second load while the first
// one's still awaiting the network — the response for the stale URL is
// simply dropped instead of racing with the newer one to paint the panel.
let requestToken = 0;

function renderLoading() {
  app.innerHTML = `<p class="text-ink-500">Checking this page…</p>`;
}

function renderError(message: string, isLoginPrompt = false) {
  app.innerHTML = `
    <div class="card p-4">
      <p class="text-danger-600 dark:text-rose-300">${escapeHtml(message)}</p>
      ${
        isLoginPrompt
          ? `<a class="btn-secondary mt-3" href="${WEB_APP_URL}/login" target="_blank" rel="noreferrer">Open CareerPilot to log in</a>`
          : ""
      }
    </div>`;
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
      <div class="mt-2">${matchBadge(score?.overall_score, score?.recommendation)}</div>
      ${
        score
          ? `${evidenceList("Matched", score.matched_skills)}${evidenceList("Missing", score.missing_skills)}`
          : `<p class="mt-2 text-ink-500">Not scored yet.</p><a class="btn-secondary mt-2" href="${WEB_APP_URL}/jobs/${job.id}" target="_blank" rel="noreferrer">Calculate in CareerPilot</a>`
      }
    </div>

    <div class="card mt-3 p-4">
      <p class="text-xs font-semibold uppercase tracking-wide text-ink-500">Application materials</p>
      <div class="mt-2">${materialsBadge(data.materials_status)}</div>
      ${
        data.materials_status === "current"
          ? ""
          : `<a class="btn-secondary mt-2" href="${WEB_APP_URL}/applications/${job.id}" target="_blank" rel="noreferrer">Open in CareerPilot</a>`
      }
    </div>

    <div class="card mt-3 p-4">
      <p class="text-xs font-semibold uppercase tracking-wide text-ink-500">Assisted apply</p>
      <p class="mt-1 text-ink-500">Fills what it can confidently map into the real form on this page. Never submits — you review and submit yourself.</p>
      <button id="fill-btn" type="button" class="btn-primary mt-2">Fill this page</button>
      <div id="fill-status" class="mt-2"></div>
    </div>`;

  document.getElementById("fill-btn")?.addEventListener("click", () => void runFill(url));
}

async function runFill(url: string) {
  const button = document.getElementById("fill-btn") as HTMLButtonElement | null;
  const statusEl = document.getElementById("fill-status");
  if (!button || !statusEl) return;
  button.disabled = true;
  statusEl.textContent = "Looking up this application…";

  try {
    const autofill = await getAutofillData(url);
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) throw new Error("Could not read the current tab.");

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
      renderError(err.message, true);
      return;
    }
    statusEl.textContent = err instanceof Error ? err.message : String(err);
  } finally {
    button.disabled = false;
  }
}

async function loadForUrl(url: string) {
  currentUrl = url;
  const token = ++requestToken;
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
      renderError(err.message, true);
    } else if (err instanceof ApiError) {
      renderError(err.message);
    } else {
      renderError(err instanceof Error ? err.message : String(err));
    }
  }
}

chrome.runtime.onMessage.addListener((message: { type?: string; url?: string }) => {
  if (message?.type === "TAB_CHANGED" && message.url && message.url !== currentUrl) {
    void loadForUrl(message.url);
  }
});

void (async () => {
  const url = await getActiveTabUrl();
  if (url) {
    void loadForUrl(url);
  } else {
    renderError("Could not read the current tab.");
  }
})();
