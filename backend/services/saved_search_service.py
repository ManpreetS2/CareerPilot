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
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.core.rate_limit import guard_expensive
from backend.db.database import SessionLocal
from backend.db.models import JobRecord, SavedSearchMatchRecord, SavedSearchRecord
from backend.schemas.saved_search import SavedSearchCreate, SavedSearchUpdate
from backend.schemas.schemas import Job
from backend.services.job_posting_time import DATE_POSTED_WINDOWS
from backend.services.job_service import scout_jobs
from backend.services.opportunity_type import matches_opportunity_filter

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
    today: date,
) -> bool:
    """Whether a freshly-scouted job satisfies one saved search's own
    filters. Narrowed to fields resolve_job_listing_metadata can classify
    without an LLM call (opportunity/employment/work-mode heuristics, plus
    the source-provided posting date) — that's all a job honestly has
    moments after being scouted, before any Job Intelligence extraction or
    Fit scoring has run on it."""

    if not matches_opportunity_filter(job.opportunity_type or "unknown", opportunity):
        return False
    if employment_type and job.employment_type not in employment_type:
        return False
    if work_mode and job.work_mode not in work_mode:
        return False
    if date_posted:
        window = DATE_POSTED_WINDOWS.get(date_posted)
        if window and (job.date_posted is None or (today - job.date_posted) > window):
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
    """Each search paired with its unseen-match count."""
    searches = (
        db.query(SavedSearchRecord)
        .filter(SavedSearchRecord.user_id == user_id)
        .order_by(SavedSearchRecord.created_at.desc())
        .all()
    )
    result: list[tuple[SavedSearchRecord, int]] = []
    for search in searches:
        unseen = (
            db.query(SavedSearchMatchRecord)
            .filter(
                SavedSearchMatchRecord.saved_search_id == search.id,
                SavedSearchMatchRecord.seen_at.is_(None),
            )
            .count()
        )
        result.append((search, unseen))
    return result


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


async def _run_one_saved_search(db: Session, search: SavedSearchRecord) -> None:
    with guard_expensive(search.user_id, "scheduled_scout"):
        # scout_jobs is fully synchronous (httpx + a thread pool internally)
        # — running it bare here would block the whole event loop for the
        # entire multi-provider scout, freezing every concurrent live request.
        jobs: list[Job] = await asyncio.to_thread(scout_jobs, [search.query_text], search.location)

    today = datetime.now(timezone.utc).date()
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
        if not job_matches_search_filters(
            job,
            opportunity=search.opportunity,
            employment_type=search.employment_type,
            work_mode=search.work_mode,
            date_posted=search.date_posted,
            today=today,
        ):
            continue
        record = job_records.get(job.id)
        if record is None or record.id in existing_job_ids:
            continue
        db.add(SavedSearchMatchRecord(saved_search_id=search.id, job_id=record.id))
        existing_job_ids.add(record.id)
        new_match_count += 1

    search.last_run_at = datetime.now(timezone.utc)
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
                # anything) must not block the rest of this tick's batch —
                # last_run_at is left untouched, so it's retried next tick.
                logger.exception("saved search run failed id=%s", search.id)
