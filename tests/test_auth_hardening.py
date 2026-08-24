"""Auth hardening: hashed sessions, password bounds, CSRF, cookies, extension header."""

from __future__ import annotations

import json

import pytest

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


def test_settings_reject_wildcard_and_non_exact_origins() -> None:
    from backend.core.config import validate_origin_settings

    with pytest.raises(RuntimeError, match="Wildcard"):
        validate_origin_settings(Settings(allowed_origins="*"))
    with pytest.raises(RuntimeError, match="Wildcard"):
        validate_origin_settings(Settings(allowed_origins="https://*.example.com"))
    with pytest.raises(RuntimeError, match="path"):
        validate_origin_settings(Settings(allowed_origins="https://example.com/app"))
    with pytest.raises(RuntimeError, match="query"):
        validate_origin_settings(Settings(allowed_origins="https://example.com?q=1"))
    with pytest.raises(RuntimeError, match="http:// or https://"):
        validate_origin_settings(Settings(allowed_origins="ftp://example.com"))
    with pytest.raises(RuntimeError, match="chrome-extension"):
        validate_origin_settings(Settings(extension_origin="https://evil.example"))
    validate_origin_settings(
        Settings(
            allowed_origins="http://localhost:5173,https://127.0.0.1:5173",
            extension_origin="chrome-extension://abcdefghijklmnopabcdefghijklmnop",
        )
    )


VALID_EXTENSION_ORIGIN = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"

_INVALID_EXTENSION_ORIGINS = (
    "",
    "   ",
    "chrome-extension://",
    "chrome-extension://abc",
    "chrome-extension://abcdefghijklmnopabcdefghijklmno",  # 31 chars
    "chrome-extension://abcdefghijklmnopabcdefghijklmnopq",  # 33 chars
    "chrome-extension://evil.com",
    "chrome-extension://abcdefghijklmnopabcdefghijklmnop:80",
    "chrome-extension://USER@abcdefghijklmnopabcdefghijklmnop",
    "chrome-extension://ABCDEFGHIJKLMNOPABCDEFGHIJKLMNOP",
    "chrome-extension://abcdefghijklmnopqrstuvwxyzabcdef",  # letters beyond a-p
    "chrome-extension://*",
    "chrome-extension://abcdefghijklmnopabcdefghijklmnop/",
    "chrome-extension://abcdefghijklmnopabcdefghijklmnop/path",
    "chrome-extension://abcdefghijklmnopabcdefghijklmnop?x=1",
    "chrome-extension://abcdefghijklmnopabcdefghijklmnop#fragment",
    " chrome-extension://abcdefghijklmnopabcdefghijklmnop",
    "chrome-extension://abcdefghijklmnopabcdefghijklmnop ",
    "chrome-extension://abcdefghijklmnopabcdefghijklmnop,chrome-extension://abcdefghijklmnopabcdefghijklmnop",
    "https://abcdefghijklmnopabcdefghijklmnop",
)


@pytest.mark.parametrize("origin", _INVALID_EXTENSION_ORIGINS)
def test_extension_origin_must_be_exact_32_char_a_to_p_id(origin: str) -> None:
    from backend.core.config import _validate_extension_origin

    with pytest.raises(RuntimeError, match="chrome-extension"):
        _validate_extension_origin(origin)


def test_extension_origin_accepts_exact_full_string_match() -> None:
    from backend.core.config import _validate_extension_origin, validate_origin_settings

    _validate_extension_origin(VALID_EXTENSION_ORIGIN)
    validate_origin_settings(
        Settings(
            allowed_origins="http://localhost:5173",
            extension_origin=VALID_EXTENSION_ORIGIN,
        )
    )


def test_blank_extension_origin_still_disables_extension_cors() -> None:
    from backend.core.config import validate_origin_settings

    cfg = Settings(allowed_origins="http://localhost:5173", extension_origin="")
    validate_origin_settings(cfg)
    assert VALID_EXTENSION_ORIGIN not in cfg.cors_allow_origins
    assert all(not item.startswith("chrome-extension://") for item in cfg.cors_allow_origins)


def test_invalid_extension_origin_is_not_normalized_or_ignored() -> None:
    from backend.core.config import validate_origin_settings

    padded = f" {VALID_EXTENSION_ORIGIN} "
    with pytest.raises(RuntimeError, match="chrome-extension"):
        validate_origin_settings(
            Settings(allowed_origins="http://localhost:5173", extension_origin=padded)
        )


def _assert_secret_absent(response, caplog, secret: str) -> None:
    body = response.text
    serialized = str(response.json())
    logs = caplog.text
    assert secret not in body
    assert secret not in serialized
    assert secret not in logs
    detail = response.json().get("detail")
    blob = json.dumps(detail)
    assert "input" not in blob or secret not in blob
    assert secret not in blob


def test_signup_and_login_validation_does_not_echo_passwords(isolated_client, caplog) -> None:
    import logging

    caplog.set_level(logging.DEBUG)
    client, _SessionLocal = isolated_client
    client.cookies.clear()
    short = "leakPw7"
    long = "leak-long-" + ("x" * 130)
    signup_short = client.post(
        "/api/auth/signup",
        json={"email": "short-echo@example.com", "password": short},
    )
    assert signup_short.status_code == 422
    _assert_secret_absent(signup_short, caplog, short)

    signup_long = client.post(
        "/api/auth/signup",
        json={"email": "long-echo@example.com", "password": long},
    )
    assert signup_long.status_code == 422
    _assert_secret_absent(signup_long, caplog, long)

    login_short = client.post(
        "/api/auth/login",
        json={"email": "login-echo@example.com", "password": short},
    )
    assert login_short.status_code in {401, 422}
    _assert_secret_absent(login_short, caplog, short)

    login_long = client.post(
        "/api/auth/login",
        json={"email": "login-echo@example.com", "password": long},
    )
    assert login_long.status_code == 422
    _assert_secret_absent(login_long, caplog, long)
