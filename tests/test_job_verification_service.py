"""Job Verification heuristics tests. Most of this file is pure logic with no
network; check_still_open's outbound-fetch safety (it re-fetches an
already-stored posting URL server-side, the same SSRF surface as
ingest_job_url) is tested below with a mocked transport — see also
test_url_safety.py for the shared validator's own unit tests."""

from __future__ import annotations

import socket
from datetime import datetime, timedelta, timezone

import httpx

from backend.schemas.schemas import Job
from backend.services.job_verification_service import (
    DEFAULT_STALE_AFTER_DAYS,
    _decide_verification,
    check_staleness,
    check_still_open,
    detect_suspicious_signals,
    verify_job,
)

_RealClient = httpx.Client  # captured before any test monkeypatches httpx.Client itself


def _job(**overrides) -> Job:
    defaults = dict(
        title="Software Engineer Intern",
        company="Aether Analytics",
        url="https://example.com/jobs/1",
        description="Build Python services that power analytics dashboards for our customers.",
        source="manual",
    )
    defaults.update(overrides)
    return Job(**defaults)


def test_detect_suspicious_signals_flags_missing_company() -> None:
    reasons = detect_suspicious_signals(_job(company="Unknown"))
    assert any("Company name" in r for r in reasons)


def test_detect_suspicious_signals_flags_short_description() -> None:
    reasons = detect_suspicious_signals(_job(description="Apply now."))
    assert any("Description" in r for r in reasons)


def test_detect_suspicious_signals_flags_scam_phrases() -> None:
    reasons = detect_suspicious_signals(
        _job(description="Great role. Please pay a registration fee via Western Union to start.")
    )
    assert any("scam-posting language" in r for r in reasons)
    assert any("western union" in r for r in reasons)
    assert any("registration fee" in r for r in reasons)


def test_detect_suspicious_signals_flags_unextracted_manual_placeholder() -> None:
    from backend.services.job_scout_service import MANUAL_INGEST_PLACEHOLDER_DESCRIPTION

    reasons = detect_suspicious_signals(
        _job(description=MANUAL_INGEST_PLACEHOLDER_DESCRIPTION, source="manual")
    )
    assert any("never extracted" in r for r in reasons)


def test_detect_suspicious_signals_clean_job_has_no_flags() -> None:
    assert detect_suspicious_signals(_job()) == []


def test_check_staleness_true_when_old() -> None:
    old_date = (datetime.now(timezone.utc).date() - timedelta(days=DEFAULT_STALE_AFTER_DAYS + 5))
    assert check_staleness(_job(date_posted=old_date)) is True


def test_check_staleness_false_when_recent() -> None:
    recent_date = datetime.now(timezone.utc).date() - timedelta(days=2)
    assert check_staleness(_job(date_posted=recent_date)) is False


def test_check_staleness_false_when_no_date() -> None:
    assert check_staleness(_job(date_posted=None)) is False


def test_decide_verification_suspicious_wins_over_everything() -> None:
    status, notes = _decide_verification(
        suspicious=["Company name is missing or unverified."],
        is_open=True,
        open_check_reason="looks fine",
        stale_by_age=False,
    )
    assert status == "flagged"
    assert "Flagged for review" in notes


def test_decide_verification_confirmed_closed_is_stale() -> None:
    status, notes = _decide_verification(
        suspicious=[], is_open=False, open_check_reason="404", stale_by_age=False
    )
    assert status == "stale"
    assert notes == "404"


def test_decide_verification_confirmed_closed_and_old_keeps_both_facts() -> None:
    status, notes = _decide_verification(
        suspicious=[], is_open=False, open_check_reason="404", stale_by_age=True
    )
    assert status == "stale"
    assert "404" in notes
    assert "days ago" in notes


def test_decide_verification_uncertain_and_old_is_stale() -> None:
    status, _ = _decide_verification(
        suspicious=[], is_open=None, open_check_reason="timeout", stale_by_age=True
    )
    assert status == "stale"


def test_decide_verification_uncertain_and_recent_is_flagged() -> None:
    status, notes = _decide_verification(
        suspicious=[], is_open=None, open_check_reason="timeout", stale_by_age=False
    )
    assert status == "flagged"
    assert "Could not confirm" in notes


def test_decide_verification_open_and_old_is_stale() -> None:
    status, _ = _decide_verification(
        suspicious=[], is_open=True, open_check_reason="fine", stale_by_age=True
    )
    assert status == "stale"


def test_decide_verification_open_and_recent_is_verified() -> None:
    status, notes = _decide_verification(
        suspicious=[], is_open=True, open_check_reason="fine", stale_by_age=False
    )
    assert status == "verified"
    assert "no red flags" in notes


def test_verify_job_short_circuits_on_suspicious_without_network(monkeypatch) -> None:
    """A suspicious job should never trigger check_still_open's network call."""
    from backend.services import job_verification_service as mod

    def boom(_url: str):
        raise AssertionError("check_still_open should not be called for a suspicious job")

    monkeypatch.setattr(mod, "check_still_open", boom)
    status, _ = verify_job(_job(company="Unknown"))
    assert status == "flagged"


# ---------------------------------------------------------------------------
# check_still_open — outbound-fetch safety (SSRF regression, same gap and
# fix as ingest_job_url). Must never raise — an unsafe target stays
# "uncertain" (None), which _decide_verification then correctly treats as
# never-confidently-verified, not a crash.
# ---------------------------------------------------------------------------


def _fake_resolve(ip: str):
    def _getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    return _getaddrinfo


def test_check_still_open_treats_private_address_as_uncertain_not_a_crash(monkeypatch) -> None:
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200, text="fine")

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: _RealClient(transport=httpx.MockTransport(handler)))
    is_open, reason = check_still_open("https://127.0.0.1:9000/internal")
    assert is_open is None
    assert "not safe" in reason.lower()
    assert called["n"] == 0


def test_check_still_open_treats_redirect_to_private_address_as_uncertain(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_resolve("93.184.216.34"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://169.254.169.254/latest/meta-data/"})

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: _RealClient(transport=httpx.MockTransport(handler)))
    is_open, reason = check_still_open("https://example.com/jobs/1")
    assert is_open is None
    assert "not safe" in reason.lower()


def test_check_still_open_succeeds_for_a_safe_url(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_resolve("93.184.216.34"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="Apply now for this great role.")

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: _RealClient(transport=httpx.MockTransport(handler)))
    is_open, reason = check_still_open("https://example.com/jobs/1")
    assert is_open is True


_LEAKY_URL = "https://user:hunter2@10.10.10.5/jobs?token=supersecret123"
_LEAKY_FRAGMENTS = (
    "hunter2",
    "supersecret123",
    "10.10.10.5",
    "user:hunter2",
    "token=supersecret123",
    _LEAKY_URL,
)


def test_check_still_open_sanitizes_httpx_timeout_note_and_logs(monkeypatch, caplog) -> None:
    """A timeout whose exception text contains a URL, credentials, query
    token, hostname, and internal IP must become a generic verification note.
    None of those values may appear in the note or in captured logs."""
    import logging

    from backend.services import job_verification_service as mod

    leaky = httpx.TimeoutException(
        f"timed out while requesting {_LEAKY_URL}",
        request=httpx.Request("GET", _LEAKY_URL),
    )

    def boom(*_a, **_k):
        raise leaky

    monkeypatch.setattr(mod, "fetch_url_safely", boom)
    with caplog.at_level(logging.DEBUG):
        is_open, reason = check_still_open("https://example.com/jobs/1")
    assert is_open is None
    haystack = f"{reason}\n{caplog.text}"
    for fragment in _LEAKY_FRAGMENTS:
        assert fragment not in haystack
    assert "could not reach" in reason.lower() or "could not confirm" in reason.lower()


def test_check_still_open_sanitizes_connection_error_note(monkeypatch, caplog) -> None:
    import logging

    from backend.services import job_verification_service as mod

    leaky = httpx.ConnectError(
        f"Failed to establish connection to {_LEAKY_URL} (response: 500 internal)",
        request=httpx.Request("GET", _LEAKY_URL),
    )

    def boom(*_a, **_k):
        raise leaky

    monkeypatch.setattr(mod, "fetch_url_safely", boom)
    with caplog.at_level(logging.DEBUG):
        is_open, reason = check_still_open("https://example.com/jobs/1")
    assert is_open is None
    haystack = f"{reason}\n{caplog.text}"
    for fragment in _LEAKY_FRAGMENTS:
        assert fragment not in haystack
    assert "500 internal" not in haystack.lower()


def test_verify_and_store_does_not_persist_raw_httpx_exception(monkeypatch) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.db.database import Base
    from backend.db.models import JobRecord
    from backend.services import job_verification_service as mod

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(mod, "SessionLocal", session_factory)

    leaky = httpx.TimeoutException(
        f"timed out while requesting {_LEAKY_URL}",
        request=httpx.Request("GET", _LEAKY_URL),
    )
    monkeypatch.setattr(
        mod,
        "fetch_url_safely",
        lambda *_a, **_k: (_ for _ in ()).throw(leaky),
    )

    with session_factory() as db:
        db.add(
            JobRecord(
                public_id="verify-sanitize-1",
                title="Software Engineer Intern",
                company="Aether Analytics",
                url="https://example.com/jobs/1",
                description="Build Python services that power analytics dashboards for our customers.",
                source="manual",
                status="discovered",
            )
        )
        db.commit()

    job = mod.verify_and_store("verify-sanitize-1")
    haystack = job.verification_notes or ""
    for fragment in _LEAKY_FRAGMENTS:
        assert fragment not in haystack

    with session_factory() as db:
        stored = db.query(JobRecord).filter(JobRecord.public_id == "verify-sanitize-1").one()
        persisted = stored.verification_notes or ""
    for fragment in _LEAKY_FRAGMENTS:
        assert fragment not in persisted
    assert "could not reach" in persisted.lower() or "could not confirm" in persisted.lower()
