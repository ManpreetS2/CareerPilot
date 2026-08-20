"""Fit-scoring Day 1 mocks. No real scoring yet."""

from __future__ import annotations

from backend.schemas.schemas import MatchScore
from backend.services.job_service import get_job


def mock_match_score(job_id: str) -> MatchScore:
    job = get_job(job_id)
    scores = {
        "job-001": 86.0,
        "job-002": 78.0,
        "job-003": 71.0,
    }
    overall = scores.get(job_id, 70.0)
    recommendation: str = "apply" if overall >= 80 else "consider"
    return MatchScore(
        job_id=job.id or job_id,
        overall_score=overall,
        skill_score=overall - 4,
        experience_score=72.0,
        education_score=90.0,
        location_score=80.0,
        preference_score=88.0,
        matched_skills=["Python", "SQL", "FastAPI"],
        partial_matches=["React"],
        missing_skills=["Kubernetes"],
        recommendation=recommendation,  # type: ignore[arg-type]
        rationale=(
            f"Mock Day 1 score for {job.title} at {job.company}. "
            "Real fit scoring is not implemented yet."
        ),
    )
