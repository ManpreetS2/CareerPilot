"""Job listing and discovery routes."""

from __future__ import annotations

import logging
import time

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
    list_stored_match_scores,
    score_jobs_batch,
)
from backend.services.verified_fit_service import verify_top_ranked_jobs
from backend.services.job_scout_service import (
    JobScoutError,
    consume_scout_run_stats,
    ingest_job_url,
    normalize_job,
    persist_jobs,
)
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

_SCOUT_LOG_KEYS = frozenset(
    {
        "stage",
        "source",
        "duration_ms",
        "count",
        "scored",
        "skipped",
        "jobs",
        "query_count",
        "sources_ok",
        "sources_failed",
    }
)


def _log_job_scout(stage: str, **fields: object) -> None:
    parts = [f"job_scout stage={stage}"]
    for key, value in fields.items():
        if key not in _SCOUT_LOG_KEYS or value is None:
            continue
        parts.append(f"{key}={value}")
    logger.info(" ".join(parts))


def _auto_score_scouted_jobs(db: Session, jobs: list[Job], user_id: int) -> tuple[int, int]:
    """Persist a deterministic fit score for each scouted job.

    Uses `score_jobs_batch` only — never `score_job_with_intelligence` — so Find Jobs
    does not call Gemini/Ollama/Claude/OpenAI. One unscoreable listing is
    skipped; it must not fail the scout response.
    """
    started = time.perf_counter()
    missing_ids = sum(1 for job in jobs if not job.id)
    ids = [job.id for job in jobs if job.id]
    try:
        scored, skipped = score_jobs_batch(db, ids, user_id)
    except CandidateRequiredError:
        logger.info("Scout auto-score skipped all jobs reason=CandidateRequiredError")
        scored, skipped = 0, len(ids)
    skipped += missing_ids
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    avg_ms = int(elapsed_ms / scored) if scored else 0
    logger.info(
        "Scout auto-score done scored=%s skipped=%s duration_ms=%s avg_ms=%s",
        scored,
        skipped,
        elapsed_ms,
        avg_ms,
    )
    return scored, skipped


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
    consume_scout_run_stats()
    total_started = time.perf_counter()
    criteria_started = time.perf_counter()
    criteria = derive_scout_criteria(db, user.id)
    # An explicit query is cleaned exactly like a saved one: both end up in
    # the same outbound query string, so both need the same whitespace
    # collapsing and length bound.
    explicit_query = clean_search_term(what) if what else ""
    explicit_location = clean_search_term(where) if where else ""
    queries = [explicit_query] if explicit_query else criteria.queries
    location = explicit_location or criteria.location
    _log_job_scout(
        "criteria",
        duration_ms=int((time.perf_counter() - criteria_started) * 1000),
        query_count=len(queries),
    )

    jobs = scout_jobs(queries=queries, location=location)
    stats = consume_scout_run_stats()
    score_started = time.perf_counter()
    auto_scored, auto_skipped = _auto_score_scouted_jobs(db, jobs, user.id)
    stored_scores = list_stored_match_scores(db, user.id)
    verify_top_ranked_jobs(db, user.id, [job.id for job in jobs if job.id], stored_scores)
    _log_job_scout(
        "score",
        duration_ms=int((time.perf_counter() - score_started) * 1000),
        scored=auto_scored,
        skipped=auto_skipped,
    )
    sources_ok = len(stats.sources_ok) if stats is not None else 0
    sources_failed = len(stats.sources_failed) if stats is not None else 0
    if stats is not None and jobs and sources_failed:
        note = (
            f"Scouted and stored {len(jobs)} job(s) from live sources. "
            f"Auto-scored {auto_scored}. Some sources were unavailable, but we "
            "found opportunities from the remaining sources."
        )
    else:
        note = (
            f"Scouted and stored {len(jobs)} job(s) from live sources. "
            f"Auto-scored {auto_scored}."
        )
    _log_job_scout(
        "total",
        duration_ms=int((time.perf_counter() - total_started) * 1000),
        jobs=len(jobs),
        sources_ok=sources_ok,
        sources_failed=sources_failed,
    )
    return ScoutJobsResponse(
        jobs=jobs,
        note=note,
        jobs_found=len(jobs),
        matched_count=auto_scored,
        sources_searched=sources_ok,
        sources_unavailable=sources_failed,
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
