"""Ollama LLMClient request/response regressions. Network is always mocked."""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from backend.services.llm_client import (
    LLMClient,
    LLMConfigurationError,
    LLMEmptyResponseError,
    LLMProviderError,
    get_llm_client,
)
from backend.services.llm_structured_schemas import (
    application_materials_llm_schema,
    candidate_profile_llm_schema,
    job_intelligence_llm_schema,
)


SECRET_PROMPT = "SECRET_PROMPT_DO_NOT_LOG"
SECRET_SYSTEM = "SECRET_SYSTEM_DO_NOT_LOG"
SECRET_THINKING = "SECRET_THINKING_TRACE"
SECRET_BODY = '{"error":"model missing with secret token sk-test"}'


def _ollama_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.core.config.settings.ollama_base_url", "http://127.0.0.1:11434")
    monkeypatch.setattr("backend.core.config.settings.ollama_model", "qwen3:14b")
    monkeypatch.setattr("backend.core.config.settings.ollama_connect_timeout_seconds", 3.0)
    monkeypatch.setattr("backend.core.config.settings.ollama_read_timeout_seconds", 180.0)
    monkeypatch.setattr("backend.core.config.settings.ollama_keep_alive", "30m")
    monkeypatch.setattr("backend.core.config.settings.ollama_num_ctx", 8192)
    monkeypatch.setattr("backend.core.config.settings.ollama_num_predict", 4096)


def _client(monkeypatch: pytest.MonkeyPatch) -> LLMClient:
    _ollama_settings(monkeypatch)
    return LLMClient(provider="ollama")


class _FakeResponse:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = {}

    def json(self) -> object:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    @property
    def text(self) -> str:
        if isinstance(self._payload, dict):
            return json.dumps(self._payload)
        return SECRET_BODY


def _patch_httpx(monkeypatch: pytest.MonkeyPatch, response: _FakeResponse | Exception, captured: dict):
    class FakeClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, url, *, json=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers or {}
            if isinstance(response, Exception):
                raise response
            return response

    monkeypatch.setattr("httpx.Client", FakeClient)


def test_get_llm_client_ollama_does_not_require_cloud_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    _ollama_settings(monkeypatch)
    monkeypatch.setattr("backend.core.config.settings.gemini_api_key", None)
    monkeypatch.setattr("backend.core.config.settings.openai_api_key", None)
    monkeypatch.setattr("backend.core.config.settings.anthropic_api_key", None)
    client = get_llm_client("ollama")
    assert client.provider == "ollama"
    assert client.model == "qwen3:14b"


def test_ollama_request_payload_and_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)
    captured: dict = {}
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
    _patch_httpx(
        monkeypatch,
        _FakeResponse(200, {"done": True, "message": {"content": '{"ok": true}', "thinking": SECRET_THINKING}}),
        captured,
    )
    text = client._generate_ollama(SECRET_PROMPT, SECRET_SYSTEM, schema)
    assert json.loads(text) == {"ok": True}
    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    payload = captured["json"]
    assert payload["model"] == "qwen3:14b"
    assert payload["stream"] is False
    assert payload["think"] is False
    assert payload["keep_alive"] == "30m"
    assert payload["format"] == schema
    assert payload["options"]["temperature"] == 0
    assert payload["options"]["num_ctx"] == 8192
    assert payload["options"]["num_predict"] == 4096
    assert payload["messages"] == [
        {"role": "system", "content": SECRET_SYSTEM},
        {"role": "user", "content": SECRET_PROMPT},
    ]
    kwargs = captured["client_kwargs"]
    assert kwargs["trust_env"] is False
    assert kwargs["follow_redirects"] is False
    assert kwargs["verify"] is True
    timeout = kwargs["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect == 3.0
    assert timeout.read == 180.0
    headers = captured["headers"]
    joined = json.dumps(headers).lower()
    assert "authorization" not in joined
    assert "x-api-key" not in joined
    assert "gemini" not in joined
    assert "openai" not in joined
    assert "anthropic" not in joined
    assert "tailscale" not in joined


def test_ollama_returns_only_message_content(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)
    captured: dict = {}
    _patch_httpx(
        monkeypatch,
        _FakeResponse(
            200,
            {
                "done": True,
                "message": {"content": "  hello-content  ", "thinking": SECRET_THINKING},
            },
        ),
        captured,
    )
    assert client._generate_ollama("prompt", None, None) == "hello-content"


@pytest.mark.parametrize(
    ("response", "exc_type"),
    [
        (httpx.ConnectError("refused"), LLMProviderError),
        (httpx.ConnectTimeout("connect"), LLMProviderError),
        (httpx.ReadTimeout("read"), LLMProviderError),
        (_FakeResponse(404, {"error": SECRET_BODY}), LLMProviderError),
        (_FakeResponse(500, {"error": SECRET_BODY}), LLMProviderError),
        (_FakeResponse(200, {"done": True, "message": {"content": ""}}), LLMEmptyResponseError),
        (_FakeResponse(200, {"done": False, "message": {"content": "partial"}}), LLMProviderError),
        (_FakeResponse(200, {"done": True, "message": {}}), LLMEmptyResponseError),
        (_FakeResponse(200, {"done": True}), LLMProviderError),
        (_FakeResponse(200, "not-an-object"), LLMProviderError),
    ],
)
def test_ollama_failures_are_normalized(
    monkeypatch: pytest.MonkeyPatch,
    response: object,
    exc_type: type[Exception],
) -> None:
    client = _client(monkeypatch)
    captured: dict = {}
    _patch_httpx(monkeypatch, response, captured)  # type: ignore[arg-type]
    with pytest.raises(exc_type) as exc:
        client._generate_ollama(SECRET_PROMPT, SECRET_SYSTEM, None)
    message = str(exc.value)
    assert SECRET_PROMPT not in message
    assert SECRET_SYSTEM not in message
    assert SECRET_BODY not in message
    assert "127.0.0.1" not in message
    assert "/api/chat" not in message


def test_malformed_json_body_is_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)
    captured: dict = {}
    _patch_httpx(monkeypatch, _FakeResponse(200, json.JSONDecodeError("x", "doc", 0)), captured)
    with pytest.raises(LLMProviderError):
        client._generate_ollama(SECRET_PROMPT, None, None)


def test_ollama_logs_are_sanitized(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    client = _client(monkeypatch)
    captured: dict = {}
    _patch_httpx(monkeypatch, httpx.ConnectError("connection refused to 127.0.0.1:11434"), captured)
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(LLMProviderError):
            client._generate_ollama(SECRET_PROMPT, SECRET_SYSTEM, None)
    blob = caplog.text
    assert SECRET_PROMPT not in blob
    assert SECRET_SYSTEM not in blob
    assert SECRET_THINKING not in blob
    assert "127.0.0.1" not in blob
    assert "/api/chat" not in blob
    assert SECRET_BODY not in blob


def test_structured_schemas_omit_persistence_fields() -> None:
    profile = candidate_profile_llm_schema()
    assert profile["type"] == "object"
    assert "id" not in profile.get("properties", {})
    assert "id" not in profile.get("required", [])
    intelligence = job_intelligence_llm_schema()
    assert "job_id" not in intelligence.get("properties", {})
    assert "job_id" not in intelligence.get("required", [])
    materials = application_materials_llm_schema()
    props = materials.get("properties", {})
    assert "approval_status" not in props
    assert "grounded" not in props
    assert "eligibility_confirmed" not in props
    assert "job_id" not in props
    assert "tailored_bullets" in props


def test_unsupported_provider_still_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(LLMConfigurationError):
        LLMClient(provider="not-a-provider")
