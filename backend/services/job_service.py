"""Job discovery Day 1 mocks. No scraping yet."""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import HTTPException, status

from backend.schemas.schemas import Job, JobIntelligence

MOCK_JOBS: list[Job] = [
    Job(
        id="job-001",
        title="Software Engineer Intern",
        company="Aether Analytics",
        location="San Francisco, CA (Hybrid)",
        salary="$45/hr",
        url="https://example.com/jobs/aether-swe-intern",
        description=(
            "Build Python services that power analytics dashboards. "
            "Work with FastAPI, SQL, and a small React frontend."
        ),
        source="mock",
        date_posted=date(2026, 8, 12),
        date_scraped=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
        ats="Greenhouse",
        status="verified",
    ),
    Job(
        id="job-002",
        title="Backend Intern",
        company="Harbor Health",
        location="Remote (US)",
        salary="$40/hr",
        url="https://example.com/jobs/harbor-backend-intern",
        description=(
            "Help maintain HIPAA-aware APIs. Python, PostgreSQL, and automated tests "
            "are the core of the intern project."
        ),
        source="mock",
        date_posted=date(2026, 8, 8),
        date_scraped=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
        ats="Lever",
        status="discovered",
    ),
    Job(
        id="job-003",
        title="Full-Stack Intern",
        company="Nimbus Retail",
        location="Austin, TX",
        salary="$38/hr",
        url="https://example.com/jobs/nimbus-fullstack-intern",
        description=(
            "Ship features across a FastAPI backend and a React storefront. "
            "Mentorship-heavy intern program."
        ),
        source="mock",
        date_posted=date(2026, 8, 1),
        date_scraped=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
        ats="Ashby",
        status="discovered",
    ),
]


def list_jobs() -> list[Job]:
    return list(MOCK_JOBS)


def get_job(job_id: str) -> Job:
    for job in MOCK_JOBS:
        if job.id == job_id:
            return job
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found")


def scout_jobs() -> list[Job]:
    """Day 1 placeholder for future job discovery."""
    return list_jobs()


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
