"""Thin LLM provider abstraction.

Secrets come from environment variables. This module does not implement
CareerPilot agent workflows — it only generates plain text.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

import httpx

from backend.core.config import SUPPORTED_LLM_PROVIDERS, settings, validate_ollama_base_url

logger = logging.getLogger(__name__)

ProviderName = Literal["ollama", "gemini", "anthropic", "openai"]


class LLMConfigurationError(RuntimeError):
    """Raised when a provider is requested without the required API key."""


class LLMProviderError(RuntimeError):
    """Provider request failed after any allowed internal retry was exhausted."""


class LLMEmptyResponseError(RuntimeError):
    """Provider returned an empty payload (eligible for structured-output retry)."""


class LLMClient:
    """Normalize generate() across Ollama, Gemini, Anthropic, and OpenAI."""

    def __init__(self, provider: ProviderName | str = "gemini") -> None:
        self.provider = provider.lower().strip()
        if self.provider not in SUPPORTED_LLM_PROVIDERS:
            raise LLMConfigurationError(
                "Unsupported LLM provider. Use ollama, gemini, anthropic, or openai."
            )
        self.model = self._resolve_model()
        self._ensure_configured()

    def _resolve_model(self) -> str:
        if self.provider == "ollama":
            return settings.ollama_model
        if self.provider == "gemini":
            return settings.gemini_model
        if self.provider == "anthropic":
            return settings.anthropic_model
        return settings.openai_model

    def _ensure_configured(self) -> None:
        if self.provider == "ollama":
            model = (settings.ollama_model or "").strip()
            if not model:
                raise LLMConfigurationError("Ollama is not configured.")
            try:
                validate_ollama_base_url(settings.ollama_base_url)
            except RuntimeError as exc:
                raise LLMConfigurationError("Ollama is not configured.") from exc
            return
        key = self._api_key()
        if not key:
            env_name = {
                "gemini": "GEMINI_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY",
                "openai": "OPENAI_API_KEY",
            }[self.provider]
            raise LLMConfigurationError(
                f"{env_name} is not set. Copy .env.example to .env and add your key."
            )

    def _api_key(self) -> str | None:
        if self.provider == "ollama":
            return None
        if self.provider == "gemini":
            return settings.gemini_api_key
        if self.provider == "anthropic":
            return settings.anthropic_api_key
        return settings.openai_api_key

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        """Return plain text from the selected provider."""
        if not prompt or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")

        logger.info("LLM generate provider=%s model=%s", self.provider, self.model)
        if self.provider == "ollama":
            return self._generate_ollama(prompt, system_prompt, json_schema)
        if self.provider == "gemini":
            return self._generate_gemini(prompt, system_prompt)
        if self.provider == "anthropic":
            return self._generate_anthropic(prompt, system_prompt)
        return self._generate_openai(prompt, system_prompt)

    def _generate_ollama(
        self,
        prompt: str,
        system_prompt: str | None,
        json_schema: dict[str, Any] | None,
    ) -> str:
        try:
            base = validate_ollama_base_url(settings.ollama_base_url).rstrip("/")
        except RuntimeError as exc:
            raise LLMConfigurationError("Ollama is not configured.") from exc
        timeout = httpx.Timeout(
            connect=float(settings.ollama_connect_timeout_seconds),
            read=float(settings.ollama_read_timeout_seconds),
            write=float(settings.ollama_read_timeout_seconds),
            pool=float(settings.ollama_connect_timeout_seconds),
        )
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,
            "keep_alive": settings.ollama_keep_alive,
            "options": {
                "temperature": 0,
                "num_ctx": int(settings.ollama_num_ctx),
                "num_predict": int(settings.ollama_num_predict),
            },
        }
        if json_schema is not None:
            body["format"] = json_schema
        try:
            with httpx.Client(
                timeout=timeout,
                follow_redirects=False,
                trust_env=False,
                verify=True,
            ) as client:
                response = client.post(f"{base}/api/chat", json=body)
        except httpx.TimeoutException:
            logger.warning("Ollama request failed category=timeout")
            raise LLMProviderError("Ollama provider request failed.") from None
        except httpx.HTTPError:
            logger.warning("Ollama request failed category=connection")
            raise LLMProviderError("Ollama provider request failed.") from None
        except Exception:
            logger.warning("Ollama request failed category=connection")
            raise LLMProviderError("Ollama provider request failed.") from None
        if response.status_code >= 400:
            logger.warning("Ollama request failed category=http_status")
            raise LLMProviderError("Ollama provider request failed.")
        try:
            payload = response.json()
        except Exception:
            logger.warning("Ollama request failed category=malformed")
            raise LLMProviderError("Ollama provider request failed.") from None
        if not isinstance(payload, dict):
            logger.warning("Ollama request failed category=malformed")
            raise LLMProviderError("Ollama provider request failed.")
        if payload.get("done") is not True:
            logger.warning("Ollama request failed category=incomplete")
            raise LLMProviderError("Ollama provider request failed.")
        message = payload.get("message")
        if not isinstance(message, dict):
            logger.warning("Ollama request failed category=malformed")
            raise LLMProviderError("Ollama provider request failed.")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            logger.warning("Ollama request failed category=empty")
            raise LLMEmptyResponseError("Ollama returned an empty response.")
        return content.strip()

    def _generate_gemini(self, prompt: str, system_prompt: str | None) -> str:
        from google import genai
        from google.genai import types
        from google.genai import errors as genai_errors

        client = genai.Client(api_key=self._api_key())
        config = None
        if system_prompt:
            config = types.GenerateContentConfig(system_instruction=system_prompt)

        last_error: Exception | None = None
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config,
                )
                text = getattr(response, "text", None)
                if not text:
                    raise LLMEmptyResponseError("Gemini returned an empty response.")
                return text.strip()
            except LLMEmptyResponseError:
                raise
            except genai_errors.APIError as exc:
                last_error = exc
                status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
                logger.warning(
                    "Gemini APIError attempt=%s status=%s type=%s",
                    attempt + 1,
                    status,
                    type(exc).__name__,
                )
                # Retry once on transient provider pressure / rate limits.
                if status in {429, 500, 503} and attempt == 0:
                    continue
                raise LLMProviderError("Gemini provider request failed.") from exc
            except Exception as exc:  # noqa: BLE001 — normalize provider failures
                raise LLMProviderError("Gemini provider request failed.") from exc
        raise LLMProviderError("Gemini provider request failed.") from last_error

    def _generate_anthropic(self, prompt: str, system_prompt: str | None) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=self._api_key())
        kwargs: dict[str, object] = {}
        if system_prompt:
            kwargs["system"] = system_prompt
        try:
            message = client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            )
        except Exception as exc:  # noqa: BLE001
            raise LLMProviderError("Anthropic provider request failed.") from exc
        parts: list[str] = []
        for block in message.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        result = "".join(parts).strip()
        if not result:
            raise LLMEmptyResponseError("Anthropic returned an empty response.")
        return result

    def _generate_openai(self, prompt: str, system_prompt: str | None) -> str:
        from openai import OpenAI

        client = OpenAI(api_key=self._api_key())
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        try:
            response = client.chat.completions.create(model=self.model, messages=messages)
        except Exception as exc:  # noqa: BLE001
            raise LLMProviderError("OpenAI provider request failed.") from exc
        text = response.choices[0].message.content
        if not text:
            raise LLMEmptyResponseError("OpenAI returned an empty response.")
        return text.strip()


def get_llm_client(provider: str | None = None) -> LLMClient:
    """Build a client from an explicit provider or DEFAULT_LLM_PROVIDER."""
    return LLMClient(provider=provider or settings.default_llm_provider)


if __name__ == "__main__":
    # Manual smoke test: python -m backend.services.llm_client
    demo = LLMClient(provider=settings.default_llm_provider)
    output = demo.generate(
        "Reply with a single short sentence confirming the CareerPilot LLM client works."
    )
    print(output)
