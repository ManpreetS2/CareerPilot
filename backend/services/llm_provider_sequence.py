"""Sequential LLM provider order for complete structured operations.

Fallback is not performed inside a single generate() call. Pipelines iterate
this list around parse, validate, ground, and usability gates.
"""

from __future__ import annotations

from backend.core.config import parse_llm_provider_order, settings


def configured_provider_names() -> list[str]:
    """Return the configured provider sequence, defaulting to Gemini-only."""

    return parse_llm_provider_order(settings.llm_provider_order)


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
