"""Optional Gemini enrichment for ambiguous search text.

Never emits SQL, ORM, or URLs. Falls back immediately on timeout or error.
Does not send resume or profile data. Does not use Ollama.
"""

from __future__ import annotations

import json
import logging

from backend.core.config import settings
from backend.services.job_search_parser import JobSearchIntent

logger = logging.getLogger(__name__)

_SEARCH_TIMEOUT_SECONDS = 4.0
_GEMINI_MODEL = "gemini-3.5-flash-lite"

_INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "roles": {"type": "array", "items": {"type": "string"}},
        "locations": {"type": "array", "items": {"type": "string"}},
        "opportunity_types": {
            "type": "array",
            "items": {"type": "string", "enum": ["internship", "role", "unknown"]},
        },
        "employment_types": {"type": "array", "items": {"type": "string"}},
        "experience_levels": {"type": "array", "items": {"type": "string"}},
        "work_modes": {
            "type": "array",
            "items": {"type": "string", "enum": ["remote", "hybrid", "onsite"]},
        },
        "industries": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "roles",
        "locations",
        "opportunity_types",
        "employment_types",
        "experience_levels",
        "work_modes",
        "industries",
    ],
    "additionalProperties": False,
}

_ALLOWED_EMPLOYMENT = {
    "internship",
    "new_grad",
    "full_time",
    "part_time",
    "contract",
    "temporary",
    "co_op",
    "fellowship",
}
_ALLOWED_EXPERIENCE = {
    "intern",
    "new_grad",
    "entry",
    "junior",
    "mid",
    "senior",
    "staff",
    "principal",
    "lead",
    "manager",
    "director",
}
_ALLOWED_OPPORTUNITY = {"internship", "role", "unknown"}
_ALLOWED_WORK = {"remote", "hybrid", "onsite"}


def _needs_llm(intent: JobSearchIntent) -> bool:
    leftover = (intent.query or "").strip()
    if not leftover or len(leftover) < 10:
        return False
    return not (intent.roles and (intent.locations or intent.work_modes or intent.employment_types))


def enrich_search_intent(raw: str, deterministic: JobSearchIntent) -> JobSearchIntent:
    """Best-effort Gemini parse. Always returns a validated JobSearchIntent."""
    if not _needs_llm(deterministic):
        return deterministic
    if not (settings.gemini_api_key or "").strip():
        return deterministic
    try:
        from backend.services.llm_client import LLMClient

        client = LLMClient(
            provider="gemini",
            model=_GEMINI_MODEL,
            request_timeout_seconds=_SEARCH_TIMEOUT_SECONDS,
        )
        prompt = (
            "Extract job-search filters from this user query. "
            "Return only the JSON object. Never invent SQL, URLs, or database filters.\n\n"
            f"Query:\n{raw[:400]}"
        )
        payload = client.generate(
            prompt,
            system_prompt="You extract structured job search filters. Temperature must stay factual.",
            json_schema=_INTENT_SCHEMA,
        )
        data = json.loads(payload)
    except Exception:
        logger.info("search_intent gemini fallback to deterministic")
        return deterministic

    merged = deterministic.model_copy(deep=True)
    merged.roles = merged.roles or [item for item in data.get("roles") or [] if isinstance(item, str)][:5]
    merged.locations = merged.locations or [
        item for item in data.get("locations") or [] if isinstance(item, str)
    ][:5]
    merged.industries = merged.industries or [
        item.lower() for item in data.get("industries") or [] if isinstance(item, str)
    ][:5]
    if not merged.opportunity_types:
        merged.opportunity_types = [
            item for item in data.get("opportunity_types") or [] if item in _ALLOWED_OPPORTUNITY
        ]
    if not merged.employment_types:
        merged.employment_types = [
            item for item in data.get("employment_types") or [] if item in _ALLOWED_EMPLOYMENT
        ]
    if not merged.experience_levels:
        merged.experience_levels = [
            item for item in data.get("experience_levels") or [] if item in _ALLOWED_EXPERIENCE
        ]
    if not merged.work_modes:
        merged.work_modes = [item for item in data.get("work_modes") or [] if item in _ALLOWED_WORK]
    merged.parser_source = "gemini"
    return merged
