"""Explainable Fit & Gap scoring routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.api.dependencies import get_current_user
from backend.api.profile_gate import enforce_grounded_candidate
from backend.db.database import get_db
from backend.db.models import User
from backend.schemas.job_requirements import JobRequirementProfile
from backend.schemas.match_evidence import MatchEvidenceResponse
from backend.schemas.schemas import JobIntelligence, MatchScore
from backend.services.analysis_service import (
    CandidateRequiredError,
    JobNotFoundError,
    RequirementsUnavailableError,
    ScoringError,
    StoredScoreNotFoundError,
    get_stored_match_score,
    load_job,
)
from backend.services.job_intelligence_service import (
    EmptyGroundedIntelligenceError,
    JobIntelligenceNotFoundError,
    PostingEvidenceError,
    StructuredIntelligenceError,
    extract_job_intelligence,
    get_stored_job_intelligence,
)
from backend.services.llm_client import LLMConfigurationError, LLMProviderError
from backend.services.job_requirement_extractor import extract_requirement_profile, load_requirement_profile
from backend.services.scoring_orchestrator import score_job_with_intelligence
from backend.services.verified_fit_service import score_job_verified

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["scoring"])


def _http_for_scoring_error(exc: Exception) -> HTTPException:
    if isinstance(exc, JobNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, (CandidateRequiredError, RequirementsUnavailableError)):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, ScoringError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    logger.error("Unexpected scoring failure category=internal")
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unable to calculate fit score.",
    )


def _http_for_intelligence_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (JobNotFoundError, JobIntelligenceNotFoundError)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, (PostingEvidenceError, EmptyGroundedIntelligenceError)):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, LLMConfigurationError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Job requirement extraction is not configured.",
        )
    if isinstance(exc, (LLMProviderError, StructuredIntelligenceError)):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to extract structured job requirements.",
        )
    logger.error("Unexpected job intelligence failure category=internal")
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unable to save extracted job requirements.",
    )


def _is_intelligence_pipeline_error(exc: Exception) -> bool:
    return isinstance(
        exc,
        (
            PostingEvidenceError,
            EmptyGroundedIntelligenceError,
            LLMConfigurationError,
            LLMProviderError,
            StructuredIntelligenceError,
        ),
    )


@router.get("/jobs/{job_id}/intelligence", response_model=JobIntelligence)
def get_job_intelligence_route(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JobIntelligence:
    """Return stored grounded requirements without invoking a provider."""
    try:
        return get_stored_job_intelligence(db, job_id)
    except Exception as exc:  # noqa: BLE001 — map to sanitized HTTP
        raise _http_for_intelligence_error(exc) from exc


@router.post("/jobs/{job_id}/intelligence", response_model=JobIntelligence)
def extract_job_intelligence_route(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JobIntelligence:
    """Explicitly extract, ground, and persist requirements for one job."""
    try:
        return extract_job_intelligence(db, job_id)
    except Exception as exc:  # noqa: BLE001 — map to sanitized HTTP
        raise _http_for_intelligence_error(exc) from exc


@router.get("/jobs/{job_id}/score", response_model=MatchScore)
def get_stored_score_route(
    job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> MatchScore:
    """Return the latest stored fit score. Never scores, writes, or calls a provider."""
    try:
        return get_stored_match_score(db, job_id, user.id)
    except StoredScoreNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — map to sanitized HTTP
        raise _http_for_scoring_error(exc) from exc


@router.post("/jobs/{job_id}/score", response_model=MatchScore)
def score_job_route(
    job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> MatchScore:
    """Calculate and persist an explainable fit score using the request session."""
    enforce_grounded_candidate(db, user.id)
    try:
        score_job_with_intelligence(db, job_id, user.id)
        job = load_job(db, job_id)
        return score_job_verified(db, job, user.id)
    except Exception as exc:  # noqa: BLE001 — map to sanitized HTTP
        if _is_intelligence_pipeline_error(exc):
            raise _http_for_intelligence_error(exc) from exc
        raise _http_for_scoring_error(exc) from exc


@router.get("/jobs/{job_id}/match-evidence", response_model=MatchEvidenceResponse)
def get_match_evidence_route(
    job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """Read persisted match evidence. Never scores, writes, or calls an LLM."""
    from backend.services.match_evidence_service import get_match_evidence

    try:
        return get_match_evidence(db, job_id, user.id)
    except StoredScoreNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — map to sanitized HTTP
        raise _http_for_scoring_error(exc) from exc


@router.get("/jobs/{job_id}/requirements", response_model=JobRequirementProfile)
def get_requirement_profile_route(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JobRequirementProfile:
    job = load_job(db, job_id)
    profile = load_requirement_profile(db, job)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job requirements have not been extracted.",
        )
    return profile


@router.post("/jobs/{job_id}/requirements", response_model=JobRequirementProfile)
def extract_requirement_profile_route(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JobRequirementProfile:
    job = load_job(db, job_id)
    return extract_requirement_profile(db, job, force=True)
