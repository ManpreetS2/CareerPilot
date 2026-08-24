"""Cross-user isolation for private records. Sanitized 404/409 only."""

from __future__ import annotations

from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD
from tests.mvp_helpers import insert_candidate, insert_grounded_package, seed_materials_prerequisites


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
