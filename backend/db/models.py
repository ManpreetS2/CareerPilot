"""SQLAlchemy persistence models for Day 1 foundations."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from backend.db.database import Base


class User(Base):
    """A real login identity. One User has at most one Candidate (see
    Candidate.user_id) — everything else (jobs, match scores, application
    packages, form-fill attempts) is scoped through that Candidate."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class UserSession(Base):
    """A server-side-revocable login session. `token` is the opaque,
    high-entropy value stored in the session cookie — validating a request
    means looking this row up, not decoding/verifying a signed value, so
    logout (deleting the row) immediately invalidates it everywhere."""

    __tablename__ = "user_sessions"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    projects: Mapped[list] = mapped_column(JSON, default=list)
    experience: Mapped[list] = mapped_column(JSON, default=list)
    education: Mapped[list] = mapped_column(JSON, default=list)
    certifications: Mapped[list] = mapped_column(JSON, default=list)
    strengths: Mapped[list] = mapped_column(JSON, default=list)
    evidence_links: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    preferences: Mapped[list["TargetPreference"]] = relationship(back_populates="candidate")


class TargetPreference(Base):
    __tablename__ = "target_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int | None] = mapped_column(ForeignKey("candidates.id"), nullable=True)
    # Set directly (not just derived through candidate_id) because
    # preferences can legitimately be saved before a Candidate row exists —
    # a user can fill in "Job preferences" before ever uploading a resume.
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    target_roles: Mapped[list] = mapped_column(JSON, default=list)
    preferred_locations: Mapped[list] = mapped_column(JSON, default=list)
    remote_preference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    work_authorization: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sponsorship_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    constraints: Mapped[list] = mapped_column(JSON, default=list)
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    github_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    portfolio_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    earliest_start_date: Mapped[str | None] = mapped_column(String(128), nullable=True)
    currently_enrolled_in_program: Mapped[str | None] = mapped_column(String(16), nullable=True)
    expected_graduation: Mapped[str | None] = mapped_column(String(64), nullable=True)
    degree_pursuing: Mapped[str | None] = mapped_column(String(128), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(64), nullable=True)
    race_ethnicity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    veteran_status: Mapped[str | None] = mapped_column(String(128), nullable=True)
    disability_status: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    candidate: Mapped[Candidate | None] = relationship(back_populates="preferences")


class JobRecord(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    salary: Mapped[str | None] = mapped_column(String(128), nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    date_posted: Mapped[str | None] = mapped_column(String(32), nullable=True)
    date_scraped: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ats: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="discovered")
    verification_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    intelligence: Mapped["JobIntelligenceRecord | None"] = relationship(back_populates="job")
    match_scores: Mapped[list["MatchScoreRecord"]] = relationship(back_populates="job")
    applications: Mapped[list["ApplicationPackageRecord"]] = relationship(back_populates="job")
    form_fill_attempts: Mapped[list["FormFillAttemptRecord"]] = relationship(back_populates="job")


class JobIntelligenceRecord(Base):
    __tablename__ = "job_intelligence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), unique=True)
    required_skills: Mapped[list] = mapped_column(JSON, default=list)
    preferred_skills: Mapped[list] = mapped_column(JSON, default=list)
    years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    education_requirements: Mapped[list] = mapped_column(JSON, default=list)
    tech_stack: Mapped[list] = mapped_column(JSON, default=list)
    seniority: Mapped[str | None] = mapped_column(String(64), nullable=True)
    responsibilities: Mapped[list] = mapped_column(JSON, default=list)
    likely_interview_focus: Mapped[list] = mapped_column(JSON, default=list)

    job: Mapped[JobRecord] = relationship(back_populates="intelligence")


class MatchScoreRecord(Base):
    __tablename__ = "match_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    candidate_id: Mapped[int | None] = mapped_column(ForeignKey("candidates.id"), nullable=True)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    skill_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    experience_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    education_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    preference_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    matched_skills: Mapped[list] = mapped_column(JSON, default=list)
    partial_matches: Mapped[list] = mapped_column(JSON, default=list)
    missing_skills: Mapped[list] = mapped_column(JSON, default=list)
    recommendation: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    job: Mapped[JobRecord] = relationship(back_populates="match_scores")


class ApplicationPackageRecord(Base):
    __tablename__ = "application_packages"
    # Composite on (job_id, user_id), not job_id alone — two different users
    # must each be able to have their own package for the same shared job.
    __table_args__ = (
        Index("ux_application_packages_job_user", "job_id", "user_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    candidate_id: Mapped[int | None] = mapped_column(ForeignKey("candidates.id"), nullable=True)
    tailored_bullets: Mapped[list] = mapped_column(MutableList.as_mutable(JSON), default=list)
    cover_letter_draft: Mapped[str | None] = mapped_column(Text, nullable=True)
    recruiter_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_traceability_notes: Mapped[list] = mapped_column(MutableList.as_mutable(JSON), default=list)
    approval_status: Mapped[str] = mapped_column(String(32), default="draft")
    eligibility_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    eligibility_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    job: Mapped[JobRecord] = relationship(back_populates="applications")


class FormFillAttemptRecord(Base):
    """One assisted-apply run against a real ATS form. Multiple attempts per
    job are kept (not upserted) — each run is a fresh browser session
    against a live external page, and a re-run legitimately produces new
    results as the page or the mapped data changes."""

    __tablename__ = "form_fill_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    ats_platform: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    filled_fields: Mapped[list] = mapped_column(MutableList.as_mutable(JSON), default=list)
    flagged_fields: Mapped[list] = mapped_column(MutableList.as_mutable(JSON), default=list)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    job: Mapped[JobRecord] = relationship(back_populates="form_fill_attempts")
