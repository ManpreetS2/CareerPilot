"""Sequential Ollama → Gemini fallback at the structured-pipeline boundary."""

from __future__ import annotations

import json
import logging

import pytest

from backend.db.models import ApplicationPackageRecord, Candidate, JobIntelligenceRecord, JobRecord
from backend.services.application_materials_agent import (
    ApplicationMaterialsParseError,
    generate_grounded_application_materials,
)
from backend.services.candidate_profile_agent import (
    ProfileExtractionError,
    build_candidate_profile_from_upload,
    extract_candidate_profile_with_llm,
)
from backend.services.job_intelligence_service import (
    EmptyGroundedIntelligenceError,
    JobNotFoundError,
    PostingEvidenceError,
    StructuredIntelligenceError,
    extract_job_intelligence,
)
from backend.services.llm_client import LLMConfigurationError, LLMProviderError
from tests.mvp_helpers import TEST_USER_ID, VALID_MATERIALS_JSON, seed_materials_prerequisites
from tests.pdf_fixtures import SAMPLE_RESUME_TEXT, build_simple_text_pdf
from tests.test_candidate_profile import _grounded_llm_payload
from tests.test_job_intelligence import _job, _payload


def _order(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.setattr("backend.core.config.settings.llm_provider_order", raw)


def _resume_order(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.setattr("backend.core.config.settings.resume_llm_provider_order", raw)


class ScriptedProviders:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.queues: dict[str, list[object]] = {}

    def script(self, provider: str, *items: object) -> None:
        self.queues[provider] = list(items)

    def get_client(self, provider: str | None = None):
        name = provider or "gemini"
        owner = self

        class _Client:
            def generate(self, prompt: str, system_prompt: str | None = None, json_schema=None) -> str:
                owner.calls.append(name)
                queue = owner.queues.setdefault(name, [])
                if not queue:
                    raise AssertionError(f"unexpected extra generate for {name}")
                item = queue.pop(0)
                if isinstance(item, Exception):
                    raise item
                if callable(item):
                    return item()
                return str(item)

        return _Client()


def _patch_clients(monkeypatch: pytest.MonkeyPatch, scripted: ScriptedProviders, *module_paths: str) -> None:
    for path in module_paths:
        monkeypatch.setattr(path, scripted.get_client)
    if any(path.endswith("get_resume_llm_client") for path in module_paths):
        monkeypatch.setattr(
            "backend.services.candidate_profile_agent.resume_provider_is_configured",
            lambda _provider: True,
        )


def _profile_modules() -> tuple[str, ...]:
    return ("backend.services.candidate_profile_agent.get_resume_llm_client",)


def _intel_modules() -> tuple[str, ...]:
    return ("backend.services.job_intelligence_service.get_llm_client",)


def _materials_modules() -> tuple[str, ...]:
    return ("backend.services.application_materials_agent.get_llm_client",)


def test_injected_generator_keeps_single_provider_call_count(isolated_session, monkeypatch: pytest.MonkeyPatch) -> None:
    _order(monkeypatch, "ollama,gemini")
    calls = {"n": 0}

    def bad(_prompt: str, _system: str | None = None) -> str:
        calls["n"] += 1
        return "not-json"

    with pytest.raises(ProfileExtractionError):
        extract_candidate_profile_with_llm(SAMPLE_RESUME_TEXT, generate_fn=bad)
    assert calls["n"] == 2


def test_candidate_ollama_success_never_calls_gemini(isolated_session, monkeypatch: pytest.MonkeyPatch) -> None:
    _resume_order(monkeypatch, "ollama,gemini")
    scripted = ScriptedProviders()
    scripted.script("ollama", json.dumps(_grounded_llm_payload()))
    scripted.script("gemini", LLMProviderError("Gemini provider request failed."))
    _patch_clients(monkeypatch, scripted, *_profile_modules())
    stored, _, _ = build_candidate_profile_from_upload(
        "alex.pdf",
        build_simple_text_pdf(SAMPLE_RESUME_TEXT),
        db=isolated_session,
        user_id=TEST_USER_ID,
        content_type="application/pdf",
    )
    assert stored.name == "Alex Rivera"
    assert scripted.calls == ["ollama"]
    assert isolated_session.query(Candidate).count() == 1


def test_candidate_offline_ollama_falls_back_to_gemini(isolated_session, monkeypatch: pytest.MonkeyPatch) -> None:
    _resume_order(monkeypatch, "ollama,gemini")
    scripted = ScriptedProviders()
    scripted.script("ollama", LLMProviderError("Ollama provider request failed."))
    scripted.script("gemini", json.dumps(_grounded_llm_payload()))
    _patch_clients(monkeypatch, scripted, *_profile_modules())
    stored, _, _ = build_candidate_profile_from_upload(
        "alex.pdf",
        build_simple_text_pdf(SAMPLE_RESUME_TEXT),
        db=isolated_session,
        user_id=TEST_USER_ID,
        content_type="application/pdf",
    )
    assert stored.name == "Alex Rivera"
    assert scripted.calls == ["ollama", "gemini"]
    assert isolated_session.query(Candidate).count() == 1


def test_candidate_invalid_json_uses_structured_retries_then_fallback(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _resume_order(monkeypatch, "ollama,gemini")
    scripted = ScriptedProviders()
    scripted.script("ollama", "not-json", "still-not-json")
    scripted.script("gemini", json.dumps(_grounded_llm_payload()))
    _patch_clients(monkeypatch, scripted, *_profile_modules())
    stored, _, _ = build_candidate_profile_from_upload(
        "alex.pdf",
        build_simple_text_pdf(SAMPLE_RESUME_TEXT),
        db=isolated_session,
        user_id=TEST_USER_ID,
        content_type="application/pdf",
    )
    assert stored.name == "Alex Rivera"
    assert scripted.calls == ["ollama", "ollama", "gemini"]
    assert isolated_session.query(Candidate).count() == 1


def test_candidate_schema_invalid_then_gemini_persists_once(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _resume_order(monkeypatch, "ollama,gemini")
    bad = {"name": "Alex Rivera", "skills": "not-a-list"}
    scripted = ScriptedProviders()
    scripted.script("ollama", json.dumps(bad), json.dumps(bad))
    scripted.script("gemini", json.dumps(_grounded_llm_payload()))
    _patch_clients(monkeypatch, scripted, *_profile_modules())
    stored, _, _ = build_candidate_profile_from_upload(
        "alex.pdf",
        build_simple_text_pdf(SAMPLE_RESUME_TEXT),
        db=isolated_session,
        user_id=TEST_USER_ID,
        content_type="application/pdf",
    )
    assert stored.name == "Alex Rivera"
    assert scripted.calls == ["ollama", "ollama", "gemini"]
    assert isolated_session.query(Candidate).count() == 1


def test_candidate_fatal_grounding_falls_back(isolated_session, monkeypatch: pytest.MonkeyPatch) -> None:
    _resume_order(monkeypatch, "ollama,gemini")
    ungrounded = _grounded_llm_payload()
    ungrounded["name"] = "Someone Not On Resume"
    scripted = ScriptedProviders()
    scripted.script("ollama", json.dumps(ungrounded))
    scripted.script("gemini", json.dumps(_grounded_llm_payload()))
    _patch_clients(monkeypatch, scripted, *_profile_modules())
    stored, _, _ = build_candidate_profile_from_upload(
        "alex.pdf",
        build_simple_text_pdf(SAMPLE_RESUME_TEXT),
        db=isolated_session,
        user_id=TEST_USER_ID,
        content_type="application/pdf",
    )
    assert stored.name == "Alex Rivera"
    assert scripted.calls == ["ollama", "gemini"]
    assert isolated_session.query(Candidate).count() == 1


def test_candidate_all_providers_fail_persists_nothing(isolated_session, monkeypatch: pytest.MonkeyPatch) -> None:
    _resume_order(monkeypatch, "ollama,gemini")
    scripted = ScriptedProviders()
    scripted.script("ollama", LLMProviderError("Ollama provider request failed."))
    scripted.script("gemini", LLMProviderError("Gemini provider request failed."))
    _patch_clients(monkeypatch, scripted, *_profile_modules())
    before = isolated_session.query(Candidate).count()
    with pytest.raises(ProfileExtractionError):
        build_candidate_profile_from_upload(
            "alex.pdf",
            build_simple_text_pdf(SAMPLE_RESUME_TEXT),
            db=isolated_session,
            user_id=TEST_USER_ID,
            content_type="application/pdf",
        )
    assert isolated_session.query(Candidate).count() == before
    assert scripted.calls == ["ollama", "gemini"]


def test_candidate_invalid_upload_does_not_call_another_provider(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _resume_order(monkeypatch, "ollama,gemini")
    scripted = ScriptedProviders()
    scripted.script("ollama", json.dumps(_grounded_llm_payload()))
    scripted.script("gemini", json.dumps(_grounded_llm_payload()))
    _patch_clients(monkeypatch, scripted, *_profile_modules())
    with pytest.raises(Exception):
        build_candidate_profile_from_upload(
            "notes.txt",
            b"not a pdf",
            db=isolated_session,
            user_id=TEST_USER_ID,
            content_type="text/plain",
        )
    assert scripted.calls == []


def test_candidate_uses_resume_order_not_global_llm_order(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _order(monkeypatch, "ollama,gemini")
    _resume_order(monkeypatch, "gemini,ollama")
    scripted = ScriptedProviders()
    scripted.script("gemini", json.dumps(_grounded_llm_payload()))
    scripted.script("ollama", LLMProviderError("Ollama provider request failed."))
    _patch_clients(monkeypatch, scripted, *_profile_modules())
    stored, _, _ = build_candidate_profile_from_upload(
        "alex.pdf",
        build_simple_text_pdf(SAMPLE_RESUME_TEXT),
        db=isolated_session,
        user_id=TEST_USER_ID,
        content_type="application/pdf",
    )
    assert stored.name == "Alex Rivera"
    assert scripted.calls == ["gemini"]


def test_candidate_skips_unconfigured_gemini_without_calling_it(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _resume_order(monkeypatch, "gemini,ollama")
    monkeypatch.setattr("backend.core.config.settings.gemini_api_key", None)
    monkeypatch.setattr("backend.core.config.settings.gemini_api_key", "")
    scripted = ScriptedProviders()
    scripted.script("gemini", LLMProviderError("should not be called"))
    scripted.script("ollama", json.dumps(_grounded_llm_payload()))
    monkeypatch.setattr(
        "backend.services.candidate_profile_agent.get_resume_llm_client",
        scripted.get_client,
    )
    stored, _, _ = build_candidate_profile_from_upload(
        "alex.pdf",
        build_simple_text_pdf(SAMPLE_RESUME_TEXT),
        db=isolated_session,
        user_id=TEST_USER_ID,
        content_type="application/pdf",
    )
    assert stored.name == "Alex Rivera"
    assert scripted.calls == ["ollama"]


def test_job_intelligence_ollama_success_never_calls_gemini(isolated_session, monkeypatch: pytest.MonkeyPatch) -> None:
    _order(monkeypatch, "ollama,gemini")
    job = _job(isolated_session)
    scripted = ScriptedProviders()
    scripted.script("ollama", json.dumps(_payload()))
    scripted.script("gemini", LLMProviderError("Gemini provider request failed."))
    _patch_clients(monkeypatch, scripted, *_intel_modules())
    stored = extract_job_intelligence(isolated_session, job.public_id)
    assert stored.required_skills
    assert scripted.calls == ["ollama"]
    assert isolated_session.query(JobIntelligenceRecord).count() == 1


def test_job_intelligence_offline_ollama_falls_back(isolated_session, monkeypatch: pytest.MonkeyPatch) -> None:
    _order(monkeypatch, "ollama,gemini")
    job = _job(isolated_session)
    scripted = ScriptedProviders()
    scripted.script("ollama", LLMProviderError("Ollama provider request failed."))
    scripted.script("gemini", json.dumps(_payload()))
    _patch_clients(monkeypatch, scripted, *_intel_modules())
    stored = extract_job_intelligence(isolated_session, job.public_id)
    assert stored.required_skills
    assert scripted.calls == ["ollama", "gemini"]
    assert isolated_session.query(JobIntelligenceRecord).count() == 1


def test_job_intelligence_invalid_json_retries_then_falls_back(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _order(monkeypatch, "ollama,gemini")
    job = _job(isolated_session)
    scripted = ScriptedProviders()
    scripted.script("ollama", "not-json", "{")
    scripted.script("gemini", json.dumps(_payload()))
    _patch_clients(monkeypatch, scripted, *_intel_modules())
    extract_job_intelligence(isolated_session, job.public_id)
    assert scripted.calls == ["ollama", "ollama", "gemini"]
    assert isolated_session.query(JobIntelligenceRecord).count() == 1


def test_job_intelligence_empty_grounded_falls_back(isolated_session, monkeypatch: pytest.MonkeyPatch) -> None:
    _order(monkeypatch, "ollama,gemini")
    job = _job(isolated_session)
    empty = _payload(
        required_skills=["NotARealSkillXYZ"],
        preferred_skills=["AlsoFakeSkill"],
        years_experience=99,
        education_requirements=["Made Up Degree"],
        tech_stack=["Unobtanium"],
        seniority="Galactic Overlord",
        responsibilities=["Invent warp drive"],
        likely_interview_focus=["Telepathy"],
    )
    scripted = ScriptedProviders()
    scripted.script("ollama", json.dumps(empty))
    scripted.script("gemini", json.dumps(_payload()))
    _patch_clients(monkeypatch, scripted, *_intel_modules())
    stored = extract_job_intelligence(isolated_session, job.public_id)
    assert stored.required_skills
    assert "ollama" in scripted.calls
    assert scripted.calls[-1] == "gemini"
    assert isolated_session.query(JobIntelligenceRecord).count() == 1


def test_job_intelligence_empty_grounded_ollama_with_unconfigured_gemini_returns_409(
    isolated_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    _order(monkeypatch, "ollama,gemini")
    client, SessionLocal = isolated_client
    with SessionLocal() as session:
        job = _job(session)
    empty = _payload(
        required_skills=["NotARealSkillXYZ"],
        preferred_skills=["AlsoFakeSkill"],
        years_experience=99,
        education_requirements=["Made Up Degree"],
        tech_stack=["Unobtanium"],
        seniority="Galactic Overlord",
        responsibilities=["Invent warp drive"],
        likely_interview_focus=["Telepathy"],
    )
    scripted = ScriptedProviders()
    scripted.script("ollama", json.dumps(empty))

    def _get_client(provider: str | None = None):
        if provider == "gemini":
            raise LLMConfigurationError("GEMINI_API_KEY is not set.")
        return scripted.get_client(provider)

    monkeypatch.setattr("backend.services.job_intelligence_service.get_llm_client", _get_client)
    response = client.post(f"/api/jobs/{job.public_id}/intelligence")
    assert response.status_code == 409
    assert response.json() == {"detail": "No supported job requirements were found."}
    with SessionLocal() as session:
        assert session.query(JobIntelligenceRecord).count() == 0
    assert scripted.calls == ["ollama"]


def test_job_intelligence_all_providers_fail_persists_nothing(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _order(monkeypatch, "ollama,gemini")
    job = _job(isolated_session)
    scripted = ScriptedProviders()
    scripted.script("ollama", LLMProviderError("Ollama provider request failed."))
    scripted.script("gemini", LLMProviderError("Gemini provider request failed."))
    _patch_clients(monkeypatch, scripted, *_intel_modules())
    with pytest.raises((StructuredIntelligenceError, LLMProviderError)):
        extract_job_intelligence(isolated_session, job.public_id)
    assert isolated_session.query(JobIntelligenceRecord).count() == 0
    assert scripted.calls == ["ollama", "gemini"]


def test_job_intelligence_missing_job_does_not_call_provider(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _order(monkeypatch, "ollama,gemini")
    scripted = ScriptedProviders()
    scripted.script("ollama", json.dumps(_payload()))
    _patch_clients(monkeypatch, scripted, *_intel_modules())
    with pytest.raises(JobNotFoundError):
        extract_job_intelligence(isolated_session, "missing-job")
    assert scripted.calls == []


def test_job_intelligence_missing_evidence_does_not_call_provider(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _order(monkeypatch, "ollama,gemini")
    record = JobRecord(
        public_id="job-empty-001",
        title="X",
        company="Y",
        url="https://example.invalid/jobs/empty",
        description="short",
        source="test",
        status="verified",
    )
    isolated_session.add(record)
    isolated_session.commit()
    scripted = ScriptedProviders()
    scripted.script("ollama", json.dumps(_payload()))
    _patch_clients(monkeypatch, scripted, *_intel_modules())
    with pytest.raises(PostingEvidenceError):
        extract_job_intelligence(isolated_session, record.public_id)
    assert scripted.calls == []


def test_job_intelligence_second_attempt_succeeds_without_calling_gemini(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _order(monkeypatch, "ollama,gemini")
    job = _job(isolated_session)
    scripted = ScriptedProviders()
    scripted.script("ollama", "not-json", json.dumps(_payload()))
    scripted.script("gemini", "GEMINI_SHOULD_NOT_RUN")
    _patch_clients(monkeypatch, scripted, *_intel_modules())
    stored = extract_job_intelligence(isolated_session, job.public_id)
    assert stored.required_skills
    assert scripted.calls == ["ollama", "ollama"]
    assert isolated_session.query(JobIntelligenceRecord).count() == 1


def test_job_intelligence_meaningful_ollama_failure_survives_unconfigured_gemini(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _order(monkeypatch, "ollama,gemini")
    job = _job(isolated_session)
    scripted = ScriptedProviders()
    scripted.script("ollama", "not-json", "still not json")
    scripted.script("gemini", LLMConfigurationError("Gemini is not configured."))
    _patch_clients(monkeypatch, scripted, *_intel_modules())
    with pytest.raises(StructuredIntelligenceError):
        extract_job_intelligence(isolated_session, job.public_id)
    assert scripted.calls == ["ollama", "ollama", "gemini"]
    assert isolated_session.query(JobIntelligenceRecord).count() == 0


def test_job_intelligence_all_providers_genuinely_unconfigured_returns_configuration_error(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _order(monkeypatch, "ollama,gemini")
    job = _job(isolated_session)
    scripted = ScriptedProviders()
    scripted.script("ollama", LLMConfigurationError("Ollama is not configured."))
    scripted.script("gemini", LLMConfigurationError("Gemini is not configured."))
    _patch_clients(monkeypatch, scripted, *_intel_modules())
    with pytest.raises(LLMConfigurationError):
        extract_job_intelligence(isolated_session, job.public_id)
    assert scripted.calls == ["ollama", "gemini"]
    assert isolated_session.query(JobIntelligenceRecord).count() == 0


def test_materials_ollama_success_never_calls_gemini(isolated_session, monkeypatch: pytest.MonkeyPatch) -> None:
    _order(monkeypatch, "ollama,gemini")
    job, _candidate = seed_materials_prerequisites(isolated_session)
    scripted = ScriptedProviders()
    scripted.script("ollama", VALID_MATERIALS_JSON)
    scripted.script("gemini", LLMProviderError("Gemini provider request failed."))
    _patch_clients(monkeypatch, scripted, *_materials_modules())
    draft = generate_grounded_application_materials(isolated_session, job.public_id, TEST_USER_ID)
    assert draft.tailored_bullets
    assert scripted.calls == ["ollama"]
    assert isolated_session.query(ApplicationPackageRecord).count() == 1


def test_materials_offline_ollama_falls_back(isolated_session, monkeypatch: pytest.MonkeyPatch) -> None:
    _order(monkeypatch, "ollama,gemini")
    job, _candidate = seed_materials_prerequisites(isolated_session)
    scripted = ScriptedProviders()
    scripted.script("ollama", LLMProviderError("Ollama provider request failed."))
    scripted.script("gemini", VALID_MATERIALS_JSON)
    _patch_clients(monkeypatch, scripted, *_materials_modules())
    generate_grounded_application_materials(isolated_session, job.public_id, TEST_USER_ID)
    assert scripted.calls == ["ollama", "gemini"]
    assert isolated_session.query(ApplicationPackageRecord).count() == 1


def test_materials_invalid_json_retries_then_falls_back(isolated_session, monkeypatch: pytest.MonkeyPatch) -> None:
    _order(monkeypatch, "ollama,gemini")
    job, _candidate = seed_materials_prerequisites(isolated_session)
    scripted = ScriptedProviders()
    scripted.script("ollama", "not-json", "still-bad")
    scripted.script("gemini", VALID_MATERIALS_JSON)
    _patch_clients(monkeypatch, scripted, *_materials_modules())
    generate_grounded_application_materials(isolated_session, job.public_id, TEST_USER_ID)
    assert scripted.calls == ["ollama", "ollama", "gemini"]
    assert isolated_session.query(ApplicationPackageRecord).count() == 1


def test_materials_fatal_grounding_falls_back(isolated_session, monkeypatch: pytest.MonkeyPatch) -> None:
    _order(monkeypatch, "ollama,gemini")
    job, _candidate = seed_materials_prerequisites(isolated_session)
    invented = json.dumps(
        {
            "tailored_bullets": ["Led production Kubernetes clusters and improved latency by 40%."],
            "cover_letter_draft": "I have deep Kubernetes experience at Globex.",
            "recruiter_message": "I used Kubernetes in production.",
            "source_traceability_notes": ["Invented Kubernetes claim"],
        }
    )
    scripted = ScriptedProviders()
    scripted.script("ollama", invented)
    scripted.script("gemini", VALID_MATERIALS_JSON)
    _patch_clients(monkeypatch, scripted, *_materials_modules())
    generate_grounded_application_materials(isolated_session, job.public_id, TEST_USER_ID)
    assert scripted.calls == ["ollama", "gemini"]
    assert isolated_session.query(ApplicationPackageRecord).count() == 1


def test_materials_all_providers_fail_persists_nothing(isolated_session, monkeypatch: pytest.MonkeyPatch) -> None:
    _order(monkeypatch, "ollama,gemini")
    job, _candidate = seed_materials_prerequisites(isolated_session)
    scripted = ScriptedProviders()
    scripted.script("ollama", LLMProviderError("Ollama provider request failed."))
    scripted.script("gemini", LLMProviderError("Gemini provider request failed."))
    _patch_clients(monkeypatch, scripted, *_materials_modules())
    with pytest.raises((ApplicationMaterialsParseError, LLMProviderError)):
        generate_grounded_application_materials(isolated_session, job.public_id, TEST_USER_ID)
    assert isolated_session.query(ApplicationPackageRecord).count() == 0
    assert scripted.calls == ["ollama", "gemini"]


def test_materials_missing_candidate_does_not_call_provider(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _order(monkeypatch, "ollama,gemini")
    job, _candidate = seed_materials_prerequisites(isolated_session)
    isolated_session.query(Candidate).delete()
    isolated_session.commit()
    scripted = ScriptedProviders()
    scripted.script("ollama", VALID_MATERIALS_JSON)
    _patch_clients(monkeypatch, scripted, *_materials_modules())
    with pytest.raises(Exception):
        generate_grounded_application_materials(isolated_session, job.public_id, TEST_USER_ID)
    assert scripted.calls == []
    assert isolated_session.query(ApplicationPackageRecord).count() == 0


def test_gemini_then_ollama_order_is_honored(isolated_session, monkeypatch: pytest.MonkeyPatch) -> None:
    _order(monkeypatch, "gemini,ollama")
    job = _job(isolated_session)
    scripted = ScriptedProviders()
    scripted.script("gemini", LLMProviderError("Gemini provider request failed."))
    scripted.script("ollama", json.dumps(_payload()))
    _patch_clients(monkeypatch, scripted, *_intel_modules())
    extract_job_intelligence(isolated_session, job.public_id)
    assert scripted.calls == ["gemini", "ollama"]
    assert isolated_session.query(JobIntelligenceRecord).count() == 1


def test_fallback_logs_are_sanitized(isolated_session, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    _resume_order(monkeypatch, "ollama,gemini")
    scripted = ScriptedProviders()
    scripted.script("ollama", LLMProviderError("Ollama provider request failed."))
    scripted.script("gemini", json.dumps(_grounded_llm_payload()))
    _patch_clients(monkeypatch, scripted, *_profile_modules())
    with caplog.at_level(logging.DEBUG, logger="backend"):
        build_candidate_profile_from_upload(
            "alex.pdf",
            build_simple_text_pdf(SAMPLE_RESUME_TEXT),
            db=isolated_session,
            user_id=TEST_USER_ID,
            content_type="application/pdf",
        )
    blob = "\n".join(record.getMessage() for record in caplog.records if record.name.startswith("backend")).lower()
    assert "alex.rivera@example.com" not in blob
    assert "127.0.0.1" not in blob
    assert "/api/chat" not in blob
    assert "sk-" not in blob


def test_candidate_persist_failure_does_not_call_next_provider(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _resume_order(monkeypatch, "ollama,gemini")
    scripted = ScriptedProviders()
    scripted.script("ollama", json.dumps(_grounded_llm_payload()))
    scripted.script("gemini", json.dumps(_grounded_llm_payload()))
    _patch_clients(monkeypatch, scripted, *_profile_modules())

    def _boom(*_args, **_kwargs):
        raise RuntimeError("synthetic database failure")

    monkeypatch.setattr(
        "backend.services.candidate_profile_agent.persist_candidate_profile",
        _boom,
    )
    with pytest.raises(RuntimeError, match="synthetic database failure"):
        build_candidate_profile_from_upload(
            "alex.pdf",
            build_simple_text_pdf(SAMPLE_RESUME_TEXT),
            db=isolated_session,
            user_id=TEST_USER_ID,
            content_type="application/pdf",
        )
    assert scripted.calls == ["ollama"]
    assert isolated_session.query(Candidate).count() == 0


def test_job_intelligence_persist_failure_does_not_call_next_provider(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _order(monkeypatch, "ollama,gemini")
    job = _job(isolated_session)
    scripted = ScriptedProviders()
    scripted.script("ollama", json.dumps(_payload()))
    scripted.script("gemini", json.dumps(_payload()))
    _patch_clients(monkeypatch, scripted, *_intel_modules())

    def _boom(*_args, **_kwargs):
        raise RuntimeError("synthetic database failure")

    monkeypatch.setattr(
        "backend.services.job_intelligence_service._persist_grounded",
        _boom,
    )
    with pytest.raises(RuntimeError, match="synthetic database failure"):
        extract_job_intelligence(isolated_session, job.public_id)
    assert scripted.calls == ["ollama"]
    assert isolated_session.query(JobIntelligenceRecord).count() == 0


def test_materials_persist_failure_does_not_call_next_provider(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _order(monkeypatch, "ollama,gemini")
    job, _candidate = seed_materials_prerequisites(isolated_session)
    scripted = ScriptedProviders()
    scripted.script("ollama", VALID_MATERIALS_JSON)
    scripted.script("gemini", VALID_MATERIALS_JSON)
    _patch_clients(monkeypatch, scripted, *_materials_modules())

    def _boom(*_args, **_kwargs):
        raise RuntimeError("synthetic database failure")

    monkeypatch.setattr(
        "backend.services.application_materials_agent._persist_grounded_draft",
        _boom,
    )
    with pytest.raises(RuntimeError, match="synthetic database failure"):
        generate_grounded_application_materials(isolated_session, job.public_id, TEST_USER_ID)
    assert scripted.calls == ["ollama"]
    assert isolated_session.query(ApplicationPackageRecord).count() == 0
