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

from backend.services.saved_search_service import run_due_saved_searches

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 15 * 60

_task: asyncio.Task | None = None


async def _tick() -> None:
    try:
        await run_due_saved_searches()
    except Exception:
        # A bad tick must not kill the loop — there's no supervisor to
        # restart it, so an unhandled exception here would silently stop
        # all future scheduled runs for the rest of the process lifetime.
        logger.exception("scheduler tick failed")


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
