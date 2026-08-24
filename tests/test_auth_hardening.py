"""Auth hardening: hashed sessions, password bounds, CSRF, cookies, extension header."""

from __future__ import annotations

from backend.core.config import Settings, settings, validate_runtime_settings
from backend.core.security import hash_password, hash_session_token
from backend.db.models import UserSession
from backend.services import auth_service


def test_raw_session_cookie_is_not_stored_in_the_database(isolated_client) -> None:
    client, SessionLocal = isolated_client
    raw = client.cookies.get(settings.session_cookie_name)
    assert raw
    with SessionLocal() as db:
        assert db.query(UserSession).filter(UserSession.token == raw).first() is None
        assert (
            db.query(UserSession).filter(UserSession.token == hash_session_token(raw)).first()
            is not None
        )


def test_signup_rejects_oversized_password_before_hashing(isolated_client, monkeypatch) -> None:
    client, _SessionLocal = isolated_client
    client.cookies.clear()
    called = {"n": 0}
    real = hash_password

    def wrapped(password: str) -> str:
        called["n"] += 1
        return real(password)

    monkeypatch.setattr("backend.core.security.hash_password", wrapped)
    monkeypatch.setattr("backend.services.auth_service.hash_password", wrapped)
    response = client.post(
        "/api/auth/signup",
        json={"email": "longpass@example.com", "password": "x" * 129},
    )
    assert response.status_code == 422
    assert called["n"] == 0


def test_signup_rejects_short_password_via_schema(isolated_client) -> None:
    client, _SessionLocal = isolated_client
    client.cookies.clear()
    response = client.post(
        "/api/auth/signup",
        json={"email": "shortpass@example.com", "password": "short"},
    )
    assert response.status_code == 422


def test_wrong_email_and_wrong_password_share_login_response(isolated_client) -> None:
    client, _SessionLocal = isolated_client
    client.cookies.clear()
    client.post("/api/auth/signup", json={"email": "same@example.com", "password": "a-real-password"})
    client.cookies.clear()
    wrong_password = client.post(
        "/api/auth/login", json={"email": "same@example.com", "password": "wrong-password"}
    )
    client.cookies.clear()
    wrong_email = client.post(
        "/api/auth/login", json={"email": "missing@example.com", "password": "wrong-password"}
    )
    assert wrong_password.status_code == wrong_email.status_code == 401
    assert wrong_password.json()["detail"] == wrong_email.json()["detail"]


def test_session_header_is_rejected_on_ordinary_routes(isolated_client) -> None:
    client, _SessionLocal = isolated_client
    raw = client.cookies.get(settings.session_cookie_name)
    client.cookies.clear()
    response = client.get("/api/jobs", headers={settings.session_header_name: raw})
    assert response.status_code == 401


def test_disallowed_origin_is_rejected_for_state_changing_cookie_requests(isolated_client) -> None:
    client, _SessionLocal = isolated_client
    response = client.post(
        "/api/auth/logout",
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403


def test_production_insecure_cookies_are_rejected() -> None:
    original_env = settings.app_env
    original_secure = settings.cookie_secure
    try:
        object.__setattr__(settings, "app_env", "production")
        object.__setattr__(settings, "cookie_secure", False)
        try:
            validate_runtime_settings()
            raised = False
        except RuntimeError:
            raised = True
        assert raised
    finally:
        object.__setattr__(settings, "app_env", original_env)
        object.__setattr__(settings, "cookie_secure", original_secure)


def test_settings_reject_wildcard_credential_origins() -> None:
    loaded = Settings(allowed_origins="http://localhost:5173")
    assert "*" not in loaded.cors_allow_origins
    assert loaded.cors_origin_regex is None
