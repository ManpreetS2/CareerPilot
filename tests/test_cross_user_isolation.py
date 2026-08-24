"""Cross-user isolation for private records. Sanitized 404/409 only."""

from __future__ import annotations

import json

from backend.db.models import Candidate, TargetPreference
from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD
from tests.mvp_helpers import (
    insert_candidate,
    insert_grounded_package,
    insert_score,
    seed_materials_prerequisites,
)

UNIQUE_MATCHED_SKILL = "UniqueMatchedSkillAlpha"
UNIQUE_MISSING_SKILL = "UniqueMissingSkillOmega"


def _signup(client, email: str, password: str = "a-real-password"):
    client.cookies.clear()
    response = client.post("/api/auth/signup", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_user_b_cannot_read_or_mutate_user_a_private_records(isolated_client) -> None:
    client, SessionLocal = isolated_client
    user_a = client.test_user_id
    with SessionLocal() as db:
        job, candidate_a = seed_materials_prerequisites(db, user_id=user_a)
        insert_grounded_package(db, job, candidate=candidate_a)
        job_id = job.public_id

    client.patch(
        f"/api/applications/{job_id}/tracking",
        json={"status": "saved"},
    )
    client.post(f"/api/jobs/{job_id}/prepare-interview")

    _signup(client, "user-b@example.com")
    with SessionLocal() as db:
        insert_candidate(db, user_id=client.get("/api/auth/me").json()["id"])

    forbidden = [
        ("GET", f"/api/jobs/{job_id}/materials"),
        ("GET", f"/api/jobs/{job_id}/score"),
        ("POST", f"/api/jobs/{job_id}/approve"),
        ("POST", f"/api/jobs/{job_id}/discard-stale-materials"),
        ("POST", f"/api/jobs/{job_id}/fill-application"),
        ("GET", f"/api/applications/{job_id}/tracking"),
        ("GET", f"/api/jobs/{job_id}/interview-prep"),
    ]
    for method, path in forbidden:
        if method == "POST" and path.endswith("/approve"):
            response = client.post(
                path,
                json={"decision": "approved", "eligibility_confirmed": True},
            )
        else:
            response = client.request(method, path)
        if path.endswith("/tracking") and response.status_code == 200:
            assert response.json().get("status") is None
            continue
        assert response.status_code in {404, 409}, (method, path, response.status_code, response.text)
        detail = str(response.json().get("detail", "")).lower()
        assert str(user_a) not in detail
        assert TEST_USER_EMAIL.lower() not in detail


def test_stale_reviewed_discard_is_owner_only(isolated_client) -> None:
    client, SessionLocal = isolated_client
    user_a = client.test_user_id
    with SessionLocal() as db:
        job, candidate_a = seed_materials_prerequisites(db, user_id=user_a)
        package = insert_grounded_package(db, job, candidate=candidate_a)
        package.approval_status = "approved"
        db.commit()
        job_id = job.public_id

    _signup(client, "other-owner@example.com")
    response = client.post(f"/api/jobs/{job_id}/discard-stale-materials")
    assert response.status_code == 409
    client.cookies.clear()
    login = client.post(
        "/api/auth/login",
        json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
    )
    assert login.status_code == 200
    # Same candidate still owns the reviewed package, so discard is invalid until the profile changes.
    same_profile = client.post(f"/api/jobs/{job_id}/discard-stale-materials")
    assert same_profile.status_code == 409


def test_user_without_candidate_cannot_read_another_users_score_or_interview(isolated_client) -> None:
    client, SessionLocal = isolated_client
    user_a = client.test_user_id
    with SessionLocal() as db:
        job, candidate_a = seed_materials_prerequisites(db, user_id=user_a, with_score=False)
        insert_score(
            db,
            job,
            candidate_a,
            recommendation="apply",
            overall_score=91.0,
            matched_skills=[UNIQUE_MATCHED_SKILL],
            missing_skills=[UNIQUE_MISSING_SKILL],
        )
        insert_grounded_package(db, job, candidate=candidate_a)
        db.add(
            TargetPreference(
                user_id=user_a,
                candidate_id=candidate_a.id,
                target_roles=["Harbor Robotics Intern"],
                preferred_locations=["Remote"],
            )
        )
        db.commit()
        job_id = job.public_id
        job_title = job.title
        candidate_name = candidate_a.name

    a_apps = client.get("/api/applications")
    assert a_apps.status_code == 200
    a_item = next(item for item in a_apps.json() if item["job_id"] == job_id)
    assert a_item["match_score"] == 91.0
    assert a_item["recommendation"] == "apply"
    a_dashboard = client.get("/api/dashboard/summary")
    assert a_dashboard.status_code == 200
    assert a_dashboard.json()["high_matches"] >= 1
    a_profile = client.get("/api/profile")
    assert a_profile.status_code == 200
    assert a_profile.json()["candidate"]["name"] == candidate_name
    assert a_profile.json()["preferences"]["target_roles"] == ["Harbor Robotics Intern"]
    client.post(f"/api/jobs/{job_id}/prepare-interview")

    b_id = _signup(client, "no-candidate-b@example.com")
    with SessionLocal() as db:
        assert db.query(Candidate).filter(Candidate.user_id == b_id).first() is None

    apps = client.get("/api/applications")
    assert apps.status_code == 200
    shared = next(item for item in apps.json() if item["job_id"] == job_id)
    assert shared["title"] == job_title
    assert shared["match_score"] is None
    assert shared["recommendation"] is None
    assert shared["approval_status"] is None
    assert shared["tracker_status"] is None
    assert UNIQUE_MATCHED_SKILL not in json.dumps(shared)
    assert UNIQUE_MISSING_SKILL not in json.dumps(shared)

    dashboard = client.get("/api/dashboard/summary")
    assert dashboard.status_code == 200
    assert dashboard.json()["high_matches"] == 0

    profile = client.get("/api/profile")
    assert profile.status_code == 200
    assert profile.json() == {"candidate": None, "preferences": None}

    stored = client.get(f"/api/jobs/{job_id}/interview-prep")
    assert stored.status_code == 404

    generated = client.post(f"/api/jobs/{job_id}/prepare-interview")
    assert generated.status_code == 200
    generated_blob = json.dumps(generated.json())
    assert UNIQUE_MATCHED_SKILL not in generated_blob
    assert UNIQUE_MISSING_SKILL not in generated_blob

    stored_after = client.get(f"/api/jobs/{job_id}/interview-prep")
    assert stored_after.status_code == 200
    stored_blob = json.dumps(stored_after.json())
    assert UNIQUE_MATCHED_SKILL not in stored_blob
    assert UNIQUE_MISSING_SKILL not in stored_blob
    with SessionLocal() as db:
        assert db.query(Candidate).filter(Candidate.user_id == b_id).first() is None


def test_profile_get_is_user_scoped_read_only(isolated_client) -> None:
    client, SessionLocal = isolated_client
    user_a = client.test_user_id
    with SessionLocal() as db:
        insert_candidate(db, user_id=user_a)
        db.add(
            TargetPreference(
                user_id=user_a,
                target_roles=["Harbor Robotics Intern"],
                preferred_locations=["Seattle"],
            )
        )
        db.commit()
        before_candidates = db.query(Candidate).count()
        before_prefs = db.query(TargetPreference).count()

    response = client.get("/api/profile")
    assert response.status_code == 200
    payload = response.json()
    assert payload["candidate"]["name"]
    assert payload["preferences"]["target_roles"] == ["Harbor Robotics Intern"]

    with SessionLocal() as db:
        assert db.query(Candidate).count() == before_candidates
        assert db.query(TargetPreference).count() == before_prefs

    _signup(client, "profile-b@example.com")
    other = client.get("/api/profile")
    assert other.status_code == 200
    assert other.json() == {"candidate": None, "preferences": None}

    client.cookies.clear()
    anonymous = client.get("/api/profile")
    assert anonymous.status_code == 401
