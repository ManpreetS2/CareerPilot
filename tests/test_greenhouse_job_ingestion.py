"""Greenhouse manual ingest + SSRF regressions. No live network."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import patch

import httpx
import pytest

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

SECRET_BODY = '{"internal":"sk-secret-token","host":"10.0.0.5","query":"token=abc"}'

INSTEAD_API = {
    "id": 7761472003,
    "title": "Software Engineering Intern",
    "updated_at": "2026-01-15T10:00:00Z",
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
    "updated_at": "2026-06-01T08:00:00Z",
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


class _FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: object | None = None,
        text: str = "",
        headers: dict[str, str] | None = None,
        url: str = "",
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text or (json.dumps(payload) if payload is not None else SECRET_BODY)
        self.headers = headers or {}
        self.url = url

    def json(self) -> object:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error",
                request=httpx.Request("GET", self.url or "https://example.com"),
                response=httpx.Response(self.status_code),
            )


@pytest.fixture
def mock_ingest_client(monkeypatch: pytest.MonkeyPatch):
    captured: dict = {"calls": []}

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, url, **kwargs):
            captured["calls"].append(url)
            handler = captured.get("handler")
            if handler is None:
                raise AssertionError("no handler configured")
            return handler(url)

    monkeypatch.setattr(job_scout_service.httpx, "Client", FakeClient)
    return captured


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


def test_ingest_greenhouse_instead_shaped(mock_ingest_client) -> None:
    def handler(url: str):
        assert url == "https://boards-api.greenhouse.io/v1/boards/instead/jobs/7761472003"
        return _FakeResponse(200, INSTEAD_API, url=url)

    mock_ingest_client["handler"] = handler
    raw = ingest_job_url(INSTEAD_URL)
    assert raw["title"] == "Software Engineering Intern"
    assert raw["company"] == "Instead"
    assert "Build APIs & services" in raw["description"]
    assert "Ship features" in raw["description"]
    assert raw["location"] == "San Francisco, CA"
    assert raw["url"] == INSTEAD_API["absolute_url"]
    assert raw["ats"] == "greenhouse"
    assert "<" not in raw["description"]


def test_ingest_greenhouse_cloudflare_shaped(mock_ingest_client) -> None:
    def handler(url: str):
        assert url == "https://boards-api.greenhouse.io/v1/boards/cloudflare/jobs/8118855"
        return _FakeResponse(200, CLOUDFLARE_API, url=url)

    mock_ingest_client["handler"] = handler
    raw = ingest_job_url(CLOUDFLARE_URL)
    assert raw["title"] == "Software Engineer Intern (Fall 2026)"
    assert raw["company"] == "Cloudflare"
    assert "edge network" in raw["description"].lower()
    assert "What you'll do" in raw["description"]
    assert raw["location"] == "London, United Kingdom"
    assert raw["url"] == CLOUDFLARE_API["absolute_url"]


def test_ingest_greenhouse_html_entities_and_structure(mock_ingest_client) -> None:
    payload = dict(INSTEAD_API)
    payload["content"] = (
        "<p>Line one with enough text to satisfy minimum description length.</p>"
        "<p>Line two &amp; more detail for the posting body.</p>"
    )
    mock_ingest_client["handler"] = lambda url: _FakeResponse(200, payload, url=url)
    raw = ingest_job_url(INSTEAD_URL)
    assert "Line one with enough text" in raw["description"]
    assert "Line two & more detail" in raw["description"]


@pytest.mark.parametrize(
    "status_code",
    [404, 500, 503],
)
def test_ingest_greenhouse_api_http_errors_fail_closed(status_code, mock_ingest_client) -> None:
    mock_ingest_client["handler"] = lambda url: _FakeResponse(status_code, url=url)
    with pytest.raises(JobScoutError) as exc:
        ingest_job_url(INSTEAD_URL)
    assert SECRET_BODY not in str(exc.value)
    assert "10.0.0" not in str(exc.value)


def test_ingest_greenhouse_timeout_fail_closed(mock_ingest_client) -> None:
    def handler(url: str):
        raise httpx.TimeoutException("timed out with secret detail")

    mock_ingest_client["handler"] = handler
    with pytest.raises(JobScoutError) as exc:
        ingest_job_url(INSTEAD_URL)
    assert "secret" not in str(exc.value).lower()


def test_ingest_greenhouse_malformed_json_fail_closed(mock_ingest_client) -> None:
    mock_ingest_client["handler"] = lambda url: _FakeResponse(200, text=SECRET_BODY, url=url)
    with pytest.raises(JobScoutError):
        ingest_job_url(INSTEAD_URL)


def test_ingest_greenhouse_missing_content_fail_closed(mock_ingest_client) -> None:
    payload = dict(INSTEAD_API)
    payload["content"] = "<p>Short.</p>"
    mock_ingest_client["handler"] = lambda url: _FakeResponse(200, payload, url=url)
    with pytest.raises(JobScoutError):
        ingest_job_url(INSTEAD_URL)


def test_ingest_greenhouse_wrong_job_id_fail_closed(mock_ingest_client) -> None:
    payload = dict(INSTEAD_API)
    payload["id"] = 9999999999
    mock_ingest_client["handler"] = lambda url: _FakeResponse(200, payload, url=url)
    with pytest.raises(JobScoutError):
        ingest_job_url(INSTEAD_URL)


def test_ingest_failure_does_not_persist_placeholder(isolated_db, mock_ingest_client) -> None:
    mock_ingest_client["handler"] = lambda url: _FakeResponse(404, url=url)
    with pytest.raises(JobScoutError):
        ingest_job_url(INSTEAD_URL)
    with isolated_db() as db:
        from backend.db.models import JobRecord

        assert db.query(JobRecord).count() == 0


def test_reingest_placeholder_upgrades_same_job(isolated_db, mock_ingest_client) -> None:
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

    mock_ingest_client["handler"] = lambda url: _FakeResponse(200, INSTEAD_API, url=url)
    raw = ingest_job_url(INSTEAD_URL)
    upgraded = job_scout_service.normalize_job(raw, "manual")
    result = persist_jobs([upgraded])

    assert len(result) == 1
    assert result[0].id == public_id
    assert result[0].description != MANUAL_INGEST_PLACEHOLDER_DESCRIPTION
    assert result[0].location == "San Francisco, CA"
    with isolated_db() as db:
        from backend.db.models import JobRecord

        assert db.query(JobRecord).count() == 1


def test_reingest_does_not_replace_valid_description_with_placeholder(isolated_db, mock_ingest_client) -> None:
    good = job_scout_service.normalize_job(
        {
            "title": "Software Engineering Intern",
            "company": "Instead",
            "url": INSTEAD_URL,
            "description": "A long grounded description that is clearly source-backed and complete.",
            "location": "San Francisco, CA",
        },
        "manual",
    )
    persist_jobs([good])

    short_payload = dict(INSTEAD_API)
    short_payload["content"] = "<p>Too short.</p>"
    mock_ingest_client["handler"] = lambda url: _FakeResponse(200, short_payload, url=url)
    with pytest.raises(JobScoutError):
        ingest_job_url(INSTEAD_URL)

    with isolated_db() as db:
        from backend.db.models import JobRecord

        record = db.query(JobRecord).one()
        assert "grounded description" in record.description


def test_reingest_canonical_host_upgrades_placeholder(isolated_db, mock_ingest_client) -> None:
    alt_url = "https://boards.greenhouse.io/instead/jobs/7761472003"
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

    api = dict(INSTEAD_API)
    api["absolute_url"] = alt_url
    mock_ingest_client["handler"] = lambda url: _FakeResponse(200, api, url=url)
    raw = ingest_job_url(alt_url)
    result = persist_jobs([job_scout_service.normalize_job(raw, "manual")])

    assert len(result) == 1
    assert result[0].id == public_id


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
    with pytest.raises(JobScoutError):
        validate_manual_ingest_url(url)


def test_ingest_rejects_http_url() -> None:
    with pytest.raises(JobScoutError):
        ingest_job_url("http://job-boards.greenhouse.io/instead/jobs/7761472003")


def test_ingest_rejects_redirect_to_private_destination(mock_ingest_client) -> None:
    lever_url = "https://jobs.lever.co/acme/abc-123"
    calls = []

    def handler(url: str):
        calls.append(url)
        if len(calls) == 1:
            return _FakeResponse(
                302,
                headers={"Location": "https://127.0.0.1/private"},
                url=url,
            )
        return _FakeResponse(200, text="<title>Role</title>", url=url)

    mock_ingest_client["handler"] = handler
    with pytest.raises(JobScoutError):
        ingest_job_url(lever_url)


def test_safe_client_disables_proxy_and_blind_redirects(mock_ingest_client) -> None:
    mock_ingest_client["handler"] = lambda url: _FakeResponse(200, INSTEAD_API, url=url)
    ingest_job_url(INSTEAD_URL)
    kwargs = mock_ingest_client["client_kwargs"]
    assert kwargs.get("trust_env") is False
    assert kwargs.get("follow_redirects") is False


def test_ingest_error_messages_are_sanitized(mock_ingest_client) -> None:
    mock_ingest_client["handler"] = lambda url: _FakeResponse(500, text=SECRET_BODY, url=url)
    with pytest.raises(JobScoutError) as exc:
        ingest_job_url(INSTEAD_URL)
    message = str(exc.value)
    assert "sk-secret" not in message
    assert "10.0.0" not in message
    assert SECRET_BODY not in message


def test_greenhouse_ingest_never_calls_post(mock_ingest_client) -> None:
    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, url, **kwargs):
            return _FakeResponse(200, INSTEAD_API, url=url)

        def post(self, url, **kwargs):
            raise AssertionError("application submission endpoint must not be called")

    with patch.object(job_scout_service.httpx, "Client", FakeClient):
        ingest_job_url(INSTEAD_URL)


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


def _job(**overrides) -> Job:
    defaults = dict(
        title="Software Engineer Intern",
        company="Acme",
        url="",
        description="Build things.",
        source="manual",
        date_scraped=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return Job(**defaults)
