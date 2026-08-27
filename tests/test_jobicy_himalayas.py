"""Jobicy and Himalayas discovery: normalization, search params, host
allowlists, failure isolation, and cross-source dedupe. No live network.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import httpx
import pytest
from sqlalchemy.orm import sessionmaker

from backend.db.models import JobRecord
from backend.services import job_scout_service
from backend.services.job_scout_service import (
    HIMALAYAS_API_HOSTS,
    HIMALAYAS_SEARCH_URL,
    JOBICY_API_HOSTS,
    JOBICY_SEARCH_URL,
    JobScoutError,
    deduplicate_jobs,
    normalize_job,
    persist_jobs,
    scout_himalayas,
    scout_jobicy,
)

SECRET_BODY = '{"internal":"sk-secret-token","host":"10.0.0.5"}'


def _json_response(url: str, payload: object, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        content=json.dumps(payload).encode(),
        request=httpx.Request("GET", url),
    )


@pytest.fixture
def mock_fetch(monkeypatch: pytest.MonkeyPatch):
    captured: dict = {"calls": [], "kwargs": [], "by_url": {}}

    def fake_fetch(url, **kwargs):
        captured["calls"].append(url)
        captured["kwargs"].append(kwargs)
        for prefix, handler in captured["by_url"].items():
            if url.startswith(prefix):
                return handler(url, **kwargs)
        raise AssertionError(f"no handler configured for {url}")

    monkeypatch.setattr(job_scout_service, "fetch_url_safely", fake_fetch)
    return captured


def _jobicy_listing(**overrides) -> dict:
    listing = {
        "id": 77131,
        "url": "https://jobicy.com/jobs/77131-senior-backend-engineer",
        "jobTitle": "Senior Backend Engineer",
        "companyName": "Northwind",
        "jobGeo": "Anywhere",
        "jobExcerpt": "Build APIs.",
        "jobDescription": "<p>Build backend services in Python.</p>",
        "pubDate": "2026-08-21T05:54:39",
        "salaryMin": 80000,
        "salaryMax": 120000,
        "salaryCurrency": "USD",
        "salaryPeriod": "yearly",
    }
    listing.update(overrides)
    return listing


def _himalayas_listing(**overrides) -> dict:
    listing = {
        "title": "Senior Software Engineer",
        "companyName": "Stripe",
        "companySlug": "stripe",
        "guid": "stripe-senior-software-engineer-abc123",
        "applicationLink": "https://stripe.com/careers/senior-engineer",
        "excerpt": "We are looking for a Senior Software Engineer...",
        "description": "<p>We are looking for a Senior Software Engineer to join our remote team.</p>",
        "pubDate": int(datetime(2026, 8, 21, tzinfo=timezone.utc).timestamp() * 1000),
        "minSalary": 120000,
        "maxSalary": 180000,
        "currency": "USD",
        "salaryPeriod": "annual",
        "locationRestrictions": [],
    }
    listing.update(overrides)
    return listing


def test_normalize_jobicy_job_maps_fields() -> None:
    job = normalize_job(_jobicy_listing(), "jobicy")
    assert job.title == "Senior Backend Engineer"
    assert job.company == "Northwind"
    assert job.location == "Anywhere"
    assert job.salary == "$80,000–$120,000"
    assert job.url == "https://jobicy.com/jobs/77131-senior-backend-engineer"
    assert job.description == "Build backend services in Python."
    assert job.source == "jobicy"
    assert job.date_posted == date(2026, 8, 21)


def test_normalize_jobicy_job_defaults_location_and_excerpt() -> None:
    job = normalize_job(
        _jobicy_listing(jobGeo="", jobDescription="", jobExcerpt="<p>Short blurb.</p>", salaryMin=None, salaryMax=None),
        "jobicy",
    )
    assert job.location == "Remote"
    assert job.description == "Short blurb."
    assert job.salary is None


def test_normalize_himalayas_job_maps_fields() -> None:
    job = normalize_job(_himalayas_listing(), "himalayas")
    assert job.title == "Senior Software Engineer"
    assert job.company == "Stripe"
    assert job.location == "Remote"
    assert job.salary == "$120,000–$180,000"
    assert job.url == "https://stripe.com/careers/senior-engineer"
    assert "Senior Software Engineer" in job.description
    assert job.source == "himalayas"
    assert job.date_posted == date(2026, 8, 21)


def test_normalize_himalayas_job_joins_location_restrictions() -> None:
    job = normalize_job(
        _himalayas_listing(
            locationRestrictions=[
                {"alpha2": "US", "name": "United States", "slug": "united-states"},
                {"alpha2": "CA", "name": "Canada", "slug": "canada"},
            ]
        ),
        "himalayas",
    )
    assert job.location == "United States, Canada"


def test_scout_jobicy_sends_tag_and_restricts_hosts(mock_fetch) -> None:
    mock_fetch["by_url"][JOBICY_SEARCH_URL] = lambda url, **_: _json_response(
        url, {"jobs": [_jobicy_listing()]}
    )
    listings = scout_jobicy("software engineer")
    assert [item["id"] for item in listings] == [77131]
    assert mock_fetch["calls"][0].startswith(JOBICY_SEARCH_URL)
    assert "tag=software" in mock_fetch["calls"][0]
    assert mock_fetch["kwargs"][0]["allowed_hosts"] == JOBICY_API_HOSTS


def test_scout_jobicy_omits_short_tag_and_filters_locally(mock_fetch) -> None:
    mock_fetch["by_url"][JOBICY_SEARCH_URL] = lambda url, **_: _json_response(
        url,
        {
            "jobs": [
                _jobicy_listing(id=1, jobTitle="AI Engineer"),
                _jobicy_listing(id=2, jobTitle="Chef"),
            ]
        },
    )
    listings = scout_jobicy("AI")
    assert "tag=" not in mock_fetch["calls"][0]
    assert [item["id"] for item in listings] == [1]


def test_scout_jobicy_error_message_is_sanitized(mock_fetch) -> None:
    mock_fetch["by_url"][JOBICY_SEARCH_URL] = lambda url, **_: _json_response(
        url, {"error": SECRET_BODY}, status_code=500
    )
    with pytest.raises(JobScoutError) as exc:
        scout_jobicy("engineer")
    assert "sk-secret" not in str(exc.value)


def test_scout_himalayas_sends_query_and_restricts_hosts(mock_fetch) -> None:
    mock_fetch["by_url"][HIMALAYAS_SEARCH_URL] = lambda url, **_: _json_response(
        url, {"jobs": [_himalayas_listing()]}
    )
    listings = scout_himalayas("software engineer")
    assert listings[0]["guid"] == "stripe-senior-software-engineer-abc123"
    assert mock_fetch["calls"][0].startswith(HIMALAYAS_SEARCH_URL)
    assert "q=software" in mock_fetch["calls"][0]
    assert mock_fetch["kwargs"][0]["allowed_hosts"] == HIMALAYAS_API_HOSTS


def test_scout_himalayas_error_message_is_sanitized(mock_fetch) -> None:
    mock_fetch["by_url"][HIMALAYAS_SEARCH_URL] = lambda url, **_: _json_response(
        url, {"ok": False, "errors": SECRET_BODY}, status_code=500
    )
    with pytest.raises(JobScoutError) as exc:
        scout_himalayas("engineer")
    assert "sk-secret" not in str(exc.value)


def test_jobicy_and_himalayas_same_url_collapse_to_one_row(isolated_engine, monkeypatch) -> None:
    SessionLocal = sessionmaker(bind=isolated_engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(job_scout_service, "SessionLocal", SessionLocal)
    shared_url = "https://jobs.example.com/senior-backend-engineer"
    persist_jobs(
        [
            normalize_job(_jobicy_listing(url=shared_url), "jobicy"),
            normalize_job(_himalayas_listing(applicationLink=shared_url), "himalayas"),
        ]
    )
    with SessionLocal() as db:
        rows = db.query(JobRecord).all()
        assert len(rows) == 1
        assert rows[0].url == shared_url


def test_deduplicate_jobs_collapses_jobicy_and_himalayas_same_url() -> None:
    shared_url = "https://jobs.example.com/senior-backend-engineer"
    jobs = [
        normalize_job(_jobicy_listing(url=shared_url), "jobicy"),
        normalize_job(_himalayas_listing(applicationLink=shared_url), "himalayas"),
    ]
    assert len(deduplicate_jobs(jobs)) == 1
