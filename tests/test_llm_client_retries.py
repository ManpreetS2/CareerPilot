"""Exact provider retry call-count regressions for LLMClient."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from google.genai import errors as genai_errors

from backend.services.llm_client import LLMAuthError, LLMClient, LLMProviderError, LLMRateLimitError


def _make_gemini_client() -> LLMClient:
    with (
        patch("backend.core.config.settings.gemini_api_key", "test-key"),
        patch("backend.core.config.settings.gemini_model", "gemini-test"),
    ):
        return LLMClient(provider="gemini")


def test_gemini_transient_retries_exactly_once_then_succeeds() -> None:
    calls = {"n": 0}

    def generate_content(**_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise genai_errors.APIError(503, {"message": "unavailable"})
        return SimpleNamespace(text=" recovered ")

    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = generate_content

    client = _make_gemini_client()
    with patch("google.genai.Client", return_value=fake_client):
        result = client._generate_gemini("hello", None)

    assert result == "recovered"
    assert calls["n"] == 2


def test_gemini_transient_exhausted_exactly_two_calls() -> None:
    calls = {"n": 0}

    def generate_content(**_kwargs):
        calls["n"] += 1
        raise genai_errors.APIError(429, {"message": "rate limited"})

    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = generate_content

    client = _make_gemini_client()
    with patch("google.genai.Client", return_value=fake_client):
        with pytest.raises(LLMRateLimitError):
            client._generate_gemini("hello", None)

    assert calls["n"] == 2


def test_gemini_auth_failure_does_not_retry() -> None:
    calls = {"n": 0}

    def generate_content(**_kwargs):
        calls["n"] += 1
        raise genai_errors.APIError(401, {"message": "unauthorized"})

    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = generate_content

    client = _make_gemini_client()
    with patch("google.genai.Client", return_value=fake_client):
        with pytest.raises(LLMAuthError):
            client._generate_gemini("hello", None)

    assert calls["n"] == 1


def test_gemini_non_transient_no_retry() -> None:
    calls = {"n": 0}

    def generate_content(**_kwargs):
        calls["n"] += 1
        raise genai_errors.APIError(400, {"message": "bad request"})

    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = generate_content

    client = _make_gemini_client()
    with patch("google.genai.Client", return_value=fake_client):
        with pytest.raises(LLMProviderError):
            client._generate_gemini("hello", None)

    assert calls["n"] == 1
