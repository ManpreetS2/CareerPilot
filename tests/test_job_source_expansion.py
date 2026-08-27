"""Greenhouse/Lever bulk discovery, Remotive, and staleness-by-absence
regressions. No live network; mocks fetch_url_safely the same way
test_greenhouse_job_ingestion.py does for the existing manual-ingest path.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from backend.db.models import JobRecord
from backend.schemas.schemas import Job
from backend.services import job_scout_service, job_verification_service
from backend.services.job_scout_service import (
    JobScoutError,
    _parse_epoch_millis,
    _title_matches_query,
    normalize_job,
    parse_lever_posting_url,
    persist_jobs,
    scout_greenhouse,
    scout_lever,
    scout_remotive,
)
from backend.services.job_verification_service import (
    DEFAULT_ABSENCE_STALE_AFTER_DAYS,
    mark_stale_if_unseen,
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
    """Routes each call by URL so a test can script per-board/per-company
    responses (including a deliberately-missing one, to simulate a dead
    board without the test needing to track call order)."""
    captured: dict = {"calls": [], "by_url": {}}

    def fake_fetch(url, **kwargs):
        captured["calls"].append(url)
        for prefix, handler in captured["by_url"].items():
            if url.startswith(prefix):
                return handler(url, **kwargs)
        raise AssertionError(f"no handler configured for {url}")

    monkeypatch.setattr(job_scout_service, "fetch_url_safely", fake_fetch)
    return captured


@pytest.fixture
def isolated_db(monkeypatch: pytest.MonkeyPatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.db.database import Base

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(job_scout_service, "SessionLocal", session_factory)
    monkeypatch.setattr(job_verification_service, "SessionLocal", session_factory)
    return session_factory


# ---------------------------------------------------------------------------
# Pure unit tests: URL parsing, title filter, epoch parsing
# ---------------------------------------------------------------------------


def test_parse_lever_posting_url_extracts_company_and_id() -> None:
    ref = parse_lever_posting_url("https://jobs.lever.co/acme/f25a6c49-5ed4-4aa0-a5bb-b30e9790f90c")
    assert ref == ("acme", "f25a6c49-5ed4-4aa0-a5bb-b30e9790f90c")


@pytest.mark.parametrize(
    "url",
    [
        "https://jobs.lever.co/acme/not-a-uuid",
        "https://boards.greenhouse.io/acme/jobs/123",
        "",
    ],
)
def test_parse_lever_posting_url_rejects_non_matching_urls(url: str) -> None:
    assert parse_lever_posting_url(url) is None


def test_title_matches_query_is_any_word_not_exact_phrase() -> None:
    assert _title_matches_query("Backend Software Engineer", "software engineer intern")
    assert not _title_matches_query("Sales Development Representative", "software engineer intern")
    assert _title_matches_query("Anything", "") is True  # blank query matches everything


def test_parse_epoch_millis_handles_valid_and_invalid_input() -> None:
    assert _parse_epoch_millis(1750119882479) == date(2025, 6, 17)
    assert _parse_epoch_millis(None) is None
    assert _parse_epoch_millis("1750119882479") is None  # string, not numeric
    assert _parse_epoch_millis(True) is None  # bool is technically an int — must not pass


# ---------------------------------------------------------------------------
# normalize_job branches
# ---------------------------------------------------------------------------


def test_normalize_greenhouse_job_maps_fields() -> None:
    raw = {
        "id": 7532733,
        "title": "Backend Engineer Intern",
        "company_name": "Stripe",
        "location": {"name": "San Francisco, CA"},
        "first_published": "2026-06-01T08:00:00Z",
        "content": "<p>Build payments infrastructure.</p>",
        "_board_token": "stripe",
    }
    job = normalize_job(raw, "greenhouse")
    assert job.title == "Backend Engineer Intern"
    assert job.company == "Stripe"
    assert job.location == "San Francisco, CA"
    assert job.url == "https://boards.greenhouse.io/stripe/jobs/7532733"
    assert job.description == "Build payments infrastructure."
    assert job.source == "greenhouse"
    assert job.ats == "greenhouse"
    assert job.date_posted == date(2026, 6, 1)


def test_normalize_greenhouse_job_falls_back_to_board_token_company_name() -> None:
    raw = {"id": 1, "title": "Role", "content": "Enough description text here.", "_board_token": "acme-co"}
    job = normalize_job(raw, "greenhouse")
    assert job.company == "Acme Co"


def test_normalize_lever_job_maps_fields() -> None:
    raw = {
        "id": "f25a6c49-5ed4-4aa0-a5bb-b30e9790f90c",
        "text": "Pharmacy Technician",
        "categories": {"location": "Romeoville, IL", "commitment": "Full-time"},
        "hostedUrl": "https://jobs.lever.co/ro/f25a6c49-5ed4-4aa0-a5bb-b30e9790f90c",
        "createdAt": 1750119882479,
        "descriptionPlain": "Deliver patient care.",
        "_company_slug": "ro",
    }
    job = normalize_job(raw, "lever")
    assert job.title == "Pharmacy Technician"
    assert job.company == "Ro"
    assert job.location == "Romeoville, IL"
    assert job.url == "https://jobs.lever.co/ro/f25a6c49-5ed4-4aa0-a5bb-b30e9790f90c"
    assert job.description == "Deliver patient care."
    assert job.source == "lever"
    assert job.ats == "lever"
    assert job.date_posted == date(2025, 6, 17)


def test_normalize_remotive_job_maps_fields() -> None:
    raw = {
        "id": 2091098,
        "url": "https://remotive.com/remote-jobs/software-development/senior-golang-developer-2091098",
        "title": "Senior Golang Developer",
        "company_name": "Lemon.io",
        "candidate_required_location": "Worldwide",
        "salary": "$80,000 - $120,000",
        "publication_date": "2026-08-21T05:54:39",
        "description": "<p>Build backend services.</p>",
    }
    job = normalize_job(raw, "remotive")
    assert job.title == "Senior Golang Developer"
    assert job.company == "Lemon.io"
    assert job.location == "Worldwide"
    assert job.salary == "$80,000 - $120,000"
    assert job.url == raw["url"]
    assert job.description == "Build backend services."
    assert job.source == "remotive"
    assert job.date_posted == date(2026, 8, 21)


def test_normalize_remotive_job_defaults_location_to_remote_when_blank() -> None:
    raw = {"id": 1, "url": "https://remotive.com/remote-jobs/x", "title": "Role", "description": "Text."}
    job = normalize_job(raw, "remotive")
    assert job.location == "Remote"


# ---------------------------------------------------------------------------
# scout_greenhouse / scout_lever / scout_remotive
# ---------------------------------------------------------------------------


def _greenhouse_board_payload(*jobs: dict) -> dict:
    return {"jobs": list(jobs)}


def test_scout_greenhouse_fetches_configured_board_and_filters_by_title(
    monkeypatch: pytest.MonkeyPatch, mock_fetch
) -> None:
    monkeypatch.setattr(job_scout_service.settings, "greenhouse_board_tokens", "stripe")
    mock_fetch["by_url"]["https://boards-api.greenhouse.io/v1/boards/stripe/jobs"] = (
        lambda url, **_: _json_response(
            url,
            _greenhouse_board_payload(
                {"id": 1, "title": "Software Engineer Intern", "content": "Build things."},
                {"id": 2, "title": "Sales Development Rep", "content": "Sell things."},
            ),
        )
    )
    listings = scout_greenhouse(["software engineer intern"])
    assert [item["id"] for item in listings] == [1]
    assert listings[0]["_board_token"] == "stripe"
    assert mock_fetch["calls"] == ["https://boards-api.greenhouse.io/v1/boards/stripe/jobs?content=true"]


def test_scout_greenhouse_isolates_one_dead_board_from_others(
    monkeypatch: pytest.MonkeyPatch, mock_fetch
) -> None:
    monkeypatch.setattr(job_scout_service.settings, "greenhouse_board_tokens", "deadboard,stripe")

    def dead(url, **_):
        return _json_response(url, {"error": SECRET_BODY}, status_code=404)

    mock_fetch["by_url"]["https://boards-api.greenhouse.io/v1/boards/deadboard/jobs"] = dead
    mock_fetch["by_url"]["https://boards-api.greenhouse.io/v1/boards/stripe/jobs"] = lambda url, **_: (
        _json_response(url, _greenhouse_board_payload({"id": 1, "title": "Engineer", "content": "Text."}))
    )
    listings = scout_greenhouse()
    assert [item["id"] for item in listings] == [1]


def test_scout_greenhouse_error_messages_are_sanitized(
    monkeypatch: pytest.MonkeyPatch, mock_fetch
) -> None:
    monkeypatch.setattr(job_scout_service.settings, "greenhouse_board_tokens", "deadboard")
    mock_fetch["by_url"]["https://boards-api.greenhouse.io/v1/boards/deadboard/jobs"] = (
        lambda url, **_: _json_response(url, {"error": SECRET_BODY}, status_code=500)
    )
    listings = scout_greenhouse()  # per-token failure is caught and logged, not raised
    assert listings == []


def _lever_company_payload(*jobs: dict) -> list[dict]:
    return list(jobs)


def test_scout_lever_fetches_configured_company_and_filters_by_title(
    monkeypatch: pytest.MonkeyPatch, mock_fetch
) -> None:
    monkeypatch.setattr(job_scout_service.settings, "lever_company_slugs", "ro")
    mock_fetch["by_url"]["https://api.lever.co/v0/postings/ro"] = lambda url, **_: _json_response(
        url,
        _lever_company_payload(
            {"id": "abc", "text": "Backend Engineer", "categories": {}},
            {"id": "def", "text": "Recruiter", "categories": {}},
        ),
    )
    listings = scout_lever(["backend engineer"])
    assert [item["id"] for item in listings] == ["abc"]
    assert listings[0]["_company_slug"] == "ro"


def test_scout_lever_isolates_one_dead_company_from_others(
    monkeypatch: pytest.MonkeyPatch, mock_fetch
) -> None:
    monkeypatch.setattr(job_scout_service.settings, "lever_company_slugs", "deadco,ro")
    mock_fetch["by_url"]["https://api.lever.co/v0/postings/deadco"] = lambda url, **_: _json_response(
        url, {"error": SECRET_BODY}, status_code=404
    )
    mock_fetch["by_url"]["https://api.lever.co/v0/postings/ro"] = lambda url, **_: _json_response(
        url, _lever_company_payload({"id": "abc", "text": "Engineer", "categories": {}})
    )
    listings = scout_lever()
    assert [item["id"] for item in listings] == ["abc"]


def test_scout_remotive_builds_search_query_and_returns_jobs(mock_fetch) -> None:
    mock_fetch["by_url"]["https://remotive.com/api/remote-jobs"] = lambda url, **_: _json_response(
        url, {"jobs": [{"id": 1, "url": "https://remotive.com/x", "title": "Engineer"}]}
    )
    listings = scout_remotive("software engineer")
    assert [item["id"] for item in listings] == [1]
    assert "search=software" in mock_fetch["calls"][0]


def test_scout_remotive_error_message_is_sanitized(mock_fetch) -> None:
    mock_fetch["by_url"]["https://remotive.com/api/remote-jobs"] = lambda url, **_: _json_response(
        url, {"error": SECRET_BODY}, status_code=500
    )
    with pytest.raises(JobScoutError) as exc:
        scout_remotive("engineer")
    assert "sk-secret" not in str(exc.value)


# ---------------------------------------------------------------------------
# Dedup collapse across manual paste vs. bulk discovery
# ---------------------------------------------------------------------------


def test_lever_manual_paste_and_bulk_discovery_collapse_to_one_row(isolated_db) -> None:
    manual = normalize_job(
        {
            "title": "Pharmacy Technician (pasted)",
            "company": "Ro",
            "url": "https://jobs.lever.co/ro/f25a6c49-5ed4-4aa0-a5bb-b30e9790f90c",
            "description": "Pasted description.",
            "ats": "lever",
        },
        "manual",
    )
    persist_jobs([manual])

    discovered = normalize_job(
        {
            "id": "f25a6c49-5ed4-4aa0-a5bb-b30e9790f90c",
            "text": "Pharmacy Technician",
            "categories": {"location": "Romeoville, IL"},
            "hostedUrl": "https://jobs.lever.co/ro/f25a6c49-5ed4-4aa0-a5bb-b30e9790f90c",
            "createdAt": 1750119882479,
            "descriptionPlain": "A genuinely longer discovered description with real detail.",
            "_company_slug": "ro",
        },
        "lever",
    )
    persist_jobs([discovered])

    with isolated_db() as db:
        rows = db.query(JobRecord).all()
        assert len(rows) == 1


def test_greenhouse_manual_paste_and_bulk_discovery_collapse_to_one_row(isolated_db) -> None:
    manual = normalize_job(
        {
            "title": "Backend Intern (pasted)",
            "company": "Stripe",
            "url": "https://boards.greenhouse.io/stripe/jobs/7532733",
            "description": "Pasted description.",
            "ats": "greenhouse",
        },
        "manual",
    )
    persist_jobs([manual])

    discovered = normalize_job(
        {
            "id": 7532733,
            "title": "Backend Engineer Intern",
            "company_name": "Stripe",
            "content": "A genuinely longer discovered description with real detail.",
            "_board_token": "stripe",
        },
        "greenhouse",
    )
    persist_jobs([discovered])

    with isolated_db() as db:
        rows = db.query(JobRecord).all()
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# Staleness by absence
# ---------------------------------------------------------------------------


def _seed_job(
    db,
    *,
    public_id: str,
    source: str = "adzuna",
    status: str = "discovered",
    date_scraped: datetime,
) -> JobRecord:
    record = JobRecord(
        public_id=public_id,
        title="Role",
        company="Acme",
        url=f"https://example.invalid/{public_id}",
        description="A real description of the role and its requirements.",
        source=source,
        status=status,
        date_scraped=date_scraped,
    )
    db.add(record)
    db.commit()
    return record


def test_mark_stale_if_unseen_marks_old_discovered_jobs(isolated_db) -> None:
    with isolated_db() as db:
        old = datetime.now(timezone.utc) - timedelta(days=DEFAULT_ABSENCE_STALE_AFTER_DAYS + 1)
        _seed_job(db, public_id="old-1", date_scraped=old)

    count = mark_stale_if_unseen()
    assert count == 1
    with isolated_db() as db:
        record = db.query(JobRecord).filter(JobRecord.public_id == "old-1").one()
        assert record.status == "stale"
        assert record.verification_notes is not None


def test_mark_stale_if_unseen_excludes_recent_jobs(isolated_db) -> None:
    with isolated_db() as db:
        recent = datetime.now(timezone.utc) - timedelta(days=1)
        _seed_job(db, public_id="recent-1", date_scraped=recent)

    assert mark_stale_if_unseen() == 0


def test_mark_stale_if_unseen_excludes_manual_source(isolated_db) -> None:
    with isolated_db() as db:
        old = datetime.now(timezone.utc) - timedelta(days=DEFAULT_ABSENCE_STALE_AFTER_DAYS + 1)
        _seed_job(db, public_id="manual-1", source="manual", date_scraped=old)

    assert mark_stale_if_unseen() == 0


def test_mark_stale_if_unseen_excludes_already_flagged(isolated_db) -> None:
    with isolated_db() as db:
        old = datetime.now(timezone.utc) - timedelta(days=DEFAULT_ABSENCE_STALE_AFTER_DAYS + 1)
        _seed_job(db, public_id="flagged-1", status="flagged", date_scraped=old)

    assert mark_stale_if_unseen() == 0
    with isolated_db() as db:
        record = db.query(JobRecord).filter(JobRecord.public_id == "flagged-1").one()
        assert record.status == "flagged"


def test_reappearing_stale_job_resets_to_discovered(isolated_db) -> None:
    with isolated_db() as db:
        old = datetime.now(timezone.utc) - timedelta(days=DEFAULT_ABSENCE_STALE_AFTER_DAYS + 1)
        _seed_job(db, public_id="adzuna-reappear", status="stale", date_scraped=old)

    reappeared = Job(
        title="Role",
        company="Acme",
        url="https://example.invalid/adzuna-reappear",
        description="A real description of the role and its requirements.",
        source="adzuna",
        date_scraped=datetime.now(timezone.utc),
        status="discovered",
    )
    persist_jobs([reappeared])

    with isolated_db() as db:
        record = db.query(JobRecord).filter(JobRecord.public_id == "adzuna-reappear").one()
        assert record.status == "discovered"


def test_reappearing_flagged_job_is_not_reset(isolated_db) -> None:
    """persist_jobs only resets a "stale" status — "flagged" reflects a
    suspicious-content verdict that mere reappearance must not overwrite."""
    with isolated_db() as db:
        old = datetime.now(timezone.utc) - timedelta(days=DEFAULT_ABSENCE_STALE_AFTER_DAYS + 1)
        _seed_job(db, public_id="adzuna-flagged-reappear", status="flagged", date_scraped=old)

    reappeared = Job(
        title="Role",
        company="Acme",
        url="https://example.invalid/adzuna-flagged-reappear",
        description="A real description of the role and its requirements.",
        source="adzuna",
        date_scraped=datetime.now(timezone.utc),
        status="discovered",
    )
    persist_jobs([reappeared])

    with isolated_db() as db:
        record = db.query(JobRecord).filter(JobRecord.public_id == "adzuna-flagged-reappear").one()
        assert record.status == "flagged"


# ---------------------------------------------------------------------------
# run_scout: one source failing must not take down the others
# ---------------------------------------------------------------------------


def test_run_scout_survives_greenhouse_failure(
    monkeypatch: pytest.MonkeyPatch, mock_fetch, isolated_db
) -> None:
    monkeypatch.setattr(job_scout_service.settings, "greenhouse_board_tokens", "deadboard")
    monkeypatch.setattr(job_scout_service.settings, "lever_company_slugs", "")

    # Every non-Greenhouse source raises JobScoutError (unconfigured/unreachable)
    # so the test isolates exactly one source's behavior: Greenhouse's own
    # per-token failure must not raise out of run_scout.
    monkeypatch.setattr(job_scout_service, "scout_remoteok", lambda *_a, **_k: (_ for _ in ()).throw(JobScoutError("x")))
    monkeypatch.setattr(job_scout_service, "scout_adzuna", lambda *_a, **_k: (_ for _ in ()).throw(JobScoutError("x")))
    monkeypatch.setattr(job_scout_service, "scout_remotive", lambda *_a, **_k: (_ for _ in ()).throw(JobScoutError("x")))
    monkeypatch.setattr(job_scout_service, "scout_jobicy", lambda *_a, **_k: (_ for _ in ()).throw(JobScoutError("x")))
    monkeypatch.setattr(job_scout_service, "scout_himalayas", lambda *_a, **_k: (_ for _ in ()).throw(JobScoutError("x")))
    mock_fetch["by_url"]["https://boards-api.greenhouse.io/v1/boards/deadboard/jobs"] = (
        lambda url, **_: _json_response(url, {"error": SECRET_BODY}, status_code=500)
    )

    result = job_scout_service.run_scout(["software engineer intern"])
    assert result == []  # every source failed/empty, but run_scout itself must not raise
