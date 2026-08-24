"""Approval Agent tests. Uses the shared isolated_session/isolated_client
fixtures (tests/conftest.py) — never touches data/careerpilot.db.

Split into service-level tests (mechanism, direct function calls) and
route-level tests (HTTP contract via TestClient)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from backend.db.models import ApplicationPackageRecord, Candidate, JobRecord
from backend.schemas.schemas import ApprovalRequest
from backend.services.application_service import apply_approval, get_or_generate_application_package, get_stored_application_package
from tests.mvp_helpers import fake_grounded_generator, insert_grounded_package, seed_materials_prerequisites


def _job(session, *, public_id: str = "manual-abc123", title: str = "Software Engineer Intern") -> JobRecord:
    record = JobRecord(
        public_id=public_id,
        title=title,
        company="Acme",
        url=f"https://example.com/jobs/{public_id}",
        description="Build things.",
        source="manual",
        status="discovered",
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _candidate(session, *, name: str = "Jordan Avery Quill") -> Candidate:
    record = Candidate(
        name=name,
        email="jordan@example.com",
        phone="+1-555-0101",
        skills=["Python"],
        projects=[],
        experience=[],
        education=[],
        certifications=[],
        strengths=[],
        evidence_links=[],
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


# ---------------------------------------------------------------------------
# Generation: creation, idempotency, missing job
# ---------------------------------------------------------------------------


def test_generate_materials_creates_and_persists_a_package(isolated_session) -> None:
    seed_materials_prerequisites(isolated_session)
    package = get_or_generate_application_package(isolated_session, "manual-abc123", generator=fake_grounded_generator)
    assert package.job_id == "manual-abc123"
    assert package.approval_status == "pending_review"
    assert len(package.tailored_bullets) > 0
    assert package.eligibility_confirmed is False
    assert package.eligibility_notes is None
    assert package.decision_notes is None


def test_generate_materials_is_idempotent_not_regenerated(isolated_session) -> None:
    seed_materials_prerequisites(isolated_session)
    first = get_or_generate_application_package(isolated_session, "manual-abc123", generator=fake_grounded_generator)
    second = get_or_generate_application_package(isolated_session, "manual-abc123", generator=fake_grounded_generator)
    assert first.tailored_bullets == second.tailored_bullets
    assert first.cover_letter_draft == second.cover_letter_draft
    assert isolated_session.query(ApplicationPackageRecord).count() == 1


def test_generate_materials_missing_job_404s(isolated_session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_or_generate_application_package(isolated_session, "does-not-exist")
    assert exc_info.value.status_code == 404


def test_generate_materials_independent_across_jobs(isolated_session) -> None:
    seed_materials_prerequisites(isolated_session, public_id="job-a", title="Backend Intern")
    seed_materials_prerequisites(isolated_session, public_id="job-b", title="Frontend Intern")
    a = get_or_generate_application_package(isolated_session, "job-a", generator=fake_grounded_generator)
    b = get_or_generate_application_package(isolated_session, "job-b", generator=fake_grounded_generator)
    assert a.job_id != b.job_id
    assert "Backend" not in "".join(b.tailored_bullets + [b.cover_letter_draft or ""])
    assert isolated_session.query(ApplicationPackageRecord).count() == 2


def test_generate_materials_associates_current_candidate(isolated_session) -> None:
    job, candidate = seed_materials_prerequisites(isolated_session)
    get_or_generate_application_package(isolated_session, "manual-abc123", generator=fake_grounded_generator)
    record = isolated_session.query(ApplicationPackageRecord).first()
    assert record.candidate_id == candidate.id


def test_generate_materials_candidate_id_none_without_a_candidate(isolated_session) -> None:
    job = _job(isolated_session)
    insert_grounded_package(isolated_session, job)
    record = isolated_session.query(ApplicationPackageRecord).first()
    assert record.candidate_id is None


# ---------------------------------------------------------------------------
# Race-safety: unique index + recovery path
# ---------------------------------------------------------------------------


def test_unique_index_rejects_a_direct_duplicate_insert(isolated_session) -> None:
    job = _job(isolated_session)
    isolated_session.add(
        ApplicationPackageRecord(job_id=job.id, tailored_bullets=[], source_traceability_notes=[])
    )
    isolated_session.commit()
    isolated_session.add(
        ApplicationPackageRecord(job_id=job.id, tailored_bullets=[], source_traceability_notes=[])
    )
    with pytest.raises(IntegrityError):
        isolated_session.commit()
    isolated_session.rollback()


def test_generate_materials_recovers_from_a_lost_race_instead_of_erroring(isolated_session, monkeypatch) -> None:
    """Simulates two concurrent generate calls for the same job: this
    session's own existence check misses (as if a concurrent request hadn't
    committed yet from its point of view), but a winner row is already
    committed by the time this session's insert runs — it must recover the
    winner's data instead of raising or creating a duplicate row."""
    job, candidate = seed_materials_prerequisites(isolated_session)
    winner = ApplicationPackageRecord(
        job_id=job.id,
        candidate_id=candidate.id,
        tailored_bullets=["winner bullet"],
        cover_letter_draft="winner letter",
        recruiter_message="winner message",
        source_traceability_notes=["winner note"],
        approval_status="pending_review",
        grounded=True,
    )
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
        if model is ApplicationPackageRecord:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return _EmptyQuery()
        return real_query(model)

    monkeypatch.setattr(isolated_session, "query", query_that_misses_once)

    result = get_or_generate_application_package(
        isolated_session, "manual-abc123", generator=fake_grounded_generator
    )
    assert result.tailored_bullets == ["winner bullet"]
    assert result.cover_letter_draft == "winner letter"
    monkeypatch.undo()
    assert isolated_session.query(ApplicationPackageRecord).count() == 1


# ---------------------------------------------------------------------------
# JSON column mutation tracking (MutableList)
# ---------------------------------------------------------------------------


def test_tailored_bullets_in_place_mutation_persists(isolated_session, isolated_engine) -> None:
    from sqlalchemy.orm import sessionmaker

    job = _job(isolated_session)
    record = ApplicationPackageRecord(job_id=job.id, tailored_bullets=["first"], source_traceability_notes=[])
    isolated_session.add(record)
    isolated_session.commit()

    record.tailored_bullets.append("second")
    isolated_session.commit()

    fresh_session = sessionmaker(bind=isolated_engine)()
    try:
        reloaded = fresh_session.query(ApplicationPackageRecord).filter_by(job_id=job.id).first()
        assert reloaded.tailored_bullets == ["first", "second"]
    finally:
        fresh_session.close()


def test_source_traceability_notes_in_place_mutation_persists(isolated_session, isolated_engine) -> None:
    from sqlalchemy.orm import sessionmaker

    job = _job(isolated_session)
    record = ApplicationPackageRecord(job_id=job.id, tailored_bullets=[], source_traceability_notes=["a"])
    isolated_session.add(record)
    isolated_session.commit()

    record.source_traceability_notes[0] = "b"
    isolated_session.commit()

    fresh_session = sessionmaker(bind=isolated_engine)()
    try:
        reloaded = fresh_session.query(ApplicationPackageRecord).filter_by(job_id=job.id).first()
        assert reloaded.source_traceability_notes == ["b"]
    finally:
        fresh_session.close()


# ---------------------------------------------------------------------------
# Approval gate: eligibility confirmation
# ---------------------------------------------------------------------------


def test_approve_without_eligibility_confirmation_is_rejected(isolated_session) -> None:
    job = _job(isolated_session)
    insert_grounded_package(isolated_session, job)
    with pytest.raises(HTTPException) as exc_info:
        apply_approval(isolated_session, "manual-abc123", ApprovalRequest(decision="approved"))
    assert exc_info.value.status_code == 422


def test_approve_with_eligibility_confirmation_succeeds(isolated_session) -> None:
    job = _job(isolated_session)
    candidate = _candidate(isolated_session)
    insert_grounded_package(isolated_session, job, candidate=candidate)
    result = apply_approval(
        isolated_session,
        "manual-abc123",
        ApprovalRequest(decision="approved", eligibility_confirmed=True, eligibility_notes="all good"),
    )
    assert result.approval_status == "approved"

    package = get_stored_application_package(isolated_session, "manual-abc123")
    assert package.approval_status == "approved"
    assert package.eligibility_confirmed is True
    assert package.eligibility_notes == "all good"


def test_reject_does_not_require_eligibility_confirmation(isolated_session) -> None:
    job = _job(isolated_session)
    insert_grounded_package(isolated_session, job)
    result = apply_approval(isolated_session, "manual-abc123", ApprovalRequest(decision="rejected"))
    assert result.approval_status == "rejected"


def test_edit_requested_does_not_require_eligibility_confirmation(isolated_session) -> None:
    job = _job(isolated_session)
    insert_grounded_package(isolated_session, job)
    result = apply_approval(isolated_session, "manual-abc123", ApprovalRequest(decision="edit_requested"))
    assert result.approval_status == "edit_requested"


def test_approve_without_generated_materials_conflicts(isolated_session) -> None:
    _job(isolated_session)
    with pytest.raises(HTTPException) as exc_info:
        apply_approval(isolated_session, "manual-abc123", ApprovalRequest(decision="rejected"))
    assert exc_info.value.status_code == 409


def test_approve_missing_job_404s(isolated_session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        apply_approval(isolated_session, "does-not-exist", ApprovalRequest(decision="rejected"))
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Regression coverage: the shared grounded-package gate (is_package_ready_for_apply)
# ---------------------------------------------------------------------------


def test_approve_rejects_an_ungrounded_package(isolated_session) -> None:
    """Regression test for a real gap: a package with grounded=False could
    still be approved and then pass _load_approved_application() in Form
    Fill. apply_approval() must reject the approval itself, not rely on
    Form Fill to catch it later."""
    job = _job(isolated_session)
    candidate = _candidate(isolated_session)
    record = ApplicationPackageRecord(
        job_id=job.id,
        candidate_id=candidate.id,
        tailored_bullets=["A bullet."],
        cover_letter_draft="Dear team,",
        source_traceability_notes=[],
        approval_status="pending_review",
        grounded=False,
    )
    isolated_session.add(record)
    isolated_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        apply_approval(
            isolated_session, "manual-abc123", ApprovalRequest(decision="approved", eligibility_confirmed=True)
        )
    assert exc_info.value.status_code == 409
    isolated_session.refresh(record)
    assert record.approval_status == "pending_review"  # unchanged, not silently approved


def test_approve_rejects_a_blank_package(isolated_session) -> None:
    """grounded=True alone isn't enough — a package with no real content
    (empty bullets and no cover letter) must not be approvable either."""
    job = _job(isolated_session)
    candidate = _candidate(isolated_session)
    record = ApplicationPackageRecord(
        job_id=job.id,
        candidate_id=candidate.id,
        tailored_bullets=[],
        cover_letter_draft=None,
        source_traceability_notes=[],
        approval_status="pending_review",
        grounded=True,
    )
    isolated_session.add(record)
    isolated_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        apply_approval(
            isolated_session, "manual-abc123", ApprovalRequest(decision="approved", eligibility_confirmed=True)
        )
    assert exc_info.value.status_code == 409


def test_approve_rejects_a_wrong_candidate_package(isolated_session) -> None:
    """A package generated against a candidate profile that's since been
    superseded by a fresh resume upload must not be approvable against the
    new, current candidate."""
    job = _job(isolated_session)
    stale_candidate = _candidate(isolated_session, name="Stale Candidate")
    insert_grounded_package(isolated_session, job, candidate=stale_candidate)
    _candidate(isolated_session, name="Current Candidate")  # now the current candidate

    with pytest.raises(HTTPException) as exc_info:
        apply_approval(
            isolated_session, "manual-abc123", ApprovalRequest(decision="approved", eligibility_confirmed=True)
        )
    assert exc_info.value.status_code == 409


def test_reject_and_edit_requested_remain_allowed_on_an_ungrounded_package(isolated_session) -> None:
    """The gate only blocks approval — a reviewer must still be able to
    reject or request edits on a bad package (the corrective action for
    exactly this situation)."""
    job = _job(isolated_session)
    candidate = _candidate(isolated_session)
    record = ApplicationPackageRecord(
        job_id=job.id,
        candidate_id=candidate.id,
        tailored_bullets=["A bullet."],
        cover_letter_draft="Dear team,",
        source_traceability_notes=[],
        approval_status="pending_review",
        grounded=False,
    )
    isolated_session.add(record)
    isolated_session.commit()

    rejected = apply_approval(isolated_session, "manual-abc123", ApprovalRequest(decision="rejected"))
    assert rejected.approval_status == "rejected"

    record.approval_status = "pending_review"
    isolated_session.commit()
    edited = apply_approval(isolated_session, "manual-abc123", ApprovalRequest(decision="edit_requested"))
    assert edited.approval_status == "edit_requested"


def test_reapproving_stays_confirmed(isolated_session) -> None:
    job = _job(isolated_session)
    candidate = _candidate(isolated_session)
    insert_grounded_package(isolated_session, job, candidate=candidate)
    apply_approval(isolated_session, "manual-abc123", ApprovalRequest(decision="approved", eligibility_confirmed=True))
    result = apply_approval(
        isolated_session, "manual-abc123", ApprovalRequest(decision="approved", eligibility_confirmed=True)
    )
    assert result.approval_status == "approved"
    package = get_stored_application_package(isolated_session, "manual-abc123")
    assert package.eligibility_confirmed is True


# ---------------------------------------------------------------------------
# Regression coverage: eligibility_confirmed must never be silently reset
# ---------------------------------------------------------------------------


def test_edit_request_after_approval_does_not_clear_eligibility_confirmed(isolated_session) -> None:
    job = _job(isolated_session)
    candidate = _candidate(isolated_session)
    insert_grounded_package(isolated_session, job, candidate=candidate)
    apply_approval(isolated_session, "manual-abc123", ApprovalRequest(decision="approved", eligibility_confirmed=True))

    # Edit request with the schema's default eligibility_confirmed=False —
    # this must not downgrade the confirmation that was already recorded.
    apply_approval(isolated_session, "manual-abc123", ApprovalRequest(decision="edit_requested"))

    package = get_stored_application_package(isolated_session, "manual-abc123")
    assert package.approval_status == "edit_requested"
    assert package.eligibility_confirmed is True


def test_reject_after_approval_does_not_clear_eligibility_confirmed(isolated_session) -> None:
    job = _job(isolated_session)
    candidate = _candidate(isolated_session)
    insert_grounded_package(isolated_session, job, candidate=candidate)
    apply_approval(isolated_session, "manual-abc123", ApprovalRequest(decision="approved", eligibility_confirmed=True))
    apply_approval(isolated_session, "manual-abc123", ApprovalRequest(decision="rejected"))

    package = get_stored_application_package(isolated_session, "manual-abc123")
    assert package.approval_status == "rejected"
    assert package.eligibility_confirmed is True


def test_omitting_notes_fields_does_not_clear_previously_set_values(isolated_session) -> None:
    """A decision that never mentions eligibility_notes/notes at all must
    leave whatever was already stored alone — omitted and explicitly-empty
    are different things, even though Pydantic defaults both to None/""."""
    job = _job(isolated_session)
    candidate = _candidate(isolated_session)
    insert_grounded_package(isolated_session, job, candidate=candidate)
    apply_approval(
        isolated_session,
        "manual-abc123",
        ApprovalRequest(
            decision="approved",
            eligibility_confirmed=True,
            eligibility_notes="needs sponsorship",
            notes="initial review",
        ),
    )

    # This decision's payload never sets eligibility_notes or notes at all —
    # constructed the same way FastAPI would from a JSON body missing those
    # keys (Pydantic defaults kick in, model_fields_set does not include
    # them).
    apply_approval(isolated_session, "manual-abc123", ApprovalRequest(decision="edit_requested"))

    package = get_stored_application_package(isolated_session, "manual-abc123")
    assert package.approval_status == "edit_requested"
    assert package.eligibility_notes == "needs sponsorship"
    assert package.decision_notes == "initial review"


def test_edit_request_never_sets_eligibility_confirmed_true(isolated_session) -> None:
    """edit_requested/rejected can't set eligibility_confirmed at all —
    only an approval (which requires it) can, so a caller can't sneak a
    confirmation through a decision type that doesn't require one."""
    job = _job(isolated_session)
    insert_grounded_package(isolated_session, job)
    apply_approval(
        isolated_session, "manual-abc123", ApprovalRequest(decision="edit_requested", eligibility_confirmed=True)
    )
    package = get_stored_application_package(isolated_session, "manual-abc123")
    assert package.eligibility_confirmed is False


# ---------------------------------------------------------------------------
# Regression coverage: notes fields (eligibility_notes, decision_notes)
# ---------------------------------------------------------------------------


def test_eligibility_notes_can_be_set_then_cleared(isolated_session) -> None:
    job = _job(isolated_session)
    candidate = _candidate(isolated_session)
    insert_grounded_package(isolated_session, job, candidate=candidate)
    apply_approval(
        isolated_session,
        "manual-abc123",
        ApprovalRequest(decision="approved", eligibility_confirmed=True, eligibility_notes="needs sponsorship"),
    )
    package = get_stored_application_package(isolated_session, "manual-abc123")
    assert package.eligibility_notes == "needs sponsorship"

    # Clearing: an empty string must actually clear it, not be ignored.
    apply_approval(
        isolated_session,
        "manual-abc123",
        ApprovalRequest(decision="approved", eligibility_confirmed=True, eligibility_notes=""),
    )
    package = get_stored_application_package(isolated_session, "manual-abc123")
    assert package.eligibility_notes is None


def test_eligibility_notes_can_be_updated_on_a_non_approve_decision(isolated_session) -> None:
    job = _job(isolated_session)
    insert_grounded_package(isolated_session, job)
    apply_approval(
        isolated_session,
        "manual-abc123",
        ApprovalRequest(decision="edit_requested", eligibility_notes="flag for legal review"),
    )
    package = get_stored_application_package(isolated_session, "manual-abc123")
    assert package.eligibility_notes == "flag for legal review"


def test_decision_notes_persisted_for_each_decision_type(isolated_session) -> None:
    job = _job(isolated_session)
    insert_grounded_package(isolated_session, job)

    apply_approval(isolated_session, "manual-abc123", ApprovalRequest(decision="edit_requested", notes="rewrite bullet 2"))
    package = get_stored_application_package(isolated_session, "manual-abc123")
    assert package.decision_notes == "rewrite bullet 2"

    apply_approval(isolated_session, "manual-abc123", ApprovalRequest(decision="rejected", notes="not a fit"))
    package = get_stored_application_package(isolated_session, "manual-abc123")
    assert package.decision_notes == "not a fit"


def test_decision_notes_can_be_cleared(isolated_session) -> None:
    job = _job(isolated_session)
    insert_grounded_package(isolated_session, job)
    apply_approval(isolated_session, "manual-abc123", ApprovalRequest(decision="edit_requested", notes="fix typo"))
    apply_approval(isolated_session, "manual-abc123", ApprovalRequest(decision="edit_requested", notes=""))
    package = get_stored_application_package(isolated_session, "manual-abc123")
    assert package.decision_notes is None


def test_notes_round_trip_unicode_and_special_characters(isolated_session) -> None:
    job = _job(isolated_session)
    candidate = _candidate(isolated_session)
    insert_grounded_package(isolated_session, job, candidate=candidate)
    tricky = "Needs H-1B sponsorship — café résumé 日本語 <script>alert(1)</script> \"quoted\""
    apply_approval(
        isolated_session,
        "manual-abc123",
        ApprovalRequest(decision="approved", eligibility_confirmed=True, eligibility_notes=tricky, notes=tricky),
    )
    package = get_stored_application_package(isolated_session, "manual-abc123")
    assert package.eligibility_notes == tricky
    assert package.decision_notes == tricky


def test_full_decision_lifecycle_preserves_expected_state(isolated_session) -> None:
    job = _job(isolated_session)
    candidate = _candidate(isolated_session)
    insert_grounded_package(isolated_session, job, candidate=candidate)

    apply_approval(isolated_session, "manual-abc123", ApprovalRequest(decision="edit_requested", notes="fix intro"))
    package = get_stored_application_package(isolated_session, "manual-abc123")
    assert package.approval_status == "edit_requested"
    assert package.eligibility_confirmed is False

    apply_approval(
        isolated_session,
        "manual-abc123",
        ApprovalRequest(decision="approved", eligibility_confirmed=True, eligibility_notes="confirmed"),
    )
    package = get_stored_application_package(isolated_session, "manual-abc123")
    assert package.approval_status == "approved"
    assert package.eligibility_confirmed is True
    assert package.eligibility_notes == "confirmed"
    # This approve call's payload never mentioned `notes` at all, so the
    # edit-request note from the previous step is left untouched rather
    # than silently cleared — notes only change when a caller explicitly
    # sends a value for that field.
    assert package.decision_notes == "fix intro"

    apply_approval(isolated_session, "manual-abc123", ApprovalRequest(decision="rejected", notes="changed mind"))
    package = get_stored_application_package(isolated_session, "manual-abc123")
    assert package.approval_status == "rejected"
    assert package.eligibility_confirmed is True
    assert package.decision_notes == "changed mind"


# ---------------------------------------------------------------------------
# Route-level tests: real HTTP contract via TestClient
# ---------------------------------------------------------------------------


def test_generate_materials_route_404s_for_unknown_job(isolated_client) -> None:
    client, _SessionLocal = isolated_client
    response = client.post("/api/jobs/does-not-exist/generate-materials")
    assert response.status_code == 404


def test_generate_materials_route_returns_persisted_shape(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        seed_materials_prerequisites(db)
    client.app.state.application_materials_generator = fake_grounded_generator
    response = client.post("/api/jobs/manual-abc123/generate-materials")
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == "manual-abc123"
    assert body["approval_status"] == "pending_review"
    assert body["eligibility_confirmed"] is False
    assert isinstance(body["tailored_bullets"], list)


def test_generate_materials_route_is_idempotent(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        seed_materials_prerequisites(db)
    client.app.state.application_materials_generator = fake_grounded_generator
    first = client.post("/api/jobs/manual-abc123/generate-materials").json()
    second = client.post("/api/jobs/manual-abc123/generate-materials").json()
    assert first["tailored_bullets"] == second["tailored_bullets"]
    with SessionLocal() as db:
        assert db.query(ApplicationPackageRecord).count() == 1


def test_approve_route_without_materials_returns_409(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        _job(db)
    response = client.post("/api/jobs/manual-abc123/approve", json={"decision": "rejected"})
    assert response.status_code == 409


def test_approve_route_without_eligibility_confirmed_returns_422(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        seed_materials_prerequisites(db)
    client.app.state.application_materials_generator = fake_grounded_generator
    client.post("/api/jobs/manual-abc123/generate-materials")
    response = client.post("/api/jobs/manual-abc123/approve", json={"decision": "approved"})
    assert response.status_code == 422
    assert "confirm" in response.json()["detail"].lower()


def test_approve_route_with_eligibility_confirmed_returns_200(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        seed_materials_prerequisites(db)
    client.app.state.application_materials_generator = fake_grounded_generator
    client.post("/api/jobs/manual-abc123/generate-materials")
    response = client.post(
        "/api/jobs/manual-abc123/approve",
        json={"decision": "approved", "eligibility_confirmed": True, "eligibility_notes": "clear"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["approval_status"] == "approved"


def test_approve_route_rejects_invalid_decision_value(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        seed_materials_prerequisites(db)
    client.app.state.application_materials_generator = fake_grounded_generator
    client.post("/api/jobs/manual-abc123/generate-materials")
    response = client.post("/api/jobs/manual-abc123/approve", json={"decision": "maybe"})
    assert response.status_code == 422


def test_approve_route_requires_decision_field(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        seed_materials_prerequisites(db)
    client.app.state.application_materials_generator = fake_grounded_generator
    client.post("/api/jobs/manual-abc123/generate-materials")
    response = client.post("/api/jobs/manual-abc123/approve", json={})
    assert response.status_code == 422


def test_approve_route_missing_job_returns_404(isolated_client) -> None:
    client, _SessionLocal = isolated_client
    response = client.post("/api/jobs/does-not-exist/approve", json={"decision": "rejected"})
    assert response.status_code == 404


def test_full_route_flow_generate_then_approve_then_regenerate_reflects_state(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        seed_materials_prerequisites(db)
    client.app.state.application_materials_generator = fake_grounded_generator

    generated = client.post("/api/jobs/manual-abc123/generate-materials").json()
    assert generated["approval_status"] == "pending_review"

    approved = client.post(
        "/api/jobs/manual-abc123/approve",
        json={
            "decision": "approved",
            "eligibility_confirmed": True,
            "eligibility_notes": "sponsorship confirmed",
            "notes": "looks good",
        },
    )
    assert approved.status_code == 200

    reread = client.post("/api/jobs/manual-abc123/generate-materials").json()
    assert reread["approval_status"] == "approved"
    assert reread["eligibility_confirmed"] is True
    assert reread["eligibility_notes"] == "sponsorship confirmed"
    assert reread["decision_notes"] == "looks good"


def test_route_omitting_notes_keys_entirely_does_not_clear_them(isolated_client) -> None:
    """Regression test for a real bug caught in live testing: a JSON body
    that never includes eligibility_notes/notes at all (the normal shape
    for an edit/reject request that isn't touching either field) must not
    wipe out values a prior approve request already set."""
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        seed_materials_prerequisites(db)
    client.app.state.application_materials_generator = fake_grounded_generator
    client.post("/api/jobs/manual-abc123/generate-materials")
    client.post(
        "/api/jobs/manual-abc123/approve",
        json={
            "decision": "approved",
            "eligibility_confirmed": True,
            "eligibility_notes": "needs sponsorship",
            "notes": "initial pass",
        },
    )

    # Real client shape: an edit request whose body simply doesn't mention
    # eligibility_notes or notes, as opposed to sending them as null.
    response = client.post("/api/jobs/manual-abc123/approve", json={"decision": "edit_requested"})
    assert response.status_code == 200

    reread = client.post("/api/jobs/manual-abc123/generate-materials").json()
    assert reread["approval_status"] == "edit_requested"
    assert reread["eligibility_notes"] == "needs sponsorship"
    assert reread["decision_notes"] == "initial pass"
