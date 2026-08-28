import {
  ApiError,
  BackendUnreachableError,
  downloadResumeVersionFile,
  getActiveTabUrl,
  getAutofillData,
  getPanelData,
  ingestJobUrl,
  isJobPageUrl,
  listResumeVersions,
  NotLoggedInError,
  originPattern,
  requestVerifiedFit,
  saveTrackedJob,
  unsaveTrackedJob,
  type ExtensionResumeVersion,
  type PanelData,
  type ResumeExportFormat,
} from "./api";
import { attachDocumentInPage, verifyResumeAttachmentInPage } from "./attachFile";
import { WEB_APP_URL } from "./config";
import { COVER_LETTER_FILE_SUPPORT } from "./cover-letter-file";
import { classifyAutofillFields, type FieldStatusRow } from "./field-status";
import { fillFormInPage } from "./fillForm";
import { recognizeJobPage } from "./job-recognition";
import { eligibilityLabel, materialsActionLabel } from "./panel-states";
import { escapeHtml, materialsBadge, matchBadge, scoutedTimeAgo, sourceBadge, statusBadge } from "./render";

const app = document.getElementById("app")!;
// Guards against a fast tab switch firing a second load while the first
// one's still awaiting the network — the response for the stale URL is
// simply dropped instead of racing with the newer one to paint the panel.
let requestToken = 0;
let renderedUrl: string | null = null;
let currentData: PanelData | null = null;
let previewRows: FieldStatusRow[] | null = null;
let verifyStageTimer: number | null = null;
let resumeVersions: ExtensionResumeVersion[] = [];
let selectedVersionId: string | null = null;
let selectedFormat: ResumeExportFormat = "pdf";
let attachStatus: "not_attached" | "attaching" | "attached" | "manual" | "failed" = "not_attached";
let attachDetail = "";
let versionsError = "";

const VERIFY_STAGES = [
  "Reading full posting",
  "Checking requirements",
  "Checking eligibility",
  "Calculating match",
  "Almost ready",
];

function resetDocumentState() {
  resumeVersions = [];
  selectedVersionId = null;
  selectedFormat = "pdf";
  attachStatus = "not_attached";
  attachDetail = "";
  versionsError = "";
}

function defaultVersionId(versions: ExtensionResumeVersion[], jobId: string | null | undefined): string | null {
  const forJob = versions.filter((version) => version.job_id === jobId);
  if (forJob.length === 1) return forJob[0].id;
  return null;
}

function attachStatusLabel(): string {
  if (attachStatus === "attaching") return "Attaching…";
  if (attachStatus === "attached") return "Attached ✓";
  if (attachStatus === "manual") return "Needs manual upload";
  if (attachStatus === "failed") return "Failed — Retry";
  return "Not attached";
}

function formatVersionOption(version: ExtensionResumeVersion): string {
  const when = version.created_at ? version.created_at.slice(0, 10) : "";
  const job = version.job_title ? `${version.job_title} · ${version.company}` : "No linked job";
  return `v${version.version_number} · ${job}${when ? ` · ${when}` : ""}`;
}

function documentsCard(): string {
  const options = resumeVersions
    .map((version) => {
      const selected = version.id === selectedVersionId ? " selected" : "";
      return `<option value="${escapeHtml(version.id)}"${selected}>${escapeHtml(formatVersionOption(version))}</option>`;
    })
    .join("");
  const chosen = resumeVersions.find((version) => version.id === selectedVersionId);
  const provenance = chosen
    ? `${chosen.provenance_status.replaceAll("_", " ")}${chosen.matches_current_profile ? " · matches current profile" : ""}`
    : "";
  const cover = COVER_LETTER_FILE_SUPPORT.available
    ? ""
    : `<p class="mt-2 text-xs text-ink-500">Cover letter file: not available. Approved cover letter text can still be filled.</p>`;
  return `
    <div class="mt-3" id="documents-card">
      <p class="text-xs font-semibold uppercase tracking-wide text-ink-500">Documents</p>
      <label class="mt-2 block text-xs font-semibold text-ink-500" for="resume-version-select">Resume</label>
      <select id="resume-version-select" class="btn-secondary mt-1 w-full text-left">
        <option value="">Select a resume version</option>
        ${options}
      </select>
      ${provenance ? `<p class="mt-1 text-xs text-ink-500">${escapeHtml(provenance)}</p>` : ""}
      <p class="mt-2 text-xs font-semibold text-ink-500">Format</p>
      <div class="mt-1 flex gap-3 text-xs">
        <label><input type="radio" name="resume-format" value="pdf"${selectedFormat === "pdf" ? " checked" : ""} /> PDF</label>
        <label><input type="radio" name="resume-format" value="docx"${selectedFormat === "docx" ? " checked" : ""} /> DOCX</label>
      </div>
      <p class="mt-2 text-xs" data-attach-status="${attachStatus}">Status: ${escapeHtml(attachStatusLabel())}</p>
      ${attachDetail ? `<p class="mt-1 text-xs text-ink-500">${escapeHtml(attachDetail)}</p>` : ""}
      ${versionsError ? `<p class="mt-1 text-xs text-danger-600">${escapeHtml(versionsError)}</p>` : ""}
      ${cover}
    </div>`;
}

function stopVerifyStages() {
  if (verifyStageTimer != null) {
    window.clearInterval(verifyStageTimer);
    verifyStageTimer = null;
  }
}

function jobAnalysisUrl(jobId: string): string {
  return `${WEB_APP_URL}/jobs/${encodeURIComponent(jobId)}`;
}

function jobPrepareUrl(jobId: string): string {
  return `${WEB_APP_URL}/jobs/${encodeURIComponent(jobId)}/prepare`;
}

function header(opts: { signedIn?: boolean; company?: string; title?: string; extra?: string }): string {
  const auth = opts.signedIn === false ? "Signed out" : "Signed in";
  const role = opts.title
    ? `<p class="mt-2 truncate-2 font-semibold leading-snug">${escapeHtml(opts.title)}</p>
       <p class="truncate-2 text-ink-500">${escapeHtml(opts.company ?? "")}</p>`
    : "";
  return `
    <header class="mb-3">
      <p class="brand-mark text-[11px] font-semibold uppercase tracking-[0.18em] text-ink-500">CareerPilot</p>
      <p class="mt-1 text-xs text-ink-500">${auth}${opts.extra ? ` · ${escapeHtml(opts.extra)}` : ""}</p>
      ${role}
    </header>`;
}

function renderLoading() {
  app.innerHTML = `${header({ extra: "Checking this page" })}<p class="text-ink-500">Checking this page…</p>`;
}

/** Shown for pages that could never be a job posting (chrome:// internals,
 * the New Tab page, file://). Deliberately not the "not tracked yet" state,
 * which would imply CareerPilot could track this page if you asked it to. */
function renderIdle() {
  currentData = null;
  renderedUrl = null;
  app.innerHTML = `
    ${header({ extra: "No job page" })}
    <div class="card p-4">
      <p class="font-semibold">No job page open</p>
      <p class="mt-1 text-ink-500">Open a job posting in this tab and the panel will check it automatically.</p>
    </div>`;
}

function renderError(message: string, kind: "login" | "retry" = "retry") {
  currentData = null;
  app.innerHTML = `
    ${header({ signedIn: kind !== "login", extra: kind === "login" ? "Signed out" : "Can't reach CareerPilot" })}
    <div class="card p-4">
      <p class="text-danger-600 dark:text-rose-300">${escapeHtml(message)}</p>
      ${
        kind === "login"
          ? `<a class="btn-secondary mt-3" href="${WEB_APP_URL}/login" target="_blank" rel="noreferrer">Open CareerPilot to log in</a>`
          : `<button id="retry-btn" type="button" class="btn-secondary mt-3">Try again</button>`
      }
    </div>`;
  document.getElementById("retry-btn")?.addEventListener("click", () => void refresh());
}

function renderUnsupported(url: string) {
  currentData = { tracked: false, job: null, score: null, materials_status: null, platform: "unsupported", apply_ready: false, apply_blocked_reason: null, materials_unverified: false };
  renderedUrl = url;
  app.innerHTML = `
    ${header({ extra: "Unsupported site" })}
    <div class="card p-4">
      <p class="font-semibold">This site isn't supported</p>
      <p class="mt-1 text-ink-500">CareerPilot's side panel recognizes Greenhouse and Lever job pages. This tab is not one of those postings.</p>
    </div>`;
}

function renderSupportedUntracked(url: string, platform: "greenhouse" | "lever") {
  const label = platform === "greenhouse" ? "Greenhouse" : "Lever";
  currentData = { tracked: false, job: null, score: null, materials_status: null, platform, apply_ready: false, apply_blocked_reason: null, materials_unverified: false };
  renderedUrl = url;
  app.innerHTML = `
    ${header({ extra: `${label} job recognized` })}
    <div class="card p-4">
      <p class="font-semibold">Supported ${escapeHtml(label)} job recognized</p>
      <p class="mt-1 text-ink-500">This posting is not in CareerPilot yet. Add it once — CareerPilot will reuse the canonical job if it already exists.</p>
      <button id="ingest-btn" type="button" class="btn-primary mt-3">Add this job</button>
      <p id="ingest-status" class="mt-2 text-ink-500"></p>
    </div>`;
  document.getElementById("ingest-btn")?.addEventListener("click", () => void runIngest(url));
}

function evidenceList(label: string, skills: string[]): string {
  if (skills.length === 0) return "";
  return `<div class="mt-2"><p class="text-xs font-semibold uppercase tracking-wide text-ink-500">${label}</p>
    <div class="mt-1 flex flex-wrap gap-1.5">
      ${skills.map((s) => `<span class="rounded-lg bg-ink-100 px-2 py-0.5 text-xs text-ink-700 dark:bg-ink-800 dark:text-ink-100">${escapeHtml(s)}</span>`).join("")}
    </div></div>`;
}

function bulletList(items: string[]): string {
  return `<ul class="mt-1 list-disc space-y-1 pl-4 text-ink-700 dark:text-ink-200">${items
    .map((item) => `<li class="truncate-2">${escapeHtml(item)}</li>`)
    .join("")}</ul>`;
}

function fieldPreviewList(rows: FieldStatusRow[]): string {
  return `<ul class="mt-2 space-y-1">
    ${rows
      .map(
        (row) =>
          `<li class="flex items-start justify-between gap-2"><span class="truncate-2">${escapeHtml(row.label)}</span><span class="shrink-0 text-xs font-semibold">${escapeHtml(row.status)}</span></li>`,
      )
      .join("")}
  </ul>
  <p class="mt-2 text-xs text-ink-500">CareerPilot never presses Submit. Review the form on the page, then submit it yourself.</p>`;
}

function assistedApplyCard(data: PanelData, job: { id?: string | null }): string {
  const heading = `<p class="text-xs font-semibold uppercase tracking-wide text-ink-500">Assisted apply</p>`;

  if (data.platform === "unsupported") {
    return `
    <div class="card mt-3 p-4">
      ${heading}
      <p class="mt-1 text-ink-500">Only Greenhouse and Lever application pages can be filled. Open this job's real application page to use it.</p>
    </div>`;
  }

  if (!data.apply_ready) {
    return `
    <div class="card mt-3 p-4">
      ${heading}
      <p class="mt-1 text-ink-500">${escapeHtml(data.apply_blocked_reason ?? "This application isn't ready to fill yet.")}</p>
      <a class="btn-secondary mt-2" href="${jobPrepareUrl(job.id ?? "")}" target="_blank" rel="noreferrer">Prepare it in CareerPilot</a>
    </div>`;
  }

  const unverifiedNotice = data.materials_unverified
    ? `<p class="mt-2 rounded-lg bg-amber-100 px-2.5 py-2 text-xs font-semibold text-warn-600 dark:bg-amber-950/40 dark:text-amber-200">These materials were kept without evidence checks. Read them before you submit — they may claim experience your resume doesn't show.</p>`
    : "";

  const preview = previewRows
    ? `<div class="mt-3" data-panel-state="autofill_preview">${fieldPreviewList(previewRows)}</div>`
    : "";

  return `
    <div class="card mt-3 p-4">
      ${heading}
      <p class="mt-1 text-ink-500">Fills what it can confidently map into the real form on this page. Never submits — you review and submit yourself.</p>
      ${unverifiedNotice}
      <div class="panel-actions">
        <button id="preview-btn" type="button" class="btn-secondary">Preview autofill</button>
        <button id="fill-btn" type="button" class="btn-primary">Fill safe fields</button>
      </div>
      ${documentsCard()}
      ${preview}
      <div id="fill-status" role="status" class="mt-2"></div>
    </div>`;
}

function prepareCard(data: PanelData, jobId: string): string {
  const verified = data.score?.score_kind === "verified";
  const ineligible = data.score?.eligibility_status === "likely_ineligible";
  const materials = materialsActionLabel(data.materials_status, data.approval_status);
  let body = `<p class="mt-1 text-ink-500">Materials: ${escapeHtml(materials)}</p>`;
  if (!verified) {
    body += `<p class="mt-2 text-ink-500">Verify this match before preparing an application.</p>`;
  } else if (ineligible) {
    body += `<p class="mt-2 rounded-lg bg-rose-100 px-2.5 py-2 text-xs font-semibold text-danger-600 dark:bg-rose-950/40 dark:text-rose-200">This posting looks like a poor target based on stated requirements. CareerPilot will not treat it as a strong apply.</p>`;
  } else {
    body += `<a class="btn-secondary mt-2" href="${jobPrepareUrl(jobId)}" target="_blank" rel="noreferrer">Prepare Application</a>`;
  }
  return `
    <div class="card mt-3 p-4">
      <p class="text-xs font-semibold uppercase tracking-wide text-ink-500">Prepare Application</p>
      ${body}
    </div>`;
}

function matchSection(data: PanelData, jobId: string): string {
  const score = data.score;
  const verified = score?.score_kind === "verified";
  const mustHave = (data.must_have ?? []).filter(Boolean).slice(0, 4);
  const why = (score?.match_reasons?.length ? score.match_reasons : score?.matched_skills ?? []).slice(0, 4);
  const watch = score?.watchouts?.[0] || score?.gap_reasons?.[0] || score?.missing_skills?.[0] || "";
  const verifiedDetails =
    verified && score
      ? `<dl class="mt-2 grid grid-cols-2 gap-x-2 gap-y-1 text-xs">
          ${score.qualification_score != null ? `<dt class="text-ink-500">Qualification</dt><dd>${Math.round(score.qualification_score)}</dd>` : ""}
          ${score.preference_score != null ? `<dt class="text-ink-500">Preference</dt><dd>${Math.round(score.preference_score)}</dd>` : ""}
          ${score.eligibility_status ? `<dt class="text-ink-500">Eligibility</dt><dd class="truncate-2">${escapeHtml(eligibilityLabel(score.eligibility_status))}</dd>` : ""}
          ${score.confidence_level ? `<dt class="text-ink-500">Confidence</dt><dd>${escapeHtml(score.confidence_level)}</dd>` : ""}
        </dl>`
      : score?.eligibility_status
        ? `<p class="mt-2 text-xs text-ink-500">Eligibility: ${escapeHtml(eligibilityLabel(score.eligibility_status))}</p>`
        : "";
  const verifyCta = !verified
    ? `<button id="verify-btn" type="button" class="btn-secondary mt-2">Verify Match</button><p id="verify-status" class="mt-2 text-ink-500"></p>`
    : "";
  return `
    <div class="card mt-3 p-4">
      <p class="text-xs font-semibold uppercase tracking-wide text-ink-500">Match state</p>
      <div class="mt-2">${matchBadge(score?.overall_score, score?.recommendation, score?.score_kind)}</div>
      ${
        score
          ? `${verifiedDetails}`
          : `<p class="mt-2 text-ink-500">Not scored yet.</p><a class="btn-secondary mt-2" href="${jobAnalysisUrl(jobId)}" target="_blank" rel="noreferrer">Calculate in CareerPilot</a>`
      }
      ${verifyCta}
    </div>
    ${
      score
        ? `<div class="card mt-3 p-4">
            <p class="text-xs font-semibold uppercase tracking-wide text-ink-500">Eligibility</p>
            <p class="mt-1 font-semibold">${escapeHtml(eligibilityLabel(score.eligibility_status))}</p>
          </div>`
        : ""
    }
    ${
      mustHave.length
        ? `<div class="card mt-3 p-4">
            <p class="text-xs font-semibold uppercase tracking-wide text-ink-500">Top requirements</p>
            ${bulletList(mustHave)}
          </div>`
        : ""
    }
    ${
      why.length
        ? `<div class="card mt-3 p-4">
            <p class="text-xs font-semibold uppercase tracking-wide text-ink-500">Why you match</p>
            ${bulletList(why)}
          </div>`
        : evidenceList("Matched", score?.matched_skills ?? [])
    }
    ${
      watch
        ? `<div class="card mt-3 p-4">
            <p class="text-xs font-semibold uppercase tracking-wide text-ink-500">Gaps / watch out</p>
            <p class="mt-1 truncate-2">${escapeHtml(watch)}</p>
          </div>`
        : evidenceList("Missing", score?.missing_skills ?? [])
    }`;
}

function renderTracked(data: PanelData, url: string) {
  const job = data.job!;
  const seenAgo = scoutedTimeAgo(job.date_scraped);
  const saved = Boolean(data.saved || job.saved);
  const jobId = job.id ?? "";
  const stale = job.status === "stale";

  currentData = data;
  renderedUrl = url;

  app.innerHTML = `
    ${header({ company: job.company, title: job.title, extra: data.platform === "unsupported" ? "Tracked job" : "Job recognized" })}
    <div class="card p-4">
      <p class="truncate-2 text-xs text-ink-500">${escapeHtml(job.company)}</p>
      <h1 class="truncate-2 font-semibold leading-snug">${escapeHtml(job.title)}</h1>
      <div class="mt-2 flex flex-wrap items-center gap-1.5">
        ${statusBadge(job.status)}
        ${sourceBadge(job.source)}
        ${seenAgo ? `<span class="text-xs text-ink-500">${escapeHtml(seenAgo)}</span>` : ""}
      </div>
      ${stale ? `<p class="mt-2 text-xs font-semibold text-warn-600">This posting looks stale or closed. Confirm it is still open before applying.</p>` : ""}
    </div>

    ${matchSection(data, jobId)}

    <div class="card mt-3 p-4">
      <p class="text-xs font-semibold uppercase tracking-wide text-ink-500">Application materials</p>
      <div class="mt-2">${materialsBadge(data.materials_status)}</div>
      <p class="mt-1 text-xs text-ink-500">${escapeHtml(materialsActionLabel(data.materials_status, data.approval_status))}</p>
      ${
        data.materials_status === "current"
          ? ""
          : `<a class="btn-secondary mt-2" href="${jobPrepareUrl(jobId)}" target="_blank" rel="noreferrer">Open in CareerPilot</a>`
      }
    </div>

    ${prepareCard(data, jobId)}

    <div class="card mt-3 p-4">
      <p class="text-xs font-semibold uppercase tracking-wide text-ink-500">Actions</p>
      <div class="panel-actions">
        <button id="save-btn" type="button" class="btn-secondary">${saved ? "Saved" : "Save"}</button>
        ${saved ? `<button id="unsave-btn" type="button" class="btn-ghost">Unsave</button>` : ""}
        <a class="btn-secondary" href="${jobAnalysisUrl(jobId)}" target="_blank" rel="noreferrer">Open full CareerPilot analysis</a>
      </div>
    </div>

    ${assistedApplyCard(data, job)}`;

  document.getElementById("fill-btn")?.addEventListener("click", () => void runFill(url));
  document.getElementById("preview-btn")?.addEventListener("click", () => void runPreview(url));
  document.getElementById("save-btn")?.addEventListener("click", () => {
    if (saved) return;
    void runSave(jobId, url, false);
  });
  document.getElementById("unsave-btn")?.addEventListener("click", () => void runSave(jobId, url, true));
  document.getElementById("verify-btn")?.addEventListener("click", () => void runVerify(jobId, url));
  bindDocumentControls(jobId);
}

function refreshDocumentsCard() {
  const jobId = currentData?.job?.id;
  const slot = document.getElementById("documents-card");
  if (!jobId || !slot) return;
  slot.outerHTML = documentsCard();
  bindDocumentControls(jobId);
}

function bindDocumentControls(jobId: string) {
  document.getElementById("resume-version-select")?.addEventListener("change", (event) => {
    selectedVersionId = (event.target as HTMLSelectElement).value || null;
    attachStatus = "not_attached";
    attachDetail = "";
    const slot = document.getElementById("documents-card");
    if (slot) {
      slot.outerHTML = documentsCard();
      bindDocumentControls(jobId);
    }
  });
  document.querySelectorAll<HTMLInputElement>("input[name='resume-format']").forEach((input) => {
    input.addEventListener("change", () => {
      if (input.checked && (input.value === "pdf" || input.value === "docx")) {
        selectedFormat = input.value;
        if (attachStatus === "attached") {
          attachStatus = "not_attached";
          attachDetail = "";
        }
      }
    });
  });
}

async function loadResumeVersions(jobId: string, token: number) {
  try {
    const started = performance.now();
    const listed = await listResumeVersions(jobId);
    console.debug(
      `[CareerPilot] resume-version list ${Math.round(performance.now() - started)}ms count=${listed.versions.length}`,
    );
    if (token !== requestToken) return;
    resumeVersions = listed.versions;
    if (selectedVersionId && !resumeVersions.some((version) => version.id === selectedVersionId)) {
      selectedVersionId = null;
    }
    if (!selectedVersionId) selectedVersionId = defaultVersionId(resumeVersions, jobId);
    versionsError = "";
    const slot = document.getElementById("documents-card");
    if (slot) {
      slot.outerHTML = documentsCard();
      bindDocumentControls(jobId);
    }
  } catch (err) {
    if (token !== requestToken) return;
    versionsError = err instanceof NotLoggedInError || err instanceof Error ? err.message : "Could not load resume versions.";
    const slot = document.getElementById("documents-card");
    if (slot) {
      slot.outerHTML = documentsCard();
      bindDocumentControls(jobId);
    }
  }
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

async function runPreview(url: string) {
  const statusEl = document.getElementById("fill-status");
  if (statusEl) statusEl.textContent = "Loading field preview…";
  try {
    const autofill = await getAutofillData(url);
    if (renderedUrl !== url) return;
    previewRows = classifyAutofillFields(autofill.fields);
    if (currentData) renderTracked(currentData, url);
  } catch (err) {
    if (err instanceof NotLoggedInError) {
      renderError(err.message, "login");
      return;
    }
    if (statusEl) statusEl.textContent = err instanceof Error ? err.message : String(err);
  }
}

async function runFill(url: string) {
  const button = document.getElementById("fill-btn") as HTMLButtonElement | null;
  const statusEl = document.getElementById("fill-status");
  if (!button || !statusEl) return;
  button.disabled = true;
  statusEl.textContent = "Checking page access…";

  try {
    if (!(await ensurePageAccess(url))) {
      statusEl.textContent = "CareerPilot needs permission to fill this site's form. Click Fill this page again to allow it.";
      return;
    }

    statusEl.textContent = "Looking up this application…";
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) throw new Error("Could not read the current tab.");
    if (tab.url !== url) {
      statusEl.textContent = "This tab changed — rechecking it now.";
      void refresh();
      return;
    }

    let attachedName: string | null = null;
    if (selectedVersionId) {
      attachStatus = "attaching";
      attachDetail = "";
      refreshDocumentsCard();
      statusEl.textContent = "Downloading resume…";
      const downloadStarted = performance.now();
      const file = await downloadResumeVersionFile(selectedVersionId, selectedFormat);
      console.debug(
        `[CareerPilot] resume ${selectedFormat} fetch ${Math.round(performance.now() - downloadStarted)}ms version_id=${selectedVersionId}`,
      );
      statusEl.textContent = "Attaching resume…";
      const attachStarted = performance.now();
      const attached = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: attachDocumentInPage,
        args: [
          {
            kind: "resume" as const,
            filename: file.filename,
            mimeType: file.mimeType,
            bytesBase64: file.bytesBase64,
          },
        ],
      });
      console.debug(`[CareerPilot] resume attach ${Math.round(performance.now() - attachStarted)}ms`);
      const attachResult = attached?.[0]?.result;
      if (!attachResult || attachResult.status !== "attached") {
        attachStatus = attachResult?.status === "manual" || attachResult?.status === "ambiguous" ? "manual" : "failed";
        attachDetail = attachResult?.reason || "Attach manually.";
        refreshDocumentsCard();
        statusEl.textContent = attachDetail;
        return;
      }
      attachedName = attachResult.verifiedName;
      attachStatus = "attached";
      attachDetail = "";
      refreshDocumentsCard();
    }

    const autofill = await getAutofillData(url);
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
    if (attachedName) {
      const verifyStarted = performance.now();
      const stillThere = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: verifyResumeAttachmentInPage,
        args: [attachedName],
      });
      console.debug(`[CareerPilot] resume verify ${Math.round(performance.now() - verifyStarted)}ms`);
      if (!stillThere?.[0]?.result?.attached) {
        attachStatus = "failed";
        attachDetail = "Resume needs re-attachment.";
        refreshDocumentsCard();
        statusEl.textContent = "Resume needs re-attachment. Safe fields were not marked ready.";
        return;
      }
    }
    const parts: string[] = [];
    if (attachedName) parts.push(`<p class="mt-2 text-xs font-semibold">Resume attached</p>`);
    if (result.filled.length > 0) {
      parts.push(
        `<p class="mt-2 text-xs font-semibold uppercase tracking-wide text-ink-500">Safe fields filled</p><ul class="mt-1 list-disc pl-4">${result.filled
          .map((f) => `<li>${escapeHtml(f.name)}</li>`)
          .join("")}</ul>`,
      );
    }
    if (result.flagged.length > 0) {
      parts.push(
        `<p class="mt-2 text-xs font-semibold uppercase tracking-wide text-warn-600">Manual review required</p><ul class="mt-1 list-disc pl-4">${result.flagged
          .map((f) => `<li>${escapeHtml(f.name)} — ${escapeHtml(f.reason)}</li>`)
          .join("")}</ul>`,
      );
    }
    parts.push(`<p class="mt-2 text-xs font-semibold">Ready for your review</p>`);
    parts.push(`<p class="mt-2 text-xs text-ink-500">Submit was not pressed. Review the page, then submit yourself.</p>`);
    statusEl.innerHTML = parts.join("") || "Nothing on this page matched.";
  } catch (err) {
    if (err instanceof NotLoggedInError) {
      renderError(err.message, "login");
      return;
    }
    if (attachStatus === "attaching") {
      attachStatus = "failed";
      attachDetail = err instanceof Error ? err.message : "Download failed.";
      refreshDocumentsCard();
    }
    statusEl.textContent = err instanceof Error ? err.message : String(err);
  } finally {
    button.disabled = false;
  }
}

async function runSave(jobId: string, url: string, currentlySaved: boolean) {
  const button = document.getElementById("save-btn") as HTMLButtonElement | null;
  if (button) button.disabled = true;
  try {
    if (currentlySaved) {
      await unsaveTrackedJob(jobId);
    } else {
      await saveTrackedJob(jobId);
    }
    if (renderedUrl !== url || !currentData?.job) return;
    currentData.saved = !currentlySaved;
    currentData.job.saved = !currentlySaved;
    renderTracked(currentData, url);
  } catch (err) {
    if (err instanceof NotLoggedInError) {
      renderError(err.message, "login");
      return;
    }
    if (button) button.disabled = false;
  }
}

async function runVerify(jobId: string, url: string) {
  const statusEl = document.getElementById("verify-status");
  const button = document.getElementById("verify-btn") as HTMLButtonElement | null;
  if (button) button.disabled = true;
  let stage = 0;
  if (statusEl) statusEl.textContent = VERIFY_STAGES[0];
  stopVerifyStages();
  verifyStageTimer = window.setInterval(() => {
    stage = Math.min(stage + 1, VERIFY_STAGES.length - 1);
    if (statusEl) statusEl.textContent = VERIFY_STAGES[stage];
  }, 400);
  try {
    await requestVerifiedFit(jobId);
    stopVerifyStages();
    if (renderedUrl !== url) return;
    const data = await getPanelData(url);
    if (renderedUrl !== url) return;
    previewRows = null;
    renderTracked(data, url);
  } catch (err) {
    stopVerifyStages();
    if (err instanceof NotLoggedInError) {
      renderError(err.message, "login");
      return;
    }
    if (statusEl) {
      statusEl.textContent =
        err instanceof Error ? `${err.message} Remaining a Potential Match.` : "Verification failed. Remaining a Potential Match.";
    }
    if (button) button.disabled = false;
  }
}

async function runIngest(url: string) {
  const button = document.getElementById("ingest-btn") as HTMLButtonElement | null;
  const statusEl = document.getElementById("ingest-status");
  if (button) button.disabled = true;
  if (statusEl) statusEl.textContent = "Adding this job…";
  try {
    await ingestJobUrl(url);
    if (renderedUrl !== url) return;
    await loadForUrl(url);
  } catch (err) {
    if (err instanceof NotLoggedInError) {
      renderError(err.message, "login");
      return;
    }
    if (statusEl) statusEl.textContent = err instanceof Error ? err.message : String(err);
    if (button) button.disabled = false;
  }
}

async function loadForUrl(url: string) {
  const token = ++requestToken;
  previewRows = null;
  stopVerifyStages();
  if (renderedUrl && renderedUrl !== url) resetDocumentState();
  if (!isJobPageUrl(url)) {
    resetDocumentState();
    renderIdle();
    return;
  }
  const recognition = recognizeJobPage(url);
  renderLoading();
  const started = performance.now();
  try {
    const data = await getPanelData(url);
    if (token !== requestToken) return;
    console.debug(`[CareerPilot] panel-data ${Math.round(performance.now() - started)}ms`);
    if (!data.tracked) {
      resetDocumentState();
      if (recognition.supported) {
        renderSupportedUntracked(url, recognition.platform === "unsupported" ? "greenhouse" : recognition.platform);
        return;
      }
      renderUnsupported(url);
      return;
    }
    renderTracked(data, url);
    if (data.apply_ready && data.job?.id) {
      void loadResumeVersions(data.job.id, token);
    }
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
  if (message?.type === "TAB_CHANGED" && message.url) {
    void loadForUrl(message.url);
  }
});

void refresh();
