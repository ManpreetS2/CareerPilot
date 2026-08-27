"""Candidate API routes — real parse-resume pipeline + preferences."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from backend.api.dependencies import get_current_user
from backend.db.database import get_db
from backend.db.models import Candidate, TargetPreference, User
from backend.schemas.schemas import CurrentProfile, ParseResumeResponse, TargetPreferences
from backend.services.application_materials_agent import (
    candidate_record_to_profile,
    preference_record_to_schema,
)
from backend.services.candidate_profile_agent import (
    ANNUAL_SALARY_MAX,
    ANNUAL_SALARY_MIN,
    MAX_UPLOAD_BYTES,
    CandidateProfileError,
    InvalidResumeError,
    OCRUnavailableError,
    OversizedResumeError,
    ProfileExtractionError,
    ProfileGroundingError,
    ResumeExtractionError,
    build_candidate_profile_from_upload,
)
from backend.services.llm_client import LLMConfigurationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["candidate"])


@router.get("/profile", response_model=CurrentProfile)
def get_current_profile(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CurrentProfile:
    """Read-only current candidate and latest preferences. No provider call, no write."""

    candidate = db.query(Candidate).filter(Candidate.user_id == user.id).first()
    preference = (
        db.query(TargetPreference)
        .filter(TargetPreference.user_id == user.id)
        .order_by(TargetPreference.id.desc())
        .first()
    )
    return CurrentProfile(
        candidate=candidate_record_to_profile(candidate) if candidate is not None else None,
        preferences=preference_record_to_schema(preference) if preference is not None else None,
    )


def _http_for_candidate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, OversizedResumeError):
        return HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc))
    if isinstance(exc, InvalidResumeError):
        detail = str(exc)
        lowered = detail.lower()
        if "could not be read" in lowered or "no pages" in lowered:
            detail = "Resume could not be read."
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    if isinstance(exc, OCRUnavailableError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if isinstance(exc, ProfileGroundingError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if isinstance(exc, LLMConfigurationError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service temporarily unavailable. Please try again.",
        )
    if isinstance(exc, ProfileExtractionError):
        text = (str(exc) or "").lower()
        if "timed out" in text:
            return HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Resume analysis timed out. Please try again.",
            )
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service temporarily unavailable. Please try again.",
        )
    if isinstance(exc, ResumeExtractionError):
        text = (str(exc) or "").lower()
        if "too little" in text or "readable" in text:
            detail = "Resume contained too little readable text."
        else:
            detail = "Resume could not be read."
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)
    if isinstance(exc, CandidateProfileError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    logger.error("Unexpected candidate profile failure type=%s", type(exc).__name__)
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unable to process resume.",
    )


@router.post("/parse-resume", response_model=ParseResumeResponse)
async def parse_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ParseResumeResponse:
    """Parse an uploaded PDF into a grounded CandidateProfile and persist it."""
    # Read at most MAX+1 bytes so oversized uploads fail without buffering unbounded content.
    filename = file.filename
    content_type = file.content_type
    try:
        content = await file.read(MAX_UPLOAD_BYTES + 1)
    finally:
        await file.close()

    def _process() -> ParseResumeResponse:
        candidate, extraction, report = build_candidate_profile_from_upload(
            filename,
            content,
            db=db,
            user_id=user.id,
            content_type=content_type,
        )
        note = (
            f"Grounded candidate profile extracted via {extraction.method}. "
            f"Rejected unsupported claims: {report.total_rejected}."
        )
        return ParseResumeResponse(candidate=candidate, preferences=None, note=note)

    try:
        return await run_in_threadpool(_process)
    except Exception as exc:  # noqa: BLE001 — map domain errors; unexpected become 500
        raise _http_for_candidate_error(exc) from exc


@router.post("/preferences", response_model=TargetPreferences, status_code=status.HTTP_201_CREATED)
def save_preferences(
    preferences: TargetPreferences,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TargetPreferences:
    """Validate preferences and persist them to SQLite."""
    if not preferences.target_roles:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one target role is required",
        )
    if preferences.salary_min is not None and not (
        ANNUAL_SALARY_MIN <= preferences.salary_min <= ANNUAL_SALARY_MAX
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Minimum base salary must be an annual USD amount between 10000 and 1000000.",
        )

    candidate = db.query(Candidate).filter(Candidate.user_id == user.id).first()
    record = TargetPreference(
        user_id=user.id,
        candidate_id=candidate.id if candidate else None,
        target_roles=preferences.target_roles,
        preferred_locations=preferences.preferred_locations,
        remote_preference=preferences.remote_preference,
        salary_min=preferences.salary_min,
        work_authorization=preferences.work_authorization,
        sponsorship_required=preferences.sponsorship_required,
        constraints=preferences.constraints,
        legal_name=preferences.legal_name,
        linkedin_url=preferences.linkedin_url,
        github_url=preferences.github_url,
        portfolio_url=preferences.portfolio_url,
        earliest_start_date=preferences.earliest_start_date,
        currently_enrolled_in_program=preferences.currently_enrolled_in_program,
        expected_graduation=preferences.expected_graduation,
        degree_pursuing=preferences.degree_pursuing,
        gender=preferences.gender,
        race_ethnicity=preferences.race_ethnicity,
        veteran_status=preferences.veteran_status,
        disability_status=preferences.disability_status,
    )
    try:
        db.add(record)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return preferences
