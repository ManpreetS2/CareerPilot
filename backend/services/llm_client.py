"""Thin LLM provider abstraction.

Secrets come from environment variables. This module does not implement
CareerPilot agent workflows — it only generates plain text.
"""

from __future__ import annotations

import logging
from typing import Literal

from backend.core.config import settings

logger = logging.getLogger(__name__)

ProviderName = Literal["gemini", "anthropic", "openai"]


class LLMConfigurationError(RuntimeError):
    """Raised when a provider is requested without the required API key."""


class LLMProviderError(RuntimeError):
    """Provider request failed after any allowed internal retry was exhausted."""


class LLMEmptyResponseError(RuntimeError):
    """Provider returned an empty payload (eligible for structured-output retry)."""


class LLMClient:
    """Normalize generate() across Gemini, Anthropic, and OpenAI."""

    def __init__(self, provider: ProviderName | str = "gemini") -> None:
        self.provider = provider.lower().strip()
        if self.provider not in {"gemini", "anthropic", "openai"}:
            raise LLMConfigurationError(
                f"Unsupported LLM provider '{provider}'. Use gemini, anthropic, or openai."
            )
        self.model = self._resolve_model()
        self._ensure_configured()

    def _resolve_model(self) -> str:
        if self.provider == "gemini":
            return settings.gemini_model
        if self.provider == "anthropic":
            return settings.anthropic_model
        return settings.openai_model

    def _ensure_configured(self) -> None:
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
        if self.provider == "gemini":
            return settings.gemini_api_key
        if self.provider == "anthropic":
            return settings.anthropic_api_key
        return settings.openai_api_key

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        """Return plain text from the selected provider."""
        if not prompt or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")

        logger.info("LLM generate provider=%s model=%s", self.provider, self.model)
        if self.provider == "gemini":
            return self._generate_gemini(prompt, system_prompt)
        if self.provider == "anthropic":
            return self._generate_anthropic(prompt, system_prompt)
        return self._generate_openai(prompt, system_prompt)

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
