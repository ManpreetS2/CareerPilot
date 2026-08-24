"""Shared Pydantic models for CareerPilot AI.

Keep these intentionally small for Day 1. Nested models replace untyped dicts
for projects, experience, and education. Agent-specific payloads come later.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


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
    remote_preference: str | None = None
    salary_min: int | None = Field(
        default=None,
        description="Minimum acceptable base salary in annual USD (not hourly).",
    )
    work_authorization: str | None = None
    sponsorship_required: bool | None = None
    constraints: list[str] = Field(default_factory=list)
    legal_name: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    earliest_start_date: str | None = None
    currently_enrolled_in_program: str | None = None
    expected_graduation: str | None = None
    degree_pursuing: str | None = None
    gender: str | None = None
    race_ethnicity: str | None = None
    veteran_status: str | None = None
    disability_status: str | None = None

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
    status: Literal["discovered", "verified", "flagged", "stale"] = "discovered"
    verification_notes: str | None = None
    verified_at: datetime | None = None


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


class InterviewPrep(BaseModel):
    job_id: str
    likely_questions: list[str] = Field(default_factory=list)
    talking_points: list[str] = Field(default_factory=list)
    gaps_to_address: list[str] = Field(default_factory=list)


class ParseResumeResponse(BaseModel):
    candidate: CandidateProfile
    preferences: TargetPreferences | None = None
    note: str = "Grounded candidate profile extracted from the uploaded resume."


class ScoutJobsResponse(BaseModel):
    jobs: list[Job]
    note: str = "Day 1 mock response. Job discovery is not implemented yet."


class IngestJobUrlRequest(BaseModel):
    url: str


class JobVerificationResponse(BaseModel):
    jobs: list[Job]
    verified: int = 0
    flagged: int = 0
    stale: int = 0


class ApprovalRequest(BaseModel):
    decision: Literal["approved", "edit_requested", "rejected"]
    notes: str | None = None
    eligibility_confirmed: bool = False
    eligibility_notes: str | None = None


class ApprovalResponse(BaseModel):
    job_id: str
    approval_status: str
    message: str


class JobWithScore(BaseModel):
    job: Job
    match: MatchScore | None = None


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
    created_at: datetime | None = None
    updated_at: datetime | None = None
    allowed_statuses: list[TrackerStatus] = Field(default_factory=list)


class ApplicationTrackerUpdate(BaseModel):
    status: TrackerStatus
    note: str | None = None


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


class CurrentProfile(BaseModel):
    """Authenticated read of the current user's stored candidate and preferences."""

    candidate: CandidateProfile | None = None
    preferences: TargetPreferences | None = None
