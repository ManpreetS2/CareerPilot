"""Saved Searches: CRUD, the background tick that reruns them, and the
filter predicate deciding whether a freshly-scouted job is a genuine new
match.

The tick reuses the exact discovery pipeline a manual "Find Jobs" click
already uses (scout_jobs) — a saved search is not a separate search
implementation, just an unattended trigger for the existing one.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.core.rate_limit import guard_expensive
from backend.db.database import SessionLocal
from backend.db.models import JobRecord, SavedSearchMatchRecord, SavedSearchRecord
from backend.schemas.saved_search import SavedSearchCreate, SavedSearchUpdate
from backend.schemas.schemas import Job
from backend.services.job_posting_time import (
    cutoff_for_date_posted_window,
    parse_posting_time,
    posting_in_window,
)
from backend.services.job_search_parser import parse_job_search_intent, scout_terms_from_intent
from backend.services.job_service import clean_search_term, scout_jobs
from backend.services.opportunity_type import matches_opportunity_filter
from backend.services.profile_readiness import require_ready_profile

logger = logging.getLogger(__name__)

MAX_SEARCHES_PER_TICK = 5
MIN_CADENCE_HOURS = 3


class SavedSearchError(Exception):
    """Sanitized saved-search error. str(exc) is safe for HTTP details."""


class SavedSearchNotFoundError(SavedSearchError):
    def __init__(self) -> None:
        super().__init__("Saved search not found.")


def _as_utc(value: datetime | None) -> datetime | None:
    """SQLite's DateTime column round-trips as naive even when written with
    an aware datetime.now(timezone.utc) — every value read back needs this
    before arithmetic against a freshly-created aware datetime."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def job_matches_search_filters(
    job: Job,
    *,
    opportunity: str | None,
    employment_type: list[str],
    work_mode: list[str],
    date_posted: str | None,
    date_posted_raw: str | None,
    now: datetime,
) -> bool:
    """Whether a freshly-scouted job satisfies one saved search's own
    filters. Narrowed to opportunity/employment/work-mode/date-posted:
    fields `record_to_job` already puts on the returned `Job` (or, for
    date_posted, the raw JobRecord string this function re-parses) without
    an extra `resolve_job_listing_metadata` call per job. `experience_level`
    is classifiable the same deterministic way, but doing so here would mean
    a second metadata-resolution pass over every scouted job on every tick;
    that cost hasn't been justified yet, so it's deferred. `verified_state`
    and `eligibility` are excluded for a different reason: they depend on
    Fit scoring against the user's profile, which hasn't run on a
    just-scouted job at all.

    Uses the same `job_posting_time` helpers as job_query_service.query_jobs
    so a saved search's "new match" agrees with what Discover's identical
    date_posted filter would show for the same posting.
    """

    if not matches_opportunity_filter(job.opportunity_type or "unknown", opportunity):
        return False
    if employment_type and job.employment_type not in employment_type:
        return False
    if work_mode and job.work_mode not in work_mode:
        return False
    cutoff = cutoff_for_date_posted_window(date_posted, now)
    if cutoff:
        posting = parse_posting_time(date_posted_raw, now=now)
        if posting is None or not posting_in_window(posting, cutoff, now):
            return False
    return True


def _owned_search(db: Session, search_id: int, user_id: int) -> SavedSearchRecord:
    record = (
        db.query(SavedSearchRecord)
        .filter(SavedSearchRecord.id == search_id, SavedSearchRecord.user_id == user_id)
        .first()
    )
    if record is None:
        raise SavedSearchNotFoundError()
    return record


def create_saved_search(db: Session, user_id: int, request: SavedSearchCreate) -> SavedSearchRecord:
    record = SavedSearchRecord(
        user_id=user_id,
        label=request.label.strip(),
        query_text=request.query_text.strip(),
        location=request.location,
        opportunity=request.opportunity,
        employment_type=list(request.employment_type),
        work_mode=list(request.work_mode),
        date_posted=request.date_posted,
        cadence_hours=max(request.cadence_hours, MIN_CADENCE_HOURS),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_saved_searches(db: Session, user_id: int) -> list[tuple[SavedSearchRecord, int]]:
    """Each search paired with its unseen-match count, via one grouped
    count query rather than one query per search."""
    searches = (
        db.query(SavedSearchRecord)
        .filter(SavedSearchRecord.user_id == user_id)
        .order_by(SavedSearchRecord.created_at.desc())
        .all()
    )
    if not searches:
        return []
    search_ids = [search.id for search in searches]
    unseen_counts = dict(
        db.query(SavedSearchMatchRecord.saved_search_id, func.count(SavedSearchMatchRecord.id))
        .filter(
            SavedSearchMatchRecord.saved_search_id.in_(search_ids),
            SavedSearchMatchRecord.seen_at.is_(None),
        )
        .group_by(SavedSearchMatchRecord.saved_search_id)
        .all()
    )
    return [(search, unseen_counts.get(search.id, 0)) for search in searches]


def update_saved_search(
    db: Session, search_id: int, user_id: int, request: SavedSearchUpdate
) -> SavedSearchRecord:
    record = _owned_search(db, search_id, user_id)
    fields = request.model_fields_set
    if "label" in fields and request.label is not None:
        record.label = request.label.strip()
    if "enabled" in fields and request.enabled is not None:
        record.enabled = request.enabled
    if "cadence_hours" in fields and request.cadence_hours is not None:
        record.cadence_hours = max(request.cadence_hours, MIN_CADENCE_HOURS)
    db.commit()
    db.refresh(record)
    return record


def delete_saved_search(db: Session, search_id: int, user_id: int) -> None:
    record = _owned_search(db, search_id, user_id)
    db.query(SavedSearchMatchRecord).filter(
        SavedSearchMatchRecord.saved_search_id == record.id
    ).delete()
    db.delete(record)
    db.commit()


def list_matches(db: Session, search_id: int, user_id: int) -> list[tuple[SavedSearchMatchRecord, JobRecord]]:
    _owned_search(db, search_id, user_id)  # ownership check; sanitized 404 if not this user's
    return (
        db.query(SavedSearchMatchRecord, JobRecord)
        .join(JobRecord, JobRecord.id == SavedSearchMatchRecord.job_id)
        .filter(SavedSearchMatchRecord.saved_search_id == search_id)
        .order_by(SavedSearchMatchRecord.first_seen_at.desc())
        .all()
    )


def mark_matches_seen(db: Session, search_id: int, user_id: int) -> int:
    _owned_search(db, search_id, user_id)
    now = datetime.now(timezone.utc)
    updated = (
        db.query(SavedSearchMatchRecord)
        .filter(
            SavedSearchMatchRecord.saved_search_id == search_id,
            SavedSearchMatchRecord.seen_at.is_(None),
        )
        .update({SavedSearchMatchRecord.seen_at: now}, synchronize_session=False)
    )
    db.commit()
    return updated


def _scout_terms_for_saved_search(search: SavedSearchRecord) -> tuple[list[str], str | None]:
    """Same query-shaping a live "Find Jobs" click applies (backend.api.routes.jobs._run_scout)
    before calling scout_jobs — a saved search stored as free text like
    "remote data analyst intern in Chicago" must be split into role terms +
    location the same way, or its background results silently disagree with
    what typing that same text into Discover would return."""
    query = clean_search_term(search.query_text) if search.query_text else ""
    location = clean_search_term(search.location) if search.location else ""
    if not query:
        return [], location or None
    intent = parse_job_search_intent(query)
    structured = bool(intent.locations or intent.work_modes or intent.industries or intent.opportunity_types)
    if not structured:
        return [query], location or None
    scout_queries, scout_location = scout_terms_from_intent(intent)
    queries = [clean_search_term(term) for term in scout_queries if term] or [query]
    resolved_location = location or (clean_search_term(scout_location) if scout_location else "")
    return queries, resolved_location or None


async def _run_one_saved_search(db: Session, search: SavedSearchRecord) -> None:
    # Same profile-first gate the live route re-checks on every call
    # (backend.api.routes.jobs.trigger_scout) — a saved search created while
    # ready must stop auto-scouting if the owner's profile later becomes
    # not-ready, rather than keep running indefinitely in the background.
    require_ready_profile(db, search.user_id)

    queries, location = _scout_terms_for_saved_search(search)
    with guard_expensive(search.user_id, "scheduled_scout"):
        # scout_jobs is fully synchronous (httpx + a thread pool internally)
        # — running it bare here would block the whole event loop for the
        # entire multi-provider scout, freezing every concurrent live request.
        jobs: list[Job] = await asyncio.to_thread(scout_jobs, queries, location)

    now = datetime.now(timezone.utc)
    existing_job_ids = {
        row[0]
        for row in db.query(SavedSearchMatchRecord.job_id)
        .filter(SavedSearchMatchRecord.saved_search_id == search.id)
        .all()
    }
    job_records = {
        record.public_id: record
        for record in db.query(JobRecord)
        .filter(JobRecord.public_id.in_([job.id for job in jobs if job.id]))
        .all()
    }

    new_match_count = 0
    for job in jobs:
        if not job.id:
            continue
        record = job_records.get(job.id)
        if record is None or record.id in existing_job_ids:
            continue
        if not job_matches_search_filters(
            job,
            opportunity=search.opportunity,
            employment_type=search.employment_type,
            work_mode=search.work_mode,
            date_posted=search.date_posted,
            date_posted_raw=record.date_posted,
            now=now,
        ):
            continue
        db.add(SavedSearchMatchRecord(saved_search_id=search.id, job_id=record.id))
        existing_job_ids.add(record.id)
        new_match_count += 1

    search.last_run_at = now
    db.commit()
    logger.info("saved search run id=%s new_matches=%s", search.id, new_match_count)


async def run_due_saved_searches() -> None:
    """One scheduler tick. Small, per-user catalog — cadence math happens in
    Python over the (short) list of enabled searches rather than in SQL,
    same "hundreds of rows, not millions" philosophy job_query_service.py
    already documents for the jobs table itself."""

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        enabled = db.query(SavedSearchRecord).filter(SavedSearchRecord.enabled.is_(True)).all()
        overdue = [
            search
            for search in enabled
            if _as_utc(search.last_run_at) is None
            or (now - _as_utc(search.last_run_at)) >= timedelta(hours=search.cadence_hours)
        ]
        overdue.sort(key=lambda search: (search.last_run_at is not None, _as_utc(search.last_run_at) or now))
        for search in overdue[:MAX_SEARCHES_PER_TICK]:
            try:
                await _run_one_saved_search(db, search)
            except Exception:
                # One saved search failing (rate-limited, a source outage,
                # a not-ready profile, anything) must not block the rest of
                # this tick's batch — last_run_at is left untouched, so it's
                # retried next tick. The rollback is required, not optional:
                # this session is shared across every search in the loop, and
                # without it a failed search's pending (uncommitted) inserts
                # would sit in the session and get flushed and committed
                # anyway by the NEXT search's successful commit —
                # autocommitting a batch that was supposed to be isolated.
                db.rollback()
                logger.exception("saved search run failed id=%s", search.id)
