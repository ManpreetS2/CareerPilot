"""Interview-prep routes. Generation is explicit; GET is read-only."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.api.dependencies import get_current_user
from backend.db.database import get_db
from backend.db.models import User
from backend.schemas.schemas import InterviewAnswerFeedback, InterviewAnswerRequest, InterviewPrep
from backend.services.interview_service import (
    InterviewIntelligenceMissingError,
    InterviewJobNotFoundError,
    InterviewPrepError,
    generate_and_store_interview_prep,
    get_interview_answer_feedback,
    get_interview_prep,
)
from backend.services.llm_client import LLMConfigurationError, LLMEmptyResponseError, LLMProviderError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["interview"])


def _http_for_interview_error(exc: Exception) -> HTTPException:
    if isinstance(exc, InterviewJobNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, InterviewIntelligenceMissingError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, LLMConfigurationError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview answer feedback is not configured.",
        )
    if isinstance(exc, (LLMProviderError, LLMEmptyResponseError)):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The language model request failed.",
        )
    if isinstance(exc, InterviewPrepError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    logger.error("Unexpected interview-prep failure category=internal")
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unable to prepare interview materials.",
    )


@router.get("/jobs/{job_id}/interview-prep", response_model=InterviewPrep)
def read_interview_prep(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InterviewPrep:
    """Return the stored interview-prep record without generating a new one."""
    try:
        prep = get_interview_prep(db, job_id, user.id)
    except Exception as exc:  # noqa: BLE001 — map to sanitized HTTP
        raise _http_for_interview_error(exc) from exc
    if prep is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview prep has not been generated.",
        )
    return prep


@router.post("/jobs/{job_id}/prepare-interview", response_model=InterviewPrep)
def prepare_interview(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InterviewPrep:
    """Explicit deterministic interview-prep generation. Does not call a provider."""
    try:
        return generate_and_store_interview_prep(db, job_id, user.id)
    except Exception as exc:  # noqa: BLE001 — map to sanitized HTTP
        raise _http_for_interview_error(exc) from exc


@router.post("/jobs/{job_id}/interview-prep/feedback", response_model=InterviewAnswerFeedback)
def answer_interview_question(
    job_id: str,
    payload: InterviewAnswerRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InterviewAnswerFeedback:
    """Explicit mock-interview practice round. Calls a provider; not persisted."""
    generate_fn = getattr(request.app.state, "interview_answer_generator", None)
    try:
        return get_interview_answer_feedback(
            db, job_id, user.id, payload.question, payload.answer, generate_fn=generate_fn
        )
    except Exception as exc:  # noqa: BLE001 — map to sanitized HTTP
        raise _http_for_interview_error(exc) from exc
