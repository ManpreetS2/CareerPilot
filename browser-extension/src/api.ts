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

async function sessionHeaders(): Promise<Record<string, string>> {
  const sessionCookie = await chrome.cookies.get({ url: BACKEND_URL, name: SESSION_COOKIE_NAME });
  if (!sessionCookie) throw new NotLoggedInError();
  return { [SESSION_HEADER_NAME]: sessionCookie.value };
}

async function extensionGet<T>(path: string, params: Record<string, string>): Promise<T> {
  const headers = await sessionHeaders();
  const query = new URLSearchParams(params).toString();
  const response = await fetch(`${BACKEND_URL}${path}?${query}`, { headers });
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
};

export type MaterialsStatus = "missing" | "current" | "stale_pending" | "stale_reviewed" | null;

export type PanelData = {
  tracked: boolean;
  job: Job | null;
  score: MatchScore | null;
  materials_status: MaterialsStatus;
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

export async function getActiveTabUrl(): Promise<string | null> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab?.url ?? null;
}
