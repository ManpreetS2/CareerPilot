"""The generic background-loop lifecycle: start/cancel, and one bad tick
must not kill the loop (there is no supervisor to restart it)."""

from __future__ import annotations

import asyncio

import pytest

import backend.services.scheduler as scheduler


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


def _make_noop():
    async def _noop():
        return None

    return _noop
