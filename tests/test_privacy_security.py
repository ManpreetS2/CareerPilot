"""Privacy, account deletion, login throttling, expensive-endpoint, and header tests.

Uses isolated in-memory SQLite only. Never touches data/careerpilot.db.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from fastapi import HTTPException

from backend.core.config import settings
from backend.core.rate_limit import LOGIN_IDENTITY, hash_key, runtime_guards
from backend.core.security import generate_session_token, hash_session_token
from backend.db.models import (
    ApplicationEventRecord,
    ApplicationPackageRecord,
    ApplicationTrackerRecord,
    Candidate,
    FormFillAttemptRecord,
    InterviewPrepRecord,
    JobRecord,
    MatchEvidenceRecord,
    MatchScoreRecord,
    ResumeVersionRecord,
    SavedJobRecord,
    SavedSearchMatchRecord,
    SavedSearchRecord,
    TargetPreference,
    User,
    UserSession,
)
from backend.schemas.schemas import TargetPreferences
from backend.services.application_materials_agent import _materials_prompt_preferences
from backend.services.candidate_profile_agent import MAX_UPLOAD_BYTES
from tests.conftest import TEST_USER_PASSWORD
from tests.mvp_helpers import (
    insert_grounded_package,
    insert_ready_profile,
    insert_score,
    seed_materials_prerequisites,
)


def _signup(client, email: str, password: str = "a-real-password-1") -> int:
    client.cookies.clear()
    response = client.post("/api/auth/signup", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def test_unauthenticated_delete_account_rejected(isolated_client) -> None:
    client, _ = isolated_client
    client.cookies.clear()
    response = client.delete("/api/account")
    assert response.status_code == 401


def test_delete_account_revokes_all_sessions_and_private_data(isolated_client) -> None:
    client, SessionLocal = isolated_client
    user_a = client.test_user_id
    with SessionLocal() as db:
        job, candidate_a = seed_materials_prerequisites(db, user_id=user_a)
        insert_grounded_package(db, job, candidate=candidate_a)
        score = insert_score(db, job, candidate=candidate_a)
        db.add(
            MatchEvidenceRecord(
                user_id=user_a,
                job_id=job.id,
                candidate_id=candidate_a.id,
                match_score_id=score.id,
                payload_json={"private": True},
            )
        )
        db.add(
            FormFillAttemptRecord(
                job_id=job.id,
                user_id=user_a,
                ats_platform="greenhouse",
                status="completed",
                filled_fields=[],
                flagged_fields=[],
            )
        )
        db.add(
            SavedSearchRecord(
                user_id=user_a,
                label="Backend intern roles",
                query_text="backend engineer intern",
            )
        )
        db.commit()
        job_id = job.public_id
        job_pk = job.id

    client.patch(f"/api/applications/{job_id}/tracking", json={"status": "saved"})
    client.post(f"/api/jobs/{job_id}/save")
    client.post(f"/api/jobs/{job_id}/prepare-interview")

    with SessionLocal() as db:
        search = db.query(SavedSearchRecord).filter(SavedSearchRecord.user_id == user_a).one()
        db.add(SavedSearchMatchRecord(saved_search_id=search.id, job_id=job_pk))
        db.commit()
        assert db.query(ApplicationEventRecord).filter(ApplicationEventRecord.user_id == user_a).count() > 0

    raw_b = generate_session_token()
    with SessionLocal() as db:
        db.add(
            UserSession(
                token=hash_session_token(raw_b),
                user_id=user_a,
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            )
        )
        db.commit()

    deleted = client.delete("/api/account")
    assert deleted.status_code == 204, deleted.text

    me = client.get("/api/auth/me")
    assert me.status_code == 401

    client.cookies.set(settings.session_cookie_name, raw_b)
    me_b = client.get("/api/auth/me")
    assert me_b.status_code == 401

    with SessionLocal() as db:
        assert db.query(User).filter(User.id == user_a).first() is None
        assert db.query(UserSession).filter(UserSession.user_id == user_a).count() == 0
        assert db.query(Candidate).filter(Candidate.user_id == user_a).count() == 0
        assert db.query(TargetPreference).filter(TargetPreference.user_id == user_a).count() == 0
        assert db.query(MatchScoreRecord).count() == 0
        assert db.query(ApplicationPackageRecord).filter(
            ApplicationPackageRecord.user_id == user_a
        ).count() == 0
        assert db.query(ApplicationTrackerRecord).filter(
            ApplicationTrackerRecord.user_id == user_a
        ).count() == 0
        assert db.query(InterviewPrepRecord).filter(InterviewPrepRecord.user_id == user_a).count() == 0
        assert db.query(SavedJobRecord).filter(SavedJobRecord.user_id == user_a).count() == 0
        assert db.query(ResumeVersionRecord).filter(ResumeVersionRecord.user_id == user_a).count() == 0
        assert db.query(MatchEvidenceRecord).filter(MatchEvidenceRecord.user_id == user_a).count() == 0
        assert db.query(FormFillAttemptRecord).filter(FormFillAttemptRecord.user_id == user_a).count() == 0
        assert db.query(ApplicationEventRecord).filter(ApplicationEventRecord.user_id == user_a).count() == 0
        assert db.query(SavedSearchRecord).filter(SavedSearchRecord.user_id == user_a).count() == 0
        assert db.query(SavedSearchMatchRecord).count() == 0
        assert db.query(JobRecord).filter(JobRecord.id == job_pk).first() is not None


def test_delete_user_a_leaves_user_b_and_shared_job(isolated_client) -> None:
    client, SessionLocal = isolated_client
    user_a = client.test_user_id
    with SessionLocal() as db:
        job, candidate_a = seed_materials_prerequisites(db, user_id=user_a)
        insert_grounded_package(db, job, candidate=candidate_a)
        insert_score(db, job, candidate=candidate_a)
        job_id = job.public_id

    user_b = _signup(client, "privacy-b@example.com")
    with SessionLocal() as db:
        insert_ready_profile(db, user_id=user_b)
        job = db.query(JobRecord).filter(JobRecord.public_id == job_id).one()
        candidate_b = db.query(Candidate).filter(Candidate.user_id == user_b).one()
        insert_grounded_package(db, job, candidate=candidate_b)
        insert_score(db, job, candidate=candidate_b)

    client.patch(f"/api/applications/{job_id}/tracking", json={"status": "applied"})
    client.post(f"/api/jobs/{job_id}/save")

    client.cookies.clear()
    login_a = client.post(
        "/api/auth/login",
        json={"email": "test-user@example.com", "password": TEST_USER_PASSWORD},
    )
    assert login_a.status_code == 200, login_a.text
    assert client.delete("/api/account").status_code == 204

    client.cookies.clear()
    login_b = client.post(
        "/api/auth/login",
        json={"email": "privacy-b@example.com", "password": "a-real-password-1"},
    )
    assert login_b.status_code == 200, login_b.text
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["id"] == user_b
    profile = client.get("/api/profile")
    assert profile.status_code == 200
    assert profile.json()["candidate"] is not None
    materials = client.get(f"/api/jobs/{job_id}/materials")
    assert materials.status_code == 200
    tracking = client.get(f"/api/applications/{job_id}/tracking")
    assert tracking.status_code == 200
    job_resp = client.get(f"/api/jobs/{job_id}")
    assert job_resp.status_code == 200

    with SessionLocal() as db:
        assert db.query(User).filter(User.id == user_a).first() is None
        assert db.query(User).filter(User.id == user_b).first() is not None
        assert db.query(JobRecord).filter(JobRecord.public_id == job_id).first() is not None


def test_delete_account_cannot_target_another_user(isolated_client) -> None:
    client, SessionLocal = isolated_client
    user_a = client.test_user_id
    user_b = _signup(client, "privacy-idor@example.com")
    client.cookies.clear()
    login_a = client.post(
        "/api/auth/login",
        json={"email": "test-user@example.com", "password": TEST_USER_PASSWORD},
    )
    assert login_a.status_code == 200, login_a.text
    deleted = client.delete(f"/api/account?user_id={user_b}")
    assert deleted.status_code == 204
    with SessionLocal() as db:
        assert db.query(User).filter(User.id == user_a).first() is None
        assert db.query(User).filter(User.id == user_b).first() is not None


def test_login_throttling_returns_429_without_enumerating_accounts(isolated_client) -> None:
    client, _ = isolated_client
    client.cookies.clear()
    email = "missing-privacy@example.com"
    for _ in range(LOGIN_IDENTITY.max_events):
        response = client.post(
            "/api/auth/login", json={"email": email, "password": "wrong-password-1"}
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid email or password."
    limited = client.post("/api/auth/login", json={"email": email, "password": "wrong-password-1"})
    assert limited.status_code == 429
    assert limited.headers.get("retry-after")
    assert "Invalid email" not in limited.json()["detail"]
    assert email not in limited.text


def test_successful_login_clears_identity_throttle(isolated_client) -> None:
    client, _ = isolated_client
    client.cookies.clear()
    email = "test-user@example.com"
    for _ in range(3):
        response = client.post(
            "/api/auth/login", json={"email": email, "password": "wrong-password-1"}
        )
        assert response.status_code == 401
    ok = client.post("/api/auth/login", json={"email": email, "password": TEST_USER_PASSWORD})
    assert ok.status_code == 200, ok.text
    client.cookies.clear()
    again = client.post("/api/auth/login", json={"email": email, "password": "wrong-password-1"})
    assert again.status_code == 401


def test_incomplete_scout_does_not_consume_expensive_guard(isolated_client, monkeypatch) -> None:
    client, _ = isolated_client
    scout = Mock(return_value=[])
    monkeypatch.setattr("backend.api.routes.jobs.scout_jobs", scout)
    response = client.post("/api/scout-jobs")
    assert response.status_code == 409
    assert scout.call_count == 0
    assert f"scout:{hash_key(str(client.test_user_id))}" not in runtime_guards._windows


def test_expensive_limits_are_per_user(isolated_client, monkeypatch) -> None:
    client, SessionLocal = isolated_client
    scout = Mock(return_value=[])
    monkeypatch.setattr("backend.api.routes.jobs.scout_jobs", scout)
    monkeypatch.setattr("backend.api.routes.jobs.score_jobs_batch", lambda *args, **kwargs: (0, 0))
    monkeypatch.setattr("backend.api.routes.jobs.verify_top_ranked_jobs", lambda *args, **kwargs: None)

    with SessionLocal() as db:
        insert_ready_profile(db, user_id=client.test_user_id)
    for _ in range(8):
        assert client.post("/api/scout-jobs").status_code == 202
    limited = client.post("/api/scout-jobs")
    assert limited.status_code == 429
    assert limited.headers.get("retry-after")
    assert scout.call_count == 8

    user_b = _signup(client, "privacy-scout-b@example.com")
    with SessionLocal() as db:
        insert_ready_profile(db, user_id=user_b)
    other = client.post("/api/scout-jobs")
    assert other.status_code == 202, other.text
    assert scout.call_count == 9


def test_concurrent_expensive_action_returns_409(isolated_client, monkeypatch) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        insert_ready_profile(db, user_id=client.test_user_id)
    token = runtime_guards.acquire_inflight(category="scout", identity=str(client.test_user_id))
    try:
        scout = Mock(return_value=[])
        monkeypatch.setattr("backend.api.routes.jobs.scout_jobs", scout)
        response = client.post("/api/scout-jobs")
        assert response.status_code == 409
        assert scout.call_count == 0
    finally:
        runtime_guards.release_inflight(token)

    monkeypatch.setattr("backend.api.routes.jobs.scout_jobs", Mock(return_value=[]))
    monkeypatch.setattr("backend.api.routes.jobs.score_jobs_batch", lambda *args, **kwargs: (0, 0))
    monkeypatch.setattr("backend.api.routes.jobs.verify_top_ranked_jobs", lambda *args, **kwargs: None)
    released = client.post("/api/scout-jobs")
    assert released.status_code == 202, released.text


def test_inflight_guard_releases_when_expensive_action_fails(isolated_client, monkeypatch) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        insert_ready_profile(db, user_id=client.test_user_id)
    monkeypatch.setattr(
        "backend.api.routes.jobs.scout_jobs",
        Mock(side_effect=HTTPException(status_code=502, detail="Scout unavailable.")),
    )
    failed = client.post("/api/scout-jobs")
    assert failed.status_code == 502
    monkeypatch.setattr("backend.api.routes.jobs.scout_jobs", Mock(return_value=[]))
    monkeypatch.setattr("backend.api.routes.jobs.score_jobs_batch", lambda *args, **kwargs: (0, 0))
    monkeypatch.setattr("backend.api.routes.jobs.verify_top_ranked_jobs", lambda *args, **kwargs: None)
    retry = client.post("/api/scout-jobs")
    assert retry.status_code == 202, retry.text


def test_security_headers_on_api_without_hsts_in_dev(isolated_client) -> None:
    client, _ = isolated_client
    response = client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "geolocation=()" in response.headers["permissions-policy"]
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "strict-transport-security" not in {k.lower() for k in response.headers}


def test_hsts_only_when_production_https(isolated_client, monkeypatch) -> None:
    client, _ = isolated_client
    monkeypatch.setattr("backend.core.security_headers.settings.app_env", "production")
    monkeypatch.setattr("backend.core.security_headers.settings.cookie_secure", True)
    response = client.get("/health")
    assert response.headers["strict-transport-security"].startswith("max-age=")


def test_oversized_preference_item_rejected(isolated_client) -> None:
    client, _ = isolated_client
    response = client.post(
        "/api/preferences",
        json={"target_roles": ["x" * 201]},
    )
    assert response.status_code == 422


def test_oversized_interview_answer_rejected(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        job, _ = seed_materials_prerequisites(db, user_id=client.test_user_id)
        job_id = job.public_id
    response = client.post(
        f"/api/jobs/{job_id}/interview-prep/feedback",
        json={"question": "Why this role?", "answer": "a" * 20001},
    )
    assert response.status_code == 422


def test_ingest_rejects_localhost_without_fetch(isolated_client, monkeypatch) -> None:
    client, _ = isolated_client
    fetch = Mock(side_effect=AssertionError("must not fetch unsafe URL"))
    monkeypatch.setattr("backend.services.url_safety.fetch_url_safely", fetch)
    monkeypatch.setattr("backend.services.job_scout_service.fetch_url_safely", fetch)
    for url in (
        "https://127.0.0.1/jobs/1",
        "https://localhost/jobs/1",
        "https://[::1]/jobs/1",
        "https://10.0.0.8/jobs/1",
        "https://192.168.1.8/jobs/1",
        "https://172.16.0.8/jobs/1",
        "https://169.254.169.254/latest/meta-data",
        "https://user:pass@example.com/jobs/1",
        "http://example.com/jobs/1",
    ):
        response = client.post("/api/jobs/ingest-url", json={"url": url})
        assert response.status_code == 422, (url, response.text)
    assert fetch.call_count == 0


def test_malformed_resume_rejected_without_parse_quota(isolated_client) -> None:
    client, _ = isolated_client
    response = client.post(
        "/api/parse-resume",
        files={"file": ("resume.pdf", b"this-is-not-a-pdf", "application/pdf")},
    )
    assert response.status_code == 400
    assert f"parse_resume:{hash_key(str(client.test_user_id))}" not in runtime_guards._windows


def test_oversized_resume_rejected_without_parse_quota(isolated_client) -> None:
    client, _ = isolated_client
    content = b"%PDF" + b"a" * (MAX_UPLOAD_BYTES + 1)
    response = client.post(
        "/api/parse-resume",
        files={"file": ("resume.pdf", content, "application/pdf")},
    )
    assert response.status_code == 413
    assert f"parse_resume:{hash_key(str(client.test_user_id))}" not in runtime_guards._windows


def test_docs_omit_locked_api_csp(isolated_client) -> None:
    client, _ = isolated_client
    response = client.get("/docs")
    assert response.status_code == 200
    csp = response.headers.get("content-security-policy", "")
    assert "default-src 'none'" not in csp
    assert response.headers["x-content-type-options"] == "nosniff"


def test_eeo_fields_are_not_copied_into_provider_prompts() -> None:
    sentinel = "EEO-PROMPT-SENTINEL-ZZ9"
    prefs = TargetPreferences(
        target_roles=["Software Engineer"],
        gender=sentinel,
        race_ethnicity=sentinel,
        veteran_status=sentinel,
        disability_status=sentinel,
        salary_min=120000,
    )
    dumped = _materials_prompt_preferences(prefs)
    assert dumped is not None
    combined = str(dumped)
    assert sentinel not in combined
    assert "120000" not in combined
    assert "gender" not in dumped
    assert "race_ethnicity" not in dumped


def test_eeo_values_are_not_logged_on_preferences(isolated_client, caplog) -> None:
    client, _ = isolated_client
    sentinel = "EEO-PRIVACY-SENTINEL-ZZ9"
    with caplog.at_level("INFO"):
        response = client.post(
            "/api/preferences",
            json={
                "target_roles": ["Software Engineer"],
                "gender": sentinel,
                "race_ethnicity": sentinel,
                "veteran_status": sentinel,
                "disability_status": sentinel,
            },
        )
    assert response.status_code == 201, response.text
    combined = " ".join(record.getMessage() for record in caplog.records)
    assert sentinel not in combined
    assert response.json()["gender"] == sentinel


def test_passwords_are_not_echoed_on_login_failure(isolated_client) -> None:
    client, _ = isolated_client
    client.cookies.clear()
    secret = "SuperSecretPassword99!"
    response = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": secret}
    )
    assert response.status_code == 401
    assert secret not in response.text


def test_rate_limit_store_evicts_instead_of_growing_unbounded() -> None:
    for index in range(4200):
        runtime_guards.check_and_record(category="login_ip", identity=f"spray-{index}")
    assert len(runtime_guards._windows) <= 4096
