"""The generic background-loop lifecycle: start/cancel, one bad tick must
not kill the loop (there is no supervisor to restart it), and the stale-
revalidation task's own independent cadence gate.

An isolated in-memory DB is wired in for every test in this file (not just
ones that care about it) — scheduler._tick() now always calls
_revalidate_due(), which does a real SessionLocal() query. Without this,
tests here would hit the actual configured database (see
backend/db/database.py) for a table (scheduler_state) that may not exist
outside this test process.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import backend.services.job_verification_service as job_verification_service
import backend.services.scheduler as scheduler
from backend.db.database import Base
from backend.db.models import SchedulerStateRecord


@pytest.fixture(autouse=True)
def _isolated_scheduler_db(monkeypatch: pytest.MonkeyPatch):
    """Every test in this file gets an isolated, empty, in-memory DB — not
    just for scheduler._revalidate_due/_mark_revalidate_run, but also for
    job_verification_service.revalidate_unseen_candidates, which _tick()
    now calls for real whenever a test doesn't explicitly mock it. Missing
    either patch would let a real (unmocked) tick query the actual
    configured database — with real, possibly hundreds of job rows in it —
    and then make real outbound HTTP requests to each candidate's real
    posting URL. An empty isolated DB makes that structurally impossible
    (zero candidates, zero network calls) rather than relying on every
    current and future test remembering to mock revalidate_unseen_candidates
    itself.
    """
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(scheduler, "SessionLocal", session_factory)
    monkeypatch.setattr(job_verification_service, "SessionLocal", session_factory)
    return session_factory


@pytest.fixture(autouse=True)
def _reset_scheduler_task():
    yield
    scheduler._task = None


async def _wait_for(predicate, timeout: float = 2.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while not predicate():
        if asyncio.get_event_loop().time() > deadline:
            raise AssertionError("condition never became true")
        await asyncio.sleep(0.01)


def test_start_creates_a_running_task(monkeypatch) -> None:
    monkeypatch.setattr(scheduler, "run_due_saved_searches", _make_noop())

    async def scenario():
        scheduler.start_background_scheduler(tick_seconds=100)
        assert scheduler._task is not None
        assert not scheduler._task.done()
        await scheduler.stop_background_scheduler()

    asyncio.run(scenario())


def test_starting_twice_does_not_create_a_second_task(monkeypatch) -> None:
    monkeypatch.setattr(scheduler, "run_due_saved_searches", _make_noop())

    async def scenario():
        scheduler.start_background_scheduler(tick_seconds=100)
        first = scheduler._task
        scheduler.start_background_scheduler(tick_seconds=100)
        assert scheduler._task is first
        await scheduler.stop_background_scheduler()

    asyncio.run(scenario())


def test_stop_cancels_the_task_cleanly(monkeypatch) -> None:
    monkeypatch.setattr(scheduler, "run_due_saved_searches", _make_noop())

    async def scenario():
        scheduler.start_background_scheduler(tick_seconds=100)
        task = scheduler._task
        await scheduler.stop_background_scheduler()
        assert task.done()
        assert scheduler._task is None

    asyncio.run(scenario())


def test_stop_without_start_is_a_safe_noop() -> None:
    async def scenario():
        await scheduler.stop_background_scheduler()

    asyncio.run(scenario())  # must not raise


def test_a_failing_tick_does_not_kill_the_loop(monkeypatch) -> None:
    calls = {"n": 0}

    async def flaky_run_due_saved_searches():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")

    monkeypatch.setattr(scheduler, "run_due_saved_searches", flaky_run_due_saved_searches)

    async def scenario():
        scheduler.start_background_scheduler(tick_seconds=0.01)
        await _wait_for(lambda: calls["n"] >= 3)
        assert not scheduler._task.done()
        await scheduler.stop_background_scheduler()

    asyncio.run(scenario())


def test_a_failing_revalidation_task_does_not_block_saved_searches(monkeypatch) -> None:
    """The two tasks in one tick get independent try/excepts — one failing
    must not suppress or be conflated with the other's own outcome."""
    saved_search_calls = {"n": 0}

    async def counting_run_due_saved_searches():
        saved_search_calls["n"] += 1

    def boom():
        raise RuntimeError("stale revalidation exploded")

    monkeypatch.setattr(scheduler, "run_due_saved_searches", counting_run_due_saved_searches)
    monkeypatch.setattr(scheduler, "_revalidate_due", boom)

    async def scenario():
        scheduler.start_background_scheduler(tick_seconds=0.01)
        await _wait_for(lambda: saved_search_calls["n"] >= 3)
        assert not scheduler._task.done()
        await scheduler.stop_background_scheduler()

    asyncio.run(scenario())


def test_revalidate_due_is_true_with_no_prior_run(_isolated_scheduler_db) -> None:
    assert scheduler._revalidate_due() is True


def test_revalidate_due_is_false_right_after_marking_a_run(_isolated_scheduler_db) -> None:
    scheduler._mark_revalidate_run()
    assert scheduler._revalidate_due() is False


def test_revalidate_due_is_true_once_the_interval_has_elapsed(_isolated_scheduler_db) -> None:
    with _isolated_scheduler_db() as db:
        old = datetime.now(timezone.utc) - timedelta(hours=scheduler.REVALIDATE_INTERVAL_HOURS + 1)
        db.add(SchedulerStateRecord(key=scheduler.REVALIDATE_STATE_KEY, last_run_at=old))
        db.commit()
    assert scheduler._revalidate_due() is True


def test_mark_revalidate_run_updates_an_existing_row(_isolated_scheduler_db) -> None:
    scheduler._mark_revalidate_run()
    first = scheduler._revalidate_due()
    assert first is False
    scheduler._mark_revalidate_run()  # must not raise (UPDATE, not a duplicate-key INSERT)
    assert scheduler._revalidate_due() is False


def test_tick_runs_revalidation_when_due_and_marks_it_run(monkeypatch) -> None:
    monkeypatch.setattr(scheduler, "run_due_saved_searches", _make_noop())
    revalidate_calls = {"n": 0}

    async def counting_revalidate():
        revalidate_calls["n"] += 1
        return 0

    monkeypatch.setattr(scheduler, "revalidate_unseen_candidates", counting_revalidate)

    asyncio.run(scheduler._tick())
    assert revalidate_calls["n"] == 1
    assert scheduler._revalidate_due() is False  # marked run by the tick itself


def test_tick_skips_revalidation_when_not_due(monkeypatch) -> None:
    monkeypatch.setattr(scheduler, "run_due_saved_searches", _make_noop())
    scheduler._mark_revalidate_run()
    revalidate_calls = {"n": 0}

    async def counting_revalidate():
        revalidate_calls["n"] += 1
        return 0

    monkeypatch.setattr(scheduler, "revalidate_unseen_candidates", counting_revalidate)

    asyncio.run(scheduler._tick())
    assert revalidate_calls["n"] == 0


def _make_noop():
    async def _noop():
        return None

    return _noop
