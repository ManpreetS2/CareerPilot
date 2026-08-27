"""Gemini native structured-output wiring and CandidateProfile validation."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.schemas.schemas import CandidateProfile
from backend.services.candidate_profile_agent import validate_and_ground_profile
from backend.services.llm_client import LLMClient
from backend.services.llm_structured_schemas import candidate_profile_llm_schema
from tests.pdf_fixtures import SAMPLE_RESUME_TEXT
from tests.test_candidate_profile import _grounded_llm_payload


def _make_gemini_client(**kwargs) -> LLMClient:
    with (
        patch("backend.core.config.settings.gemini_api_key", "test-key"),
        patch("backend.core.config.settings.gemini_model", "gemini-test"),
    ):
        return LLMClient(provider="gemini", **kwargs)


def test_gemini_receives_native_structured_output_when_schema_supplied() -> None:
    schema = candidate_profile_llm_schema()
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = SimpleNamespace(
        text=json.dumps(_grounded_llm_payload())
    )
    client = _make_gemini_client()
    with patch("google.genai.Client", return_value=fake_client):
        text = client._generate_gemini("extract", None, schema)
    payload = json.loads(text)
    CandidateProfile.model_validate(payload)
    kwargs = fake_client.models.generate_content.call_args.kwargs
    config = kwargs["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == schema
    assert config.automatic_function_calling is not None
    assert config.automatic_function_calling.disable is True
    assert kwargs["contents"] == "extract"


def test_gemini_text_generation_omits_schema_when_none() -> None:
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = SimpleNamespace(text="  plain text  ")
    client = _make_gemini_client()
    with patch("google.genai.Client", return_value=fake_client):
        text = client._generate_gemini("hello", None)
    assert text == "plain text"
    kwargs = fake_client.models.generate_content.call_args.kwargs
    config = kwargs.get("config")
    assert config is None or getattr(config, "response_json_schema", None) is None
    assert config is None or getattr(config, "response_mime_type", None) != "application/json"


def test_candidate_profile_extraction_still_validates_and_grounds() -> None:
    raw = _grounded_llm_payload()
    raw["skills"] = [*raw["skills"], "HallucinatedSkillXYZ"]
    profile, report = validate_and_ground_profile(raw, SAMPLE_RESUME_TEXT)
    CandidateProfile.model_validate(profile.model_dump())
    assert "HallucinatedSkillXYZ" not in profile.skills
    assert report.removed_skills >= 1
    assert report.total_rejected >= 1
