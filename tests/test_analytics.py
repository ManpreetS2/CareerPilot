"""Application Conversion Analytics: recording hooks and aggregation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from backend.db.models import (
    ApplicationEventRecord,
    ApplicationPackageRecord,
    ApplicationTrackerRecord,
)
from backend.schemas.schemas import ApplicationTrackerUpdate, ApprovalRequest
from backend.services.analytics_service import (
    SMALL_SAMPLE_THRESHOLD,
    build_conversion_analytics,
    record_event,
)
from backend.services.application_service import apply_approval, get_or_generate_application_package
from backend.services.application_tracker_service import update_tracking
from backend.services.saved_job_service import save_job
from tests.mvp_helpers import (
    TEST_USER_ID,
    ensure_user,
    fake_grounded_generator,
    insert_grounded_package,
    insert_job,
    insert_ready_profile,
    insert_score,
    seed_materials_prerequisites,
)


def _events(session, user_id: int = TEST_USER_ID) -> list[ApplicationEventRecord]:
    return (
        session.query(ApplicationEventRecord)
        .filter(ApplicationEventRecord.user_id == user_id)
        .order_by(ApplicationEventRecord.id.asc())
        .all()
    )


# --- Hook coverage: each hook records the real service functions calling it,
# not ApplicationEventRecord inserted directly, so a regression in the hook
# itself would be caught. ---


def test_save_job_records_a_saved_event(isolated_session) -> None:
    ensure_user(isolated_session, TEST_USER_ID)
    job = insert_job(isolated_session)
    save_job(isolated_session, TEST_USER_ID, job.public_id)
    events = _events(isolated_session)
    assert [e.event_type for e in events] == ["saved"]
    assert events[0].job_id == job.id


def test_saving_an_already_saved_job_does_not_duplicate_the_event(isolated_session) -> None:
    ensure_user(isolated_session, TEST_USER_ID)
    job = insert_job(isolated_session)
    save_job(isolated_session, TEST_USER_ID, job.public_id)
    save_job(isolated_session, TEST_USER_ID, job.public_id)
    assert len(_events(isolated_session)) == 1


def test_generating_materials_records_a_materials_generated_event(isolated_session) -> None:
    job, candidate = seed_materials_prerequisites(isolated_session)
    get_or_generate_application_package(
        isolated_session, job.public_id, TEST_USER_ID, generator=fake_grounded_generator
    )
    events = _events(isolated_session)
    assert [e.event_type for e in events] == ["materials_generated"]


def test_approving_materials_records_a_materials_approved_event(isolated_session) -> None:
    job, candidate = seed_materials_prerequisites(isolated_session)
    insert_grounded_package(isolated_session, job, candidate=candidate)
    apply_approval(
        isolated_session,
        job.public_id,
        TEST_USER_ID,
        ApprovalRequest(decision="approved", eligibility_confirmed=True),
    )
    events = _events(isolated_session)
    assert [e.event_type for e in events] == ["materials_approved"]


def test_rejecting_materials_does_not_record_an_approved_event(isolated_session) -> None:
    job, candidate = seed_materials_prerequisites(isolated_session)
    insert_grounded_package(isolated_session, job, candidate=candidate)
    apply_approval(isolated_session, job.public_id, TEST_USER_ID, ApprovalRequest(decision="rejected"))
    assert _events(isolated_session) == []


def test_tracker_status_change_records_an_event_for_tracked_statuses(isolated_session) -> None:
    ensure_user(isolated_session, TEST_USER_ID)
    job = insert_job(isolated_session)
    # A fresh tracker row may start at any status — a user logging an
    # application they found outside CareerPilot.
    update_tracking(isolated_session, job.public_id, ApplicationTrackerUpdate(status="applied"), TEST_USER_ID)
    assert [e.event_type for e in _events(isolated_session)] == ["applied"]


def test_tracker_transitions_only_record_events_for_tracked_statuses(isolated_session) -> None:
    ensure_user(isolated_session, TEST_USER_ID)
    job = insert_job(isolated_session)
    # saved and ready_to_apply are not in the tracked set — they're already
    # captured by the saved/materials hooks — only applied/interviewing/offer
    # should produce events here.
    for status in ("saved", "ready_to_apply", "applied", "interviewing", "offer"):
        update_tracking(isolated_session, job.public_id, ApplicationTrackerUpdate(status=status), TEST_USER_ID)
    assert [e.event_type for e in _events(isolated_session)] == ["applied", "interviewing", "offer"]


def test_re_setting_the_same_tracker_status_does_not_duplicate_the_event(isolated_session) -> None:
    ensure_user(isolated_session, TEST_USER_ID)
    job = insert_job(isolated_session)
    update_tracking(isolated_session, job.public_id, ApplicationTrackerUpdate(status="applied"), TEST_USER_ID)
    # Same status again (e.g. just updating the note) is an explicit no-op
    # transition per _transition_allowed — must not re-fire the event.
    update_tracking(
        isolated_session,
        job.public_id,
        ApplicationTrackerUpdate(status="applied", note="following up"),
        TEST_USER_ID,
    )
    assert [e.event_type for e in _events(isolated_session)] == ["applied"]


def test_tracker_integrity_error_recovery_records_the_event_exactly_once(isolated_session, monkeypatch) -> None:
    """Simulates the race where two requests both try to create the first
    tracker row for a job — the second hits IntegrityError and recovers by
    updating the row the first request just committed."""
    ensure_user(isolated_session, TEST_USER_ID)
    job = insert_job(isolated_session)

    real_commit = isolated_session.commit
    calls = {"n": 0}

    def flaky_commit():
        calls["n"] += 1
        if calls["n"] == 1:
            # Simulate a concurrent request having already inserted the row,
            # at a status "applied" can legally transition from.
            isolated_session.rollback()
            other = ApplicationTrackerRecord(job_id=job.id, user_id=TEST_USER_ID, status="ready_to_apply")
            isolated_session.add(other)
            real_commit()
            raise IntegrityError("unique constraint", None, None)
        return real_commit()

    monkeypatch.setattr(isolated_session, "commit", flaky_commit)
    update_tracking(isolated_session, job.public_id, ApplicationTrackerUpdate(status="applied"), TEST_USER_ID)
    assert [e.event_type for e in _events(isolated_session)] == ["applied"]


# --- Aggregation math. These seed ApplicationEventRecord rows directly with
# controlled timestamps — the hooks above already prove real callers reach
# record_event correctly; this is about build_conversion_analytics' own math. ---


def _seed_event(session, *, job, user_id: int, event_type: str, occurred_at: datetime) -> None:
    session.add(
        ApplicationEventRecord(job_id=job.id, user_id=user_id, event_type=event_type, occurred_at=occurred_at)
    )
    session.commit()


def test_empty_state_has_zeroed_funnel_and_no_breakdowns(isolated_session) -> None:
    insert_ready_profile(isolated_session)
    summary = build_conversion_analytics(isolated_session, TEST_USER_ID)
    assert [step.jobs_count for step in summary.funnel] == [0, 0, 0, 0, 0, 0]
    assert summary.by_source == []
    assert summary.by_match_score_band == []
    assert summary.median_days_saved_to_applied is None
    assert summary.rejected_count == 0


def test_funnel_counts_and_conversion_rates(isolated_session) -> None:
    candidate, _prefs = insert_ready_profile(isolated_session)
    base = datetime.now(timezone.utc)

    # Job A: full funnel through to offer.
    job_a = insert_job(isolated_session, public_id="job-a")
    for i, stage in enumerate(
        ["saved", "materials_generated", "materials_approved", "applied", "interviewing", "offer"]
    ):
        _seed_event(isolated_session, job=job_a, user_id=TEST_USER_ID, event_type=stage, occurred_at=base + timedelta(days=i))

    # Job B: saved and materials generated, never approved or applied.
    job_b = insert_job(isolated_session, public_id="job-b")
    _seed_event(isolated_session, job=job_b, user_id=TEST_USER_ID, event_type="saved", occurred_at=base)
    _seed_event(
        isolated_session, job=job_b, user_id=TEST_USER_ID, event_type="materials_generated", occurred_at=base
    )

    # Job C: saved, then rejected — never reached materials.
    job_c = insert_job(isolated_session, public_id="job-c")
    _seed_event(isolated_session, job=job_c, user_id=TEST_USER_ID, event_type="saved", occurred_at=base)
    _seed_event(isolated_session, job=job_c, user_id=TEST_USER_ID, event_type="rejected", occurred_at=base)

    summary = build_conversion_analytics(isolated_session, TEST_USER_ID)
    counts = {step.stage: step.jobs_count for step in summary.funnel}
    assert counts == {
        "saved": 3,
        "materials_generated": 2,
        "materials_approved": 1,
        "applied": 1,
        "interviewing": 1,
        "offer": 1,
    }
    rates = {step.stage: step.conversion_from_previous for step in summary.funnel}
    assert rates["saved"] is None
    assert rates["materials_generated"] == pytest.approx(round(2 / 3, 3))
    assert rates["materials_approved"] == pytest.approx(round(1 / 2, 3))
    assert rates["applied"] == pytest.approx(1.0)
    assert summary.rejected_count == 1
    assert summary.withdrawn_count == 0


def test_median_days_between_stages(isolated_session) -> None:
    insert_ready_profile(isolated_session)
    base = datetime.now(timezone.utc)

    for public_id, saved_offset, applied_offset in [("job-1", 0, 2), ("job-2", 0, 4), ("job-3", 0, 10)]:
        job = insert_job(isolated_session, public_id=public_id)
        _seed_event(
            isolated_session,
            job=job,
            user_id=TEST_USER_ID,
            event_type="saved",
            occurred_at=base + timedelta(days=saved_offset),
        )
        _seed_event(
            isolated_session,
            job=job,
            user_id=TEST_USER_ID,
            event_type="applied",
            occurred_at=base + timedelta(days=applied_offset),
        )

    summary = build_conversion_analytics(isolated_session, TEST_USER_ID)
    assert summary.median_days_saved_to_applied == pytest.approx(4.0)
    assert summary.median_days_applied_to_interviewing is None


def test_small_sample_is_labeled(isolated_session) -> None:
    insert_ready_profile(isolated_session)
    base = datetime.now(timezone.utc)
    assert SMALL_SAMPLE_THRESHOLD > 1
    job = insert_job(isolated_session, public_id="lone-job")
    _seed_event(isolated_session, job=job, user_id=TEST_USER_ID, event_type="saved", occurred_at=base)
    _seed_event(isolated_session, job=job, user_id=TEST_USER_ID, event_type="applied", occurred_at=base)

    summary = build_conversion_analytics(isolated_session, TEST_USER_ID)
    assert len(summary.by_source) == 1
    assert summary.by_source[0].total_count == 1
    assert summary.by_source[0].small_sample is True


def test_breakdown_by_source_and_match_score_band(isolated_session) -> None:
    candidate, _prefs = insert_ready_profile(isolated_session)
    base = datetime.now(timezone.utc)

    job_manual = insert_job(isolated_session, public_id="job-manual")
    job_greenhouse = insert_job(isolated_session, public_id="job-greenhouse")
    job_greenhouse.source = "greenhouse"
    isolated_session.commit()

    for job in (job_manual, job_greenhouse):
        _seed_event(isolated_session, job=job, user_id=TEST_USER_ID, event_type="saved", occurred_at=base)
    _seed_event(isolated_session, job=job_greenhouse, user_id=TEST_USER_ID, event_type="applied", occurred_at=base)

    insert_score(isolated_session, job_manual, candidate, overall_score=40.0)
    insert_score(isolated_session, job_greenhouse, candidate, overall_score=90.0)

    summary = build_conversion_analytics(isolated_session, TEST_USER_ID)

    by_source = {b.label: b for b in summary.by_source}
    assert by_source["manual"].applied_count == 0
    assert by_source["manual"].total_count == 1
    assert by_source["greenhouse"].applied_count == 1
    assert by_source["greenhouse"].applied_rate == pytest.approx(1.0)

    by_band = {b.label: b for b in summary.by_match_score_band}
    assert by_band["Below 50"].applied_count == 0
    assert by_band["85+"].applied_count == 1


def test_notice_flags_activity_older_than_earliest_recorded_event(isolated_session) -> None:
    ensure_user(isolated_session, TEST_USER_ID)
    insert_ready_profile(isolated_session)
    job = insert_job(isolated_session)
    old_tracker = ApplicationTrackerRecord(
        job_id=job.id,
        user_id=TEST_USER_ID,
        status="applied",
        created_at=datetime.now(timezone.utc) - timedelta(days=30),
    )
    isolated_session.add(old_tracker)
    isolated_session.commit()

    _seed_event(
        isolated_session, job=job, user_id=TEST_USER_ID, event_type="saved", occurred_at=datetime.now(timezone.utc)
    )

    summary = build_conversion_analytics(isolated_session, TEST_USER_ID)
    assert summary.notice is not None
    assert "predate" in summary.notice


def test_record_event_tolerates_a_repeated_event_type_for_the_same_job(isolated_session) -> None:
    # record_event() only stages the row — real callers fold it into their
    # own commit (see application_tracker_service.update_tracking), so this
    # direct unit test commits explicitly after each call.
    ensure_user(isolated_session, TEST_USER_ID)
    job = insert_job(isolated_session)
    record_event(isolated_session, job_pk=job.id, user_id=TEST_USER_ID, event_type="interviewing")
    isolated_session.commit()
    record_event(isolated_session, job_pk=job.id, user_id=TEST_USER_ID, event_type="interviewing")
    isolated_session.commit()
    assert len(_events(isolated_session)) == 2


def test_analytics_route_requires_a_ready_profile(isolated_client) -> None:
    client, SessionLocal = isolated_client
    response = client.get("/api/analytics/summary")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "profile_required"


def test_analytics_route_returns_a_summary_for_a_ready_profile(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        insert_ready_profile(db, user_id=client.test_user_id)

    response = client.get("/api/analytics/summary")
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["funnel"]) == 6
    assert body["funnel"][0]["stage"] == "saved"
