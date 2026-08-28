import { API_BASE_URL, sessionCookieUrls } from "./config";

// Same auth pattern as the original popup.js: the extension has no login UI
// of its own — it rides on whatever session the user already has from
// logging in at the CareerPilot web app in a regular tab. It CANNOT get
// there via fetch(..., {credentials:"include"}) the way the web app does:
// a fetch from chrome-extension://<id> to the API origin is a
// cross-site request from the browser's point of view, and the session
// cookie is SameSite=Lax — Lax cookies only ride along on top-level
// navigations, never a subresource fetch from a different site, so the
// browser would silently omit it here. Instead, the privileged
// chrome.cookies API (not subject to that restriction) reads the cookie's
// value directly, forwarded as X-CareerPilot-Session — accepted only by
// routes under /api/extension/.
// Must match backend/core/config.py's session_cookie_name / session_header_name.
const SESSION_COOKIE_NAME = "careerpilot_session";
const SESSION_HEADER_NAME = "X-CareerPilot-Session";

export class NotLoggedInError extends Error {
  constructor() {
    super("Log in to CareerPilot in your browser first, then try again.");
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** The backend isn't reachable at all. Distinct from ApiError (which means
 * the server answered and said no) because the remedy is completely
 * different — start CareerPilot, rather than fix something in the app. */
export class BackendUnreachableError extends Error {
  constructor() {
    super("Can't reach CareerPilot. Make sure the app is running, then try again.");
  }
}

async function sessionHeaders(): Promise<Record<string, string>> {
  for (const url of sessionCookieUrls()) {
    const sessionCookie = await chrome.cookies.get({ url, name: SESSION_COOKIE_NAME });
    if (sessionCookie?.value) {
      return { [SESSION_HEADER_NAME]: sessionCookie.value };
    }
  }
  throw new NotLoggedInError();
}

function detailMessage(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  return `Request failed (${status})`;
}

async function parseBody(response: Response): Promise<unknown> {
  if (response.status === 204) return {};
  return response.json().catch(() => ({}));
}

async function extensionRequest<T>(method: string, path: string, options?: { params?: Record<string, string>; body?: unknown }): Promise<T> {
  const headers: Record<string, string> = await sessionHeaders();
  if (options?.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  const query = options?.params ? `?${new URLSearchParams(options.params).toString()}` : "";
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}${query}`, {
      method,
      headers,
      body: options?.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    throw new BackendUnreachableError();
  }
  if (response.status === 401) throw new NotLoggedInError();
  const body = await parseBody(response);
  if (!response.ok) {
    throw new ApiError(response.status, detailMessage(body, response.status));
  }
  return body as T;
}

async function extensionGet<T>(path: string, params: Record<string, string>): Promise<T> {
  return extensionRequest<T>("GET", path, { params });
}

export type JobStatus = "discovered" | "verified" | "flagged" | "stale";

export type Job = {
  id?: string | null;
  title: string;
  company: string;
  location?: string | null;
  salary?: string | null;
  url: string;
  source: string;
  status: JobStatus;
  date_scraped?: string | null;
  saved?: boolean;
};

export type MatchScore = {
  overall_score: number;
  matched_skills: string[];
  partial_matches: string[];
  missing_skills: string[];
  recommendation: "apply" | "consider" | "skip";
  rationale: string;
  score_kind?: "full" | "preliminary" | "verified" | null;
  eligibility_status?: "likely_eligible" | "eligibility_uncertain" | "likely_ineligible" | null;
  qualification_score?: number | null;
  preference_score?: number | null;
  confidence_score?: number | null;
  confidence_level?: "high" | "medium" | "low" | null;
  match_reasons?: string[];
  watchouts?: string[];
  gap_reasons?: string[];
};

export type MaterialsStatus = "missing" | "current" | "stale_pending" | "stale_reviewed" | null;

export type Platform = "greenhouse" | "lever" | "unsupported";

export type PanelData = {
  tracked: boolean;
  job: Job | null;
  score: MatchScore | null;
  materials_status: MaterialsStatus;
  platform: Platform;
  apply_ready: boolean;
  apply_blocked_reason: string | null;
  /** The approved package was kept through an explicit grounding override,
   * so its claims were never verified against the resume. */
  materials_unverified: boolean;
  review_required?: boolean;
  saved?: boolean;
  must_have?: string[];
  approval_status?: string | null;
};

export function getPanelData(url: string): Promise<PanelData> {
  return extensionGet<PanelData>("/api/extension/panel-data", { url });
}

export type AutofillFields = Record<string, string | boolean | null | undefined>;

export type AutofillResponse = {
  job_id: string;
  platform: "greenhouse" | "lever" | "unsupported";
  fields: AutofillFields;
};

export function getAutofillData(url: string): Promise<AutofillResponse> {
  return extensionGet<AutofillResponse>("/api/extension/autofill", { url });
}

export function ingestJobUrl(url: string): Promise<Job> {
  return extensionRequest<Job>("POST", "/api/extension/ingest-url", { body: { url } });
}

export function saveTrackedJob(jobId: string): Promise<Job> {
  return extensionRequest<Job>("POST", `/api/extension/jobs/${encodeURIComponent(jobId)}/save`);
}

export function unsaveTrackedJob(jobId: string): Promise<void> {
  return extensionRequest<void>("DELETE", `/api/extension/jobs/${encodeURIComponent(jobId)}/save`);
}

export function requestVerifiedFit(jobId: string): Promise<MatchScore> {
  return extensionRequest<MatchScore>("POST", `/api/extension/jobs/${encodeURIComponent(jobId)}/verified-fit`);
}

export type ResumeExportFormat = "pdf" | "docx";

export type ExtensionResumeVersion = {
  id: string;
  job_id: string;
  job_title: string;
  company: string;
  version_number: number;
  created_at: string;
  bullet_count: number;
  provenance_status: "approved_snapshot";
  matches_current_profile: boolean;
  formats: ResumeExportFormat[];
};

export type ExtensionResumeVersionList = {
  versions: ExtensionResumeVersion[];
  current_job_id: string | null;
};

export function listResumeVersions(jobId?: string | null): Promise<ExtensionResumeVersionList> {
  return extensionGet<ExtensionResumeVersionList>(
    "/api/extension/resume-versions",
    jobId ? { job_id: jobId } : {},
  );
}

export type DownloadedResumeFile = {
  bytes: Uint8Array;
  mimeType: string;
  filename: string;
};

function contentDispositionFilename(header: string | null): string | null {
  if (!header) return null;
  const match = /filename="([^"]+)"/i.exec(header);
  return match?.[1] ?? null;
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

const PDF_MIME = "application/pdf";
const DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

export async function downloadResumeVersionFile(
  versionId: string,
  format: ResumeExportFormat,
): Promise<DownloadedResumeFile & { bytesBase64: string }> {
  if (format !== "pdf" && format !== "docx") {
    throw new ApiError(422, "Unsupported export format.");
  }
  const headers = await sessionHeaders();
  const path = `/api/extension/resume-versions/${encodeURIComponent(versionId)}/file?format=${encodeURIComponent(format)}`;
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { headers });
  } catch {
    throw new BackendUnreachableError();
  }
  if (response.status === 401) throw new NotLoggedInError();
  if (!response.ok) {
    const body = await parseBody(response);
    throw new ApiError(response.status, detailMessage(body, response.status));
  }
  const buffer = await response.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  const mimeType = (response.headers.get("content-type") || "").split(";")[0].trim().toLowerCase();
  const expected = format === "pdf" ? PDF_MIME : DOCX_MIME;
  if (mimeType !== expected) {
    throw new ApiError(415, "Unsupported document type.");
  }
  const filename = contentDispositionFilename(response.headers.get("content-disposition")) || `resume-v1.${format}`;
  return { bytes, mimeType, filename, bytesBase64: bytesToBase64(bytes) };
}

/** Only an http(s) page can ever be a job posting. Everything else the
 * browser can sit on — chrome:// internals, the New Tab page, about:blank,
 * file://, another extension's pages — is skipped outright, so those URLs
 * are never sent to the backend and the panel shows an idle state instead
 * of "not tracked", which would wrongly imply CareerPilot could track it. */
export function isJobPageUrl(url: string | null | undefined): url is string {
  if (!url) return false;
  try {
    const { protocol } = new URL(url);
    return protocol === "http:" || protocol === "https:";
  } catch {
    return false;
  }
}

/** The match pattern covering just this page's own origin, for a scoped
 * optional-permission request. Returns null for anything unparseable. */
export function originPattern(url: string): string | null {
  try {
    return `${new URL(url).origin}/*`;
  } catch {
    return null;
  }
}

export async function getActiveTabUrl(): Promise<string | null> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab?.url ?? null;
}
