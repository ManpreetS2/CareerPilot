"""Bounded concurrent source fetching: isolation, wall-clock overlap, privacy logs."""

from __future__ import annotations

import logging
import time

import pytest

from backend.services import job_scout_service
from backend.services.job_scout_service import JobScoutError


@pytest.fixture
def counted_sources(monkeypatch: pytest.MonkeyPatch):
    calls: dict[str, list] = {
        name: []
        for name in ("remoteok", "greenhouse", "lever", "adzuna", "remotive", "jobicy", "himalayas")
    }

    def _record(name, returns=None):
        def _fake(*args, **kwargs):
            calls[name].append((args, kwargs))
            return returns or []

        return _fake

    for name in ("remoteok", "greenhouse", "lever", "remotive", "jobicy", "himalayas"):
        monkeypatch.setattr(job_scout_service, f"scout_{name}", _record(name))
    monkeypatch.setattr(job_scout_service, "scout_adzuna", _record("adzuna"))
    monkeypatch.setattr(job_scout_service, "persist_jobs", lambda jobs: list(jobs))
    monkeypatch.setattr(
        "backend.services.job_verification_service.mark_stale_if_unseen", lambda *a, **k: 0
    )
    return calls


def test_two_slow_sources_overlap_instead_of_adding(counted_sources, monkeypatch) -> None:
    def _slow(*_args, **_kwargs):
        time.sleep(0.35)
        return []

    monkeypatch.setattr(job_scout_service, "scout_remoteok", _slow)
    monkeypatch.setattr(job_scout_service, "scout_greenhouse", _slow)
    started = time.perf_counter()
    result = job_scout_service.run_scout(["Cloud Engineer"])
    elapsed = time.perf_counter() - started
    assert result == []
    assert elapsed < 0.6


def test_failing_slow_source_does_not_drop_a_fast_source(counted_sources, monkeypatch) -> None:
    def _slow_fail(*_args, **_kwargs):
        time.sleep(0.2)
        raise JobScoutError("timeout")

    monkeypatch.setattr(job_scout_service, "scout_greenhouse", _slow_fail)
    job_scout_service.run_scout(["Cloud Engineer"])
    assert len(counted_sources["remoteok"]) == 1
    assert len(counted_sources["jobicy"]) == 1
    assert len(counted_sources["himalayas"]) == 1


def test_concurrent_fetch_keeps_first_wins_dedupe_order(counted_sources, monkeypatch) -> None:
    url = "https://example.com/jobs/same-role"

    def _slow_remoteok(*_args, **_kwargs):
        time.sleep(0.12)
        return [
            {
                "position": "Backend Engineer",
                "company": "Acme",
                "url": url,
                "description": "From RemoteOK",
            }
        ]

    def _fast_jobicy(*_args, **_kwargs):
        return [
            {
                "jobTitle": "Backend Engineer",
                "companyName": "Acme",
                "url": url,
                "jobDescription": "From Jobicy",
            }
        ]

    monkeypatch.setattr(job_scout_service, "scout_remoteok", _slow_remoteok)
    monkeypatch.setattr(job_scout_service, "scout_jobicy", _fast_jobicy)
    result = job_scout_service.run_scout(["Cloud Engineer"])
    matching = [job for job in result if job.url == url]
    assert len(matching) == 1
    assert matching[0].source == "remoteok"


def test_scout_logs_are_privacy_safe(counted_sources, caplog) -> None:
    secret_role = "SecretRoleXYZ"
    with caplog.at_level(logging.INFO):
        job_scout_service.run_scout([secret_role], location="SecretCity")
    blob = caplog.text
    assert secret_role not in blob
    assert "SecretCity" not in blob
    assert "job_scout stage=source" in blob
    assert "job_scout stage=dedupe" in blob
