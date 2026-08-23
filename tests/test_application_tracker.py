"""Application tracker and dashboard aggregation tests."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from backend.db.models import (
    ApplicationPackageRecord,
    ApplicationTrackerRecord,
    Candidate,
    FormFillAttemptRecord,
    InterviewPrepRecord,
    JobIntelligenceRecord,
    JobRecord,
    MatchScoreRecord,
    TargetPreference,
)
from backend.schemas.schemas import ApplicationTrackerUpdate
from backend.services.application_tracker_service import (
    TrackerInvalidTransitionError,
    TrackerJobNotFoundError,
    allowed_statuses_for,
    get_dashboard_summary,
    get_tracking,
    list_applications,
    update_tracking,
)
from backend.services.application_service import apply_approval, get_or_generate_application_package
from tests.mvp_helpers import insert_grounded_package
from backend.services.interview_service import generate_and_store_interview_prep
from backend.schemas.schemas import ApprovalRequest
import pytest


def _job(session, *, public_id: str = "job-track", status: str = "discovered") -> JobRecord:
    record = JobRecord(
        public_id=public_id,
        title="Backend Intern",
        company="Acme",
        url=f"https://example.com/jobs/{public_id}",
        description="Build APIs.",
        source="manual",
        status=status,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _candidate(session) -> Candidate:
    record = Candidate(
        name="Jordan Avery",
        email="jordan@example.com",
        skills=["Python"],
        projects=[{"name": "Demo", "description": "Python app", "technologies": ["Python"]}],
        experience=[{"title": "Intern", "company": "Acme", "highlights": ["Wrote Python tests."]}],
        education=[{"institution": "State University", "degree": "B.S.", "field": "Computer Science"}],
        certifications=[],
        strengths=["Backend"],
        evidence_links=[],
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def test_tracker_get_is_read_only(isolated_session) -> None:
    job = _job(isolated_session)
    item = get_tracking(isolated_session, job.public_id)
    assert item.status is None
    assert isolated_session.query(ApplicationTrackerRecord).count() == 0
    listed = list_applications(isolated_session)
    assert listed[0].tracker_status is None
    assert isolated_session.query(ApplicationTrackerRecord).count() == 0


def test_tracker_missing_job_404(isolated_session) -> None:
    with pytest.raises(TrackerJobNotFoundError):
        get_tracking(isolated_session, "missing")
    with pytest.raises(TrackerJobNotFoundError):
        update_tracking(
            isolated_session,
            "missing",
            ApplicationTrackerUpdate(status="saved"),
        )


def test_tracker_idempotent_creation(isolated_session) -> None:
    job = _job(isolated_session)
    first = update_tracking(isolated_session, job.public_id, ApplicationTrackerUpdate(status="saved"))
    second = update_tracking(isolated_session, job.public_id, ApplicationTrackerUpdate(status="saved"))
    assert first.status == "saved"
    assert second.status == "saved"
    assert isolated_session.query(ApplicationTrackerRecord).count() == 1


def test_tracker_unique_conflict_recovery(isolated_session, monkeypatch) -> None:
    job = _job(isolated_session)
    winner = ApplicationTrackerRecord(job_id=job.id, status="saved")
    isolated_session.add(winner)
    isolated_session.commit()

    real_query = isolated_session.query
    call_count = {"n": 0}

    class _EmptyQuery:
        def filter(self, *_a, **_k):
            return self

        def first(self):
            return None

    def query_that_misses_once(model):
        if model is ApplicationTrackerRecord:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return _EmptyQuery()
        return real_query(model)

    monkeypatch.setattr(isolated_session, "query", query_that_misses_once)
    result = update_tracking(
        isolated_session,
        job.public_id,
        ApplicationTrackerUpdate(status="pending_review"),
    )
    monkeypatch.undo()
    assert result.status == "pending_review"
    assert isolated_session.query(ApplicationTrackerRecord).count() == 1


def test_tracker_unique_index_rejects_direct_duplicate(isolated_session) -> None:
    job = _job(isolated_session)
    isolated_session.add(ApplicationTrackerRecord(job_id=job.id, status="saved"))
    isolated_session.commit()
    isolated_session.add(ApplicationTrackerRecord(job_id=job.id, status="applied"))
    with pytest.raises(IntegrityError):
        isolated_session.commit()
    isolated_session.rollback()


def test_invalid_status_transition(isolated_session) -> None:
    job = _job(isolated_session)
    update_tracking(isolated_session, job.public_id, ApplicationTrackerUpdate(status="applied"))
    with pytest.raises(TrackerInvalidTransitionError, match="applied"):
        update_tracking(isolated_session, job.public_id, ApplicationTrackerUpdate(status="saved"))


def test_tracker_status_change_does_not_mutate_approval_or_form_fill(isolated_session) -> None:
    job = _job(isolated_session)
    insert_grounded_package(isolated_session, job)
    apply_approval(
        isolated_session,
        job.public_id,
        ApprovalRequest(decision="approved", eligibility_confirmed=True, notes="ok"),
    )
    fill_count = isolated_session.query(FormFillAttemptRecord).count()
    update_tracking(isolated_session, job.public_id, ApplicationTrackerUpdate(status="applied"))
    refreshed = isolated_session.query(ApplicationPackageRecord).one()
    assert refreshed.approval_status == "approved"
    assert refreshed.eligibility_confirmed is True
    assert isolated_session.query(FormFillAttemptRecord).count() == fill_count


def test_dashboard_empty_state_zero_counts(isolated_session) -> None:
    summary = get_dashboard_summary(isolated_session)
    assert summary.profile_completion == 0
    assert summary.skills_count == 0
    assert summary.jobs_discovered == 0
    assert summary.jobs_verified == 0
    assert summary.high_matches == 0
    assert summary.ready_to_apply == 0
    assert summary.applications_saved == 0
    assert summary.applications_ready == 0
    assert summary.applications_applied == 0
    assert summary.interviews == 0


def test_dashboard_real_aggregation(isolated_session) -> None:
    candidate = _candidate(isolated_session)
    isolated_session.add(
        TargetPreference(
            candidate_id=candidate.id,
            target_roles=["Software Engineer Intern"],
            preferred_locations=["Remote"],
        )
    )
    verified = _job(isolated_session, public_id="verified-job", status="verified")
    discovered = _job(isolated_session, public_id="discovered-job", status="discovered")
    isolated_session.add(
        JobIntelligenceRecord(
            job_id=verified.id,
            required_skills=["Python"],
            preferred_skills=[],
            education_requirements=[],
            tech_stack=["Python"],
            responsibilities=[],
            likely_interview_focus=["Python"],
        )
    )
    isolated_session.add(
        MatchScoreRecord(
            job_id=verified.id,
            candidate_id=candidate.id,
            overall_score=88.0,
            skill_score=90.0,
            matched_skills=["Python"],
            partial_matches=[],
            missing_skills=[],
            recommendation="apply",
            rationale="Strong Python match.",
        )
    )
    isolated_session.add(
        MatchScoreRecord(
            job_id=discovered.id,
            candidate_id=candidate.id,
            overall_score=40.0,
            skill_score=40.0,
            matched_skills=[],
            partial_matches=[],
            missing_skills=["SQL"],
            recommendation="skip",
            rationale="Missing SQL.",
        )
    )
    isolated_session.commit()
    insert_grounded_package(isolated_session, verified, candidate=candidate)
    apply_approval(
        isolated_session,
        verified.public_id,
        ApprovalRequest(decision="approved", eligibility_confirmed=True),
    )
    update_tracking(
        isolated_session,
        verified.public_id,
        ApplicationTrackerUpdate(status="ready_to_apply"),
    )
    isolated_session.add(
        InterviewPrepRecord(
            job_id=verified.id,
            likely_questions=["What is Python?"],
            talking_points=["Use stored Python evidence."],
            gaps_to_address=[],
        )
    )
    isolated_session.commit()

    summary = get_dashboard_summary(isolated_session)
    assert summary.jobs_discovered == 2
    assert summary.jobs_verified == 1
    assert summary.high_matches == 1
    assert summary.ready_to_apply == 1
    assert summary.applications_ready == 1
    assert summary.applications_applied == 0
    assert summary.interviews == 0
    assert summary.skills_count == 1
    assert summary.profile_completion > 0
    assert summary.target_roles == ["Software Engineer Intern"]
    assert summary.preferred_location == "Remote"


def test_tracker_http_contracts(isolated_client) -> None:
    client, SessionLocal = isolated_client
    empty = client.get("/api/dashboard/summary")
    assert empty.status_code == 200
    assert empty.json()["jobs_discovered"] == 0

    listed = client.get("/api/applications")
    assert listed.status_code == 200
    assert listed.json() == []

    missing = client.get("/api/applications/nope/tracking")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Job not found."

    with SessionLocal() as db:
        _job(db, public_id="http-job")

    before = client.get("/api/applications/http-job/tracking")
    assert before.status_code == 200
    assert before.json()["status"] is None
    with SessionLocal() as db:
        assert db.query(ApplicationTrackerRecord).count() == 0

    created = client.patch(
        "/api/applications/http-job/tracking",
        json={"status": "saved"},
    )
    assert created.status_code == 200
    assert created.json()["status"] == "saved"
    assert "applied" not in created.json()["allowed_statuses"]
    assert "pending_review" in created.json()["allowed_statuses"]
    assert "saved" in created.json()["allowed_statuses"]

    invalid = client.patch(
        "/api/applications/http-job/tracking",
        json={"status": "applied"},
    )
    assert invalid.status_code == 409

    schema = client.patch(
        "/api/applications/http-job/tracking",
        json={"status": "not-a-status"},
    )
    assert schema.status_code == 422

    listed = client.get("/api/applications")
    assert listed.status_code == 200
    assert listed.json()[0]["allowed_statuses"] == created.json()["allowed_statuses"]


def test_allowed_statuses_contract_matches_backend_transitions() -> None:
    assert "applied" not in allowed_statuses_for("saved")
    assert allowed_statuses_for("saved")[0] == "saved"
    assert set(allowed_statuses_for(None)) == {
        "saved",
        "pending_review",
        "approved",
        "ready_to_apply",
        "applied",
        "interviewing",
        "rejected",
        "offer",
        "withdrawn",
    }


def test_interview_prep_record_alone_does_not_increment_interviews(isolated_session) -> None:
    job = _job(isolated_session, public_id="prep-only", status="verified")
    isolated_session.add(
        InterviewPrepRecord(
            job_id=job.id,
            likely_questions=["What is Python?"],
            talking_points=["Use stored Python evidence."],
            gaps_to_address=[],
        )
    )
    isolated_session.commit()
    update_tracking(isolated_session, job.public_id, ApplicationTrackerUpdate(status="saved"))
    summary = get_dashboard_summary(isolated_session)
    assert summary.interviews == 0


def test_tracker_interviewing_increments_interviews_once(isolated_session) -> None:
    first = _job(isolated_session, public_id="int-a")
    second = _job(isolated_session, public_id="int-b")
    update_tracking(isolated_session, first.public_id, ApplicationTrackerUpdate(status="interviewing"))
    update_tracking(isolated_session, second.public_id, ApplicationTrackerUpdate(status="applied"))
    isolated_session.add(
        InterviewPrepRecord(
            job_id=second.id,
            likely_questions=["Unused prep"],
            talking_points=[],
            gaps_to_address=[],
        )
    )
    isolated_session.commit()
    summary = get_dashboard_summary(isolated_session)
    assert summary.interviews == 1


def test_dashboard_reads_do_not_mutate_rows(isolated_session) -> None:
    job = _job(isolated_session)
    item = update_tracking(isolated_session, job.public_id, ApplicationTrackerUpdate(status="saved"))
    first = get_dashboard_summary(isolated_session)
    second = get_dashboard_summary(isolated_session)
    refreshed = isolated_session.query(ApplicationTrackerRecord).one()
    assert first == second
    assert refreshed.status == "saved"
    assert refreshed.updated_at == item.updated_at
    assert isolated_session.query(ApplicationTrackerRecord).count() == 1


def test_generating_interview_prep_does_not_change_tracker_status(isolated_session) -> None:
    candidate = _candidate(isolated_session)
    job = _job(isolated_session, public_id="prep-status", status="verified")
    isolated_session.add(
        JobIntelligenceRecord(
            job_id=job.id,
            required_skills=["Python"],
            preferred_skills=[],
            education_requirements=[],
            tech_stack=["Python"],
            seniority="intern",
            responsibilities=[],
            likely_interview_focus=["Python"],
        )
    )
    isolated_session.commit()
    update_tracking(isolated_session, job.public_id, ApplicationTrackerUpdate(status="saved"))
    generate_and_store_interview_prep(isolated_session, job.public_id)
    tracking = get_tracking(isolated_session, job.public_id)
    assert tracking.status == "saved"
    summary = get_dashboard_summary(isolated_session)
    assert summary.interviews == 0
    generate_and_store_interview_prep(isolated_session, job.public_id)
    assert get_tracking(isolated_session, job.public_id).status == "saved"
    assert isolated_session.query(InterviewPrepRecord).count() == 1
    _ = candidate
