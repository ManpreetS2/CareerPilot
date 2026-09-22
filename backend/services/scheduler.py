"""Minimal in-process background-task loop.

Not a scheduling library — the actual need (periodically check what's due)
doesn't call for one, and none is a dependency of this project. A single
asyncio task started from FastAPI's lifespan, cancelled on shutdown. If a
second scheduled job type shows up later, it gets added to the same tick
rather than spawning a second loop.

Deliberately single-process: confirmed via backend/core/rate_limit.py's own
docstring that this app runs as one uvicorn worker today. If that changes,
a DB-level lease would be needed so two workers don't both run the same
tick — not solved here.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from backend.db.database import SessionLocal
from backend.db.models import SchedulerStateRecord
from backend.services.job_verification_service import revalidate_unseen_candidates
from backend.services.saved_search_service import run_due_saved_searches

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 15 * 60

# Stale revalidation makes real network calls per candidate job — no need to
# check anywhere near as often as the saved-search tick. Gated independently
# via SchedulerStateRecord rather than given its own loop, per this module's
# "second job type gets added to the same tick" design.
REVALIDATE_STATE_KEY = "stale_revalidation"
REVALIDATE_INTERVAL_HOURS = 24

_task: asyncio.Task | None = None


def _revalidate_due() -> bool:
    with SessionLocal() as db:
        state = db.get(SchedulerStateRecord, REVALIDATE_STATE_KEY)
        if state is None:
            return True
        last_run_at = state.last_run_at
        if last_run_at.tzinfo is None:
            # SQLite's DateTime column round-trips as naive even when written
            # with an aware datetime.now(timezone.utc) — see the identical
            # note on saved_search_service._as_utc.
            last_run_at = last_run_at.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - last_run_at) >= timedelta(hours=REVALIDATE_INTERVAL_HOURS)


def _mark_revalidate_run() -> None:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        state = db.get(SchedulerStateRecord, REVALIDATE_STATE_KEY)
        if state is None:
            db.add(SchedulerStateRecord(key=REVALIDATE_STATE_KEY, last_run_at=now))
        else:
            state.last_run_at = now
        db.commit()


async def _tick() -> None:
    try:
        await run_due_saved_searches()
    except Exception:
        # A bad tick must not kill the loop — there's no supervisor to
        # restart it, so an unhandled exception here would silently stop
        # all future scheduled runs for the rest of the process lifetime.
        # Each task gets its own try/except: one task failing must not
        # suppress or be conflated with the other's own success/failure.
        logger.exception("scheduler tick failed: saved searches")

    try:
        if _revalidate_due():
            await revalidate_unseen_candidates()
            _mark_revalidate_run()
    except Exception:
        logger.exception("scheduler tick failed: stale revalidation")


async def _loop(tick_seconds: int) -> None:
    while True:
        await _tick()
        await asyncio.sleep(tick_seconds)


def start_background_scheduler(tick_seconds: int = POLL_INTERVAL_SECONDS) -> None:
    global _task
    if _task is not None:
        return
    _task = asyncio.create_task(_loop(tick_seconds))


async def stop_background_scheduler() -> None:
    global _task
    if _task is None:
        return
    _task.cancel()
    await asyncio.gather(_task, return_exceptions=True)
    _task = None
