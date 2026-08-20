"""Candidate API routes — real parse-resume pipeline + preferences."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.db.models import TargetPreference
from backend.schemas.schemas import ParseResumeResponse, TargetPreferences
from backend.services.candidate_profile_agent import (
    CandidateProfileError,
    InvalidResumeError,
    OCRUnavailableError,
    ProfileExtractionError,
    ProfileGroundingError,
    ResumeExtractionError,
    build_candidate_profile_from_upload,
)
from backend.services.llm_client import LLMConfigurationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["candidate"])


def _http_for_candidate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, InvalidResumeError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, OCRUnavailableError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if isinstance(exc, ProfileGroundingError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if isinstance(exc, (ProfileExtractionError, LLMConfigurationError)):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Candidate profile extraction provider failed. Check LLM configuration and retry.",
        )
    if isinstance(exc, ResumeExtractionError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if isinstance(exc, CandidateProfileError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    logger.exception("Unexpected candidate profile failure: %s", type(exc).__name__)
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unable to process resume.",
    )


@router.post("/parse-resume", response_model=ParseResumeResponse)
async def parse_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ParseResumeResponse:
    """Parse an uploaded PDF into a grounded CandidateProfile and persist it."""
    content = await file.read()

    def _process() -> ParseResumeResponse:
        candidate, extraction, report = build_candidate_profile_from_upload(
            file.filename,
            content,
            db=db,
        )
        note = (
            f"Grounded candidate profile extracted via {extraction.method}. "
            f"Rejected unsupported claims: {len(report.rejected)}."
        )
        return ParseResumeResponse(candidate=candidate, preferences=None, note=note)

    try:
        return await run_in_threadpool(_process)
    except Exception as exc:  # noqa: BLE001 — map domain errors; unexpected become 500
        if isinstance(
            exc,
            (
                CandidateProfileError,
                LLMConfigurationError,
            ),
        ):
            raise _http_for_candidate_error(exc) from exc
        raise _http_for_candidate_error(exc) from exc


@router.post("/preferences", response_model=TargetPreferences, status_code=status.HTTP_201_CREATED)
def save_preferences(
    preferences: TargetPreferences,
    db: Session = Depends(get_db),
) -> TargetPreferences:
    """Validate preferences and persist them to SQLite."""
    if not preferences.target_roles:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one target role is required",
        )
    record = TargetPreference(
        target_roles=preferences.target_roles,
        preferred_locations=preferences.preferred_locations,
        remote_preference=preferences.remote_preference,
        salary_min=preferences.salary_min,
        work_authorization=preferences.work_authorization,
        sponsorship_required=preferences.sponsorship_required,
        constraints=preferences.constraints,
    )
    db.add(record)
    db.commit()
    return preferences
