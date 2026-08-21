/** Shared TypeScript types mirroring backend Pydantic schemas. */

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
};

export type ApprovalDecision = "approved" | "edit_requested" | "rejected";

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

export type HealthResponse = {
  status: string;
  database: string;
};
