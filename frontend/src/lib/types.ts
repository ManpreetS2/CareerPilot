/** Shared TypeScript types mirroring backend Pydantic schemas. */

export type User = {
  id: number;
  email: string;
  created_at: string;
};

export type Project = {
  name: string;
  description?: string | null;
  technologies: string[];
  url?: string | null;
};

export type Experience = {
  title: string;
  company: string;
  start_date?: string | null;
  end_date?: string | null;
  highlights: string[];
};

export type Education = {
  institution: string;
  degree?: string | null;
  field?: string | null;
  graduation_year?: string | null;
};

export type CandidateProfile = {
  id?: string | null;
  name: string;
  email?: string | null;
  phone?: string | null;
  skills: string[];
  projects: Project[];
  experience: Experience[];
  education: Education[];
  certifications: string[];
  strengths: string[];
  evidence_links: string[];
};

export type TargetPreferences = {
  target_roles: string[];
  preferred_locations: string[];
  remote_preference?: string | null;
  /** Minimum acceptable base salary in annual USD (not hourly). */
  salary_min?: number | null;
  work_authorization?: string | null;
  sponsorship_required?: boolean | null;
  constraints: string[];
  legal_name?: string | null;
  linkedin_url?: string | null;
  github_url?: string | null;
  portfolio_url?: string | null;
  earliest_start_date?: string | null;
  currently_enrolled_in_program?: string | null;
  expected_graduation?: string | null;
  degree_pursuing?: string | null;
  gender?: string | null;
  race_ethnicity?: string | null;
  veteran_status?: string | null;
  disability_status?: string | null;
};

export type CurrentProfile = {
  candidate: CandidateProfile | null;
  preferences: TargetPreferences | null;
};

export type JobStatus = "discovered" | "verified" | "flagged" | "stale";

export type Job = {
  id?: string | null;
  title: string;
  company: string;
  location?: string | null;
  salary?: string | null;
  url: string;
  description: string;
  source: string;
  date_posted?: string | null;
  date_scraped?: string | null;
  ats?: string | null;
  status: JobStatus;
  verification_notes?: string | null;
  verified_at?: string | null;
};

export type JobVerificationResponse = {
  jobs: Job[];
  verified: number;
  flagged: number;
  stale: number;
};

export type JobIntelligence = {
  job_id?: string | null;
  required_skills: string[];
  preferred_skills: string[];
  years_experience?: number | null;
  education_requirements: string[];
  tech_stack: string[];
  seniority?: string | null;
  responsibilities: string[];
  likely_interview_focus: string[];
};

export type MatchScore = {
  job_id: string;
  overall_score: number;
  skill_score?: number | null;
  experience_score?: number | null;
  education_score?: number | null;
  location_score?: number | null;
  preference_score?: number | null;
  matched_skills: string[];
  partial_matches: string[];
  missing_skills: string[];
  recommendation: "apply" | "consider" | "skip";
  rationale: string;
};

export type ApplicationPackage = {
  job_id: string;
  tailored_bullets: string[];
  cover_letter_draft?: string | null;
  recruiter_message?: string | null;
  source_traceability_notes: string[];
  approval_status: "draft" | "pending_review" | "approved" | "edit_requested" | "rejected";
  eligibility_confirmed: boolean;
  eligibility_notes?: string | null;
  decision_notes?: string | null;
  grounded?: boolean;
  /** Kept through an explicit per-job grounding override: real stored
   * materials whose claims were never verified against the resume. */
  grounding_override?: boolean;
  unsupported_claims?: string[];
};

export type ResumeVersion = {
  id: string;
  job_id: string;
  version_number: number;
  tailored_bullets: string[];
  source_traceability_notes: string[];
  created_at: string;
};

export type ResumeVersionSummary = {
  id: string;
  job_id: string;
  job_title: string;
  company: string;
  version_number: number;
  created_at: string;
  bullet_count: number;
  provenance_status: "approved_snapshot";
  matches_current_profile: boolean;
};

export type ResumeVersionProfile = {
  name?: string | null;
  email?: string | null;
  phone?: string | null;
  skills?: unknown[] | null;
  projects?: unknown[] | null;
  experience?: unknown[] | null;
  education?: unknown[] | null;
  certifications?: unknown[] | null;
  strengths?: unknown[] | null;
  evidence_links?: unknown[] | null;
  legal_name?: string | null;
  linkedin_url?: string | null;
  github_url?: string | null;
  portfolio_url?: string | null;
};

export type ResumeVersionDetail = ResumeVersionSummary & {
  tailored_bullets: string[];
  source_traceability_notes: string[];
  profile: ResumeVersionProfile;
};

export type ApprovalDecision = "approved" | "edit_requested" | "rejected";

export type FlaggedField = {
  field: string;
  reason: string;
};

export type FilledField = {
  field: string;
  value: string;
};

export type FormFillResult = {
  job_id: string;
  ats_platform: "greenhouse" | "lever" | "unsupported";
  status: "filled" | "needs_review" | "failed";
  filled_fields: FilledField[];
  flagged_fields: FlaggedField[];
  error_message?: string | null;
  created_at?: string | null;
};

export type ApprovalResponse = {
  job_id: string;
  approval_status: string;
  message: string;
};

export type ParseResumeResponse = {
  candidate: CandidateProfile;
  preferences?: TargetPreferences | null;
  note?: string;
};

export type ScoutJobsResponse = {
  jobs: Job[];
  note?: string;
};

export type InterviewPrep = {
  job_id: string;
  likely_questions: string[];
  talking_points: string[];
  gaps_to_address: string[];
};

/** Ephemeral — one practice round, never persisted server-side. */
export type InterviewAnswerFeedback = {
  question: string;
  answer: string;
  feedback: string;
};

export type TrackerStatus =
  | "saved"
  | "pending_review"
  | "approved"
  | "ready_to_apply"
  | "applied"
  | "interviewing"
  | "rejected"
  | "offer"
  | "withdrawn";

export type ApplicationTrackerItem = {
  job_id: string;
  status?: TrackerStatus | null;
  note?: string | null;
  /** ISO date string (YYYY-MM-DD), e.g. from an <input type="date">. */
  reminder_date?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  allowed_statuses?: TrackerStatus[];
};

export type ApplicationListItem = {
  job_id: string;
  title: string;
  company: string;
  match_score?: number | null;
  recommendation?: "apply" | "consider" | "skip" | null;
  approval_status?: ApplicationPackage["approval_status"] | null;
  tracker_status?: TrackerStatus | null;
  reminder_date?: string | null;
  updated_at?: string | null;
  allowed_statuses?: TrackerStatus[];
};

export type DashboardSummary = {
  profile_completion: number;
  skills_count: number;
  target_roles: string[];
  preferred_location?: string | null;
  jobs_discovered: number;
  jobs_verified: number;
  high_matches: number;
  ready_to_apply: number;
  applications_saved: number;
  applications_ready: number;
  applications_applied: number;
  interviews: number;
};

export type HealthResponse = {
  status: string;
  database: string;
};
