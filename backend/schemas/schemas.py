"""Shared Pydantic models for CareerPilot AI.

Keep these intentionally small for Day 1. Nested models replace untyped dicts
for projects, experience, and education. Agent-specific payloads come later.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class Project(BaseModel):
    name: str
    description: str | None = None
    technologies: list[str] = Field(default_factory=list)
    url: str | None = None


class Experience(BaseModel):
    title: str
    company: str
    start_date: str | None = None
    end_date: str | None = None
    highlights: list[str] = Field(default_factory=list)


class Education(BaseModel):
    institution: str
    degree: str | None = None
    field: str | None = None
    graduation_year: str | None = None


class CandidateProfile(BaseModel):
    id: str | None = None
    name: str
    email: str | None = None
    phone: str | None = None
    skills: list[str] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    evidence_links: list[str] = Field(default_factory=list)


class TargetPreferences(BaseModel):
    """User-stated job search preferences.

    salary_min is annual USD base salary (not hourly).
    """

    target_roles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    remote_preference: str | None = Field(default=None, max_length=64)
    salary_min: int | None = Field(
        default=None,
        description="Minimum acceptable base salary in annual USD (not hourly).",
    )
    work_authorization: str | None = Field(default=None, max_length=128)
    sponsorship_required: bool | None = None
    constraints: list[str] = Field(default_factory=list)
    legal_name: str | None = Field(default=None, max_length=255)
    linkedin_url: str | None = Field(default=None, max_length=512)
    github_url: str | None = Field(default=None, max_length=512)
    portfolio_url: str | None = Field(default=None, max_length=512)
    earliest_start_date: str | None = Field(default=None, max_length=128)
    currently_enrolled_in_program: str | None = Field(default=None, max_length=16)
    expected_graduation: str | None = Field(default=None, max_length=64)
    degree_pursuing: str | None = Field(default=None, max_length=128)
    academic_year: str | None = Field(default=None, max_length=32)
    work_mode_preferences: list[str] = Field(default_factory=list)
    relocation_willingness: str | None = Field(default=None, max_length=16)
    field_of_study: str | None = Field(default=None, max_length=128)
    industry_preferences: list[str] = Field(default_factory=list)
    opportunity_preference: str | None = Field(default=None, max_length=32)
    experience_levels: list[str] = Field(default_factory=list)
    skill_preferences: list[str] = Field(default_factory=list)
    gender: str | None = Field(default=None, max_length=64)
    race_ethnicity: str | None = Field(default=None, max_length=64)
    veteran_status: str | None = Field(default=None, max_length=128)
    disability_status: str | None = Field(default=None, max_length=128)

    @field_validator("salary_min")
    @classmethod
    def validate_annual_salary(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value < 10_000 or value > 1_000_000:
            raise ValueError(
                "salary_min must be an annual USD amount between 10000 and 1000000"
            )
        return value

    @field_validator(
        "target_roles",
        "preferred_locations",
        "constraints",
        "work_mode_preferences",
        "industry_preferences",
        "experience_levels",
        "skill_preferences",
    )
    @classmethod
    def _bounded_preference_lists(cls, value: list[str]) -> list[str]:
        if len(value) > 40:
            raise ValueError("Too many items.")
        for item in value:
            if len(item) > 200:
                raise ValueError("An item is too long.")
        return value


class Job(BaseModel):
    id: str | None = None
    title: str
    company: str
    location: str | None = None
    salary: str | None = None
    url: str
    description: str
    source: str
    date_posted: date | None = None
    date_scraped: datetime | None = None
    ats: str | None = None
    source_job_id: str | None = None
    content_status: Literal["full", "partial", "unknown"] | None = None
    content_hash: str | None = None
    status: Literal["discovered", "verified", "flagged", "stale"] = "discovered"
    verification_notes: str | None = None
    verified_at: datetime | None = None
    opportunity_type: Literal["internship", "role", "unknown"] | None = None
    employment_type: str | None = None
    work_mode: Literal["remote", "hybrid", "onsite", "unknown"] | None = None
    saved: bool = False


class JobIntelligence(BaseModel):
    job_id: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    years_experience: int | None = None
    education_requirements: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    seniority: str | None = None
    responsibilities: list[str] = Field(default_factory=list)
    likely_interview_focus: list[str] = Field(default_factory=list)


class MatchScore(BaseModel):
    job_id: str
    overall_score: float = Field(ge=0, le=100)
    skill_score: float | None = Field(default=None, ge=0, le=100)
    experience_score: float | None = Field(default=None, ge=0, le=100)
    education_score: float | None = Field(default=None, ge=0, le=100)
    location_score: float | None = Field(default=None, ge=0, le=100)
    preference_score: float | None = Field(default=None, ge=0, le=100)
    matched_skills: list[str] = Field(default_factory=list)
    partial_matches: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    recommendation: Literal["apply", "consider", "skip"]
    rationale: str
    qualification_score: float | None = Field(default=None, ge=0, le=100)
    confidence_score: float | None = Field(default=None, ge=0, le=100)
    confidence_level: Literal["high", "medium", "low"] | None = None
    eligibility_status: Literal["likely_eligible", "eligibility_uncertain", "likely_ineligible"] | None = None
    match_tier: Literal["strong_match", "good_match", "possible_match", "weak_match"] | None = None
    apply_recommendation: Literal["strong_apply", "apply", "consider", "probably_skip"] | None = None
    ranking_score: float | None = Field(default=None, ge=0, le=100)
    scoring_version: int = 1
    score_kind: Literal["full", "preliminary", "verified"] | None = None
    match_reasons: list[str] = Field(default_factory=list)
    gap_reasons: list[str] = Field(default_factory=list)
    watchouts: list[str] = Field(default_factory=list)
    covered_responsibilities: list[str] = Field(default_factory=list)
    partial_responsibilities: list[str] = Field(default_factory=list)
    uncovered_responsibilities: list[str] = Field(default_factory=list)


class ApplicationPackage(BaseModel):
    job_id: str
    tailored_bullets: list[str] = Field(default_factory=list)
    cover_letter_draft: str | None = None
    recruiter_message: str | None = None
    source_traceability_notes: list[str] = Field(default_factory=list)
    approval_status: Literal["draft", "pending_review", "approved", "edit_requested", "rejected"] = (
        "draft"
    )
    eligibility_confirmed: bool = False
    eligibility_notes: str | None = None
    decision_notes: str | None = None
    grounded: bool = False
    # True only when the owner explicitly chose to keep a draft whose claims
    # could not all be verified. Kept separate from `grounded` so a reader
    # can distinguish "verified" from "deliberately unverified" rather than
    # seeing one ambiguous false.
    grounding_override: bool = False
    unsupported_claims: list[str] = Field(default_factory=list)


class GenerateMaterialsRequest(BaseModel):
    """Body for POST /api/jobs/{job_id}/generate-materials. Optional: the
    default request generates normally and fails if grounding rejects the
    draft."""

    override_grounding: bool = False


class CreateResumeVersionRequest(BaseModel):
    """Explicit create has no client-supplied snapshot fields.

    Extra keys are rejected so callers cannot inject hashes, paths, or IDs.
    """

    model_config = ConfigDict(extra="forbid")


class ResumeVersion(BaseModel):
    id: str
    job_id: str
    version_number: int = Field(ge=1)
    tailored_bullets: list[str] = Field(default_factory=list)
    source_traceability_notes: list[str] = Field(default_factory=list)
    created_at: datetime


class ResumeVersionSummary(BaseModel):
    id: str
    job_id: str
    job_title: str
    company: str
    version_number: int = Field(ge=1)
    created_at: datetime
    bullet_count: int = Field(ge=0)
    provenance_status: Literal["approved_snapshot"] = "approved_snapshot"
    matches_current_profile: bool


class ResumeVersionProfile(BaseModel):
    """Allowlisted historical display fields from one immutable version."""

    name: str | None = None
    email: str | None = None
    phone: str | None = None
    skills: list | None = None
    projects: list | None = None
    experience: list | None = None
    education: list | None = None
    certifications: list | None = None
    strengths: list | None = None
    evidence_links: list | None = None
    legal_name: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None


class ResumeVersionDetail(ResumeVersionSummary):
    tailored_bullets: list[str] = Field(default_factory=list)
    source_traceability_notes: list[str] = Field(default_factory=list)
    profile: ResumeVersionProfile


class ExtensionResumeVersion(ResumeVersionSummary):
    formats: list[Literal["pdf", "docx"]] = Field(default_factory=lambda: ["pdf", "docx"])


class ExtensionResumeVersionList(BaseModel):
    versions: list[ExtensionResumeVersion] = Field(default_factory=list)
    current_job_id: str | None = None


class InterviewPrep(BaseModel):
    job_id: str
    likely_questions: list[str] = Field(default_factory=list)
    talking_points: list[str] = Field(default_factory=list)
    gaps_to_address: list[str] = Field(default_factory=list)


class InterviewAnswerRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    answer: str = Field(min_length=1, max_length=20000)


class InterviewAnswerFeedback(BaseModel):
    """Ephemeral — never persisted. One practice round, not saved history."""

    question: str
    answer: str
    feedback: str


class ParseResumeResponse(BaseModel):
    candidate: CandidateProfile
    preferences: TargetPreferences | None = None
    note: str = "Grounded candidate profile extracted from the uploaded resume."


class ScoutJobsResponse(BaseModel):
    jobs: list[Job]
    note: str = "Day 1 mock response. Job discovery is not implemented yet."
    jobs_found: int = 0
    matched_count: int = 0
    sources_searched: int = 0
    sources_unavailable: int = 0


class IngestJobUrlRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class JobVerificationResponse(BaseModel):
    jobs: list[Job]
    verified: int = 0
    flagged: int = 0
    stale: int = 0


class ApprovalRequest(BaseModel):
    decision: Literal["approved", "edit_requested", "rejected"]
    notes: str | None = Field(default=None, max_length=4000)
    eligibility_confirmed: bool = False
    eligibility_notes: str | None = Field(default=None, max_length=4000)


class ApprovalResponse(BaseModel):
    job_id: str
    approval_status: str
    message: str


class JobWithScore(BaseModel):
    job: Job
    match: MatchScore | None = None


class JobListItem(BaseModel):
    job: Job
    match: MatchScore | None = None
    saved: bool = False


class JobListPage(BaseModel):
    items: list[JobListItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 40
    verified_count: int = 0
    potential_count: int = 0
    ids: list[str] = Field(default_factory=list)


class ParseSearchRequest(BaseModel):
    query: str = Field(default="", max_length=500)


class FlaggedField(BaseModel):
    field: str
    reason: str


class FilledField(BaseModel):
    field: str
    value: str


class FormFillResult(BaseModel):
    job_id: str
    ats_platform: Literal["greenhouse", "lever", "unsupported"]
    status: Literal["filled", "needs_review", "failed"]
    filled_fields: list[FilledField] = Field(default_factory=list)
    flagged_fields: list[FlaggedField] = Field(default_factory=list)
    error_message: str | None = None
    created_at: datetime | None = None


class AutofillFields(BaseModel):
    """Raw candidate/application field values for the browser extension's
    content script to fill directly into a real page — no server-side
    browser involved, so no field-detection results here, only values."""

    full_name: str
    first_name: str
    last_name: str
    email: str | None = None
    phone: str | None = None
    current_company: str | None = None
    location: str | None = None
    legal_name: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    cover_letter: str | None = None
    work_authorization: str | None = None
    sponsorship_required: bool | None = None
    earliest_start_date: str | None = None
    currently_enrolled_in_program: str | None = None
    expected_graduation: str | None = None
    degree_pursuing: str | None = None
    gender: str | None = None
    race_ethnicity: str | None = None
    veteran_status: str | None = None
    disability_status: str | None = None


class AutofillResponse(BaseModel):
    job_id: str
    platform: Literal["greenhouse", "lever", "unsupported"]
    fields: AutofillFields


class ExtensionPanelData(BaseModel):
    """Read-only status for the extension side panel: is the active tab's
    URL a job CareerPilot has seen, and if so, its score/materials status.
    Never generates, writes, or calls a provider — a passive status poll,
    unlike /api/extension/autofill which requires an approved package."""

    tracked: bool
    job: Job | None = None
    score: MatchScore | None = None
    materials_status: Literal["missing", "current", "stale_pending", "stale_reviewed"] | None = None
    # Whether assisted apply could ever run on this URL, derived from the same
    # detect_ats_platform the autofill route uses. Sent so the panel can hide
    # the fill action on a posting it can never fill instead of offering a
    # button that always fails — and so the host allowlist stays defined in
    # one place here rather than being duplicated in the extension.
    platform: Literal["greenhouse", "lever", "unsupported"] = "unsupported"
    # Whether assisted apply would actually run right now, and if not, the
    # reason the autofill route itself would have given. Lets the panel state
    # what is still needed instead of showing a button that fails on click.
    apply_ready: bool = False
    apply_blocked_reason: str | None = None
    # True when the package behind apply_ready was kept through an explicit
    # grounding override. The panel must say so before filling a real
    # application form with claims that were never verified.
    materials_unverified: bool = False
    review_required: bool = False
    saved: bool = False
    must_have: list[str] = Field(default_factory=list)
    approval_status: str | None = None


TrackerStatus = Literal[
    "saved",
    "pending_review",
    "approved",
    "ready_to_apply",
    "applied",
    "interviewing",
    "rejected",
    "offer",
    "withdrawn",
]


class ApplicationTrackerItem(BaseModel):
    job_id: str
    status: TrackerStatus | None = None
    note: str | None = None
    reminder_date: date | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    allowed_statuses: list[TrackerStatus] = Field(default_factory=list)


class ApplicationTrackerUpdate(BaseModel):
    status: TrackerStatus
    note: str | None = Field(default=None, max_length=4000)
    reminder_date: date | None = None


class ApplicationListItem(BaseModel):
    job_id: str
    title: str
    company: str
    match_score: float | None = None
    recommendation: Literal["apply", "consider", "skip"] | None = None
    approval_status: Literal[
        "draft", "pending_review", "approved", "edit_requested", "rejected"
    ] | None = None
    tracker_status: TrackerStatus | None = None
    reminder_date: date | None = None
    updated_at: datetime | None = None
    allowed_statuses: list[TrackerStatus] = Field(default_factory=list)


class DashboardSummary(BaseModel):
    profile_completion: int = 0
    skills_count: int = 0
    target_roles: list[str] = Field(default_factory=list)
    preferred_location: str | None = None
    jobs_discovered: int = 0
    jobs_verified: int = 0
    high_matches: int = 0
    ready_to_apply: int = 0
    applications_saved: int = 0
    applications_ready: int = 0
    applications_applied: int = 0
    interviews: int = 0


_PASSWORD_MIN = 8
_PASSWORD_MAX = 128


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=_PASSWORD_MIN, max_length=_PASSWORD_MAX)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("password")
    @classmethod
    def _bounded_password(cls, value: str) -> str:
        if len(value) < _PASSWORD_MIN or len(value) > _PASSWORD_MAX:
            raise ValueError("Password does not meet length requirements.")
        return value


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=_PASSWORD_MAX)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class UserPublic(BaseModel):
    id: int
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ProfileReadinessPayload(BaseModel):
    """Canonical profile-readiness contract. Deterministic; never LLM-derived."""

    ready: bool
    code: str | None = None
    missing: list[str] = Field(default_factory=list)
    next_route: str | None = None


class CurrentProfile(BaseModel):
    """Authenticated read of the current user's stored candidate and preferences."""

    candidate: CandidateProfile | None = None
    preferences: TargetPreferences | None = None
    readiness: ProfileReadinessPayload
