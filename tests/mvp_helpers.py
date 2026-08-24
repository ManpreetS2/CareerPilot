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
)

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


def insert_candidate(session) -> Candidate:
    record = Candidate(
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
        matched_skills=["Python", "SQL"],
        partial_matches=[],
        missing_skills=["Docker"],
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
    with_score: bool = True,
    title: str = "Software Engineer Intern",
):
    candidate = session.query(Candidate).order_by(Candidate.id.desc()).first() or insert_candidate(session)
    job = session.query(JobRecord).filter_by(public_id=public_id).first()
    if job is None:
        job = insert_job(session, public_id=public_id, title=title)
    if session.query(JobIntelligenceRecord).filter_by(job_id=job.id).first() is None:
        insert_intelligence(session, job)
    if with_score and session.query(MatchScoreRecord).filter_by(job_id=job.id, candidate_id=candidate.id).first() is None:
        insert_score(session, job, candidate)
    if session.query(TargetPreference).filter_by(candidate_id=candidate.id).first() is None:
        session.add(
            TargetPreference(
                candidate_id=candidate.id,
                target_roles=["Software Engineer Intern"],
                preferred_locations=["Remote"],
            )
        )
        session.commit()
    return job, candidate


def insert_grounded_package(
    session, job: JobRecord, *, candidate: Candidate | None = None
) -> ApplicationPackageRecord:
    if candidate is None:
        candidate = session.query(Candidate).order_by(Candidate.id.desc()).first()
    payload = json.loads(VALID_MATERIALS_JSON)
    record = ApplicationPackageRecord(
        job_id=job.id,
        candidate_id=candidate.id if candidate is not None else None,
        tailored_bullets=payload["tailored_bullets"],
        cover_letter_draft=payload["cover_letter_draft"],
        recruiter_message=payload["recruiter_message"],
        source_traceability_notes=payload["source_traceability_notes"],
        approval_status="pending_review",
        grounded=True,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


seed_materials_prerequisites = seed_materials_prerequisites
VALID_MATERIALS_JSON = VALID_MATERIALS_JSON
fake_grounded_generator = fake_grounded_generator
insert_grounded_package = insert_grounded_package
