"""Job listing and discovery routes."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session, joinedload

from backend.api.dependencies import get_current_user
from backend.api.profile_gate import enforce_profile_ready
from backend.db.database import get_db
from backend.db.models import JobRecord, User
from backend.schemas.schemas import (
    IngestJobUrlRequest,
    Job,
    JobListPage,
    JobVerificationResponse,
    MatchScore,
    ParseSearchRequest,
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
    record_to_job,
    scout_jobs,
)
from backend.services.job_verification_service import verify_all, verify_and_store
from backend.services.job_search_parser import (
    JobSearchIntent,
    parse_job_search_intent,
    scout_terms_from_intent,
)
from backend.services.job_search_llm import enrich_search_intent
from backend.services.job_query_service import query_jobs
from backend.services.saved_job_service import list_saved_jobs, save_job, unsave_job
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
def get_jobs(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[Job]:
    records = (
        db.query(JobRecord)
        .options(joinedload(JobRecord.requirement_profile))
        .order_by(JobRecord.date_scraped.desc())
        .all()
    )
    return [record_to_job(record) for record in records]


@router.get("/jobs/query", response_model=JobListPage)
def query_jobs_route(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    q: str | None = None,
    tab: str = Query("discover"),
    opportunity: str | None = None,
    employment_type: list[str] | None = Query(None),
    experience_level: list[str] | None = Query(None),
    work_mode: list[str] | None = Query(None),
    location: list[str] | None = Query(None),
    industry: list[str] | None = Query(None),
    verified_state: str = "all",
    eligibility: str = "all",
    confidence: str = "all",
    date_posted: str | None = None,
    sort: str = "best_match",
    page: int = 1,
    page_size: int = 40,
) -> JobListPage:
    """Filter the canonical stored catalog. Never replaces persisted jobs."""
    parsed = parse_job_search_intent(q)
    allowed_employment = {
        "internship",
        "new_grad",
        "full_time",
        "part_time",
        "contract",
        "temporary",
        "co_op",
        "fellowship",
    }
    allowed_work = {"remote", "hybrid", "onsite"}
    allowed_experience = {
        "intern",
        "new_grad",
        "entry",
        "junior",
        "mid",
        "senior",
        "staff",
        "principal",
        "lead",
        "manager",
        "director",
    }
    if employment_type:
        parsed.employment_types = [item for item in employment_type if item in allowed_employment]
    if experience_level:
        parsed.experience_levels = [item for item in experience_level if item in allowed_experience]
    if work_mode:
        parsed.work_modes = [item for item in work_mode if item in allowed_work]
    if location:
        parsed.locations = [item[:80] for item in location if item and item.strip()][:8]
    if industry:
        parsed.industries = [item.lower()[:40] for item in industry if item and item.strip()][:8]
    if verified_state in {"all", "verified", "potential"}:
        parsed.verified_state = verified_state  # type: ignore[assignment]
    if eligibility in {"all", "likely_eligible", "eligibility_uncertain", "likely_ineligible"}:
        parsed.eligibility_state = eligibility  # type: ignore[assignment]
    if confidence in {"all", "high", "medium", "low"}:
        parsed.confidence_state = confidence  # type: ignore[assignment]
    if date_posted in {"past_24h", "past_3d", "past_7d", "past_14d", "past_30d"}:
        parsed.date_posted = date_posted  # type: ignore[assignment]
    tab_value = tab if tab in {"discover", "matches", "saved"} else "discover"
    sort_value = sort if sort in {"best_match", "newest", "qualification", "preference"} else "best_match"
    return query_jobs(
        db,
        user.id,
        parsed,
        tab=tab_value,  # type: ignore[arg-type]
        opportunity=opportunity,
        sort=sort_value,  # type: ignore[arg-type]
        page=page,
        page_size=page_size,
    )


@router.post("/jobs/search-intent", response_model=JobSearchIntent)
def parse_search_intent_route(payload: ParseSearchRequest, user: User = Depends(get_current_user)) -> JobSearchIntent:
    deterministic = parse_job_search_intent(payload.query)
    return enrich_search_intent(payload.query, deterministic)


@router.get("/jobs/saved", response_model=list[Job])
def list_saved_jobs_route(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[Job]:
    return list_saved_jobs(db, user.id)


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
    enforce_profile_ready(db, user.id)
    consume_scout_run_stats()
    total_started = time.perf_counter()
    criteria_started = time.perf_counter()
    criteria = derive_scout_criteria(db, user.id)
    # An explicit query is cleaned exactly like a saved one: both end up in
    # the same outbound query string, so both need the same whitespace
    # collapsing and length bound.
    explicit_query = clean_search_term(what) if what else ""
    explicit_location = clean_search_term(where) if where else ""
    if explicit_query:
        intent = parse_job_search_intent(explicit_query)
        structured = bool(
            intent.locations or intent.work_modes or intent.industries or intent.opportunity_types
        )
        if structured:
            scout_queries, scout_location = scout_terms_from_intent(intent)
            queries = [clean_search_term(term) for term in scout_queries if term] or [explicit_query]
            location = (
                explicit_location
                or (clean_search_term(scout_location) if scout_location else "")
                or criteria.location
            )
        else:
            queries = [explicit_query]
            location = explicit_location or criteria.location
    else:
        queries = criteria.queries
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


@router.post("/jobs/{job_id}/save", response_model=Job)
def save_job_route(
    job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Job:
    return save_job(db, user.id, job_id).job


@router.delete("/jobs/{job_id}/save", status_code=status.HTTP_204_NO_CONTENT)
def unsave_job_route(
    job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Response:
    unsave_job(db, user.id, job_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/jobs/{job_id}", response_model=Job)
def get_job_by_id(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Job:
    record = (
        db.query(JobRecord)
        .options(joinedload(JobRecord.requirement_profile))
        .filter(JobRecord.public_id == job_id)
        .first()
    )
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found")
    return record_to_job(record)


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
