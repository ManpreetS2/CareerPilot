"""Server gates for the profile-first workflow. No provider work when incomplete."""

from __future__ import annotations

from unittest.mock import Mock

from backend.db.models import Candidate, TargetPreference
from tests.mvp_helpers import insert_candidate, insert_job, insert_ready_profile


def test_profile_get_includes_readiness_for_empty_user(isolated_client) -> None:
    client, _ = isolated_client
    response = client.get("/api/profile")
    assert response.status_code == 200
    body = response.json()
    assert body["candidate"] is None
    assert body["preferences"] is None
    assert body["readiness"] == {
        "ready": False,
        "code": "profile_required",
        "missing": ["candidate_profile", "candidate_evidence", "target_roles"],
        "next_route": "/profile",
    }


def test_profile_get_readiness_when_complete(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        insert_ready_profile(db, user_id=client.test_user_id)
    body = client.get("/api/profile").json()
    assert body["readiness"]["ready"] is True
    assert body["readiness"]["missing"] == []
    assert body["readiness"]["code"] is None
    assert body["candidate"]["name"]
    assert body["preferences"]["target_roles"]


def test_incomplete_profile_does_not_call_scout_jobs(isolated_client, monkeypatch) -> None:
    client, _ = isolated_client
    scout = Mock(return_value=[])
    monkeypatch.setattr("backend.api.routes.jobs.scout_jobs", scout)
    score = Mock(return_value=(0, 0))
    monkeypatch.setattr("backend.api.routes.jobs.score_jobs_batch", score)
    verify = Mock()
    monkeypatch.setattr("backend.api.routes.jobs.verify_top_ranked_jobs", verify)

    response = client.post("/api/scout-jobs")
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "profile_required"
    assert "candidate_profile" in detail["missing"]
    assert detail["next_route"] == "/profile"
    assert scout.call_count == 0
    assert score.call_count == 0
    assert verify.call_count == 0


def test_partial_profile_without_roles_does_not_scout(isolated_client, monkeypatch) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        insert_candidate(db, user_id=client.test_user_id)
    scout = Mock(return_value=[])
    monkeypatch.setattr("backend.api.routes.jobs.scout_jobs", scout)

    response = client.post("/api/scout-jobs")
    assert response.status_code == 409
    assert response.json()["detail"]["missing"] == ["target_roles"]
    assert scout.call_count == 0


def test_complete_profile_scout_executes(isolated_client, monkeypatch) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        insert_ready_profile(db, user_id=client.test_user_id)
    scout = Mock(return_value=[])
    monkeypatch.setattr("backend.api.routes.jobs.scout_jobs", scout)
    monkeypatch.setattr("backend.api.routes.jobs.score_jobs_batch", lambda *args, **kwargs: (0, 0))
    monkeypatch.setattr("backend.api.routes.jobs.verify_top_ranked_jobs", lambda *args, **kwargs: None)

    response = client.post("/api/scout-jobs")
    assert response.status_code == 202
    assert scout.call_count == 1


def test_incomplete_profile_does_not_score(isolated_client, monkeypatch) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        insert_job(db, public_id="score-blocked")
    score = Mock()
    monkeypatch.setattr("backend.api.routes.scoring.score_job_with_intelligence", score)

    response = client.post("/api/jobs/score-blocked/score")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "profile_required"
    assert score.call_count == 0


def test_incomplete_profile_does_not_generate_materials(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        insert_job(db, public_id="materials-blocked")
    response = client.post("/api/jobs/materials-blocked/generate-materials")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "profile_required"


def test_incomplete_profile_does_not_prepare_interview(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        insert_job(db, public_id="interview-blocked")
    response = client.post("/api/jobs/interview-blocked/prepare-interview")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "profile_required"


def test_grounded_candidate_without_roles_can_score_unknown_job(isolated_client) -> None:
    """Scoring needs grounded evidence, not discovery preferences."""
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        insert_candidate(db, user_id=client.test_user_id)
    response = client.post("/api/jobs/missing-for-grounded-score/score")
    assert response.status_code == 404


def test_incomplete_profile_does_not_run_verified_fit(isolated_client, monkeypatch) -> None:
    from backend.core.config import settings

    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        insert_job(db, public_id="verified-fit-blocked")
    score = Mock()
    monkeypatch.setattr("backend.api.routes.applications.score_job_with_intelligence", score)
    token = client.cookies.get(settings.session_cookie_name)
    response = client.post(
        "/api/extension/jobs/verified-fit-blocked/verified-fit",
        headers={settings.session_header_name: token},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "profile_required"
    assert score.call_count == 0


def test_readiness_is_user_scoped(isolated_client, monkeypatch) -> None:
    client, SessionLocal = isolated_client
    user_a = client.test_user_id
    with SessionLocal() as db:
        insert_ready_profile(db, user_id=user_a)
    scout = Mock(return_value=[])
    monkeypatch.setattr("backend.api.routes.jobs.scout_jobs", scout)
    monkeypatch.setattr("backend.api.routes.jobs.score_jobs_batch", lambda *args, **kwargs: (0, 0))
    monkeypatch.setattr("backend.api.routes.jobs.verify_top_ranked_jobs", lambda *args, **kwargs: None)

    assert client.post("/api/scout-jobs").status_code == 202
    assert scout.call_count == 1

    signup = client.post(
        "/api/auth/signup",
        json={"email": "empty-b@example.com", "password": "a-real-password"},
    )
    assert signup.status_code == 201
    scout.reset_mock()

    profile = client.get("/api/profile").json()
    assert profile["readiness"]["ready"] is False
    assert profile["candidate"] is None
    blocked = client.post("/api/scout-jobs")
    assert blocked.status_code == 409
    assert scout.call_count == 0
    with SessionLocal() as db:
        b_id = signup.json()["id"]
        assert db.query(Candidate).filter(Candidate.user_id == b_id).first() is None
        assert db.query(TargetPreference).filter(TargetPreference.user_id == b_id).first() is None
