"""Pydantic JSON schemas for Ollama structured output.

These describe raw model output only. Persistence, ownership, and approval
fields are omitted so the model cannot be asked to invent them.
"""

from __future__ import annotations

from typing import Any

from backend.schemas.schemas import CandidateProfile, JobIntelligence


def _without_fields(schema: dict[str, Any], names: set[str]) -> dict[str, Any]:
    trimmed = dict(schema)
    properties = dict(trimmed.get("properties") or {})
    for name in names:
        properties.pop(name, None)
    trimmed["properties"] = properties
    required = trimmed.get("required")
    if isinstance(required, list):
        trimmed["required"] = [item for item in required if item not in names]
    return trimmed


def candidate_profile_llm_schema() -> dict[str, Any]:
    return _without_fields(CandidateProfile.model_json_schema(), {"id"})


def job_intelligence_llm_schema() -> dict[str, Any]:
    return _without_fields(JobIntelligence.model_json_schema(), {"job_id"})


def application_materials_llm_schema() -> dict[str, Any]:
    from backend.services.application_materials_agent import ApplicationMaterialsStructuredOutput

    return ApplicationMaterialsStructuredOutput.model_json_schema()
