"""Configuration regressions for Ollama URLs, provider order, and bounds.

These tests must never open a network connection or require a live Ollama host.
"""

from __future__ import annotations

import logging
import socket

import pytest

from backend.core.config import (
    parse_llm_provider_order,
    settings,
    validate_llm_settings,
    validate_ollama_base_url,
    validate_runtime_settings,
)


def test_blank_provider_order_preserves_gemini_only() -> None:
    assert parse_llm_provider_order(None) == ["gemini"]
    assert parse_llm_provider_order("") == ["gemini"]
    assert parse_llm_provider_order("   ") == ["gemini"]


def test_provider_order_parses_supported_names() -> None:
    assert parse_llm_provider_order("ollama,gemini") == ["ollama", "gemini"]
    assert parse_llm_provider_order("gemini, ollama") == ["gemini", "ollama"]
    assert parse_llm_provider_order("anthropic") == ["anthropic"]
    assert parse_llm_provider_order("openai") == ["openai"]


@pytest.mark.parametrize(
    "raw",
    ["ollama,unknown", "ollama,ollama", "ollama,,gemini", ",", "ollama, gemini, "],
)
def test_provider_order_rejects_empty_unknown_and_duplicates(raw: str) -> None:
    with pytest.raises(RuntimeError) as exc:
        parse_llm_provider_order(raw)
    message = str(exc.value)
    assert "provider" in message.lower()
    assert "unknown" not in message.lower() or "unsupported" in message.lower() or "duplicate" in message.lower() or "empty" in message.lower()
    assert "ollama,unknown" not in message
    assert raw.strip(",") not in message or raw in {",", "ollama,,gemini"}


def test_loopback_http_urls_are_accepted() -> None:
    assert validate_ollama_base_url("http://127.0.0.1:11434") == "http://127.0.0.1:11434"
    assert validate_ollama_base_url("http://localhost:11434").startswith("http://")
    assert validate_ollama_base_url("http://[::1]:11434").startswith("http://")


def test_exact_tailscale_https_hostname_is_accepted() -> None:
    url = "https://host-device.tailnet.ts.net"
    assert validate_ollama_base_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://203.0.113.10:11434",
        "http://example.invalid:11434",
        "http://host-device.tailnet.ts.net",
        "https://user:pass@host-device.tailnet.ts.net",
        "https://host-device.tailnet.ts.net/api",
        "https://host-device.tailnet.ts.net?x=1",
        "https://host-device.tailnet.ts.net#frag",
        "https://*.ts.net",
        "https://host*.tailnet.ts.net",
        "ftp://127.0.0.1:11434",
        "https://example.invalid",
    ],
)
def test_ollama_url_rejects_remote_http_credentials_paths_and_wildcards(url: str) -> None:
    with pytest.raises(RuntimeError) as exc:
        validate_ollama_base_url(url)
    message = str(exc.value)
    assert "Ollama" in message or "base URL" in message
    assert "203.0.113.10" not in message
    assert "example.invalid" not in message
    assert "user:pass" not in message
    assert "host-device" not in message
    assert "*.ts.net" not in message


def test_ollama_model_and_numeric_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ollama_model", "qwen3:14b")
    monkeypatch.setattr(settings, "ollama_base_url", "http://127.0.0.1:11434")
    monkeypatch.setattr(settings, "ollama_connect_timeout_seconds", 3.0)
    monkeypatch.setattr(settings, "ollama_read_timeout_seconds", 180.0)
    monkeypatch.setattr(settings, "ollama_keep_alive", "30m")
    monkeypatch.setattr(settings, "ollama_num_ctx", 8192)
    monkeypatch.setattr(settings, "ollama_num_predict", 4096)
    monkeypatch.setattr(settings, "llm_provider_order", "")
    validate_llm_settings(settings)

    monkeypatch.setattr(settings, "ollama_model", "")
    with pytest.raises(RuntimeError):
        validate_llm_settings(settings)
    monkeypatch.setattr(settings, "ollama_model", "qwen3:14b\ncurl evil")
    with pytest.raises(RuntimeError) as exc:
        validate_llm_settings(settings)
    assert "curl evil" not in str(exc.value)

    monkeypatch.setattr(settings, "ollama_model", "qwen3:14b")
    monkeypatch.setattr(settings, "ollama_connect_timeout_seconds", 0)
    with pytest.raises(RuntimeError):
        validate_llm_settings(settings)
    monkeypatch.setattr(settings, "ollama_connect_timeout_seconds", 3.0)
    monkeypatch.setattr(settings, "ollama_read_timeout_seconds", -1)
    with pytest.raises(RuntimeError):
        validate_llm_settings(settings)
    monkeypatch.setattr(settings, "ollama_read_timeout_seconds", 180.0)
    monkeypatch.setattr(settings, "ollama_num_ctx", 0)
    with pytest.raises(RuntimeError):
        validate_llm_settings(settings)
    monkeypatch.setattr(settings, "ollama_num_ctx", 8192)
    monkeypatch.setattr(settings, "ollama_num_predict", 0)
    with pytest.raises(RuntimeError):
        validate_llm_settings(settings)
    monkeypatch.setattr(settings, "ollama_num_predict", 4096)
    monkeypatch.setattr(settings, "ollama_keep_alive", "")
    with pytest.raises(RuntimeError):
        validate_llm_settings(settings)
    monkeypatch.setattr(settings, "ollama_keep_alive", "30m")
    monkeypatch.setattr(settings, "resume_llm_provider_order", "gemini,ollama")
    monkeypatch.setattr(settings, "resume_gemini_model", "gemini-3.5-flash-lite")
    monkeypatch.setattr(settings, "resume_ollama_model", "qwen3.5:4b")
    monkeypatch.setattr(settings, "resume_ollama_keep_alive", "2m")
    validate_llm_settings(settings)
    monkeypatch.setattr(settings, "resume_ollama_model", "")
    with pytest.raises(RuntimeError):
        validate_llm_settings(settings)


def test_config_validation_does_not_open_network_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*_args, **_kwargs):
        raise AssertionError("configuration must not open network sockets")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(settings, "ollama_base_url", "http://127.0.0.1:11434")
    monkeypatch.setattr(settings, "ollama_model", "qwen3:14b")
    monkeypatch.setattr(settings, "llm_provider_order", "ollama,gemini")
    validate_ollama_base_url(settings.ollama_base_url)
    parse_llm_provider_order(settings.llm_provider_order)
    validate_llm_settings(settings)
    validate_runtime_settings()


def test_config_errors_do_not_echo_endpoints_or_secrets(caplog: pytest.LogCaptureFixture) -> None:
    secret = "SECRET_TOKEN_DO_NOT_LOG_VALUE"
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(RuntimeError) as exc:
            validate_ollama_base_url(f"https://{secret}@host.tailnet.ts.net")
    blob = caplog.text + str(exc.value)
    assert secret not in blob
    assert "host.tailnet.ts.net" not in blob
