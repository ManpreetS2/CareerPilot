"""Employer requirement profile, search intent, and pipeline contracts.

Job Intelligence remains the legacy skills/responsibilities extractor.
This module is the structured "what does the employer actually require?" model.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

EXTRACTION_VERSION = 1

ContentStatus = Literal["full", "partial", "unknown"]
RequirementImportance = Literal["hard_required", "required", "preferred"]
RequirementStatus = Literal[
    "satisfied",
    "partially_satisfied",
    "not_satisfied",
    "unknown",
    "not_applicable",
]
GroupOperator = Literal["any_of", "all_of"]
WorkMode = Literal["remote", "hybrid", "onsite", "unknown"]
EmploymentType = Literal[
    "internship",
    "new_grad",
    "full_time",
    "part_time",
    "contract",
    "temporary",
    "co_op",
    "fellowship",
    "unknown",
]
ExperienceLevel = Literal[
    "intern",
    "new_grad",
    "entry",
    "junior",
    "mid",
    "senior",
    "staff",
    "principal",
    "lead",
    "manager",
    "director",
    "executive",
    "unknown",
]
AcademicYear = Literal[
    "freshman",
    "sophomore",
    "junior",
    "senior",
    "final_year",
    "graduate_student",
    "unknown",
]
PipelineStage = Literal[
    "discovered",
    "verified_open",
    "requirements_pending",
    "requirements_ready",
    "eligibility_ready",
    "fit_ready",
    "materials_ready",
    "review_required",
    "approved",
    "autofill_ready",
]


class Requirement(BaseModel):
    id: str
    category: str
    text: str
    importance: RequirementImportance = "required"
    evidence_text: str
    structured_condition: dict | None = None


class RequirementGroup(BaseModel):
    id: str
    operator: GroupOperator
    requirement_ids: list[str]
    text: str
    evidence_text: str
    importance: RequirementImportance = "hard_required"


class JobLocation(BaseModel):
    label: str
    evidence_text: str | None = None


class CanonicalJobContent(BaseModel):
    title: str
    company: str
    full_description: str
    source: str
    canonical_url: str
    source_job_id: str | None = None
    posted_at: str | None = None
    fetched_at: datetime | None = None
    content_status: ContentStatus = "unknown"
    content_hash: str
    source_fingerprint: str


class JobRequirementProfile(BaseModel):
    job_id: str | None = None
    role_title: str | None = None
    role_family: str | None = None
    experience_level: ExperienceLevel = "unknown"
    employment_type: EmploymentType = "unknown"
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    primary_responsibilities: list[str] = Field(default_factory=list)
    secondary_responsibilities: list[str] = Field(default_factory=list)
    experience_requirements: list[Requirement] = Field(default_factory=list)
    education_requirements: list[Requirement] = Field(default_factory=list)
    enrollment_requirements: list[Requirement] = Field(default_factory=list)
    academic_year_requirements: list[Requirement] = Field(default_factory=list)
    graduation_requirements: list[Requirement] = Field(default_factory=list)
    degree_completion_requirements: list[Requirement] = Field(default_factory=list)
    field_of_study_requirements: list[Requirement] = Field(default_factory=list)
    gpa_requirements: list[Requirement] = Field(default_factory=list)
    certifications: list[Requirement] = Field(default_factory=list)
    licenses: list[Requirement] = Field(default_factory=list)
    work_authorization_requirements: list[Requirement] = Field(default_factory=list)
    sponsorship_information: list[Requirement] = Field(default_factory=list)
    cpt_information: list[Requirement] = Field(default_factory=list)
    opt_information: list[Requirement] = Field(default_factory=list)
    security_clearance_requirements: list[Requirement] = Field(default_factory=list)
    locations: list[JobLocation] = Field(default_factory=list)
    work_mode: WorkMode = "unknown"
    remote_scope: str | None = None
    timezone_requirements: str | None = None
    hybrid_onsite_frequency: int | None = None
    relocation_requirements: list[Requirement] = Field(default_factory=list)
    travel_requirements: list[Requirement] = Field(default_factory=list)
    salary_or_compensation: str | None = None
    paid_status: Literal["paid", "unpaid", "unknown"] = "unknown"
    start_date_requirements: list[Requirement] = Field(default_factory=list)
    program_duration: str | None = None
    other_required_qualifications: list[Requirement] = Field(default_factory=list)
    other_preferred_qualifications: list[Requirement] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    requirement_groups: list[RequirementGroup] = Field(default_factory=list)
    extraction_confidence: float = 0.0
    source_fingerprint: str
    extraction_version: int = EXTRACTION_VERSION
    content_status: ContentStatus = "unknown"
    canonical: CanonicalJobContent | None = None


class RequirementComparison(BaseModel):
    requirement_id: str
    status: RequirementStatus
    reason: str


class GroupComparison(BaseModel):
    group_id: str
    status: RequirementStatus
    reason: str


class EligibilityReport(BaseModel):
    status: Literal["likely_eligible", "eligibility_uncertain", "likely_ineligible"]
    comparisons: list[RequirementComparison] = Field(default_factory=list)
    groups: list[GroupComparison] = Field(default_factory=list)
    watchouts: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


class SearchIntent(BaseModel):
    """Validated typed filters. Never SQL. Never outbound URLs."""

    raw_query: str | None = None
    roles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    employment_types: list[EmploymentType] = Field(default_factory=list)
    experience_levels: list[ExperienceLevel] = Field(default_factory=list)
    work_modes: list[WorkMode] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    salary_min: int | None = None
    start_season: str | None = None
    parser_ready: bool = False


class PipelineStatus(BaseModel):
    job_id: str
    stage: PipelineStage
    error_category: str | None = None
    updated_at: datetime | None = None
