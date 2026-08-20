"""Fit-score placeholder routes."""

from __future__ import annotations

from fastapi import APIRouter

from backend.schemas.schemas import MatchScore
from backend.services.analysis_service import mock_match_score

router = APIRouter(prefix="/api", tags=["scoring"])


@router.post("/jobs/{job_id}/score", response_model=MatchScore)
def score_job(job_id: str) -> MatchScore:
    """Day 1 mock fit score. Real scoring is not implemented."""
    return mock_match_score(job_id)
