"""Fit-scoring Day 1 mocks. No real scoring yet."""

from __future__ import annotations

import hashlib

from backend.schemas.schemas import MatchScore
from backend.services.job_service import get_job


def mock_match_score(job_id: str) -> MatchScore:
    job = get_job(job_id)
    # Deterministic per job_id (not random per call) so sort/filter-by-match
    # stay meaningful in the UI until Day 4's real Fit & Gap agent replaces
    # this mock. A prior version keyed off 3 hardcoded ids from the old
    # MOCK_JOBS dataset ("job-001" etc); real DB-backed jobs never match
    # those, which flattened every real job to the same fallback score.
    digest = hashlib.sha256(job_id.encode()).hexdigest()
    overall = 55.0 + (int(digest[:4], 16) % 41)  # stable pseudo-score in [55, 95]
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
