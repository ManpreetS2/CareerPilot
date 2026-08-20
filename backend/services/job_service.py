"""Job discovery — DB-backed listing. Scouting/normalization/persistence
logic lives in job_scout_service.py; this module reads what's been stored."""

from __future__ import annotations

from datetime import date

from fastapi import HTTPException, status

from backend.db.database import SessionLocal
from backend.db.models import JobRecord
from backend.schemas.schemas import Job, JobIntelligence


def record_to_job(record: JobRecord) -> Job:
    return Job(
        id=record.public_id,
        title=record.title,
        company=record.company,
        location=record.location,
        salary=record.salary,
        url=record.url,
        description=record.description,
        source=record.source,
        date_posted=date.fromisoformat(record.date_posted) if record.date_posted else None,
        date_scraped=record.date_scraped,
        ats=record.ats,
        status=record.status,
        verification_notes=record.verification_notes,
        verified_at=record.verified_at,
    )


def list_jobs() -> list[Job]:
    with SessionLocal() as db:
        records = db.query(JobRecord).order_by(JobRecord.date_scraped.desc()).all()
        return [record_to_job(record) for record in records]


def get_job(job_id: str) -> Job:
    with SessionLocal() as db:
        record = db.query(JobRecord).filter(JobRecord.public_id == job_id).first()
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found")
        return record_to_job(record)


def scout_jobs(query: str = "software engineer intern", location: str | None = None) -> list[Job]:
    # Deferred import: job_scout_service imports record_to_job from this module,
    # so the reverse import must happen at call time to avoid a circular import.
    from backend.services.job_scout_service import run_scout

    return run_scout(query=query, location=location)


def mock_job_intelligence(job_id: str) -> JobIntelligence:
    get_job(job_id)
    return JobIntelligence(
        job_id=job_id,
        required_skills=["Python", "SQL", "REST APIs"],
        preferred_skills=["FastAPI", "Docker", "React"],
        years_experience=0,
        education_requirements=["Bachelor's in CS or equivalent intern experience"],
        tech_stack=["Python", "FastAPI", "PostgreSQL", "React"],
        seniority="intern",
        responsibilities=[
            "Implement API endpoints with tests",
            "Write SQL queries and small schema changes",
            "Collaborate in weekly sprint reviews",
        ],
        likely_interview_focus=["Python fundamentals", "SQL joins", "API design"],
    )
