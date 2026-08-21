"""Explainable Fit & Gap scoring routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.schemas.schemas import MatchScore
from backend.services.analysis_service import (
    CandidateRequiredError,
    JobNotFoundError,
    RequirementsUnavailableError,
    ScoringError,
    score_job,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["scoring"])


def _http_for_scoring_error(exc: Exception) -> HTTPException:
    if isinstance(exc, JobNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, (CandidateRequiredError, RequirementsUnavailableError)):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, ScoringError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    logger.exception("Unexpected scoring failure: %s", type(exc).__name__)
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unable to calculate fit score.",
    )


@router.post("/jobs/{job_id}/score", response_model=MatchScore)
def score_job_route(job_id: str, db: Session = Depends(get_db)) -> MatchScore:
    """Calculate and persist an explainable fit score using the request session."""
    try:
        return score_job(db, job_id)
    except Exception as exc:  # noqa: BLE001 — map to sanitized HTTP
        raise _http_for_scoring_error(exc) from exc
