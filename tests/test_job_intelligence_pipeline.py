"""Scoring orchestration and maintenance backfill regressions."""

from __future__ import annotations

import json
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.database import Base
from backend.db.models import JobIntelligenceRecord, MatchScoreRecord
from backend.schemas.schemas import JobIntelligence
from backend.services.analysis_service import RequirementsUnavailableError, score_job
from backend.services.llm_client import LLMConfigurationError, LLMProviderError
from backend.services.job_intelligence_service import StructuredIntelligenceError
from backend.services.scoring_orchestrator import score_job_with_intelligence
from scripts.backfill_job_intelligence import (
    PRODUCTION_DATABASE,
    BackfillCounts,
    assert_safe_database_path,
    format_backfill_counts,
    main as backfill_main,
    run_backfill,
    sqlite_path_from_url,
)
from scripts.test_job_intelligence_real_descriptions import (
    SourcePosting,
    _counts_line,
    _final_result,
    _first_configured_provider,
    _has_required_variety,
    _select_postings,
)
from tests.test_fit_scoring import TEST_USER_ID, _candidate, _intelligence
from tests.test_job_intelligence import SequenceGenerator, _job, _payload


@pytest.fixture(autouse=True)
def _block_unexpected_network(monkeypatch: pytest.MonkeyPatch) -> None:
    original_connect = socket.socket.connect
    loopback = {"127.0.0.1", "localhost", "::1"}

    def forbidden_connect(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) and address else address
        port = address[1] if isinstance(address, tuple) and len(address) > 1 else None
        # Windows TestClient/asyncio may use loopback sockets. Still forbid Ollama.
        if host in loopback and port != 11434:
            return original_connect(self, address, *args, **kwargs)
        raise AssertionError("network/provider calls are forbidden in pipeline tests")

    monkeypatch.setattr(socket.socket, "connect", forbidden_connect)


def _grounded_payload(**overrides) -> dict:
    payload = _payload(
        required_skills=["Python"],
        preferred_skills=["Docker"],
        years_experience=None,
        education_requirements=[],
        tech_stack=[],
        seniority=None,
        responsibilities=[],
        likely_interview_focus=[],
    )
    payload.update(overrides)
    return payload


def _described_job(session, *, public_id: str = "pipeline-job"):
    return _job(
        session,
        public_id=public_id,
        title="Platform Engineer",
        description="Requirements:\nPython\nPreferred Skills:\nDocker",
    )


def test_score_with_stored_intelligence_makes_zero_provider_calls(isolated_session) -> None:
    _candidate(isolated_session, skills=["Python"])
    job = _described_job(isolated_session)
    _intelligence(
        isolated_session,
        job,
        required=["Python"],
        preferred=["Docker"],
        tech=[],
        years=None,
        education=[],
    )
    generator = Mock(side_effect=AssertionError("provider must not run"))

    result = score_job_with_intelligence(
        isolated_session,
        job.public_id,
        TEST_USER_ID,
        generate_fn=generator,
    )

    assert "full Job Intelligence" in result.rationale
    generator.assert_not_called()
    assert isolated_session.query(JobIntelligenceRecord).count() == 1
    assert isolated_session.query(MatchScoreRecord).count() == 1


def test_missing_intelligence_extracts_once_before_scoring(isolated_session) -> None:
    _candidate(isolated_session, skills=["Python"])
    job = _described_job(isolated_session)
    generator = Mock(return_value=json.dumps(_grounded_payload()))

    result = score_job_with_intelligence(
        isolated_session,
        job.public_id,
        TEST_USER_ID,
        generate_fn=generator,
    )

    assert "full Job Intelligence" in result.rationale
    assert generator.call_count == 1
    assert isolated_session.query(JobIntelligenceRecord).count() == 1
    assert isolated_session.query(MatchScoreRecord).count() == 1

    repeated = score_job_with_intelligence(
        isolated_session,
        job.public_id,
        TEST_USER_ID,
        generate_fn=generator,
    )

    assert repeated == result
    assert generator.call_count == 1
    assert isolated_session.query(JobIntelligenceRecord).count() == 1
    assert isolated_session.query(MatchScoreRecord).count() == 1


@pytest.mark.parametrize(
    ("generator", "expected_error"),
    [
        (
            Mock(side_effect=LLMProviderError("private provider detail")),
            LLMProviderError,
        ),
        (
            Mock(side_effect=LLMConfigurationError("private configuration detail")),
            LLMConfigurationError,
        ),
        (
            SequenceGenerator("invalid", "still invalid"),
            StructuredIntelligenceError,
        ),
    ],
)
def test_extraction_failures_persist_no_score(
    isolated_session,
    generator,
    expected_error: type[Exception],
) -> None:
    _candidate(isolated_session, skills=["Python"])
    job = _described_job(isolated_session)

    with pytest.raises(expected_error):
        score_job_with_intelligence(
            isolated_session,
            job.public_id,
            TEST_USER_ID,
            generate_fn=generator,
        )

    assert isolated_session.query(JobIntelligenceRecord).count() == 0
    assert isolated_session.query(MatchScoreRecord).count() == 0


def test_descriptionless_job_preserves_existing_unavailable_behavior(isolated_session) -> None:
    _candidate(isolated_session, skills=["Python"])
    job = _job(
        isolated_session,
        public_id="descriptionless-job",
        title="Generalist",
        description="",
    )
    generator = Mock(side_effect=AssertionError("provider must not run"))

    with pytest.raises(RequirementsUnavailableError):
        score_job_with_intelligence(
            isolated_session,
            job.public_id,
            TEST_USER_ID,
            generate_fn=generator,
        )

    generator.assert_not_called()
    assert isolated_session.query(JobIntelligenceRecord).count() == 0
    assert isolated_session.query(MatchScoreRecord).count() == 0


def test_non_scoreable_extraction_never_falls_back_to_provisional(
    isolated_session,
) -> None:
    _candidate(isolated_session, skills=["Python"])
    job = _job(
        isolated_session,
        public_id="non-scoreable-intelligence",
        title="Platform Engineer",
        description=(
            "Requirements:\nPython\n"
            "Responsibilities:\nBuild APIs"
        ),
    )
    generator = Mock(
        return_value=json.dumps(
            _grounded_payload(
                required_skills=[],
                preferred_skills=[],
                responsibilities=["Build APIs"],
            )
        )
    )

    with pytest.raises(RequirementsUnavailableError):
        score_job_with_intelligence(
            isolated_session,
            job.public_id,
            TEST_USER_ID,
            generate_fn=generator,
        )

    assert generator.call_count == 1
    assert isolated_session.query(JobIntelligenceRecord).count() == 1
    assert isolated_session.query(MatchScoreRecord).count() == 0


def test_stored_non_scoreable_intelligence_does_not_fallback_through_score_job(
    isolated_session,
) -> None:
    _candidate(isolated_session, skills=["Python"])
    job = _job(
        isolated_session,
        public_id="stored-non-scoreable",
        title="Platform Engineer",
        description="Requirements:\nPython\nResponsibilities:\nBuild APIs",
    )
    isolated_session.add(
        JobIntelligenceRecord(
            job_id=job.id,
            required_skills=[],
            preferred_skills=[],
            years_experience=None,
            education_requirements=[],
            tech_stack=[],
            seniority=None,
            responsibilities=["Build APIs"],
            likely_interview_focus=["System design"],
        )
    )
    isolated_session.commit()
    provider = Mock(side_effect=AssertionError("score_job must not call a provider"))

    with patch(
        "backend.services.job_intelligence_service.get_llm_client",
        provider,
    ):
        with pytest.raises(RequirementsUnavailableError):
            score_job(isolated_session, job.public_id, TEST_USER_ID)

    provider.assert_not_called()
    assert isolated_session.query(MatchScoreRecord).count() == 0
    assert isolated_session.query(JobIntelligenceRecord).count() == 1


def test_persist_recovers_from_duplicate_job_insert(isolated_session) -> None:
    from backend.services.job_intelligence_service import _persist_grounded

    job = _described_job(isolated_session, public_id="persist-race")
    isolated_session.add(
        JobIntelligenceRecord(
            job_id=job.id,
            required_skills=["Go"],
            preferred_skills=[],
            years_experience=None,
            education_requirements=[],
            tech_stack=[],
            seniority=None,
            responsibilities=[],
            likely_interview_focus=[],
        )
    )
    isolated_session.commit()
    incoming = JobIntelligence(
        job_id=job.public_id,
        required_skills=["Python"],
        preferred_skills=["Docker"],
        years_experience=2,
        education_requirements=[],
        tech_stack=[],
        seniority="mid",
        responsibilities=[],
        likely_interview_focus=[],
    )
    original_query = isolated_session.query
    misses = {"remaining": 1}

    def query(entity, *args, **kwargs):
        result = original_query(entity, *args, **kwargs)
        if entity is not JobIntelligenceRecord or misses["remaining"] <= 0:
            return result
        original_filter = result.filter

        def filtered(*filter_args, **filter_kwargs):
            query_result = original_filter(*filter_args, **filter_kwargs)
            original_first = query_result.first

            def first():
                if misses["remaining"] > 0:
                    misses["remaining"] -= 1
                    return None
                return original_first()

            query_result.first = first
            return query_result

        result.filter = filtered
        return result

    isolated_session.query = query
    stored = _persist_grounded(isolated_session, job, incoming)
    isolated_session.query = original_query

    assert stored.required_skills == ["Python"]
    rows = isolated_session.query(JobIntelligenceRecord).all()
    assert len(rows) == 1
    assert rows[0].required_skills == ["Python"]
    assert rows[0].preferred_skills == ["Docker"]


class _NullLock:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_concurrent_first_scores_extract_once_and_leave_one_row(tmp_path) -> None:
    database_path = tmp_path / "concurrent-pipeline.sqlite"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    SessionFactory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    with SessionFactory() as db:
        _candidate(db, skills=["Python"])
        job = _described_job(db, public_id="concurrent-pipeline")

    def generate(_prompt: str, _system: str | None) -> str:
        time.sleep(0.1)
        return json.dumps(_grounded_payload())

    generator = Mock(side_effect=generate)

    def calculate() -> float:
        with SessionFactory() as db:
            return score_job_with_intelligence(
                db,
                job.public_id,
                TEST_USER_ID,
                generate_fn=generator,
            ).overall_score

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _index: calculate(), range(2)))
        assert len(results) == 2
        assert generator.call_count == 1
        with SessionFactory() as db:
            assert db.query(JobIntelligenceRecord).count() == 1
            assert db.query(MatchScoreRecord).count() == 1
    finally:
        engine.dispose()


def test_concurrent_first_scores_without_process_lock_leave_one_intelligence_row(
    tmp_path,
) -> None:
    database_path = tmp_path / "concurrent-unlocked.sqlite"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    SessionFactory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    with SessionFactory() as db:
        _candidate(db, skills=["Python"])
        job = _described_job(db, public_id="concurrent-unlocked")

    def generate(_prompt: str, _system: str | None) -> str:
        time.sleep(0.15)
        return json.dumps(_grounded_payload())

    generator = Mock(side_effect=generate)

    def calculate() -> float:
        with SessionFactory() as db:
            return score_job_with_intelligence(
                db,
                job.public_id,
                TEST_USER_ID,
                generate_fn=generator,
            ).overall_score

    try:
        with patch(
            "backend.services.scoring_orchestrator._JOB_LOCKS",
            tuple(_NullLock() for _ in range(64)),
        ):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _index: calculate(), range(2)))
        assert len(results) == 2
        with SessionFactory() as db:
            assert db.query(JobIntelligenceRecord).count() == 1
            assert db.query(MatchScoreRecord).count() >= 1
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        (LLMProviderError("private payload"), 502),
        (LLMConfigurationError("private configuration"), 503),
    ],
)
def test_score_api_maps_extraction_failures_without_fallback(
    isolated_client,
    failure: Exception,
    expected_status: int,
) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as session:
        _candidate(session, skills=["Python"])
        job = _described_job(session)
    fake_client = Mock()
    fake_client.generate.side_effect = failure

    with patch(
        "backend.services.job_intelligence_service.get_llm_client",
        return_value=fake_client,
    ):
        response = client.post(f"/api/jobs/{job.public_id}/score")

    assert response.status_code == expected_status
    assert "private" not in response.text
    with SessionLocal() as session:
        assert session.query(JobIntelligenceRecord).count() == 0
        assert session.query(MatchScoreRecord).count() == 0


def test_score_api_maps_structured_failure_without_fallback(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as session:
        _candidate(session, skills=["Python"])
        job = _described_job(session)
    fake_client = Mock()
    fake_client.generate.side_effect = ["invalid", "still invalid"]

    with patch(
        "backend.services.job_intelligence_service.get_llm_client",
        return_value=fake_client,
    ):
        response = client.post(f"/api/jobs/{job.public_id}/score")

    assert response.status_code == 502
    assert fake_client.generate.call_count == 2
    with SessionLocal() as session:
        assert session.query(JobIntelligenceRecord).count() == 0
        assert session.query(MatchScoreRecord).count() == 0


def test_backfill_skips_existing_and_descriptionless_jobs(isolated_session) -> None:
    existing = _described_job(isolated_session, public_id="backfill-existing")
    _intelligence(
        isolated_session,
        existing,
        required=["Python"],
        preferred=[],
        tech=[],
        years=None,
        education=[],
    )
    _job(
        isolated_session,
        public_id="backfill-empty",
        title="Generalist",
        description="",
    )
    _described_job(isolated_session, public_id="backfill-eligible")
    generator = Mock(return_value=json.dumps(_grounded_payload()))

    counts = run_backfill(isolated_session, generate_fn=generator)

    assert counts == BackfillCounts(
        scanned=3,
        eligible=1,
        extracted=1,
        skipped=2,
        failed=0,
    )
    assert generator.call_count == 1
    assert isolated_session.query(JobIntelligenceRecord).count() == 2


def test_backfill_is_idempotent_and_dry_run_is_read_only(isolated_session) -> None:
    _described_job(isolated_session, public_id="backfill-idempotent")
    generator = Mock(return_value=json.dumps(_grounded_payload()))

    dry_run = run_backfill(
        isolated_session,
        generate_fn=generator,
        dry_run=True,
    )
    assert dry_run.eligible == 1
    assert dry_run.extracted == 0
    assert generator.call_count == 0
    assert isolated_session.query(JobIntelligenceRecord).count() == 0

    first = run_backfill(isolated_session, generate_fn=generator)
    second = run_backfill(isolated_session, generate_fn=generator)

    assert first.extracted == 1
    assert second.extracted == 0
    assert second.skipped == 1
    assert generator.call_count == 1
    assert isolated_session.query(JobIntelligenceRecord).count() == 1


def test_backfill_reextract_updates_without_duplicates(isolated_session) -> None:
    job = _described_job(isolated_session, public_id="backfill-reextract")
    _intelligence(
        isolated_session,
        job,
        required=["Python"],
        preferred=[],
        tech=[],
        years=None,
        education=[],
    )
    generator = Mock(
        return_value=json.dumps(
            _grounded_payload(required_skills=["Python"], preferred_skills=["Docker"])
        )
    )

    counts = run_backfill(
        isolated_session,
        generate_fn=generator,
        reextract=True,
    )

    assert counts.extracted == 1
    assert generator.call_count == 1
    assert isolated_session.query(JobIntelligenceRecord).count() == 1
    stored = isolated_session.query(JobIntelligenceRecord).one()
    assert stored.preferred_skills == ["Docker"]


def test_backfill_failure_does_not_corrupt_successful_rows(isolated_session) -> None:
    _described_job(isolated_session, public_id="backfill-success")
    _described_job(isolated_session, public_id="backfill-failure")
    generator = SequenceGenerator(
        json.dumps(_grounded_payload()),
        LLMProviderError("private provider output"),
    )

    counts = run_backfill(isolated_session, generate_fn=generator)

    assert counts.extracted == 1
    assert counts.failed == 1
    assert isolated_session.query(JobIntelligenceRecord).count() == 1


def test_backfill_limit_and_output_are_count_only(isolated_session) -> None:
    private_markers = [
        "PRIVATE-BACKFILL-ONE",
        "PRIVATE-BACKFILL-TWO",
    ]
    for index, marker in enumerate(private_markers, start=1):
        _job(
            isolated_session,
            public_id=f"backfill-limit-{index}",
            title="Platform Engineer",
            description=f"Requirements:\nPython\n{marker}",
        )
    generator = Mock(return_value=json.dumps(_grounded_payload()))

    counts = run_backfill(
        isolated_session,
        generate_fn=generator,
        limit=1,
    )
    output = format_backfill_counts(counts)

    assert counts.eligible == 2
    assert counts.extracted == 1
    assert counts.skipped == 1
    assert generator.call_count == 1
    assert all(marker not in output for marker in private_markers)
    assert output == "scanned=2 eligible=2 extracted=1 skipped=1 failed=0"


def test_manual_qa_selection_requires_varied_anonymous_scenarios() -> None:
    private_marker = "PRIVATE-REAL-DESCRIPTION-MARKER"
    postings = [
        SourcePosting("Sparse Role", "Requirements: Python"),
        SourcePosting("Ordinary Role", "Requirements: Python\n" + ("Build APIs. " * 45)),
        SourcePosting("Long Role", "Requirements: Python\n" + ("Detailed posting text. " * 90)),
        SourcePosting(
            "Mixed Role",
            "Required: Python\nPreferred: Docker\n" + ("Role detail. " * 40),
        ),
        SourcePosting(
            "Poor Format Role",
            private_marker + (" unstructured posting content" * 30),
        ),
    ]

    selected = _select_postings(postings)

    assert len(selected) == 5
    assert _has_required_variety(selected)
    output = _counts_line(
        1,
        "ordinary",
        JobIntelligence(required_skills=["Python"]),
    )
    assert private_marker not in output
    assert output.startswith("scenario=1 length=ordinary required=1")


def test_get_routes_never_extract_or_score(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as session:
        job = _described_job(session)
    fake_client = Mock()
    fake_client.generate.side_effect = AssertionError("GET must not call a provider")

    with patch(
        "backend.services.job_intelligence_service.get_llm_client",
        return_value=fake_client,
    ):
        intelligence_response = client.get(f"/api/jobs/{job.public_id}/intelligence")

    assert intelligence_response.status_code == 404
    fake_client.generate.assert_not_called()
    with SessionLocal() as session:
        assert session.query(JobIntelligenceRecord).count() == 0
        assert session.query(MatchScoreRecord).count() == 0


def test_orchestration_logs_are_count_and_identifier_only(
    isolated_session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _candidate(isolated_session, skills=["Python"])
    job = _described_job(isolated_session)
    private_marker = "PRIVATE-ORCHESTRATION-MARKER"
    generator = Mock(
        return_value=json.dumps(
            _grounded_payload(responsibilities=[private_marker])
        )
    )

    with caplog.at_level("INFO", logger="backend.services.scoring_orchestrator"):
        score_job_with_intelligence(
            isolated_session,
            job.public_id,
            TEST_USER_ID,
            generate_fn=generator,
        )

    assert private_marker not in caplog.text
    assert job.description not in caplog.text
    assert "job_pk=" in caplog.text
    assert "extracted=1" in caplog.text


def test_backfill_refuses_production_database_path() -> None:
    with pytest.raises(ValueError, match="production database"):
        assert_safe_database_path(PRODUCTION_DATABASE)
    production_url_path = sqlite_path_from_url("sqlite:///./data/careerpilot.db")
    assert production_url_path == PRODUCTION_DATABASE
    with pytest.raises(ValueError, match="production database"):
        assert_safe_database_path(production_url_path)
    assert assert_safe_database_path(PRODUCTION_DATABASE, dry_run=True) == PRODUCTION_DATABASE
    assert assert_safe_database_path(PRODUCTION_DATABASE, confirm=True) == PRODUCTION_DATABASE


def test_cli_refuses_production_mutation_without_confirm(monkeypatch, capsys) -> None:
    session_factory = Mock()
    worker = Mock()
    extractor = Mock()
    monkeypatch.setattr(
        "scripts.backfill_job_intelligence.sqlite_path_from_url",
        lambda _url: PRODUCTION_DATABASE,
    )
    monkeypatch.setattr("scripts.backfill_job_intelligence.SessionLocal", session_factory)
    monkeypatch.setattr("scripts.backfill_job_intelligence.run_backfill", worker)
    monkeypatch.setattr(
        "scripts.backfill_job_intelligence.extract_job_intelligence",
        extractor,
    )

    exit_code = backfill_main([])

    assert exit_code == 2
    session_factory.assert_not_called()
    worker.assert_not_called()
    extractor.assert_not_called()
    output = capsys.readouterr().out.strip()
    assert output.endswith("result=refused")
    assert "extracted=0" in output
    assert "careerpilot.db" not in output
    assert PRODUCTION_DATABASE.name not in output


def test_cli_production_dry_run_is_read_only_without_confirm(
    isolated_session,
    monkeypatch,
    capsys,
) -> None:
    from contextlib import contextmanager

    _described_job(isolated_session, public_id="cli-production-dry-run")
    extractor = Mock(side_effect=AssertionError("dry-run must not call a provider"))

    @contextmanager
    def fake_session():
        yield isolated_session

    monkeypatch.setattr(
        "scripts.backfill_job_intelligence.sqlite_path_from_url",
        lambda _url: PRODUCTION_DATABASE,
    )
    monkeypatch.setattr("scripts.backfill_job_intelligence.SessionLocal", fake_session)
    monkeypatch.setattr(
        "scripts.backfill_job_intelligence.extract_job_intelligence",
        extractor,
    )

    exit_code = backfill_main(["--dry-run"])

    assert exit_code == 0
    extractor.assert_not_called()
    assert isolated_session.query(JobIntelligenceRecord).count() == 0
    output = capsys.readouterr().out.strip()
    assert "extracted=0" in output
    assert "result=refused" not in output


def test_cli_confirmed_production_reaches_worker(monkeypatch, capsys) -> None:
    from contextlib import contextmanager

    worker = Mock(return_value=BackfillCounts())
    entered = {"value": False}

    @contextmanager
    def fake_session():
        entered["value"] = True
        yield Mock()

    monkeypatch.setattr(
        "scripts.backfill_job_intelligence.sqlite_path_from_url",
        lambda _url: PRODUCTION_DATABASE,
    )
    monkeypatch.setattr("scripts.backfill_job_intelligence.SessionLocal", fake_session)
    monkeypatch.setattr("scripts.backfill_job_intelligence.run_backfill", worker)

    exit_code = backfill_main(["--confirm"])

    assert exit_code == 0
    assert entered["value"] is True
    worker.assert_called_once()
    assert worker.call_args.kwargs["dry_run"] is False
    assert "result=refused" not in capsys.readouterr().out


def test_cli_temporary_database_runs_without_confirm(
    isolated_session,
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    from contextlib import contextmanager

    from backend.services.job_intelligence_service import (
        extract_job_intelligence as extract_impl,
    )

    _described_job(isolated_session, public_id="cli-temp-backfill")
    generator = Mock(return_value=json.dumps(_grounded_payload()))

    @contextmanager
    def fake_session():
        yield isolated_session

    def extract_with_fake_provider(db, public_id, generate_fn=None):
        del generate_fn
        return extract_impl(db, public_id, generate_fn=generator)

    monkeypatch.setattr(
        "scripts.backfill_job_intelligence.sqlite_path_from_url",
        lambda _url: tmp_path / "backfill.sqlite",
    )
    monkeypatch.setattr("scripts.backfill_job_intelligence.SessionLocal", fake_session)
    monkeypatch.setattr(
        "scripts.backfill_job_intelligence.extract_job_intelligence",
        extract_with_fake_provider,
    )

    exit_code = backfill_main([])

    assert exit_code == 0
    assert generator.call_count == 1
    assert isolated_session.query(JobIntelligenceRecord).count() == 1
    output = capsys.readouterr().out.strip()
    assert "extracted=1" in output
    assert "result=refused" not in output


def test_manual_qa_gate_selects_ollama_first_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("backend.core.config.settings.llm_provider_order", "ollama,gemini")
    monkeypatch.setattr("backend.core.config.settings.gemini_api_key", "")
    assert _first_configured_provider() == "ollama"


def test_manual_qa_gate_is_blocked_only_when_nothing_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("backend.core.config.settings.llm_provider_order", "ollama,gemini")
    monkeypatch.setattr("backend.core.config.settings.ollama_base_url", "")
    monkeypatch.setattr("backend.core.config.settings.gemini_api_key", "")
    assert _first_configured_provider() is None


def test_manual_qa_gate_falls_back_past_an_unconfigured_first_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("backend.core.config.settings.llm_provider_order", "gemini,ollama")
    monkeypatch.setattr("backend.core.config.settings.gemini_api_key", "")
    assert _first_configured_provider() == "ollama"


def test_manual_qa_does_not_mask_validation_failure_as_provider_blocker() -> None:
    assert _final_result(
        failed=2,
        provider_blocked=True,
        validation_failed=True,
    ) == ("fail", 1)
    assert _final_result(
        failed=1,
        provider_blocked=True,
        validation_failed=False,
    ) == ("blocked", 2)
