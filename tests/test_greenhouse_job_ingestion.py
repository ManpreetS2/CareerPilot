"""Greenhouse manual ingest + SSRF regressions. No live network."""

from __future__ import annotations

import json
import socket
from datetime import date, datetime, timezone
from unittest.mock import patch

import httpx
import pytest
from fastapi import status

from backend.schemas.schemas import Job
from backend.services import job_scout_service
from backend.services.job_scout_service import (
    JobScoutError,
    MANUAL_INGEST_PLACEHOLDER_DESCRIPTION,
    ingest_job_url,
    parse_greenhouse_posting_url,
    persist_jobs,
    validate_manual_ingest_url,
)
from backend.services.job_verification_service import check_staleness
from backend.services.url_safety import UnsafeURLError

SECRET_BODY = '{"internal":"sk-secret-token","host":"10.0.0.5","query":"token=abc"}'

INSTEAD_API = {
    "id": 7761472003,
    "title": "Software Engineering Intern",
    "company_name": "Instead",
    "first_published": "2026-06-01T08:00:00Z",
    "updated_at": "2020-01-15T10:00:00Z",
    "location": {"name": "San Francisco, CA"},
    "absolute_url": "https://job-boards.greenhouse.io/instead/jobs/7761472003",
    "content": (
        "<h2>About the role</h2>"
        "<p>Build APIs &amp; services for the platform.</p>"
        "<ul><li>Ship features</li><li>Write tests</li></ul>"
        "<br><p>Hybrid schedule in San Francisco.</p>"
    ),
}

CLOUDFLARE_API = {
    "id": 8118855,
    "title": "Software Engineer Intern (Fall 2026)",
    "company_name": "Cloudflare",
    "first_published": "2026-05-15T08:00:00Z",
    "updated_at": "2020-06-01T08:00:00Z",
    "location": {"name": "London, United Kingdom"},
    "absolute_url": "https://boards.greenhouse.io/cloudflare/jobs/8118855",
    "content": (
        "<h3>What you&#39;ll do</h3>"
        "<p>Work on edge network systems.</p>"
        "<ol><li>Learn systems design</li><li>Pair with mentors</li></ol>"
    ),
}

INSTEAD_URL = "https://job-boards.greenhouse.io/instead/jobs/7761472003"
CLOUDFLARE_URL = "https://boards.greenhouse.io/cloudflare/jobs/8118855"
API_INSTEAD = "https://boards-api.greenhouse.io/v1/boards/instead/jobs/7761472003"


def _fake_resolve(ip: str):
    def _getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    return _getaddrinfo


def _json_response(url: str, payload: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        content=json.dumps(payload).encode(),
        request=httpx.Request("GET", url),
    )


@pytest.fixture
def mock_fetch(monkeypatch: pytest.MonkeyPatch):
    captured: dict = {"calls": []}

    def fake_fetch(url, **kwargs):
        captured["calls"].append({"url": url, **kwargs})
        handler = captured.get("handler")
        if handler is None:
            raise AssertionError("no handler configured")
        return handler(url, **kwargs)

    monkeypatch.setattr(job_scout_service, "fetch_url_safely", fake_fetch)
    return captured


@pytest.fixture
def isolated_db(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.db.database import Base

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(job_scout_service, "SessionLocal", session_factory)
    return session_factory


def test_parse_greenhouse_job_boards_host() -> None:
    ref = parse_greenhouse_posting_url(INSTEAD_URL)
    assert ref is not None
    assert ref.board_token == "instead"
    assert ref.job_id == "7761472003"


def test_parse_greenhouse_job_job_boards_host() -> None:
    ref = parse_greenhouse_posting_url(CLOUDFLARE_URL)
    assert ref is not None
    assert ref.board_token == "cloudflare"
    assert ref.job_id == "8118855"


@pytest.mark.parametrize(
    "path",
    [
        "/instead%2Fevil/jobs/7761472003",
        "/instead/jobs/7761472003/extra",
        "/instead/jobs/not-a-number",
        "/instead/jobs/7761472003?token=abc",
    ],
)
def test_parse_rejects_malformed_board_or_job_paths(path: str) -> None:
    url = f"https://job-boards.greenhouse.io{path}"
    assert parse_greenhouse_posting_url(url) is None


def test_parse_rejects_non_ascii_board_token() -> None:
    assert parse_greenhouse_posting_url("https://job-boards.greenhouse.io/inste\u00e4d/jobs/1") is None


def test_ingest_greenhouse_instead_shaped(mock_fetch) -> None:
    mock_fetch["handler"] = lambda url, **_: _json_response(url, INSTEAD_API)
    raw = ingest_job_url(INSTEAD_URL)
    assert raw["title"] == "Software Engineering Intern"
    assert raw["company"] == "Instead"
    assert "Build APIs & services" in raw["description"]
    assert raw["location"] == "San Francisco, CA"
    assert raw["url"] == INSTEAD_API["absolute_url"]
    assert raw["ats"] == "greenhouse"
    assert "<" not in raw["description"]
    assert mock_fetch["calls"][0]["url"] == API_INSTEAD


def test_ingest_greenhouse_cloudflare_shaped(mock_fetch) -> None:
    api = "https://boards-api.greenhouse.io/v1/boards/cloudflare/jobs/8118855"
    mock_fetch["handler"] = lambda url, **_: _json_response(url, CLOUDFLARE_API)
    raw = ingest_job_url(CLOUDFLARE_URL)
    assert raw["title"] == "Software Engineer Intern (Fall 2026)"
    assert raw["company"] == "Cloudflare"
    assert mock_fetch["calls"][0]["url"] == api


def test_first_published_becomes_date_posted_not_updated_at(mock_fetch) -> None:
    mock_fetch["handler"] = lambda url, **_: _json_response(url, INSTEAD_API)
    raw = ingest_job_url(INSTEAD_URL)
    assert raw["date_posted"] == date(2026, 6, 1)
    assert raw["date_posted"] != date(2020, 1, 15)


def test_missing_first_published_leaves_date_posted_none(mock_fetch) -> None:
    payload = dict(INSTEAD_API)
    payload.pop("first_published", None)
    mock_fetch["handler"] = lambda url, **_: _json_response(url, payload)
    raw = ingest_job_url(INSTEAD_URL)
    assert raw["date_posted"] is None


def test_old_updated_at_does_not_make_posting_stale(mock_fetch) -> None:
    payload = dict(INSTEAD_API)
    payload["first_published"] = "2026-08-01T08:00:00Z"
    payload["updated_at"] = "2020-01-15T10:00:00Z"
    mock_fetch["handler"] = lambda url, **_: _json_response(url, payload)
    raw = ingest_job_url(INSTEAD_URL)
    job = job_scout_service.normalize_job(raw, "manual")
    assert check_staleness(job) is False


def test_official_entity_encoded_html_becomes_plain_text(mock_fetch) -> None:
    payload = dict(INSTEAD_API)
    payload["content"] = (
        "&lt;div&gt;&lt;p&gt;Paragraph with enough text for minimum description length.&lt;/p&gt;"
        "&lt;ul&gt;&lt;li&gt;Item one&lt;/li&gt;&lt;/ul&gt;&lt;/div&gt;"
    )
    mock_fetch["handler"] = lambda url, **_: _json_response(url, payload)
    raw = ingest_job_url(INSTEAD_URL)
    assert "<" not in raw["description"]
    assert "&lt;" not in raw["description"]
    assert "Paragraph with enough text" in raw["description"]
    assert "Item one" in raw["description"]


def test_company_name_preferred_over_board_token(mock_fetch) -> None:
    payload = dict(INSTEAD_API)
    payload["company_name"] = "Instead Technologies Inc."
    mock_fetch["handler"] = lambda url, **_: _json_response(url, payload)
    raw = ingest_job_url(INSTEAD_URL)
    assert raw["company"] == "Instead Technologies Inc."


def test_missing_company_name_falls_back_to_board_token(mock_fetch) -> None:
    payload = dict(INSTEAD_API)
    payload.pop("company_name", None)
    mock_fetch["handler"] = lambda url, **_: _json_response(url, payload)
    raw = ingest_job_url(INSTEAD_URL)
    assert raw["company"] == "Instead"


def test_bad_absolute_url_ignored(mock_fetch) -> None:
    payload = dict(INSTEAD_API)
    payload["absolute_url"] = "http://evil.example.com/instead/jobs/7761472003"
    mock_fetch["handler"] = lambda url, **_: _json_response(url, payload)
    raw = ingest_job_url(INSTEAD_URL)
    assert raw["url"] == INSTEAD_URL


def test_absolute_url_wrong_board_ignored(mock_fetch) -> None:
    payload = dict(INSTEAD_API)
    payload["absolute_url"] = "https://job-boards.greenhouse.io/otherco/jobs/7761472003"
    mock_fetch["handler"] = lambda url, **_: _json_response(url, payload)
    raw = ingest_job_url(INSTEAD_URL)
    assert raw["url"] == INSTEAD_URL


def test_equivalent_absolute_url_on_canonical_host_accepted(mock_fetch) -> None:
    alt = "https://boards.greenhouse.io/instead/jobs/7761472003"
    payload = dict(INSTEAD_API)
    payload["absolute_url"] = alt
    mock_fetch["handler"] = lambda url, **_: _json_response(url, payload)
    raw = ingest_job_url(alt)
    assert raw["url"] == alt


@pytest.mark.parametrize(
    "status_code",
    [404, 500, 503],
)
def test_ingest_greenhouse_api_http_errors_fail_closed(status_code, mock_fetch) -> None:
    mock_fetch["handler"] = lambda url, **_: _json_response(url, {}, status_code=status_code)
    with pytest.raises(JobScoutError) as exc:
        ingest_job_url(INSTEAD_URL)
    assert SECRET_BODY not in str(exc.value)


def test_ingest_greenhouse_timeout_fail_closed(mock_fetch) -> None:
    def handler(url, **_):
        raise httpx.TimeoutException("timed out with secret detail")

    mock_fetch["handler"] = handler
    with pytest.raises(JobScoutError) as exc:
        ingest_job_url(INSTEAD_URL)
    assert "secret" not in str(exc.value).lower()


def test_ingest_greenhouse_malformed_json_fail_closed(mock_fetch) -> None:
    mock_fetch["handler"] = lambda url, **_: httpx.Response(
        200, content=SECRET_BODY.encode(), request=httpx.Request("GET", url)
    )
    with pytest.raises(JobScoutError):
        ingest_job_url(INSTEAD_URL)


def test_ingest_failure_does_not_persist_placeholder(isolated_db, mock_fetch) -> None:
    mock_fetch["handler"] = lambda url, **_: _json_response(url, {}, status_code=404)
    with pytest.raises(JobScoutError):
        ingest_job_url(INSTEAD_URL)
    with isolated_db() as db:
        from backend.db.models import JobRecord

        assert db.query(JobRecord).count() == 0


def test_reingest_placeholder_upgrades_same_job(isolated_db, mock_fetch) -> None:
    placeholder = job_scout_service.normalize_job(
        {
            "title": "Jobs at Instead",
            "company": "Instead",
            "url": INSTEAD_URL,
            "description": MANUAL_INGEST_PLACEHOLDER_DESCRIPTION,
        },
        "manual",
    )
    stored = persist_jobs([placeholder])
    public_id = stored[0].id

    mock_fetch["handler"] = lambda url, **_: _json_response(url, INSTEAD_API)
    raw = ingest_job_url(INSTEAD_URL)
    result = persist_jobs([job_scout_service.normalize_job(raw, "manual")])

    assert len(result) == 1
    assert result[0].id == public_id
    assert result[0].description != MANUAL_INGEST_PLACEHOLDER_DESCRIPTION
    assert result[0].location == "San Francisco, CA"


@pytest.mark.parametrize(
    "url",
    [
        "http://job-boards.greenhouse.io/instead/jobs/7761472003",
        "https://job-boards.greenhouse.io:8080/instead/jobs/7761472003",
        "https://user:pass@job-boards.greenhouse.io/instead/jobs/7761472003",
        "https://localhost/instead/jobs/7761472003",
        "https://127.0.0.1/instead/jobs/7761472003",
        "https://10.0.0.5/instead/jobs/7761472003",
        "https://169.254.169.254/instead/jobs/7761472003",
        "https://greenhouse.io.evil.example/instead/jobs/7761472003",
        "https://evilgreenhouse.io/instead/jobs/7761472003",
        "https://job-boards.greenhouse.io.evil.example/instead/jobs/7761472003",
        "https://example.com/jobs/1",
    ],
)
def test_validate_manual_ingest_url_rejects_unsafe(url: str) -> None:
    with pytest.raises(UnsafeURLError):
        validate_manual_ingest_url(url)


def test_explicit_port_443_is_accepted(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_resolve("93.184.216.34"))
    url = "https://job-boards.greenhouse.io:443/instead/jobs/7761472003"
    assert validate_manual_ingest_url(url) == url


def test_ingest_unsupported_host_raises_unsafe_error() -> None:
    with pytest.raises(UnsafeURLError):
        ingest_job_url("https://example.com/jobs/1")


def test_ingest_error_messages_are_sanitized(mock_fetch) -> None:
    mock_fetch["handler"] = lambda url, **_: _json_response(url, {}, status_code=500)
    with pytest.raises(JobScoutError) as exc:
        ingest_job_url(INSTEAD_URL)
    message = str(exc.value)
    assert "sk-secret" not in message
    assert SECRET_BODY not in message


def test_greenhouse_api_fetch_uses_get_endpoint_only(mock_fetch) -> None:
    mock_fetch["handler"] = lambda url, **_: _json_response(url, INSTEAD_API)
    ingest_job_url(INSTEAD_URL)
    assert len(mock_fetch["calls"]) == 1
    assert mock_fetch["calls"][0]["url"] == API_INSTEAD


def test_ingest_url_route_maps_unsafe_url_to_422(isolated_client) -> None:
    client, _ = isolated_client
    response = client.post(
        "/api/jobs/ingest-url",
        json={"url": "https://127.0.0.1/jobs/1"},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_ingest_url_route_maps_greenhouse_upstream_failure_to_502(
    isolated_client, mock_fetch
) -> None:
    client, _ = isolated_client
    mock_fetch["handler"] = lambda url, **_: _json_response(url, {}, status_code=503)
    response = client.post(
        "/api/jobs/ingest-url",
        json={"url": INSTEAD_URL},
    )
    assert response.status_code == status.HTTP_502_BAD_GATEWAY
