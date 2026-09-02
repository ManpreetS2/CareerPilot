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
  academic_year?: string | null;
  work_mode_preferences?: string[];
  relocation_willingness?: string | null;
  field_of_study?: string | null;
  industry_preferences?: string[];
  opportunity_preference?: string | null;
  experience_levels?: string[];
  skill_preferences?: string[];
  gender?: string | null;
  race_ethnicity?: string | null;
  veteran_status?: string | null;
  disability_status?: string | null;
};

export type ProfileReadiness = {
  ready: boolean;
  code?: string | null;
  missing: string[];
  next_route?: string | null;
};

export type CurrentProfile = {
  candidate: CandidateProfile | null;
  preferences: TargetPreferences | null;
  readiness: ProfileReadiness;
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
  source_job_id?: string | null;
  content_status?: "full" | "partial" | "unknown" | null;
  content_hash?: string | null;
  status: JobStatus;
  verification_notes?: string | null;
  verified_at?: string | null;
  opportunity_type?: "internship" | "role" | "unknown" | null;
  employment_type?: string | null;
  work_mode?: "remote" | "hybrid" | "onsite" | "unknown" | null;
  saved?: boolean;
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
  qualification_score?: number | null;
  confidence_score?: number | null;
  confidence_level?: "high" | "medium" | "low" | null;
  eligibility_status?: "likely_eligible" | "eligibility_uncertain" | "likely_ineligible" | null;
  match_tier?: "strong_match" | "good_match" | "possible_match" | "weak_match" | null;
  apply_recommendation?: "strong_apply" | "apply" | "consider" | "probably_skip" | null;
  ranking_score?: number | null;
  scoring_version?: number;
  score_kind?: "full" | "preliminary" | "verified" | null;
  match_reasons?: string[];
  gap_reasons?: string[];
  watchouts?: string[];
  covered_responsibilities?: string[];
  partial_responsibilities?: string[];
  uncovered_responsibilities?: string[];
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
  jobs_found?: number;
  matched_count?: number;
  sources_searched?: number;
  sources_unavailable?: number;
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

export type JobsTab = "discover" | "matches" | "saved";
export type JobsSort = "best_match" | "newest" | "qualification" | "preference";
export type OpportunityFilter = "both" | "internship" | "role";

export type JobSearchIntent = {
  raw_query?: string | null;
  query?: string | null;
  roles: string[];
  locations: string[];
  opportunity_types: Array<"internship" | "role" | "unknown">;
  employment_types: string[];
  experience_levels: string[];
  work_modes: string[];
  remote_scopes: string[];
  industries: string[];
  skills: string[];
  salary_min?: number | null;
  date_posted?: string | null;
  verified_state: "all" | "verified" | "potential";
  eligibility_state: "all" | "likely_eligible" | "eligibility_uncertain" | "likely_ineligible";
  confidence_state: "all" | "high" | "medium" | "low";
  parser_ready: boolean;
  parser_source?: "deterministic" | "gemini" | "empty";
};

export type SearchIntent = JobSearchIntent;

export type JobListItem = {
  job: Job;
  match?: MatchScore | null;
  saved?: boolean;
};

export type JobListPage = {
  items: JobListItem[];
  total: number;
  page: number;
  page_size: number;
  verified_count: number;
  potential_count: number;
  ids: string[];
};

export type JobQueryParams = {
  q?: string;
  tab?: JobsTab;
  opportunity?: OpportunityFilter | string;
  employment_type?: string[];
  experience_level?: string[];
  work_mode?: string[];
  location?: string[];
  industry?: string[];
  verified_state?: string;
  eligibility?: string;
  confidence?: string;
  date_posted?: string;
  sort?: JobsSort | string;
  page?: number;
  page_size?: number;
};

export type Requirement = {
  id: string;
  category: string;
  text: string;
  importance: "hard_required" | "required" | "preferred";
  evidence_text: string;
  structured_condition?: Record<string, unknown> | null;
};

export type RequirementGroup = {
  id: string;
  operator: "any_of" | "all_of";
  requirement_ids: string[];
  text: string;
  evidence_text: string;
  importance: "hard_required" | "required" | "preferred";
};

export type JobRequirementProfile = {
  job_id?: string | null;
  role_title?: string | null;
  role_family?: string | null;
  experience_level?: string | null;
  employment_type?: string | null;
  required_skills: string[];
  preferred_skills: string[];
  primary_responsibilities: string[];
  requirements: Requirement[];
  requirement_groups: RequirementGroup[];
  locations: { label: string; evidence_text?: string | null }[];
  work_mode?: string | null;
  remote_scope?: string | null;
  timezone_requirements?: string | null;
  hybrid_onsite_frequency?: number | null;
  travel_requirements: Requirement[];
  relocation_requirements: Requirement[];
  paid_status?: string | null;
  extraction_confidence?: number | null;
  content_status?: "full" | "partial" | "unknown" | null;
  source_fingerprint: string;
};

export type FactorStatus = "satisfied" | "partially_satisfied" | "not_satisfied" | "unknown" | "not_applicable";

export type EvidenceRef = {
  id: string;
  source_type: string;
  source_entity_id?: string | null;
  field?: string | null;
  exact_text: string;
  locator?: string | null;
};

export type MatchFactor = {
  id: string;
  job_id: string;
  category: string;
  section: "required_skills" | "preferred_skills" | "qualifications" | "eligibility" | "work_location" | "preferences";
  label: string;
  importance?: string | null;
  status: FactorStatus;
  score_contribution?: number | null;
  max_contribution?: number | null;
  rule_id: string;
  rule_version: string;
  explanation: string;
  job_evidence_refs: string[];
  candidate_evidence_refs: string[];
  requirement_id?: string | null;
  group_id?: string | null;
  hard_blocker?: boolean;
  scoring_effect?: string | null;
};

export type RequirementEvaluation = {
  requirement_id: string;
  result: FactorStatus;
  candidate_evidence_refs: string[];
  job_evidence_refs: string[];
  explanation: string;
  rule_id: string;
  group_id?: string | null;
};

export type GroupEvaluation = {
  group_id: string;
  operator: "any_of" | "all_of";
  text: string;
  status: FactorStatus;
  importance?: string | null;
  job_evidence_refs: string[];
  branch_ids: string[];
  explanation: string;
  hard_blocker?: boolean;
};

export type MatchEvidence = {
  job_id: string;
  score?: MatchScore | null;
  full_evidence: boolean;
  notice?: string | null;
  provenance: {
    scoring_version: number;
    evidence_version: number;
    score_kind?: string | null;
    candidate_fingerprint?: string | null;
    preference_fingerprint?: string | null;
    requirement_fingerprint?: string | null;
    stale: boolean;
    stale_reasons: string[];
  };
  factors: MatchFactor[];
  evaluations: RequirementEvaluation[];
  groups: GroupEvaluation[];
  evidence: Record<string, EvidenceRef>;
};

export type EvidenceState = "satisfied" | "partial" | "unknown" | "not_satisfied";
export type PriorityLabel = "high" | "medium" | "low";
export type SkillImportance = "required" | "preferred";

export type CareerGrowthJobRef = {
  job_id: string;
  title: string;
  company: string;
  importance: SkillImportance;
  evidence_state: EvidenceState;
  saved: boolean;
};

export type SkillGrowthItem = {
  canonical_key: string;
  label: string;
  jobs_count: number;
  denominator: number;
  required_count: number;
  preferred_count: number;
  satisfied_count: number;
  partial_count: number;
  unknown_count: number;
  not_satisfied_count: number;
  candidate_evidence_state: EvidenceState;
  candidate_evidence_count: number;
  priority: PriorityLabel;
  reason: string;
  suggested_action: string;
  related_jobs: CareerGrowthJobRef[];
};

export type CareerGrowthSummary = {
  jobs_considered: number;
  jobs_with_current_evidence: number;
  saved_jobs_considered: number;
  matched_jobs_considered: number;
  stale_jobs_excluded: number;
  unavailable_jobs_excluded: number;
  generated_at: string;
  skill_gaps: SkillGrowthItem[];
  strengths: SkillGrowthItem[];
  notice?: string | null;
};
