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
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from backend.db.database import Base
from backend.db.models import ApplicationPackageRecord, Candidate, JobRecord, ResumeVersionRecord, TargetPreference, User
from backend.schemas.schemas import ApprovalRequest, CandidateProfile
from backend.services.application_materials_agent import (
    StaleApplicationMaterialsError,
    generate_grounded_application_materials,
)
from backend.services.application_service import apply_approval, discard_stale_reviewed_package
from backend.services.candidate_profile_agent import persist_candidate_profile
from backend.services.candidate_provenance import (
    build_resume_input_snapshot,
    current_resume_input_fingerprint,
    hash_resume_input_snapshot,
    snapshot_resume_input,
)
from backend.services.resume_version_service import (
    ResumeVersionConflictError,
    ResumeVersionNotFoundError,
    create_resume_version,
    get_resume_version,
    list_resume_versions,
)
from tests.mvp_helpers import (
    TEST_USER_ID,
    fake_grounded_generator,
    insert_candidate,
    insert_grounded_package,
    insert_job,
    insert_score,
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
    with pytest.raises(ResumeVersionConflictError):
        create_resume_version(isolated_session, job.public_id, TEST_USER_ID)
    assert isolated_session.query(ResumeVersionRecord).count() == 1

    package.approval_status = "pending_review"
    isolated_session.commit()
    with pytest.raises(ResumeVersionConflictError):
        create_resume_version(isolated_session, job.public_id, TEST_USER_ID)
    _approve(isolated_session, job.public_id)
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
    package.approval_status = "pending_review"
    isolated_session.commit()
    _approve(isolated_session, job.public_id)
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


def test_old_schema_gains_provenance_columns_without_losing_rows(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib

    from backend.db.init_db import init_db

    db_path = tmp_path / "old-provenance.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE users ("
                "id INTEGER PRIMARY KEY, email VARCHAR(255) NOT NULL, "
                "hashed_password VARCHAR(255) NOT NULL, created_at DATETIME)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE jobs ("
                "id INTEGER PRIMARY KEY, public_id VARCHAR(64), title VARCHAR(255) NOT NULL, "
                "company VARCHAR(255) NOT NULL, location VARCHAR(255), salary VARCHAR(128), "
                "url TEXT NOT NULL, description TEXT NOT NULL, source VARCHAR(64) NOT NULL, "
                "date_posted VARCHAR(32), date_scraped DATETIME, ats VARCHAR(64), "
                "status VARCHAR(64), verification_notes TEXT, verified_at DATETIME)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE application_packages ("
                "id INTEGER PRIMARY KEY, job_id INTEGER, user_id INTEGER, candidate_id INTEGER, "
                "tailored_bullets JSON, cover_letter_draft TEXT, recruiter_message TEXT, "
                "source_traceability_notes JSON, approval_status VARCHAR(32), "
                "eligibility_confirmed BOOLEAN, eligibility_notes TEXT, decision_notes TEXT, "
                "grounded BOOLEAN DEFAULT 0, created_at DATETIME)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE resume_versions ("
                "id INTEGER PRIMARY KEY, public_id VARCHAR(64) NOT NULL, job_id INTEGER NOT NULL, "
                "user_id INTEGER NOT NULL, candidate_id INTEGER NOT NULL, version_number INTEGER NOT NULL, "
                "tailored_bullets JSON, source_traceability_notes JSON, content_hash VARCHAR(64) NOT NULL, "
                "created_at DATETIME)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO users (email, hashed_password, created_at) "
                "VALUES ('legacy@example.com', 'x', '2026-01-01T00:00:00')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO jobs (public_id, title, company, url, description, source, status) "
                "VALUES ('legacy-job', 'Intern', 'Acme', 'https://example.com/legacy', 'desc', 'manual', 'verified')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO application_packages "
                "(job_id, user_id, candidate_id, tailored_bullets, source_traceability_notes, "
                "approval_status, grounded) VALUES (1, 1, 1, '[]', '[]', 'pending_review', 1)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO resume_versions "
                "(public_id, job_id, user_id, candidate_id, version_number, tailored_bullets, "
                "source_traceability_notes, content_hash) "
                "VALUES ('rv-legacy', 1, 1, 1, 1, '[]', '[]', 'abc')"
            )
        )
    init_db_module = importlib.import_module("backend.db.init_db")
    monkeypatch.setattr(init_db_module, "engine", engine)
    try:
        init_db()
        inspector = inspect(engine)
        package_cols = {col["name"] for col in inspector.get_columns("application_packages")}
        version_cols = {col["name"] for col in inspector.get_columns("resume_versions")}
        assert "candidate_profile_fingerprint" in package_cols
        assert "resume_input_snapshot" in version_cols
        with engine.connect() as conn:
            packages = conn.execute(text("SELECT count(*) FROM application_packages")).scalar()
            versions = conn.execute(text("SELECT count(*) FROM resume_versions")).scalar()
            users = conn.execute(text("SELECT count(*) FROM users")).scalar()
        assert packages == 1
        assert versions == 1
        assert users == 1
    finally:
        engine.dispose()


def _groundable_profile(*, name: str, email: str, extra_skill: str | None = None) -> CandidateProfile:
    skills = ["Python", "SQL"]
    if extra_skill:
        skills = [*skills, extra_skill]
    return CandidateProfile(
        name=name,
        email=email,
        phone="555-0142",
        skills=skills,
        projects=[
            {
                "name": "Campus Planner",
                "description": "Python API for campus events.",
                "technologies": ["Python", "FastAPI"],
                "url": None,
            }
        ],
        experience=[
            {
                "title": "Software Engineering Intern",
                "company": "Northstar Labs",
                "start_date": "2025-05",
                "end_date": "2025-08",
                "highlights": ["Reduced p95 latency on search endpoints by 28%."],
            }
        ],
        education=[
            {
                "institution": "State University",
                "degree": "B.S.",
                "field": "Computer Science",
                "graduation_year": "2027",
            }
        ],
        certifications=[],
        strengths=["Backend APIs"],
        evidence_links=[],
    )


def _stamp_sensitive_preferences(session, *, legal_name: str, linkedin_url: str) -> None:
    pref = session.query(TargetPreference).filter_by(user_id=TEST_USER_ID).one()
    pref.salary_min = 135000
    pref.work_authorization = "US Citizen"
    pref.gender = "prefer_not_to_say"
    pref.race_ethnicity = "Decline to answer"
    pref.veteran_status = "I am not a veteran"
    pref.disability_status = "No"
    pref.legal_name = legal_name
    pref.linkedin_url = linkedin_url
    pref.github_url = "https://github.com/example-user"
    pref.portfolio_url = "https://example.com/portfolio"
    session.commit()


_FORBIDDEN_PUBLIC_KEYS = (
    "content_hash",
    "candidate_id",
    "candidate_profile_fingerprint",
    "resume_input_snapshot",
    "approved_materials_hash",
    "user_id",
)


def _assert_public_payload_is_safe(payload: dict, row: ResumeVersionRecord, caplog: pytest.LogCaptureFixture) -> None:
    dumped = json.dumps(payload)
    for key in _FORBIDDEN_PUBLIC_KEYS:
        assert key not in payload
        assert key not in dumped
    assert row.content_hash not in dumped
    snapshot = row.resume_input_snapshot or {}
    fingerprint = getattr(row, "content_hash", "")
    assert fingerprint not in dumped or payload.get("id") == fingerprint
    assert "salary_min" not in dumped
    assert "work_authorization" not in dumped
    assert "prefer_not_to_say" not in dumped
    assert "Decline to answer" not in dumped
    assert snapshot.get("email", "missing-email") not in dumped
    logs = caplog.text
    assert row.content_hash not in logs
    if getattr(row, "candidate_id", None) is not None:
        assert f"candidate_id={row.candidate_id}" not in logs
    assert "resume_input_snapshot" not in logs
    assert "candidate_profile_fingerprint" not in logs
    assert "135000" not in logs
    assert "prefer_not_to_say" not in logs


def _approved_package_with_display_fields(session, *, public_id: str = "manual-abc123"):
    job, candidate = seed_materials_prerequisites(session, public_id=public_id)
    _stamp_sensitive_preferences(
        session,
        legal_name="Jordan Avery",
        linkedin_url="https://linkedin.com/in/jordanavery",
    )
    insert_grounded_package(session, job, candidate=candidate)
    _approve(session, public_id)
    return job, candidate


def test_same_row_profile_update_creates_new_version_not_reuse(isolated_session, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    job, candidate_a = _approved_package_with_display_fields(isolated_session)
    original_candidate_pk = candidate_a.id

    version_one = create_resume_version(isolated_session, job.public_id, TEST_USER_ID)
    assert version_one.version_number == 1
    row_one = isolated_session.query(ResumeVersionRecord).filter_by(version_number=1).one()
    snapshot_a = dict(row_one.resume_input_snapshot)
    assert snapshot_a["name"] == "Jordan Avery"
    assert "salary_min" not in snapshot_a
    assert "gender" not in snapshot_a
    assert "work_authorization" not in snapshot_a
    assert snapshot_a["legal_name"] == "Jordan Avery"
    original_bullets = list(version_one.tailored_bullets)
    original_notes = list(version_one.source_traceability_notes)

    persist_candidate_profile(
        _groundable_profile(name="Riley Chen", email="riley@example.com", extra_skill="Kubernetes"),
        isolated_session,
        TEST_USER_ID,
    )
    isolated_session.expire_all()
    current = isolated_session.query(Candidate).filter(Candidate.user_id == TEST_USER_ID).one()
    assert current.id == original_candidate_pk
    assert isolated_session.query(Candidate).count() == 1
    assert current.name == "Riley Chen"

    with pytest.raises(ResumeVersionConflictError):
        create_resume_version(isolated_session, job.public_id, TEST_USER_ID)
    assert isolated_session.query(ResumeVersionRecord).count() == 1

    discard_stale_reviewed_package(isolated_session, job.public_id, TEST_USER_ID)
    insert_score(isolated_session, job, current)
    generate_grounded_application_materials(
        isolated_session, job.public_id, TEST_USER_ID, generator=fake_grounded_generator
    )
    _approve(isolated_session, job.public_id)
    package = isolated_session.query(ApplicationPackageRecord).one()
    assert list(package.tailored_bullets) == original_bullets
    assert list(package.source_traceability_notes) == original_notes

    version_two = create_resume_version(isolated_session, job.public_id, TEST_USER_ID)
    assert version_two.version_number == 2
    assert version_two.id != version_one.id
    assert version_two.tailored_bullets == original_bullets
    assert isolated_session.query(ResumeVersionRecord).count() == 2

    repeat = create_resume_version(isolated_session, job.public_id, TEST_USER_ID)
    assert repeat.id == version_two.id
    assert isolated_session.query(ResumeVersionRecord).count() == 2

    persist_candidate_profile(
        _groundable_profile(name="Casey Ng", email="casey@example.com"),
        isolated_session,
        TEST_USER_ID,
    )
    isolated_session.expire_all()
    reloaded_one = isolated_session.query(ResumeVersionRecord).filter_by(version_number=1).one()
    assert reloaded_one.resume_input_snapshot["name"] == "Jordan Avery"
    assert reloaded_one.tailored_bullets == original_bullets

    payload = version_two.model_dump(mode="json")
    row_two = isolated_session.query(ResumeVersionRecord).filter_by(version_number=2).one()
    _assert_public_payload_is_safe(payload, row_two, caplog)


def test_legacy_package_without_fingerprint_cannot_create_version(isolated_session) -> None:
    job, candidate = seed_materials_prerequisites(isolated_session)
    record = insert_grounded_package(isolated_session, job, candidate=candidate)
    record.candidate_profile_fingerprint = None
    isolated_session.commit()
    with pytest.raises(Exception):
        _approve(isolated_session, job.public_id)
    record.approval_status = "approved"
    record.eligibility_confirmed = True
    isolated_session.commit()
    with pytest.raises(ResumeVersionConflictError):
        create_resume_version(isolated_session, job.public_id, TEST_USER_ID)
    assert isolated_session.query(ResumeVersionRecord).count() == 0


def test_sensitive_preference_change_does_not_create_new_version(isolated_session) -> None:
    job, _ = _approved_package_with_display_fields(isolated_session)
    first = create_resume_version(isolated_session, job.public_id, TEST_USER_ID)
    pref = isolated_session.query(TargetPreference).filter_by(user_id=TEST_USER_ID).one()
    pref.salary_min = 180000
    pref.work_authorization = "Permanent resident"
    pref.gender = "male"
    pref.race_ethnicity = "Other"
    pref.disability_status = "Yes"
    pref.veteran_status = "Veteran"
    isolated_session.commit()
    second = create_resume_version(isolated_session, job.public_id, TEST_USER_ID)
    assert first.id == second.id
    assert isolated_session.query(ResumeVersionRecord).count() == 1
    row = isolated_session.query(ResumeVersionRecord).one()
    assert "salary_min" not in (row.resume_input_snapshot or {})
    assert "work_authorization" not in (row.resume_input_snapshot or {})
    assert "gender" not in (row.resume_input_snapshot or {})
    assert "race_ethnicity" not in (row.resume_input_snapshot or {})
    assert "disability_status" not in (row.resume_input_snapshot or {})
    assert "veteran_status" not in (row.resume_input_snapshot or {})


def test_refresh_true_observes_in_place_preference_update(isolated_session) -> None:
    job, candidate = seed_materials_prerequisites(isolated_session)
    pref = isolated_session.query(TargetPreference).filter_by(user_id=TEST_USER_ID).one()
    pref.legal_name = "Before Refresh"
    pref.linkedin_url = "https://linkedin.com/in/before"
    isolated_session.commit()
    loaded = isolated_session.query(TargetPreference).filter_by(id=pref.id).one()
    assert loaded.legal_name == "Before Refresh"
    before = current_resume_input_fingerprint(isolated_session, TEST_USER_ID, refresh=False)

    Other = sessionmaker(bind=isolated_session.get_bind(), autocommit=False, autoflush=False)
    with Other() as other:
        row = other.get(TargetPreference, pref.id)
        assert row is not None
        row.legal_name = "After Refresh"
        row.linkedin_url = "https://linkedin.com/in/after"
        other.commit()

    stale = current_resume_input_fingerprint(isolated_session, TEST_USER_ID, refresh=False)
    assert stale == before
    refreshed = current_resume_input_fingerprint(isolated_session, TEST_USER_ID, refresh=True)
    isolated_session.refresh(candidate)
    expected = hash_resume_input_snapshot(snapshot_resume_input(candidate, loaded))
    assert loaded.legal_name == "After Refresh"
    assert refreshed == expected
    assert refreshed != before


def test_resume_input_hash_is_order_independent() -> None:
    left = {"skills": ["Python"], "projects": [{"name": "A", "url": None}]}
    right = {"projects": [{"url": None, "name": "A"}], "skills": ["Python"]}
    assert hash_resume_input_snapshot(left) == hash_resume_input_snapshot(right)
    assert build_resume_input_snapshot.__name__ == "build_resume_input_snapshot"


def test_http_create_omits_provenance_fields(isolated_client, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    client, SessionLocal = isolated_client
    _seed_approved_for_client(SessionLocal, user_id=client.test_user_id)
    created = client.post("/api/jobs/manual-abc123/resume-versions")
    assert created.status_code == 201
    listed = client.get("/api/jobs/manual-abc123/resume-versions")
    fetched = client.get(f"/api/jobs/manual-abc123/resume-versions/{created.json()['id']}")
    assert listed.status_code == 200
    assert fetched.status_code == 200
    with SessionLocal() as db:
        row = db.query(ResumeVersionRecord).one()
        _assert_public_payload_is_safe(created.json(), row, caplog)
        _assert_public_payload_is_safe(fetched.json(), row, caplog)
        _assert_public_payload_is_safe(listed.json()[0], row, caplog)


def test_stale_same_row_generate_requires_discard(isolated_session) -> None:
    job, _ = _approved_package(isolated_session)
    persist_candidate_profile(
        _groundable_profile(name="Riley Chen", email="riley@example.com", extra_skill="Kubernetes"),
        isolated_session,
        TEST_USER_ID,
    )
    with pytest.raises(StaleApplicationMaterialsError):
        generate_grounded_application_materials(
            isolated_session, job.public_id, TEST_USER_ID, generator=fake_grounded_generator
        )
    assert isolated_session.query(ApplicationPackageRecord).count() == 1
    discard_stale_reviewed_package(isolated_session, job.public_id, TEST_USER_ID)
    assert isolated_session.query(ApplicationPackageRecord).count() == 0


def test_distinct_content_version_number_collision_retries(
    isolated_session, monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    caplog.set_level(logging.DEBUG)
    job, candidate = _approved_package(isolated_session)
    first = create_resume_version(isolated_session, job.public_id, TEST_USER_ID)
    original_bullets = list(first.tailored_bullets)
    package = isolated_session.query(ApplicationPackageRecord).one()
    package.tailored_bullets = list(package.tailored_bullets) + [
        "Shipped additional FastAPI work at Northstar Labs."
    ]
    package.approval_status = "pending_review"
    isolated_session.commit()
    _approve(isolated_session, job.public_id)

    real_commit = isolated_session.commit
    raced = {"done": False}

    def _commit_with_collision():
        if not raced["done"]:
            raced["done"] = True
            Other = sessionmaker(bind=isolated_session.get_bind(), autocommit=False, autoflush=False)
            with Other() as other:
                other.add(
                    ResumeVersionRecord(
                        public_id="rv-collision-other",
                        job_id=job.id,
                        user_id=TEST_USER_ID,
                        candidate_id=candidate.id,
                        version_number=2,
                        tailored_bullets=["Competing distinct bullet about SQL."],
                        source_traceability_notes=["SQL <- skills"],
                        resume_input_snapshot={"name": "Jordan Avery"},
                        content_hash="b" * 64,
                    )
                )
                other.commit()
        return real_commit()

    monkeypatch.setattr(isolated_session, "commit", _commit_with_collision)
    second = create_resume_version(isolated_session, job.public_id, TEST_USER_ID)
    assert second.version_number == 3
    assert second.id != first.id
    rows = isolated_session.query(ResumeVersionRecord).order_by(ResumeVersionRecord.version_number).all()
    assert len(rows) == 3
    assert rows[0].tailored_bullets == original_bullets
    assert rows[1].public_id == "rv-collision-other"
    assert "UNIQUE constraint failed" not in caplog.text
    assert "resume_input_snapshot" not in caplog.text
    assert "jordan@example.com" not in caplog.text


def test_owner_can_list_global_resume_versions_newest_first(isolated_client) -> None:
    client, SessionLocal = isolated_client
    _seed_approved_for_client(SessionLocal, public_id="manual-abc123", user_id=client.test_user_id)
    first = client.post("/api/jobs/manual-abc123/resume-versions")
    assert first.status_code == 201
    _seed_approved_for_client(SessionLocal, public_id="manual-def456", user_id=client.test_user_id)
    second = client.post("/api/jobs/manual-def456/resume-versions")
    assert second.status_code == 201
    listed = client.get("/api/resume-versions")
    assert listed.status_code == 200
    body = listed.json()
    assert [item["id"] for item in body] == [second.json()["id"], first.json()["id"]]
    assert body[0]["job_id"] == "manual-def456"
    assert body[0]["job_title"]
    assert body[0]["company"]
    assert body[0]["bullet_count"] >= 1
    assert body[0]["provenance_status"] == "approved_snapshot"
    assert body[0]["matches_current_profile"] is True
    dumped = json.dumps(body)
    assert "content_hash" not in dumped
    assert "candidate_profile_fingerprint" not in dumped
    assert "approved_materials_hash" not in dumped
    assert "resume_input_snapshot" not in dumped
    assert "salary_min" not in dumped
    assert "work_authorization" not in dumped


def test_owner_can_get_global_resume_version_detail(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        job, candidate = seed_materials_prerequisites(db, user_id=client.test_user_id)
        pref = db.query(TargetPreference).filter_by(user_id=candidate.user_id).one()
        pref.salary_min = 135000
        pref.work_authorization = "US Citizen"
        pref.gender = "prefer_not_to_say"
        pref.race_ethnicity = "Decline to answer"
        pref.veteran_status = "I am not a veteran"
        pref.disability_status = "No"
        pref.legal_name = "Jordan Avery"
        pref.linkedin_url = "https://linkedin.com/in/jordanavery"
        pref.github_url = "https://github.com/example-user"
        pref.portfolio_url = "https://example.com/portfolio"
        db.commit()
        insert_grounded_package(db, job, candidate=candidate, user_id=client.test_user_id)
        _approve(db, job.public_id, client.test_user_id)
    created = client.post("/api/jobs/manual-abc123/resume-versions")
    assert created.status_code == 201
    version_id = created.json()["id"]
    detail = client.get(f"/api/resume-versions/{version_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["id"] == version_id
    assert body["tailored_bullets"]
    assert body["source_traceability_notes"]
    assert body["profile"]["name"] == "Jordan Avery"
    assert body["profile"]["legal_name"] == "Jordan Avery"
    assert body["profile"]["linkedin_url"] == "https://linkedin.com/in/jordanavery"
    dumped = json.dumps(body)
    assert "content_hash" not in dumped
    assert "resume_input_snapshot" not in dumped
    assert "salary_min" not in dumped
    assert "work_authorization" not in dumped
    assert "prefer_not_to_say" not in dumped
    assert "gender" not in dumped
    assert "race_ethnicity" not in dumped


def test_global_resume_routes_are_read_only_and_provider_free(
    isolated_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, SessionLocal = isolated_client
    _seed_approved_for_client(SessionLocal, user_id=client.test_user_id)
    created = client.post("/api/jobs/manual-abc123/resume-versions").json()

    def _blocked(*_a, **_k):
        raise AssertionError("LLM must not be called")

    monkeypatch.setattr("backend.services.llm_client.LLMClient.generate", _blocked)
    listed = client.get("/api/resume-versions")
    fetched = client.get(f"/api/resume-versions/{created['id']}")
    assert listed.status_code == 200
    assert fetched.status_code == 200
    with SessionLocal() as db:
        assert db.query(ResumeVersionRecord).count() == 1
        row = db.query(ResumeVersionRecord).one()
        created_at = row.created_at
        content_hash = row.content_hash
    listed_again = client.get("/api/resume-versions")
    assert listed_again.status_code == 200
    with SessionLocal() as db:
        row = db.query(ResumeVersionRecord).one()
        assert row.created_at == created_at
        assert row.content_hash == content_hash


def test_global_resume_list_and_detail_are_owner_scoped(isolated_client) -> None:
    client, SessionLocal = isolated_client
    _seed_approved_for_client(SessionLocal, user_id=client.test_user_id)
    created = client.post("/api/jobs/manual-abc123/resume-versions").json()
    client.post("/api/auth/logout")
    signup = client.post(
        "/api/auth/signup",
        json={"email": "other-resume@example.com", "password": "test-password-123"},
    )
    assert signup.status_code == 201
    listed = client.get("/api/resume-versions")
    fetched = client.get(f"/api/resume-versions/{created['id']}")
    assert listed.status_code == 200
    assert listed.json() == []
    assert fetched.status_code == 404
    detail = fetched.json()["detail"]
    assert "not found" in detail.lower()
    assert created["id"] not in detail
    assert "user" not in detail.lower()


def test_global_detail_stays_historical_after_display_profile_change(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        job, candidate = seed_materials_prerequisites(db, user_id=client.test_user_id)
        pref = db.query(TargetPreference).filter_by(user_id=candidate.user_id).one()
        pref.legal_name = "Jordan Avery"
        pref.linkedin_url = "https://linkedin.com/in/jordanavery"
        db.commit()
        insert_grounded_package(db, job, candidate=candidate, user_id=client.test_user_id)
        _approve(db, job.public_id, client.test_user_id)
    created = client.post("/api/jobs/manual-abc123/resume-versions")
    version_id = created.json()["id"]
    with SessionLocal() as db:
        pref = db.query(TargetPreference).filter_by(user_id=client.test_user_id).one()
        pref.legal_name = "Riley Chen Legal"
        pref.linkedin_url = "https://linkedin.com/in/riley-b"
        db.commit()
    listed = client.get("/api/resume-versions")
    detail = client.get(f"/api/resume-versions/{version_id}")
    assert listed.status_code == 200
    assert listed.json()[0]["matches_current_profile"] is False
    body = detail.json()
    assert body["matches_current_profile"] is False
    assert body["profile"]["legal_name"] == "Jordan Avery"
    assert body["profile"]["linkedin_url"] == "https://linkedin.com/in/jordanavery"
    assert "Riley Chen Legal" not in json.dumps(body)
