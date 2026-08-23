"""Auth: password hashing, signup/login/logout/session lifecycle, and
cross-user data isolation. Uses the shared isolated_session/isolated_client
fixtures (tests/conftest.py) — never touches data/careerpilot.db.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from backend.core.security import generate_session_token, hash_password, verify_password
from backend.db.models import Candidate, TargetPreference, User, UserSession
from backend.services import auth_service

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def test_hash_and_verify_round_trip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed) is True


def test_verify_rejects_wrong_password() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("wrong password", hashed) is False


def test_verify_rejects_malformed_hash_instead_of_crashing() -> None:
    assert verify_password("anything", "not-a-real-argon2-hash") is False


def test_hash_is_salted_differently_each_call() -> None:
    first = hash_password("same password")
    second = hash_password("same password")
    assert first != second
    assert verify_password("same password", first)
    assert verify_password("same password", second)


def test_generate_session_token_is_unique_and_high_entropy() -> None:
    tokens = {generate_session_token() for _ in range(100)}
    assert len(tokens) == 100
    assert all(len(token) >= 32 for token in tokens)


# ---------------------------------------------------------------------------
# Signup
# ---------------------------------------------------------------------------


def test_signup_creates_exactly_one_user(isolated_session) -> None:
    user = auth_service.signup(isolated_session, "Jordan@Example.com", "a-real-password")
    assert isolated_session.query(User).count() == 1
    assert user.email == "jordan@example.com"  # normalized lowercase
    assert user.hashed_password != "a-real-password"  # never stored in plain text


def test_signup_rejects_duplicate_email(isolated_session) -> None:
    auth_service.signup(isolated_session, "jordan@example.com", "a-real-password")
    with pytest.raises(HTTPException) as exc_info:
        auth_service.signup(isolated_session, "jordan@example.com", "a-different-password")
    assert exc_info.value.status_code == 409
    assert isolated_session.query(User).count() == 1


def test_signup_rejects_duplicate_email_case_insensitively(isolated_session) -> None:
    auth_service.signup(isolated_session, "jordan@example.com", "a-real-password")
    with pytest.raises(HTTPException) as exc_info:
        auth_service.signup(isolated_session, "JORDAN@EXAMPLE.COM", "a-different-password")
    assert exc_info.value.status_code == 409


def test_signup_rejects_a_too_short_password(isolated_session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        auth_service.signup(isolated_session, "jordan@example.com", "short")
    assert exc_info.value.status_code == 422
    assert isolated_session.query(User).count() == 0


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


def test_authenticate_succeeds_with_correct_credentials(isolated_session) -> None:
    auth_service.signup(isolated_session, "jordan@example.com", "a-real-password")
    user = auth_service.authenticate(isolated_session, "jordan@example.com", "a-real-password")
    assert user is not None
    assert user.email == "jordan@example.com"


def test_authenticate_is_case_insensitive_on_email(isolated_session) -> None:
    auth_service.signup(isolated_session, "jordan@example.com", "a-real-password")
    user = auth_service.authenticate(isolated_session, "JORDAN@example.com", "a-real-password")
    assert user is not None


def test_authenticate_returns_none_for_wrong_password(isolated_session) -> None:
    auth_service.signup(isolated_session, "jordan@example.com", "a-real-password")
    assert auth_service.authenticate(isolated_session, "jordan@example.com", "wrong-password") is None


def test_authenticate_returns_none_for_nonexistent_email(isolated_session) -> None:
    assert auth_service.authenticate(isolated_session, "nobody@example.com", "anything") is None


def test_authenticate_failure_reason_is_indistinguishable(isolated_session) -> None:
    """Wrong password and nonexistent email must be impossible to tell
    apart from the return value alone — both simply return None — so a
    login failure can't be used to enumerate which emails have accounts."""
    auth_service.signup(isolated_session, "jordan@example.com", "a-real-password")
    wrong_password = auth_service.authenticate(isolated_session, "jordan@example.com", "wrong")
    no_such_user = auth_service.authenticate(isolated_session, "nobody@example.com", "wrong")
    assert wrong_password is no_such_user is None


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


def test_create_session_then_resolve_by_token(isolated_session) -> None:
    user = auth_service.signup(isolated_session, "jordan@example.com", "a-real-password")
    session = auth_service.create_session(isolated_session, user)
    resolved = auth_service.get_user_by_token(isolated_session, session.token)
    assert resolved is not None
    assert resolved.id == user.id


def test_get_user_by_token_returns_none_for_unknown_token(isolated_session) -> None:
    assert auth_service.get_user_by_token(isolated_session, "not-a-real-token") is None


def test_get_user_by_token_returns_none_for_expired_session(isolated_session) -> None:
    user = auth_service.signup(isolated_session, "jordan@example.com", "a-real-password")
    expired = UserSession(
        token="expired-token",
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    isolated_session.add(expired)
    isolated_session.commit()
    assert auth_service.get_user_by_token(isolated_session, "expired-token") is None


def test_get_user_by_token_handles_naive_datetime_from_sqlite(isolated_session) -> None:
    """SQLite round-trips DateTime columns as naive even though they were
    written as UTC-aware — this must not raise a naive/aware TypeError."""
    user = auth_service.signup(isolated_session, "jordan@example.com", "a-real-password")
    session = auth_service.create_session(isolated_session, user)
    isolated_session.expire_all()  # force a fresh read from the DB, not the in-memory object
    resolved = auth_service.get_user_by_token(isolated_session, session.token)
    assert resolved is not None


def test_invalidate_session_deletes_it(isolated_session) -> None:
    user = auth_service.signup(isolated_session, "jordan@example.com", "a-real-password")
    session = auth_service.create_session(isolated_session, user)
    auth_service.invalidate_session(isolated_session, session.token)
    assert auth_service.get_user_by_token(isolated_session, session.token) is None


# ---------------------------------------------------------------------------
# Route-level: signup/login/logout/me
# ---------------------------------------------------------------------------


def test_signup_route_sets_a_session_cookie(isolated_client) -> None:
    client, _SessionLocal = isolated_client
    response = client.post(
        "/api/auth/signup", json={"email": "new-user@example.com", "password": "a-real-password"}
    )
    assert response.status_code == 201
    assert response.json()["email"] == "new-user@example.com"
    assert "careerpilot_session" in response.cookies


def test_signup_route_rejects_duplicate_email(isolated_client) -> None:
    client, _SessionLocal = isolated_client
    payload = {"email": "dup@example.com", "password": "a-real-password"}
    assert client.post("/api/auth/signup", json=payload).status_code == 201
    response = client.post("/api/auth/signup", json=payload)
    assert response.status_code == 409


def test_login_route_succeeds_and_sets_a_new_session_cookie(isolated_client) -> None:
    client, _SessionLocal = isolated_client
    client.post("/api/auth/signup", json={"email": "login-user@example.com", "password": "a-real-password"})
    client.cookies.clear()
    response = client.post(
        "/api/auth/login", json={"email": "login-user@example.com", "password": "a-real-password"}
    )
    assert response.status_code == 200
    assert "careerpilot_session" in response.cookies


def test_login_route_rejects_wrong_password(isolated_client) -> None:
    client, _SessionLocal = isolated_client
    client.post("/api/auth/signup", json={"email": "login-user@example.com", "password": "a-real-password"})
    client.cookies.clear()
    response = client.post(
        "/api/auth/login", json={"email": "login-user@example.com", "password": "wrong-password"}
    )
    assert response.status_code == 401


def test_me_route_requires_a_session(isolated_client) -> None:
    client, _SessionLocal = isolated_client
    client.cookies.clear()
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_me_route_returns_the_logged_in_user(isolated_client) -> None:
    client, _SessionLocal = isolated_client  # fixture already signed this client in
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json()["email"]


def test_logout_route_clears_the_cookie_and_invalidates_the_session(isolated_client) -> None:
    client, SessionLocal = isolated_client
    me_before = client.get("/api/auth/me")
    assert me_before.status_code == 200
    session_token = client.cookies.get("careerpilot_session")

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 204

    with SessionLocal() as db:
        assert db.query(UserSession).filter(UserSession.token == session_token).first() is None

    # Replaying the pre-logout cookie must not still work — a client-only
    # cookie clear that left the session row valid server-side would let a
    # stolen/copied cookie keep working after "logout".
    replayed = client.get("/api/auth/me", cookies={"careerpilot_session": session_token})
    assert replayed.status_code == 401


# ---------------------------------------------------------------------------
# Every protected route actually requires auth
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/jobs"),
        ("POST", "/api/scout-jobs"),
        ("GET", "/api/jobs/does-not-exist"),
        ("POST", "/api/preferences"),
        ("POST", "/api/jobs/does-not-exist/score"),
        ("GET", "/api/jobs/does-not-exist/intelligence"),
        ("POST", "/api/jobs/does-not-exist/generate-materials"),
        ("POST", "/api/jobs/does-not-exist/approve"),
        ("POST", "/api/jobs/does-not-exist/fill-application"),
        ("GET", "/api/extension/autofill?url=https://example.com/jobs/1"),
        ("POST", "/api/jobs/does-not-exist/prepare-interview"),
    ],
)
def test_protected_routes_401_without_a_session(isolated_client, method, path) -> None:
    client, _SessionLocal = isolated_client
    client.cookies.clear()
    response = client.request(method, path)
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Cross-user data isolation — the most important property this whole
# retrofit exists to guarantee.
# ---------------------------------------------------------------------------


def test_two_users_saved_preferences_never_cross(isolated_client) -> None:
    client, SessionLocal = isolated_client
    client.post(
        "/api/preferences",
        json={
            "target_roles": ["Backend Engineer"],
            "preferred_locations": ["Austin, TX"],
            "salary_min": None,
            "work_authorization": None,
            "sponsorship_required": None,
            "remote_preference": None,
            "constraints": [],
        },
    )
    user_one_id = client.test_user_id

    client.post("/api/auth/logout")
    client.post(
        "/api/auth/signup", json={"email": "second-user@example.com", "password": "a-real-password"}
    )
    me = client.get("/api/auth/me").json()
    user_two_id = me["id"]
    assert user_two_id != user_one_id

    client.post(
        "/api/preferences",
        json={
            "target_roles": ["Frontend Engineer"],
            "preferred_locations": ["Remote"],
            "salary_min": None,
            "work_authorization": None,
            "sponsorship_required": None,
            "remote_preference": None,
            "constraints": [],
        },
    )

    with SessionLocal() as db:
        prefs = db.query(TargetPreference).order_by(TargetPreference.id.asc()).all()
        assert len(prefs) == 2
        by_user = {pref.user_id: pref for pref in prefs}
        assert by_user[user_one_id].target_roles == ["Backend Engineer"]
        assert by_user[user_two_id].target_roles == ["Frontend Engineer"]


def test_candidate_lookup_never_resolves_to_a_different_users_row(isolated_session) -> None:
    """The core fix this whole module exists for: 'my candidate' must
    resolve strictly by user_id, never by 'whichever Candidate row happens
    to be newest' (the removed single-tenant behavior)."""
    from backend.services.application_service import _get_current_candidate

    older_other_user_candidate = Candidate(
        user_id=999,
        name="Someone Else",
        skills=[],
        projects=[],
        experience=[],
        education=[],
        certifications=[],
        strengths=[],
        evidence_links=[],
    )
    isolated_session.add(older_other_user_candidate)
    isolated_session.commit()

    # No candidate exists for user_id=1 yet — must not fall back to the
    # other user's newer row.
    assert _get_current_candidate(isolated_session, 1) is None

    mine = Candidate(
        user_id=1,
        name="Me",
        skills=[],
        projects=[],
        experience=[],
        education=[],
        certifications=[],
        strengths=[],
        evidence_links=[],
    )
    isolated_session.add(mine)
    isolated_session.commit()

    resolved = _get_current_candidate(isolated_session, 1)
    assert resolved is not None
    assert resolved.id == mine.id
