"""Resume-version foundation tests. Deterministic and provider-free.

Current gap this suite encodes (Phase 2): CareerPilot stores one mutable
application package per job/user. It does not persist immutable per-job
resume snapshots, cannot list historical tailored-bullet versions, and has
no opaque resume-version identifier for a future exporter or extension
upload. Until this service exists, the browser extension has no approved
resume artifact contract to consume.

These tests never open an external application or call a submission endpoint.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from backend.db.database import Base
from backend.db.models import ApplicationPackageRecord, Candidate, JobRecord, ResumeVersionRecord, User
from backend.schemas.schemas import ApprovalRequest
from backend.services.application_service import apply_approval
from backend.services.resume_version_service import (
    ResumeVersionConflictError,
    ResumeVersionNotFoundError,
    create_resume_version,
    get_resume_version,
    list_resume_versions,
)
from tests.mvp_helpers import (
    TEST_USER_ID,
    insert_candidate,
    insert_grounded_package,
    insert_job,
    seed_materials_prerequisites,
)


def _approve(session, job_public_id: str, user_id: int = TEST_USER_ID) -> None:
    apply_approval(
        session,
        job_public_id,
        user_id,
        ApprovalRequest(decision="approved", eligibility_confirmed=True),
    )


def _approved_package(session, *, public_id: str = "manual-abc123", user_id: int = TEST_USER_ID):
    job, candidate = seed_materials_prerequisites(session, public_id=public_id, user_id=user_id)
    insert_grounded_package(session, job, candidate=candidate, user_id=user_id)
    _approve(session, public_id, user_id)
    return job, candidate


def test_approved_grounded_package_creates_version_1(isolated_session) -> None:
    job, _ = _approved_package(isolated_session)
    version = create_resume_version(isolated_session, job.public_id, TEST_USER_ID)
    assert version.version_number == 1
    assert version.job_id == job.public_id
    assert isolated_session.query(ResumeVersionRecord).count() == 1


def test_missing_package_cannot_create_version(isolated_session) -> None:
    seed_materials_prerequisites(isolated_session)
    with pytest.raises(ResumeVersionNotFoundError):
        create_resume_version(isolated_session, "manual-abc123", TEST_USER_ID)
    assert isolated_session.query(ResumeVersionRecord).count() == 0


def test_ungrounded_package_cannot_create_version(isolated_session) -> None:
    job, candidate = seed_materials_prerequisites(isolated_session)
    record = insert_grounded_package(isolated_session, job, candidate=candidate)
    record.grounded = False
    isolated_session.commit()
    _approve_raw = isolated_session.query(ApplicationPackageRecord).one()
    _approve_raw.approval_status = "approved"
    _approve_raw.eligibility_confirmed = True
    isolated_session.commit()
    with pytest.raises(ResumeVersionConflictError):
        create_resume_version(isolated_session, job.public_id, TEST_USER_ID)
    assert isolated_session.query(ResumeVersionRecord).count() == 0


@pytest.mark.parametrize("status_name", ["pending_review", "edit_requested", "rejected"])
def test_unapproved_package_cannot_create_version(isolated_session, status_name: str) -> None:
    job, candidate = seed_materials_prerequisites(isolated_session)
    record = insert_grounded_package(isolated_session, job, candidate=candidate)
    record.approval_status = status_name
    isolated_session.commit()
    with pytest.raises(ResumeVersionConflictError):
        create_resume_version(isolated_session, job.public_id, TEST_USER_ID)
    assert isolated_session.query(ResumeVersionRecord).count() == 0


def test_outdated_candidate_package_cannot_create_version(isolated_session) -> None:
    job, _candidate = _approved_package(isolated_session)
    insert_candidate(isolated_session, user_id=TEST_USER_ID)
    with pytest.raises(ResumeVersionConflictError):
        create_resume_version(isolated_session, job.public_id, TEST_USER_ID)
    assert isolated_session.query(ResumeVersionRecord).count() == 0


def test_saved_version_snapshots_bullets_and_traceability(isolated_session) -> None:
    job, _ = _approved_package(isolated_session)
    version = create_resume_version(isolated_session, job.public_id, TEST_USER_ID)
    assert version.tailored_bullets
    assert version.source_traceability_notes
    assert "Python" in " ".join(version.tailored_bullets)


def test_changing_source_package_does_not_mutate_existing_version(isolated_session) -> None:
    job, _ = _approved_package(isolated_session)
    version = create_resume_version(isolated_session, job.public_id, TEST_USER_ID)
    original_bullets = list(version.tailored_bullets)
    package = isolated_session.query(ApplicationPackageRecord).one()
    package.tailored_bullets = ["Mutated later bullet that should not rewrite history."]
    isolated_session.commit()
    reloaded = get_resume_version(isolated_session, job.public_id, version.id, TEST_USER_ID)
    assert reloaded.tailored_bullets == original_bullets


def test_identical_snapshot_is_idempotent(isolated_session) -> None:
    job, _ = _approved_package(isolated_session)
    first = create_resume_version(isolated_session, job.public_id, TEST_USER_ID)
    second = create_resume_version(isolated_session, job.public_id, TEST_USER_ID)
    assert first.id == second.id
    assert first.version_number == second.version_number == 1
    assert isolated_session.query(ResumeVersionRecord).count() == 1


def test_changed_approved_content_creates_next_version(isolated_session) -> None:
    job, _ = _approved_package(isolated_session)
    first = create_resume_version(isolated_session, job.public_id, TEST_USER_ID)
    package = isolated_session.query(ApplicationPackageRecord).one()
    package.tailored_bullets = list(package.tailored_bullets) + [
        "Built Campus Planner with Python and FastAPI for campus events."
    ]
    isolated_session.commit()
    second = create_resume_version(isolated_session, job.public_id, TEST_USER_ID)
    assert second.version_number == 2
    assert second.id != first.id
    assert isolated_session.query(ResumeVersionRecord).count() == 2


def test_version_numbers_are_scoped_per_job_and_user(isolated_session) -> None:
    job_a, _ = _approved_package(isolated_session, public_id="job-a")
    job_b, candidate = seed_materials_prerequisites(isolated_session, public_id="job-b")
    insert_grounded_package(isolated_session, job_b, candidate=candidate)
    _approve(isolated_session, "job-b")
    a1 = create_resume_version(isolated_session, job_a.public_id, TEST_USER_ID)
    b1 = create_resume_version(isolated_session, job_b.public_id, TEST_USER_ID)
    assert a1.version_number == 1
    assert b1.version_number == 1
    assert a1.id != b1.id


def test_two_users_may_each_have_version_1_for_same_job(isolated_session) -> None:
    job, cand_a = _approved_package(isolated_session, public_id="shared-job", user_id=1)
    cand_b = insert_candidate(isolated_session, user_id=2)
    insert_grounded_package(isolated_session, job, candidate=cand_b, user_id=2)
    _approve(isolated_session, "shared-job", user_id=2)
    a1 = create_resume_version(isolated_session, "shared-job", 1)
    b1 = create_resume_version(isolated_session, "shared-job", 2)
    assert a1.version_number == 1
    assert b1.version_number == 1
    assert a1.id != b1.id
    assert isolated_session.query(ResumeVersionRecord).count() == 2
    assert cand_a.id != cand_b.id


def test_user_cannot_list_or_get_another_users_versions(isolated_session) -> None:
    job, _ = _approved_package(isolated_session, user_id=1)
    owned = create_resume_version(isolated_session, job.public_id, 1)
    insert_candidate(isolated_session, user_id=2)
    assert list_resume_versions(isolated_session, job.public_id, 2) == []
    with pytest.raises(ResumeVersionNotFoundError):
        get_resume_version(isolated_session, job.public_id, owned.id, 2)


def test_public_id_is_opaque_and_not_the_database_pk(isolated_session) -> None:
    job, _ = _approved_package(isolated_session)
    version = create_resume_version(isolated_session, job.public_id, TEST_USER_ID)
    row = isolated_session.query(ResumeVersionRecord).one()
    assert version.id != str(row.id)
    assert version.id == row.public_id
    assert not version.id.isdigit()


def test_create_never_calls_llm(isolated_session, monkeypatch: pytest.MonkeyPatch) -> None:
    job, _ = _approved_package(isolated_session)

    def _blocked(*_args, **_kwargs):
        raise AssertionError("LLM must not be called")

    monkeypatch.setattr("backend.services.llm_client.LLMClient.generate", _blocked)
    create_resume_version(isolated_session, job.public_id, TEST_USER_ID)


def test_database_failure_rolls_back_without_partial_row(isolated_session, monkeypatch: pytest.MonkeyPatch) -> None:
    job, _ = _approved_package(isolated_session)

    def _fail():
        raise RuntimeError("disk full")

    monkeypatch.setattr(isolated_session, "commit", _fail)
    with pytest.raises(Exception):
        create_resume_version(isolated_session, job.public_id, TEST_USER_ID)
    isolated_session.rollback()
    assert isolated_session.query(ResumeVersionRecord).count() == 0


def test_concurrent_identical_creation_does_not_duplicate(tmp_path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'resume-versions.sqlite'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    with SessionLocal() as session:
        _approved_package(session)

    def _create() -> str:
        with SessionLocal() as session:
            version = create_resume_version(session, "manual-abc123", TEST_USER_ID)
            return version.id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _i: _create(), range(2)))
    assert ids[0] == ids[1]
    with SessionLocal() as session:
        assert session.query(ResumeVersionRecord).count() == 1
    engine.dispose()


def test_list_is_newest_first(isolated_session) -> None:
    job, _ = _approved_package(isolated_session)
    first = create_resume_version(isolated_session, job.public_id, TEST_USER_ID)
    package = isolated_session.query(ApplicationPackageRecord).one()
    package.tailored_bullets = list(package.tailored_bullets) + ["Additional grounded Python API work."]
    isolated_session.commit()
    second = create_resume_version(isolated_session, job.public_id, TEST_USER_ID)
    listed = list_resume_versions(isolated_session, job.public_id, TEST_USER_ID)
    assert [item.id for item in listed] == [second.id, first.id]


def test_responses_omit_internal_fields(isolated_session) -> None:
    job, _ = _approved_package(isolated_session)
    version = create_resume_version(isolated_session, job.public_id, TEST_USER_ID)
    payload = version.model_dump(mode="json")
    dumped = json.dumps(payload)
    assert "content_hash" not in payload
    assert "candidate_id" not in payload
    assert "user_id" not in payload
    assert "/data/" not in dumped
    assert "prompt" not in dumped.lower()
    row = isolated_session.query(ResumeVersionRecord).one()
    assert str(row.id) not in dumped or version.id != str(row.id)


# ---------------------------------------------------------------------------
# HTTP contract
# ---------------------------------------------------------------------------


def _seed_approved_for_client(SessionLocal, *, public_id: str = "manual-abc123", user_id: int | None = None):
    with SessionLocal() as db:
        owner = user_id
        if owner is None:
            owner = db.query(User).one().id
        job, candidate = seed_materials_prerequisites(db, public_id=public_id, user_id=owner)
        insert_grounded_package(db, job, candidate=candidate, user_id=owner)
        _approve(db, public_id, owner)
        return owner


def test_create_route_returns_201_for_new_version(isolated_client) -> None:
    client, SessionLocal = isolated_client
    _seed_approved_for_client(SessionLocal, user_id=client.test_user_id)
    response = client.post("/api/jobs/manual-abc123/resume-versions")
    assert response.status_code == 201
    body = response.json()
    assert body["version_number"] == 1
    assert body["job_id"] == "manual-abc123"
    assert "content_hash" not in body
    assert "id" in body and body["id"]


def test_identical_create_route_is_idempotent(isolated_client) -> None:
    client, SessionLocal = isolated_client
    _seed_approved_for_client(SessionLocal, user_id=client.test_user_id)
    first = client.post("/api/jobs/manual-abc123/resume-versions")
    second = client.post("/api/jobs/manual-abc123/resume-versions")
    assert first.status_code == 201
    assert second.status_code in {200, 201}
    assert first.json()["id"] == second.json()["id"]
    with SessionLocal() as db:
        assert db.query(ResumeVersionRecord).count() == 1


def test_get_routes_never_write_or_call_llm(isolated_client, monkeypatch: pytest.MonkeyPatch) -> None:
    client, SessionLocal = isolated_client
    _seed_approved_for_client(SessionLocal, user_id=client.test_user_id)
    created = client.post("/api/jobs/manual-abc123/resume-versions").json()

    def _blocked(*_a, **_k):
        raise AssertionError("LLM must not be called")

    monkeypatch.setattr("backend.services.llm_client.LLMClient.generate", _blocked)
    listed = client.get("/api/jobs/manual-abc123/resume-versions")
    fetched = client.get(f"/api/jobs/manual-abc123/resume-versions/{created['id']}")
    assert listed.status_code == 200
    assert fetched.status_code == 200
    with SessionLocal() as db:
        assert db.query(ResumeVersionRecord).count() == 1


def test_cross_user_http_access_is_sanitized_404(isolated_client) -> None:
    client, SessionLocal = isolated_client
    _seed_approved_for_client(SessionLocal, user_id=client.test_user_id)
    created = client.post("/api/jobs/manual-abc123/resume-versions").json()
    client.post("/api/auth/logout")
    signup = client.post(
        "/api/auth/signup",
        json={"email": "other-user@example.com", "password": "test-password-123"},
    )
    assert signup.status_code == 201
    listed = client.get("/api/jobs/manual-abc123/resume-versions")
    fetched = client.get(f"/api/jobs/manual-abc123/resume-versions/{created['id']}")
    assert listed.status_code == 200
    assert listed.json() == []
    assert fetched.status_code == 404
    detail = fetched.json()["detail"]
    assert "not found" in detail.lower()
    assert created["id"] not in detail
    assert "user" not in detail.lower()


def test_missing_job_or_version_is_404(isolated_client) -> None:
    client, _SessionLocal = isolated_client
    missing_job = client.get("/api/jobs/does-not-exist/resume-versions")
    assert missing_job.status_code == 404
    missing_version = client.get("/api/jobs/does-not-exist/resume-versions/rv-missing")
    assert missing_version.status_code == 404


def test_unsafe_package_state_is_409(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        seed_materials_prerequisites(db, user_id=client.test_user_id)
        job = db.query(JobRecord).one()
        candidate = db.query(Candidate).one()
        insert_grounded_package(db, job, candidate=candidate, user_id=client.test_user_id)
    response = client.post("/api/jobs/manual-abc123/resume-versions")
    assert response.status_code == 409


def test_malformed_create_body_is_422(isolated_client) -> None:
    client, SessionLocal = isolated_client
    _seed_approved_for_client(SessionLocal, user_id=client.test_user_id)
    response = client.post(
        "/api/jobs/manual-abc123/resume-versions",
        json={"content_hash": "should-not-be-accepted"},
    )
    assert response.status_code == 422


def test_http_payload_has_no_internal_identifiers(isolated_client) -> None:
    client, SessionLocal = isolated_client
    _seed_approved_for_client(SessionLocal, user_id=client.test_user_id)
    body = client.post("/api/jobs/manual-abc123/resume-versions").json()
    dumped = json.dumps(body)
    with SessionLocal() as db:
        row = db.query(ResumeVersionRecord).one()
        assert body["id"] != str(row.id)
        assert "content_hash" not in body
        assert str(row.user_id) not in dumped or body["id"] != str(row.user_id)


def test_fresh_database_creates_resume_versions_table(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    from backend.db.init_db import REQUIRED_TABLES, init_db

    init_db_module = importlib.import_module("backend.db.init_db")
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.sqlite'}", future=True)
    monkeypatch.setattr(init_db_module, "engine", engine)
    try:
        init_db()
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert "resume_versions" in REQUIRED_TABLES
    assert "resume_versions" in tables


def test_old_schema_database_adds_resume_versions_without_losing_rows(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib

    from backend.db.init_db import init_db

    db_path = tmp_path / "old.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    tables_without = [
        table for table in Base.metadata.sorted_tables if table.name != "resume_versions"
    ]
    Base.metadata.create_all(bind=engine, tables=tables_without)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (email, hashed_password, created_at) "
                "VALUES ('old@example.com', 'x', '2026-01-01T00:00:00')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO jobs (public_id, title, company, url, description, source, status) "
                "VALUES ('old-job', 'Intern', 'Acme', 'https://example.com/old', 'desc', 'manual', 'verified')"
            )
        )
    init_db_module = importlib.import_module("backend.db.init_db")
    monkeypatch.setattr(init_db_module, "engine", engine)
    try:
        init_db()
        inspector = inspect(engine)
        assert "resume_versions" in inspector.get_table_names()
        with engine.connect() as conn:
            users = conn.execute(text("SELECT count(*) FROM users")).scalar()
            jobs = conn.execute(text("SELECT count(*) FROM jobs")).scalar()
        assert users == 1
        assert jobs == 1
    finally:
        engine.dispose()
