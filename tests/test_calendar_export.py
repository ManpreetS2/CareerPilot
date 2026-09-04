"""Calendar follow-up (.ics) export: RFC 5545 content correctness and the download route."""

from __future__ import annotations

from datetime import date

import pytest

from backend.db.models import ApplicationTrackerRecord, JobRecord
from backend.schemas.schemas import ApplicationTrackerUpdate
from backend.services.application_tracker_service import (
    ReminderNotSetError,
    TrackerJobNotFoundError,
    get_reminder_export_details,
    update_tracking,
)
from backend.services.calendar_export_service import build_reminder_ics, reminder_ics_filename
from tests.mvp_helpers import TEST_USER_ID, ensure_user


def _job(session, *, public_id: str = "job-cal", title: str = "Backend Intern", company: str = "Acme") -> JobRecord:
    record = JobRecord(
        public_id=public_id,
        title=title,
        company=company,
        url=f"https://example.com/jobs/{public_id}",
        description="Build APIs.",
        source="manual",
        status="discovered",
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _lines(ics_bytes: bytes) -> list[str]:
    text = ics_bytes.decode("utf-8")
    assert text.endswith("\r\n")
    return text.split("\r\n")[:-1]


class TestBuildReminderIcs:
    def test_produces_a_valid_all_day_vevent(self) -> None:
        ics = build_reminder_ics(
            job_public_id="job-1", job_title="Backend Intern", company="Acme", reminder_date=date(2026, 9, 20)
        )
        lines = _lines(ics)
        assert lines[0] == "BEGIN:VCALENDAR"
        assert lines[-1] == "END:VCALENDAR"
        assert "VERSION:2.0" in lines
        assert "BEGIN:VEVENT" in lines
        assert "DTSTART;VALUE=DATE:20260920" in lines
        # DATE-only DTEND is exclusive per RFC 5545 — the day after, not the same day.
        assert "DTEND;VALUE=DATE:20260921" in lines
        assert any(line.startswith("SUMMARY:Follow up: Backend Intern @ Acme") for line in lines)
        assert any(line.startswith("DTSTAMP:") and line.endswith("Z") for line in lines)

    def test_uid_is_deterministic_for_the_same_job_and_date(self) -> None:
        first = build_reminder_ics(job_public_id="job-1", job_title="A", company="B", reminder_date=date(2026, 1, 1))
        second = build_reminder_ics(job_public_id="job-1", job_title="A", company="B", reminder_date=date(2026, 1, 1))
        uid_first = next(line for line in _lines(first) if line.startswith("UID:"))
        uid_second = next(line for line in _lines(second) if line.startswith("UID:"))
        assert uid_first == uid_second
        assert "job-1" in uid_first
        assert "2026-01-01" in uid_first

    def test_uid_differs_for_a_different_job_or_date(self) -> None:
        base = build_reminder_ics(job_public_id="job-1", job_title="A", company="B", reminder_date=date(2026, 1, 1))
        other_job = build_reminder_ics(job_public_id="job-2", job_title="A", company="B", reminder_date=date(2026, 1, 1))
        other_date = build_reminder_ics(job_public_id="job-1", job_title="A", company="B", reminder_date=date(2026, 1, 2))
        assert base != other_job
        assert base != other_date

    def test_escapes_special_text_characters_and_newlines(self) -> None:
        ics = build_reminder_ics(
            job_public_id="job-1",
            job_title='Engineer, Backend; "Core" \\ Team\nSecond line',
            company="Acme",
            reminder_date=date(2026, 9, 20),
        )
        text = ics.decode("utf-8")
        # Raw text content must not appear unescaped, since a bare comma or
        # semicolon changes the meaning of the TEXT property in RFC 5545 and
        # a literal newline would break the record into invalid extra lines.
        assert "Engineer, Backend; \"Core\" \\ Team\nSecond line" not in text
        assert "Engineer\\, Backend\\; \"Core\" \\\\ Team\\nSecond line" in text
        # Confirm no unescaped newline mid-property: every physical CRLF line
        # is either a real property or a folded continuation (starts with a space).
        for line in _lines(ics):
            assert line == "" or line[0] == " " or ":" in line or line in ("BEGIN:VEVENT", "END:VEVENT")

    def test_folds_a_long_summary_line(self) -> None:
        long_title = "Senior Staff Principal Distinguished Software Engineering Manager"
        long_company = "A Very Long Multinational Technology Corporation Holdings Group"
        ics = build_reminder_ics(
            job_public_id="job-1", job_title=long_title, company=long_company, reminder_date=date(2026, 9, 20)
        )
        raw_lines = ics.decode("utf-8").split("\r\n")
        summary_start = next(i for i, line in enumerate(raw_lines) if line.startswith("SUMMARY:"))
        # A folded property's first physical line is at the fold limit, and
        # every continuation line begins with a single leading space and is
        # itself at or under the limit — collect all of them, however many.
        assert len(raw_lines[summary_start].encode("utf-8")) <= 75
        continuations = []
        i = summary_start + 1
        while i < len(raw_lines) and raw_lines[i].startswith(" "):
            assert len(raw_lines[i].encode("utf-8")) <= 75
            continuations.append(raw_lines[i][1:])
            i += 1
        assert continuations, "expected at least one folded continuation line"
        rejoined = raw_lines[summary_start][8:] + "".join(continuations)
        assert long_title in rejoined
        assert long_company in rejoined

    def test_does_not_fold_a_short_line(self) -> None:
        ics = build_reminder_ics(job_public_id="j", job_title="A", company="B", reminder_date=date(2026, 1, 1))
        for line in _lines(ics):
            if line.startswith("SUMMARY:"):
                assert line == "SUMMARY:Follow up: A @ B"


class TestReminderIcsFilename:
    def test_builds_a_readable_filename(self) -> None:
        assert reminder_ics_filename("Backend Intern", "Acme") == "Backend Intern Acme.ics"

    def test_strips_header_injection_and_slash_characters(self) -> None:
        # This is a suggested download filename in a Content-Disposition
        # value, not a filesystem path — the property that actually matters
        # is that it can't break out of the quoted header value or the
        # directory the browser saves into.
        name = reminder_ics_filename("Intern\r\nSet-Cookie: evil=1", "../../etc/passwd")
        assert "\r" not in name
        assert "\n" not in name
        assert '"' not in name
        assert "/" not in name

    def test_falls_back_when_stripped_to_empty(self) -> None:
        name = reminder_ics_filename("!!!", "???")
        assert name == "follow-up-reminder.ics"


class TestGetReminderExportDetails:
    def test_raises_when_job_does_not_exist(self, isolated_session) -> None:
        ensure_user(isolated_session, TEST_USER_ID)
        with pytest.raises(TrackerJobNotFoundError):
            get_reminder_export_details(isolated_session, "does-not-exist", TEST_USER_ID)

    def test_raises_when_no_tracker_row_exists(self, isolated_session) -> None:
        ensure_user(isolated_session, TEST_USER_ID)
        job = _job(isolated_session)
        with pytest.raises(ReminderNotSetError):
            get_reminder_export_details(isolated_session, job.public_id, TEST_USER_ID)

    def test_raises_when_tracker_row_has_no_reminder_date(self, isolated_session) -> None:
        ensure_user(isolated_session, TEST_USER_ID)
        job = _job(isolated_session)
        update_tracking(isolated_session, job.public_id, ApplicationTrackerUpdate(status="saved"), TEST_USER_ID)
        with pytest.raises(ReminderNotSetError):
            get_reminder_export_details(isolated_session, job.public_id, TEST_USER_ID)

    def test_returns_details_when_reminder_is_set(self, isolated_session) -> None:
        ensure_user(isolated_session, TEST_USER_ID)
        job = _job(isolated_session, title="Backend Intern", company="Acme")
        update_tracking(
            isolated_session,
            job.public_id,
            ApplicationTrackerUpdate(status="saved", reminder_date=date(2026, 9, 20)),
            TEST_USER_ID,
        )
        details = get_reminder_export_details(isolated_session, job.public_id, TEST_USER_ID)
        assert details.job_title == "Backend Intern"
        assert details.company == "Acme"
        assert details.reminder_date == date(2026, 9, 20)

    def test_does_not_leak_another_users_reminder(self, isolated_session) -> None:
        ensure_user(isolated_session, TEST_USER_ID)
        other_user_id = TEST_USER_ID + 1
        ensure_user(isolated_session, other_user_id)
        job = _job(isolated_session)
        update_tracking(
            isolated_session,
            job.public_id,
            ApplicationTrackerUpdate(status="saved", reminder_date=date(2026, 9, 20)),
            other_user_id,
        )
        with pytest.raises(ReminderNotSetError):
            get_reminder_export_details(isolated_session, job.public_id, TEST_USER_ID)


def test_download_route_returns_ics_with_correct_headers(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        job = _job(db, title="Backend Intern", company="Acme")
        update_tracking(
            db, job.public_id, ApplicationTrackerUpdate(status="saved", reminder_date=date(2026, 9, 20)), client.test_user_id
        )

    response = client.get(f"/api/applications/{job.public_id}/reminder.ics")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/calendar")
    assert ".ics" in response.headers["content-disposition"]
    assert response.content.startswith(b"BEGIN:VCALENDAR")
    assert b"DTSTART;VALUE=DATE:20260920" in response.content


def test_download_route_404s_when_job_does_not_exist(isolated_client) -> None:
    client, SessionLocal = isolated_client
    response = client.get("/api/applications/does-not-exist/reminder.ics")
    assert response.status_code == 404


def test_download_route_404s_when_no_reminder_is_set(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        job = _job(db)
    response = client.get(f"/api/applications/{job.public_id}/reminder.ics")
    assert response.status_code == 404


def test_download_route_404s_for_another_users_tracker_row(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        other_user_id = client.test_user_id + 1
        ensure_user(db, other_user_id)
        job = _job(db)
        update_tracking(
            db, job.public_id, ApplicationTrackerUpdate(status="saved", reminder_date=date(2026, 9, 20)), other_user_id
        )

    response = client.get(f"/api/applications/{job.public_id}/reminder.ics")
    assert response.status_code == 404


def test_download_route_requires_authentication(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        job = _job(db)
        update_tracking(
            db, job.public_id, ApplicationTrackerUpdate(status="saved", reminder_date=date(2026, 9, 20)), client.test_user_id
        )
    client.cookies.clear()
    response = client.get(f"/api/applications/{job.public_id}/reminder.ics")
    assert response.status_code == 401
