"""Shared fixtures for grounded materials and stored-score tests."""

from __future__ import annotations

import json

from backend.db.models import (
    ApplicationPackageRecord,
    Candidate,
    JobIntelligenceRecord,
    JobRecord,
    MatchScoreRecord,
    TargetPreference,
    User,
)
from backend.services.candidate_provenance import fingerprint_for_candidate

TEST_USER_ID = 1

VALID_MATERIALS_JSON = json.dumps(
    {
        "tailored_bullets": [
            "Built Python APIs at Northstar Labs as Software Engineering Intern and reduced p95 latency by 28%.",
            "Built Campus Planner with Python and FastAPI.",
        ],
        "cover_letter_draft": "I am applying using stored Python and SQL evidence.",
        "recruiter_message": "Happy to discuss Python.",
        "source_traceability_notes": ["Python <- candidate skills"],
    }
)


def fake_grounded_generator(_prompt: str, _system_prompt: str | None = None) -> str:
    return VALID_MATERIALS_JSON


def ensure_user(session, user_id: int = TEST_USER_ID, email: str | None = None) -> User:
    existing = session.get(User, user_id)
    if existing is not None:
        return existing
    user = User(
        id=user_id,
        email=email or f"user{user_id}@example.com",
        hashed_password="x",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def insert_job(
    session,
    *,
    public_id: str = "manual-abc123",
    title: str = "Software Engineer Intern",
) -> JobRecord:
    record = JobRecord(
        public_id=public_id,
        title=title,
        company="Acme",
        url=f"https://example.com/jobs/{public_id}",
        description="Required: Python and SQL. Preferred: Docker.",
        source="manual",
        status="verified",
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def insert_candidate(session, *, user_id: int = TEST_USER_ID) -> Candidate:
    ensure_user(session, user_id)
    previous = session.query(Candidate).filter(Candidate.user_id == user_id).first()
    if previous is not None:
        previous.user_id = None
        session.commit()
    record = Candidate(
        user_id=user_id,
        name="Jordan Avery",
        email="jordan@example.com",
        skills=["Python", "SQL"],
        projects=[
            {
                "name": "Campus Planner",
                "description": "Python API for campus events.",
                "technologies": ["Python", "FastAPI"],
                "url": None,
            }
        ],
        experience=[
            {
                "title": "Software Engineering Intern",
                "company": "Northstar Labs",
                "start_date": "2025-05",
                "end_date": "2025-08",
                "highlights": ["Reduced p95 latency on search endpoints by 28%."],
            }
        ],
        education=[
            {
                "institution": "State University",
                "degree": "B.S.",
                "field": "Computer Science",
                "graduation_year": "2027",
            }
        ],
        certifications=[],
        strengths=["Backend APIs"],
        evidence_links=[],
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def insert_intelligence(session, job: JobRecord) -> JobIntelligenceRecord:
    record = JobIntelligenceRecord(
        job_id=job.id,
        required_skills=["Python", "SQL"],
        preferred_skills=["Docker"],
        years_experience=0,
        education_requirements=["Bachelor's in CS"],
        tech_stack=["Python", "SQL"],
        seniority="intern",
        responsibilities=["Implement API endpoints with tests"],
        likely_interview_focus=["Python fundamentals"],
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def insert_score(
    session,
    job: JobRecord,
    candidate: Candidate,
    *,
    recommendation: str = "apply",
    overall_score: float = 82.0,
    matched_skills: list[str] | None = None,
    missing_skills: list[str] | None = None,
) -> MatchScoreRecord:
    record = MatchScoreRecord(
        job_id=job.id,
        candidate_id=candidate.id,
        overall_score=overall_score,
        skill_score=80.0,
        experience_score=70.0,
        education_score=100.0,
        location_score=None,
        preference_score=None,
        matched_skills=list(matched_skills or ["Python", "SQL"]),
        partial_matches=[],
        missing_skills=list(missing_skills or ["Docker"]),
        recommendation=recommendation,
        rationale="Matched Python and SQL from stored evidence.",
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def seed_materials_prerequisites(
    session,
    *,
    public_id: str = "manual-abc123",
    job_id: str | None = None,
    with_score: bool = True,
    title: str = "Software Engineer Intern",
    user_id: int = TEST_USER_ID,
):
    job_public_id = job_id or public_id
    ensure_user(session, user_id)
    candidate = (
        session.query(Candidate).filter(Candidate.user_id == user_id).first()
        or insert_candidate(session, user_id=user_id)
    )
    job = session.query(JobRecord).filter_by(public_id=job_public_id).first()
    if job is None:
        job = insert_job(session, public_id=job_public_id, title=title)
    elif title != job.title:
        job.title = title
        session.commit()
    if session.query(JobIntelligenceRecord).filter_by(job_id=job.id).first() is None:
        insert_intelligence(session, job)
    if (
        with_score
        and session.query(MatchScoreRecord)
        .filter_by(job_id=job.id, candidate_id=candidate.id)
        .first()
        is None
    ):
        insert_score(session, job, candidate)
    if session.query(TargetPreference).filter_by(user_id=user_id).first() is None:
        session.add(
            TargetPreference(
                user_id=user_id,
                candidate_id=candidate.id,
                target_roles=["Software Engineer Intern"],
                preferred_locations=["Remote"],
            )
        )
        session.commit()
    return job, candidate


def insert_grounded_package(
    session,
    job: JobRecord,
    *,
    candidate: Candidate | None = None,
    user_id: int = TEST_USER_ID,
) -> ApplicationPackageRecord:
    ensure_user(session, user_id)
    if candidate is None:
        candidate = session.query(Candidate).filter(Candidate.user_id == user_id).first()
    owner_id = candidate.user_id if candidate is not None and candidate.user_id is not None else user_id
    payload = json.loads(VALID_MATERIALS_JSON)
    fingerprint = None
    if candidate is not None:
        fingerprint = fingerprint_for_candidate(session, candidate, owner_id)
    record = ApplicationPackageRecord(
        job_id=job.id,
        user_id=owner_id,
        candidate_id=candidate.id if candidate is not None else None,
        tailored_bullets=payload["tailored_bullets"],
        cover_letter_draft=payload["cover_letter_draft"],
        recruiter_message=payload["recruiter_message"],
        source_traceability_notes=payload["source_traceability_notes"],
        approval_status="pending_review",
        grounded=True,
        candidate_profile_fingerprint=fingerprint,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record
