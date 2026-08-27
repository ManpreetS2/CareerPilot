// Same auth pattern as the original popup.js: the extension has no login UI
// of its own — it rides on whatever session the user already has from
// logging in at the CareerPilot web app in a regular tab. It CANNOT get
// there via fetch(..., {credentials:"include"}) the way the web app does:
// a fetch from chrome-extension://<id> to http://localhost:8000 is a
// cross-site request from the browser's point of view, and the session
// cookie is SameSite=Lax — Lax cookies only ride along on top-level
// navigations, never a subresource fetch from a different site, so the
// browser would silently omit it here. Instead, the privileged
// chrome.cookies API (not subject to that restriction) reads the cookie's
// value directly, forwarded as X-CareerPilot-Session — accepted only by
// routes under /api/extension/.
const BACKEND_URL = "http://localhost:8000";
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
  const sessionCookie = await chrome.cookies.get({ url: BACKEND_URL, name: SESSION_COOKIE_NAME });
  if (!sessionCookie) throw new NotLoggedInError();
  return { [SESSION_HEADER_NAME]: sessionCookie.value };
}

async function extensionGet<T>(path: string, params: Record<string, string>): Promise<T> {
  const headers = await sessionHeaders();
  const query = new URLSearchParams(params).toString();
  let response: Response;
  try {
    response = await fetch(`${BACKEND_URL}${path}?${query}`, { headers });
  } catch {
    // fetch only rejects on a transport failure (server down, DNS, refused
    // connection) — an HTTP error status resolves normally and is handled
    // below. Surfacing the raw "Failed to fetch" here would tell the user
    // nothing actionable.
    throw new BackendUnreachableError();
  }
  if (response.status === 401) throw new NotLoggedInError();
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(response.status, body.detail || `Request failed (${response.status})`);
  }
  return body as T;
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
