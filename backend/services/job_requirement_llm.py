"""Optional LLM enrichment for JobRequirementProfile.

The model only structures the posting. It never calculates Fit.
Deterministic miners always win for hard eligibility groups.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from backend.core.config import settings
from backend.schemas.job_requirements import JobRequirementProfile, Requirement
from backend.services.llm_client import LLMClient, LLMConfigurationError, LLMProviderError
from backend.services.llm_provider_sequence import invoke_provider_generate, job_requirements_provider_names
from backend.services.requirement_grounding import keep_grounded_requirement

logger = logging.getLogger(__name__)

GenerateFn = Callable[[str, str | None], str]

SYSTEM_PROMPT = (
    "Extract factual employer requirements from the complete job posting. "
    "Do not calculate fit. Do not invent. Do not strengthen employer language. "
    "evidence_text must be a verbatim clause copied from the posting."
)


class LlmRequirementDraft(BaseModel):
    category: str
    text: str
    importance: str = "required"
    evidence_text: str
    structured_condition: dict[str, Any] | None = None


class LlmProfileDraft(BaseModel):
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    primary_responsibilities: list[str] = Field(default_factory=list)
    work_mode: str | None = None
    remote_scope: str | None = None
    employment_type: str | None = None
    experience_level: str | None = None
    requirements: list[LlmRequirementDraft] = Field(default_factory=list)


def _client_for(provider: str) -> LLMClient:
    if provider == "gemini":
        return LLMClient(provider="gemini", model=settings.job_requirements_gemini_model)
    if provider == "ollama":
        return LLMClient(provider="ollama", model=settings.job_requirements_ollama_model)
    return LLMClient(provider=provider)


def _schema() -> dict[str, Any]:
    return LlmProfileDraft.model_json_schema()


def merge_llm_draft(
    profile: JobRequirementProfile,
    draft: LlmProfileDraft,
    posting: str,
) -> JobRequirementProfile:
    """Miners keep hard groups. LLM may add grounded extras only."""
    existing_kinds = {
        (item.structured_condition or {}).get("kind")
        for item in profile.requirements
        if item.structured_condition
    }
    for item in draft.requirements:
        importance = item.importance if item.importance in {"hard_required", "required", "preferred"} else "required"
        requirement = Requirement(
            id=f"llm-{len(profile.requirements) + 1}",
            category=item.category or "other",
            text=item.text,
            importance=importance,  # type: ignore[arg-type]
            evidence_text=item.evidence_text,
            structured_condition=item.structured_condition,
        )
        kind = (requirement.structured_condition or {}).get("kind")
        if kind in existing_kinds:
            continue
        if not keep_grounded_requirement(requirement, posting):
            continue
        profile.requirements.append(requirement)
        existing_kinds.add(kind)
    if draft.required_skills:
        profile.required_skills = list(dict.fromkeys([*profile.required_skills, *draft.required_skills]))
    if draft.preferred_skills:
        profile.preferred_skills = list(dict.fromkeys([*profile.preferred_skills, *draft.preferred_skills]))
    if draft.primary_responsibilities:
        profile.primary_responsibilities = list(dict.fromkeys(draft.primary_responsibilities))
    if profile.work_mode == "unknown" and draft.work_mode in {"remote", "hybrid", "onsite"}:
        profile.work_mode = draft.work_mode  # type: ignore[assignment]
    if not profile.remote_scope and draft.remote_scope:
        profile.remote_scope = draft.remote_scope
    return profile


def enrich_profile_with_llm(
    profile: JobRequirementProfile,
    *,
    generate_fn: GenerateFn | None = None,
) -> JobRequirementProfile:
    canonical = profile.canonical
    if canonical is None:
        return profile
    posting = canonical.full_description
    user_prompt = (
        f"Job title: {canonical.title}\nCompany: {canonical.company}\n\n"
        "Complete posting (do not ignore the end):\n"
        f"{posting}"
    )
    raw = ""
    if generate_fn is not None:
        raw = generate_fn(user_prompt, SYSTEM_PROMPT)
    else:
        last_error: Exception | None = None
        for provider in job_requirements_provider_names():
            try:
                client = _client_for(provider)
                raw = invoke_provider_generate(client, user_prompt, SYSTEM_PROMPT, _schema())
                break
            except (LLMConfigurationError, LLMProviderError, ValueError) as exc:
                last_error = exc
                logger.warning("job requirements llm skipped provider=%s error=%s", provider, type(exc).__name__)
        if not raw:
            if last_error:
                logger.warning("job requirements llm unavailable; keeping deterministic profile")
            return profile
    try:
        payload = json.loads(raw) if raw.strip().startswith("{") else {}
        draft = LlmProfileDraft.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, TypeError):
        logger.warning("job requirements llm output failed validation")
        return profile
    return merge_llm_draft(profile, draft, posting)
