import { API_BASE_URL } from "./config";
import type {
  ApplicationListItem,
  ApplicationPackage,
  ApplicationTrackerItem,
  ApprovalDecision,
  ApprovalResponse,
  DashboardSummary,
  FormFillResult,
  HealthResponse,
  InterviewAnswerFeedback,
  InterviewPrep,
  Job,
  JobIntelligence,
  JobRequirementProfile,
  JobVerificationResponse,
  MatchScore,
  ParseResumeResponse,
  CurrentProfile,
  ResumeVersion,
  ResumeVersionDetail,
  ResumeVersionSummary,
  ScoutJobsResponse,
  TargetPreferences,
  TrackerStatus,
  User,
} from "./types";

export class ApiClientError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      credentials: "include",
      signal: init?.signal,
    });
  } catch {
    throw new ApiClientError(
      0,
      `Cannot reach backend at ${API_BASE_URL}. Start it with: uvicorn backend.main:app --reload`,
    );
  }

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = (payload as { detail?: unknown }).detail ?? payload;
    const message =
      typeof detail === "string"
        ? detail
        : `Request failed (${response.status}) for ${path}`;
    throw new ApiClientError(response.status, message, detail);
  }
  return payload as T;
}

export const api = {
  health: (init?: RequestInit) => request<HealthResponse>("/health", init),

  signup: (email: string, password: string) =>
    request<User>("/api/auth/signup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }),

  login: (email: string, password: string) =>
    request<User>("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }),

  logout: () => request<void>("/api/auth/logout", { method: "POST" }),

  me: (init?: RequestInit) => request<User>("/api/auth/me", init),

  getProfile: (init?: RequestInit) => request<CurrentProfile>("/api/profile", init),

  parseResume: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<ParseResumeResponse>("/api/parse-resume", {
      method: "POST",
      body,
    });
  },

  savePreferences: (preferences: TargetPreferences) =>
    request<TargetPreferences>("/api/preferences", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(preferences),
    }),

  getJobs: (init?: RequestInit) => request<Job[]>("/api/jobs", init),

  scoutJobs: () =>
    request<ScoutJobsResponse>("/api/scout-jobs", {
      method: "POST",
    }),

  ingestJobUrl: (url: string) =>
    request<Job>("/api/jobs/ingest-url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    }),

  getJob: (jobId: string, init?: RequestInit) => request<Job>(`/api/jobs/${jobId}`, init),

  verifyJobs: (statusFilter: string | null = "discovered") =>
    request<JobVerificationResponse>(
      `/api/jobs/verify?status_filter=${encodeURIComponent(statusFilter ?? "none")}`,
      { method: "POST" },
    ),

  verifyJob: (jobId: string) =>
    request<Job>(`/api/jobs/${jobId}/verify`, { method: "POST" }),

  getJobIntelligence: (jobId: string, init?: RequestInit) =>
    request<JobIntelligence>(`/api/jobs/${jobId}/intelligence`, init),

  extractJobIntelligence: (jobId: string) =>
    request<JobIntelligence>(`/api/jobs/${jobId}/intelligence`, {
      method: "POST",
    }),

  getRequirementProfile: (jobId: string, init?: RequestInit) =>
    request<JobRequirementProfile>(`/api/jobs/${jobId}/requirements`, init),

  extractRequirementProfile: (jobId: string) =>
    request<JobRequirementProfile>(`/api/jobs/${jobId}/requirements`, {
      method: "POST",
    }),

  getStoredScore: (jobId: string, init?: RequestInit) =>
    request<MatchScore>(`/api/jobs/${jobId}/score`, init),

  getStoredScores: (init?: RequestInit) => request<MatchScore[]>("/api/jobs/scores", init),

  scoreJob: (jobId: string) =>
    request<MatchScore>(`/api/jobs/${jobId}/score`, {
      method: "POST",
    }),

  getStoredMaterials: (jobId: string, init?: RequestInit) =>
    request<ApplicationPackage>(`/api/jobs/${jobId}/materials`, init),

  // overrideGrounding is the owner's explicit, per-job decision to keep a
  // draft whose claims could not all be verified against their resume. It is
  // sent only when they ask for it and is never remembered between calls.
  generateMaterials: (jobId: string, overrideGrounding = false) =>
    request<ApplicationPackage>(`/api/jobs/${jobId}/generate-materials`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ override_grounding: overrideGrounding }),
    }),

  discardStaleMaterials: (jobId: string) =>
    request<{ status: string }>(`/api/jobs/${jobId}/discard-stale-materials`, {
      method: "POST",
    }),

  listResumeVersions: (jobId: string, init?: RequestInit) =>
    request<ResumeVersion[]>(`/api/jobs/${jobId}/resume-versions`, init),

  getResumeVersion: (jobId: string, versionId: string, init?: RequestInit) =>
    request<ResumeVersion>(`/api/jobs/${jobId}/resume-versions/${versionId}`, init),

  listAllResumeVersions: (init?: RequestInit) =>
    request<ResumeVersionSummary[]>("/api/resume-versions", init),

  getResumeVersionDetail: (versionId: string, init?: RequestInit) =>
    request<ResumeVersionDetail>(`/api/resume-versions/${versionId}`, init),

  createResumeVersion: (jobId: string) =>
    request<ResumeVersion>(`/api/jobs/${jobId}/resume-versions`, {
      method: "POST",
    }),

  approveApplication: (
    jobId: string,
    decision: ApprovalDecision,
    options?: { notes?: string; eligibilityConfirmed?: boolean; eligibilityNotes?: string },
  ) =>
    request<ApprovalResponse>(`/api/jobs/${jobId}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        decision,
        notes: options?.notes ?? null,
        eligibility_confirmed: options?.eligibilityConfirmed ?? false,
        eligibility_notes: options?.eligibilityNotes ?? null,
      }),
    }),

  prepareInterview: (jobId: string) =>
    request<InterviewPrep>(`/api/jobs/${jobId}/prepare-interview`, {
      method: "POST",
    }),

  getInterviewPrep: (jobId: string, init?: RequestInit) =>
    request<InterviewPrep>(`/api/jobs/${jobId}/interview-prep`, init),

  getInterviewAnswerFeedback: (jobId: string, question: string, answer: string) =>
    request<InterviewAnswerFeedback>(`/api/jobs/${jobId}/interview-prep/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, answer }),
    }),

  listApplications: () => request<ApplicationListItem[]>("/api/applications"),

  getTracking: (jobId: string) =>
    request<ApplicationTrackerItem>(`/api/applications/${jobId}/tracking`),

  updateTracking: (
    jobId: string,
    status: TrackerStatus,
    note?: string | null,
    reminderDate?: string | null,
  ) =>
    request<ApplicationTrackerItem>(`/api/applications/${jobId}/tracking`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status, note: note ?? null, reminder_date: reminderDate ?? null }),
    }),

  getDashboardSummary: (init?: RequestInit) =>
    request<DashboardSummary>("/api/dashboard/summary", init),

  fillApplication: (jobId: string) =>
    request<FormFillResult>(`/api/jobs/${jobId}/fill-application`, {
      method: "POST",
    }),
};
