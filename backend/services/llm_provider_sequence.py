"""Sequential LLM provider order for complete structured operations.

Fallback is not performed inside a single generate() call. Pipelines iterate
this list around parse, validate, ground, and usability gates.
"""

from __future__ import annotations

from backend.core.config import parse_llm_provider_order, settings, validate_ollama_base_url
from backend.services.llm_client import provider_is_configured


def configured_provider_names() -> list[str]:
    """Return the configured provider sequence, defaulting to Gemini-only."""

    return parse_llm_provider_order(settings.llm_provider_order)


def resume_provider_names() -> list[str]:
    """Resume extraction order. Independent of the global LLM_PROVIDER_ORDER."""

    return parse_llm_provider_order(settings.resume_llm_provider_order)


def job_requirements_provider_names() -> list[str]:
    """Job requirement extraction order. Independent of Fit scoring models."""

    return parse_llm_provider_order(settings.job_requirements_llm_provider_order)


def resume_provider_is_configured(provider: str) -> bool:
    """Skip known-unconfigured resume providers without waiting on them."""

    name = (provider or "").strip().lower()
    if name == "gemini":
        return bool((settings.gemini_api_key or "").strip()) and bool(
            (settings.resume_gemini_model or "").strip()
        )
    if name == "ollama":
        if not (settings.resume_ollama_model or "").strip():
            return False
        try:
            validate_ollama_base_url(settings.ollama_base_url)
        except RuntimeError:
            return False
        return True
    return provider_is_configured(name)


def uses_injected_generator(generate_fn: object | None, llm: object | None = None) -> bool:
    """Injected clients keep deterministic single-provider semantics."""

    return generate_fn is not None or llm is not None


def invoke_provider_generate(
    client: object,
    prompt: str,
    system_prompt: str | None,
    json_schema: dict | None = None,
) -> str:
    """Call generate(), passing a schema only when the client accepts it."""

    generate = getattr(client, "generate")
    try:
        return generate(prompt, system_prompt=system_prompt, json_schema=json_schema)
    except TypeError:
        return generate(prompt, system_prompt=system_prompt)
