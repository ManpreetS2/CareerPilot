"""Interview-prep routes. Generation is explicit; GET is read-only."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.schemas.schemas import InterviewPrep
from backend.services.interview_service import (
    InterviewIntelligenceMissingError,
    InterviewJobNotFoundError,
    InterviewPrepError,
    generate_and_store_interview_prep,
    get_interview_prep,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["interview"])


def _http_for_interview_error(exc: Exception) -> HTTPException:
    if isinstance(exc, InterviewJobNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, InterviewIntelligenceMissingError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, InterviewPrepError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    logger.error("Unexpected interview-prep failure category=internal")
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unable to prepare interview materials.",
    )


@router.get("/jobs/{job_id}/interview-prep", response_model=InterviewPrep)
def read_interview_prep(job_id: str, db: Session = Depends(get_db)) -> InterviewPrep:
    """Return the stored interview-prep record without generating a new one."""
    try:
        prep = get_interview_prep(db, job_id)
    except Exception as exc:  # noqa: BLE001 — map to sanitized HTTP
        raise _http_for_interview_error(exc) from exc
    if prep is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview prep has not been generated.",
        )
    return prep


@router.post("/jobs/{job_id}/prepare-interview", response_model=InterviewPrep)
def prepare_interview(job_id: str, db: Session = Depends(get_db)) -> InterviewPrep:
    """Explicit deterministic interview-prep generation. Does not call a provider."""
    try:
        return generate_and_store_interview_prep(db, job_id)
    except Exception as exc:  # noqa: BLE001 — map to sanitized HTTP
        raise _http_for_interview_error(exc) from exc
