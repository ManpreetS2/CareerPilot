import { API_BASE_URL } from "./config";
import type {
  ApplicationPackage,
  ApprovalDecision,
  ApprovalResponse,
  HealthResponse,
  InterviewPrep,
  Job,
  JobIntelligence,
  JobVerificationResponse,
  MatchScore,
  ParseResumeResponse,
  ScoutJobsResponse,
  TargetPreferences,
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
    response = await fetch(`${API_BASE_URL}${path}`, init);
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
  health: () => request<HealthResponse>("/health"),

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

  getJobs: () => request<Job[]>("/api/jobs"),

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

  getJob: (jobId: string) => request<Job>(`/api/jobs/${jobId}`),

  verifyJobs: (statusFilter: string | null = "discovered") =>
    request<JobVerificationResponse>(
      `/api/jobs/verify?status_filter=${encodeURIComponent(statusFilter ?? "none")}`,
      { method: "POST" },
    ),

  verifyJob: (jobId: string) =>
    request<Job>(`/api/jobs/${jobId}/verify`, { method: "POST" }),

  getJobIntelligence: (jobId: string) =>
    request<JobIntelligence>(`/api/jobs/${jobId}/intelligence`),

  extractJobIntelligence: (jobId: string) =>
    request<JobIntelligence>(`/api/jobs/${jobId}/intelligence`, {
      method: "POST",
    }),

  scoreJob: (jobId: string) =>
    request<MatchScore>(`/api/jobs/${jobId}/score`, {
      method: "POST",
    }),

  generateMaterials: (jobId: string) =>
    request<ApplicationPackage>(`/api/jobs/${jobId}/generate-materials`, {
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
};
