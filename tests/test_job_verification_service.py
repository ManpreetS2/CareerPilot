"""Job Verification heuristics tests. check_still_open hits a live URL and is
covered by manual verification instead — everything here is pure logic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.schemas.schemas import Job
from backend.services.job_verification_service import (
    DEFAULT_STALE_AFTER_DAYS,
    _decide_verification,
    check_staleness,
    detect_suspicious_signals,
    verify_job,
)


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
