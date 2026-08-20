"""Shared Pydantic models for CareerPilot AI.

Keep these intentionally small for Day 1. Nested models replace untyped dicts
for projects, experience, and education. Agent-specific payloads come later.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


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
    target_roles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    remote_preference: str | None = None
    salary_min: int | None = None
    work_authorization: str | None = None
    sponsorship_required: bool | None = None
    constraints: list[str] = Field(default_factory=list)


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
    status: str = "discovered"


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


class ApprovalRequest(BaseModel):
    decision: Literal["approved", "edit_requested", "rejected"]
    notes: str | None = None


class ApprovalResponse(BaseModel):
    job_id: str
    approval_status: str
    message: str


class JobWithScore(BaseModel):
    job: Job
    match: MatchScore | None = None
