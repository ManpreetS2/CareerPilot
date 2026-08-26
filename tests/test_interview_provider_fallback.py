"""Interview answer feedback must follow LLM_PROVIDER_ORDER sequentially."""

from __future__ import annotations

import logging

import pytest

from backend.db.models import InterviewPrepRecord, JobIntelligenceRecord
from backend.services.interview_service import (
    InterviewIntelligenceMissingError,
    InterviewJobNotFoundError,
    InterviewQuestionNotFoundError,
    generate_and_store_interview_prep,
    get_interview_answer_feedback,
)
from backend.services.llm_client import LLMConfigurationError, LLMEmptyResponseError, LLMProviderError
from tests.mvp_helpers import TEST_USER_ID, ensure_user
from tests.test_interview_service import _candidate, _intelligence, _job
from tests.test_llm_provider_fallback import ScriptedProviders, _order, _patch_clients

SECRET_ANSWER = "SECRET_INTERVIEW_ANSWER_DO_NOT_LOG"
SECRET_FEEDBACK = "SECRET_INTERVIEW_FEEDBACK_DO_NOT_LOG"
SECRET_HOST = "host-device.tailnet.ts.net"


def _interview_modules() -> tuple[str, ...]:
    return ("backend.services.interview_service.get_llm_client",)


def _ready(session):
    _candidate(session)
    job = _job(session)
    _intelligence(session, job)
    prep = generate_and_store_interview_prep(session, job.public_id, TEST_USER_ID)
    return job, prep.likely_questions[0]


def test_ollama_success_does_not_call_gemini(isolated_session, monkeypatch: pytest.MonkeyPatch) -> None:
    _order(monkeypatch, "ollama,gemini")
    job, question = _ready(isolated_session)
    scripted = ScriptedProviders()
    scripted.script("ollama", SECRET_FEEDBACK)
    scripted.script("gemini", "GEMINI_SHOULD_NOT_RUN")
    _patch_clients(monkeypatch, scripted, *_interview_modules())
    result = get_interview_answer_feedback(
        isolated_session, job.public_id, TEST_USER_ID, question, SECRET_ANSWER
    )
    assert result.feedback == SECRET_FEEDBACK
    assert scripted.calls == ["ollama"]


def test_ollama_unavailable_falls_back_to_gemini(isolated_session, monkeypatch: pytest.MonkeyPatch) -> None:
    _order(monkeypatch, "ollama,gemini")
    job, question = _ready(isolated_session)
    scripted = ScriptedProviders()
    scripted.script("ollama", LLMProviderError("Ollama provider request failed."))
    scripted.script("gemini", SECRET_FEEDBACK)
    _patch_clients(monkeypatch, scripted, *_interview_modules())
    result = get_interview_answer_feedback(
        isolated_session, job.public_id, TEST_USER_ID, question, SECRET_ANSWER
    )
    assert result.feedback == SECRET_FEEDBACK
    assert scripted.calls == ["ollama", "gemini"]


def test_ollama_whitespace_feedback_falls_back_to_gemini(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _order(monkeypatch, "ollama,gemini")
    job, question = _ready(isolated_session)
    scripted = ScriptedProviders()
    scripted.script("ollama", "   \n")
    scripted.script("gemini", SECRET_FEEDBACK)
    _patch_clients(monkeypatch, scripted, *_interview_modules())
    result = get_interview_answer_feedback(
        isolated_session, job.public_id, TEST_USER_ID, question, SECRET_ANSWER
    )
    assert result.feedback == SECRET_FEEDBACK
    assert scripted.calls == ["ollama", "gemini"]


def test_all_providers_fail_raises_sanitized_llm_error(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _order(monkeypatch, "ollama,gemini")
    job, question = _ready(isolated_session)
    scripted = ScriptedProviders()
    scripted.script("ollama", LLMProviderError("Ollama provider request failed."))
    scripted.script("gemini", LLMConfigurationError("Gemini is not configured."))
    _patch_clients(monkeypatch, scripted, *_interview_modules())
    with pytest.raises((LLMProviderError, LLMConfigurationError, LLMEmptyResponseError)) as exc:
        get_interview_answer_feedback(
            isolated_session, job.public_id, TEST_USER_ID, question, SECRET_ANSWER
        )
    message = str(exc.value)
    assert SECRET_ANSWER not in message
    assert SECRET_HOST not in message
    assert "/api/chat" not in message
    assert "sk-" not in message
    assert scripted.calls == ["ollama", "gemini"]


def test_blank_order_remains_gemini_only(isolated_session, monkeypatch: pytest.MonkeyPatch) -> None:
    _order(monkeypatch, "")
    job, question = _ready(isolated_session)
    scripted = ScriptedProviders()
    scripted.script("gemini", SECRET_FEEDBACK)
    scripted.script("ollama", "OLLAMA_SHOULD_NOT_RUN")
    _patch_clients(monkeypatch, scripted, *_interview_modules())
    result = get_interview_answer_feedback(
        isolated_session, job.public_id, TEST_USER_ID, question, SECRET_ANSWER
    )
    assert result.feedback == SECRET_FEEDBACK
    assert scripted.calls == ["gemini"]


def test_gemini_then_ollama_order_is_respected(isolated_session, monkeypatch: pytest.MonkeyPatch) -> None:
    _order(monkeypatch, "gemini,ollama")
    job, question = _ready(isolated_session)
    scripted = ScriptedProviders()
    scripted.script("gemini", LLMProviderError("Gemini provider request failed."))
    scripted.script("ollama", SECRET_FEEDBACK)
    _patch_clients(monkeypatch, scripted, *_interview_modules())
    result = get_interview_answer_feedback(
        isolated_session, job.public_id, TEST_USER_ID, question, SECRET_ANSWER
    )
    assert result.feedback == SECRET_FEEDBACK
    assert scripted.calls == ["gemini", "ollama"]


def test_injected_generator_is_called_exactly_once(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _order(monkeypatch, "ollama,gemini")
    job, question = _ready(isolated_session)
    scripted = ScriptedProviders()
    scripted.script("ollama", "OLLAMA_SHOULD_NOT_RUN")
    scripted.script("gemini", "GEMINI_SHOULD_NOT_RUN")
    _patch_clients(monkeypatch, scripted, *_interview_modules())
    calls = {"n": 0}

    def injected(_prompt: str, _system: str | None = None) -> str:
        calls["n"] += 1
        return "Injected feedback."

    result = get_interview_answer_feedback(
        isolated_session,
        job.public_id,
        TEST_USER_ID,
        question,
        SECRET_ANSWER,
        generate_fn=injected,
    )
    assert result.feedback == "Injected feedback."
    assert calls["n"] == 1
    assert scripted.calls == []


def test_invalid_question_makes_zero_provider_calls(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _order(monkeypatch, "ollama,gemini")
    job, _question = _ready(isolated_session)
    scripted = ScriptedProviders()
    scripted.script("ollama", SECRET_FEEDBACK)
    scripted.script("gemini", SECRET_FEEDBACK)
    _patch_clients(monkeypatch, scripted, *_interview_modules())
    with pytest.raises(InterviewQuestionNotFoundError):
        get_interview_answer_feedback(
            isolated_session, job.public_id, TEST_USER_ID, "not a stored question", SECRET_ANSWER
        )
    assert scripted.calls == []


def test_missing_job_makes_zero_provider_calls(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _order(monkeypatch, "ollama,gemini")
    scripted = ScriptedProviders()
    scripted.script("ollama", SECRET_FEEDBACK)
    _patch_clients(monkeypatch, scripted, *_interview_modules())
    with pytest.raises(InterviewJobNotFoundError):
        get_interview_answer_feedback(isolated_session, "missing", TEST_USER_ID, "Q?", SECRET_ANSWER)
    assert scripted.calls == []


def test_missing_intelligence_makes_zero_provider_calls(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _order(monkeypatch, "ollama,gemini")
    _candidate(isolated_session)
    job = _job(isolated_session)
    _intelligence(isolated_session, job)
    prep = generate_and_store_interview_prep(isolated_session, job.public_id, TEST_USER_ID)
    isolated_session.query(JobIntelligenceRecord).delete()
    isolated_session.commit()
    scripted = ScriptedProviders()
    scripted.script("ollama", SECRET_FEEDBACK)
    scripted.script("gemini", SECRET_FEEDBACK)
    _patch_clients(monkeypatch, scripted, *_interview_modules())
    with pytest.raises(InterviewIntelligenceMissingError):
        get_interview_answer_feedback(
            isolated_session, job.public_id, TEST_USER_ID, prep.likely_questions[0], SECRET_ANSWER
        )
    assert scripted.calls == []


def test_injected_database_failure_does_not_call_next_provider(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _order(monkeypatch, "ollama,gemini")
    job, question = _ready(isolated_session)
    scripted = ScriptedProviders()
    scripted.script("ollama", SECRET_FEEDBACK)
    scripted.script("gemini", SECRET_FEEDBACK)
    _patch_clients(monkeypatch, scripted, *_interview_modules())

    def _boom(*_args, **_kwargs):
        raise RuntimeError("synthetic database failure")

    monkeypatch.setattr("backend.services.interview_service.load_interview_prep_context", _boom)
    with pytest.raises(RuntimeError, match="synthetic database failure"):
        get_interview_answer_feedback(
            isolated_session, job.public_id, TEST_USER_ID, question, SECRET_ANSWER
        )
    assert scripted.calls == []


def test_feedback_does_not_persist_a_database_row(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _order(monkeypatch, "ollama,gemini")
    job, question = _ready(isolated_session)
    before_prep = isolated_session.query(InterviewPrepRecord).count()
    scripted = ScriptedProviders()
    scripted.script("ollama", SECRET_FEEDBACK)
    _patch_clients(monkeypatch, scripted, *_interview_modules())
    get_interview_answer_feedback(isolated_session, job.public_id, TEST_USER_ID, question, SECRET_ANSWER)
    assert isolated_session.query(InterviewPrepRecord).count() == before_prep


def test_feedback_logs_and_errors_are_sanitized(
    isolated_session, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _order(monkeypatch, "ollama,gemini")
    job, question = _ready(isolated_session)
    scripted = ScriptedProviders()
    scripted.script("ollama", LLMProviderError("Ollama provider request failed."))
    scripted.script("gemini", SECRET_FEEDBACK)
    _patch_clients(monkeypatch, scripted, *_interview_modules())
    with caplog.at_level(logging.DEBUG):
        get_interview_answer_feedback(
            isolated_session, job.public_id, TEST_USER_ID, question, SECRET_ANSWER
        )
    blob = caplog.text
    assert SECRET_ANSWER not in blob
    assert SECRET_FEEDBACK not in blob
    assert SECRET_HOST not in blob
    assert "/api/chat" not in blob
    assert "sk-" not in blob
    assert question not in blob


def test_other_user_question_makes_zero_provider_calls(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _order(monkeypatch, "ollama,gemini")
    job, question = _ready(isolated_session)
    other = ensure_user(isolated_session, user_id=TEST_USER_ID + 1, email="other-user@example.com")
    scripted = ScriptedProviders()
    scripted.script("ollama", SECRET_FEEDBACK)
    _patch_clients(monkeypatch, scripted, *_interview_modules())
    with pytest.raises(InterviewQuestionNotFoundError):
        get_interview_answer_feedback(isolated_session, job.public_id, other.id, question, SECRET_ANSWER)
    assert scripted.calls == []


def test_feedback_http_uses_provider_order_without_injected_generator(
    isolated_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    _order(monkeypatch, "ollama,gemini")
    client, SessionLocal = isolated_client
    client.app.state.interview_answer_generator = None
    with SessionLocal() as db:
        job, question = _ready(db)
        public_id = job.public_id
    scripted = ScriptedProviders()
    scripted.script("ollama", SECRET_FEEDBACK)
    scripted.script("gemini", "GEMINI_SHOULD_NOT_RUN")
    _patch_clients(monkeypatch, scripted, *_interview_modules())
    response = client.post(
        f"/api/jobs/{public_id}/interview-prep/feedback",
        json={"question": question, "answer": SECRET_ANSWER},
    )
    assert response.status_code == 200
    assert response.json()["feedback"] == SECRET_FEEDBACK
    assert scripted.calls == ["ollama"]
    assert SECRET_ANSWER not in response.text or response.json()["answer"] == SECRET_ANSWER


def test_unconfigured_later_provider_does_not_mask_the_real_failure(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With LLM_PROVIDER_ORDER="ollama,gemini" and no Gemini key, Ollama can
    fail for a real reason and Gemini's "not configured" error would then
    overwrite it as the error the user sees — reporting a configuration
    problem on a system that is configured and did run, and sending the user
    to fix a setting that was never wrong.

    test_all_providers_fail_raises_sanitized_llm_error above accepts any of
    the three error types, so it passes either way; this pins which one.
    """
    _order(monkeypatch, "ollama,gemini")
    job, question = _ready(isolated_session)
    scripted = ScriptedProviders()
    scripted.script("ollama", LLMProviderError("Ollama provider request failed."))
    scripted.script("gemini", LLMConfigurationError("Gemini is not configured."))
    _patch_clients(monkeypatch, scripted, *_interview_modules())

    with pytest.raises(LLMProviderError):
        get_interview_answer_feedback(
            isolated_session, job.public_id, TEST_USER_ID, question, SECRET_ANSWER
        )
    assert scripted.calls == ["ollama", "gemini"]


def test_a_configuration_error_still_surfaces_when_it_is_the_only_failure(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ranking must not suppress a configuration error outright — when
    nothing else went wrong, being unconfigured is the actionable truth."""
    _order(monkeypatch, "gemini")
    job, question = _ready(isolated_session)
    scripted = ScriptedProviders()
    scripted.script("gemini", LLMConfigurationError("Gemini is not configured."))
    _patch_clients(monkeypatch, scripted, *_interview_modules())

    with pytest.raises(LLMConfigurationError):
        get_interview_answer_feedback(
            isolated_session, job.public_id, TEST_USER_ID, question, SECRET_ANSWER
        )


def test_an_empty_response_is_not_masked_by_a_later_configuration_error(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _order(monkeypatch, "ollama,gemini")
    job, question = _ready(isolated_session)
    scripted = ScriptedProviders()
    scripted.script("ollama", LLMEmptyResponseError("empty"))
    scripted.script("gemini", LLMConfigurationError("Gemini is not configured."))
    _patch_clients(monkeypatch, scripted, *_interview_modules())

    with pytest.raises(LLMEmptyResponseError):
        get_interview_answer_feedback(
            isolated_session, job.public_id, TEST_USER_ID, question, SECRET_ANSWER
        )
