"""Job listing and discovery routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.api.dependencies import get_current_user
from backend.db.database import get_db
from backend.db.models import User
from backend.schemas.schemas import (
    IngestJobUrlRequest,
    Job,
    JobVerificationResponse,
    MatchScore,
    ScoutJobsResponse,
)
from backend.services.analysis_service import (
    CandidateRequiredError,
    RequirementsUnavailableError,
    ScoringError,
    list_stored_match_scores,
    score_job,
)
from backend.services.job_scout_service import JobScoutError, ingest_job_url, normalize_job, persist_jobs
from backend.services.job_service import (
    clean_search_term,
    derive_scout_criteria,
    get_job,
    list_jobs,
    scout_jobs,
)
from backend.services.job_verification_service import verify_all, verify_and_store
from backend.services.url_safety import UnsafeURLError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["jobs"])


def _auto_score_scouted_jobs(db: Session, jobs: list[Job], user_id: int) -> int:
    """Persist a deterministic fit score for each scouted job.

    Uses `score_job` only — never `score_job_with_intelligence` — so Find Jobs
    does not call Gemini/Ollama/Claude/OpenAI. One unscoreable listing is
    skipped; it must not fail the scout response.
    """
    scored = 0
    for job in jobs:
        if not job.id:
            logger.info("Scout auto-score skipped job without id")
            continue
        try:
            score_job(db, job.id, user_id)
            scored += 1
        except (CandidateRequiredError, RequirementsUnavailableError, ScoringError) as exc:
            logger.info("Scout auto-score skipped job_id=%s reason=%s", job.id, type(exc).__name__)
        except Exception as exc:  # noqa: BLE001 — one bad listing must not fail Find Jobs
            logger.warning("Scout auto-score failed job_id=%s error=%s", job.id, type(exc).__name__)
    return scored


@router.get("/jobs", response_model=list[Job])
def get_jobs(user: User = Depends(get_current_user)) -> list[Job]:
    return list_jobs()


@router.get("/jobs/scores", response_model=list[MatchScore])
def list_job_scores(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[MatchScore]:
    """Return stored fit scores for every job that already has one. Never scores."""
    return list_stored_match_scores(db, user.id)


@router.post("/scout-jobs", response_model=ScoutJobsResponse, status_code=status.HTTP_202_ACCEPTED)
def trigger_scout(
    what: str | None = None,
    where: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScoutJobsResponse:
    """Search every configured source, normalize/dedupe/persist, return stored jobs.

    With no `what`, the search comes from the user's saved target roles and
    preferred location. `what` previously defaulted to a fixed string, which
    made "the user typed this exact query" indistinguishable from "the user
    typed nothing" — so preferences could never take over, and every run
    searched the same hardcoded role regardless of what the user wanted.

    An explicit `what`/`where` still wins outright: this reads preferences to
    fill in a blank, never to override a deliberate search.
    """
    criteria = derive_scout_criteria(db, user.id)
    # An explicit query is cleaned exactly like a saved one: both end up in
    # the same outbound query string, so both need the same whitespace
    # collapsing and length bound.
    explicit_query = clean_search_term(what) if what else ""
    explicit_location = clean_search_term(where) if where else ""
    queries = [explicit_query] if explicit_query else criteria.queries
    location = explicit_location or criteria.location

    jobs = scout_jobs(queries=queries, location=location)
    auto_scored = _auto_score_scouted_jobs(db, jobs, user.id)
    searched = ", ".join(queries)
    where_note = f" in {location}" if location else ""
    return ScoutJobsResponse(
        jobs=jobs,
        note=(
            f"Scouted and stored {len(jobs)} job(s) from live sources for "
            f"{searched}{where_note}. Auto-scored {auto_scored}."
        ),
    )


@router.post("/jobs/ingest-url", response_model=Job, status_code=status.HTTP_201_CREATED)
def ingest_job_url_route(payload: IngestJobUrlRequest, user: User = Depends(get_current_user)) -> Job:
    """Manually add a single job URL — fetches a best-effort title/description
    and stores it with source="manual" for later review/editing."""
    url = payload.url.strip()
    if not url:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="url is required")

    try:
        raw = ingest_job_url(url)
    except UnsafeURLError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="URL is malformed.",
        ) from exc
    except JobScoutError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    job = normalize_job(raw, "manual")
    stored = persist_jobs([job])
    return stored[0]


@router.get("/jobs/{job_id}", response_model=Job)
def get_job_by_id(job_id: str, user: User = Depends(get_current_user)) -> Job:
    return get_job(job_id)


@router.post("/jobs/verify", response_model=JobVerificationResponse)
def verify_jobs_route(
    status_filter: str | None = "discovered", user: User = Depends(get_current_user)
) -> JobVerificationResponse:
    """Run "still open" + suspicious-posting checks. Defaults to only newly
    discovered jobs; pass status_filter=none (or any falsy value via empty
    string) to re-verify every job in the DB."""
    target = None if not status_filter or status_filter.lower() == "none" else status_filter
    jobs = verify_all(status_filter=target)
    return JobVerificationResponse(
        jobs=jobs,
        verified=sum(1 for job in jobs if job.status == "verified"),
        flagged=sum(1 for job in jobs if job.status == "flagged"),
        stale=sum(1 for job in jobs if job.status == "stale"),
    )


@router.post("/jobs/{job_id}/verify", response_model=Job)
def verify_job_route(job_id: str, user: User = Depends(get_current_user)) -> Job:
    return verify_and_store(job_id)
