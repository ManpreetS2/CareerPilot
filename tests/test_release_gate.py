"""High-level v1 release-gate invariants. Isolated SQLite only."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

from backend.core.config import Settings, validate_origin_settings, validate_runtime_settings
from backend.db.database import Base
from backend.db.models import MatchScoreRecord
from tests.mvp_helpers import insert_job, insert_ready_profile, insert_score


def test_fresh_sqlite_file_creates_expected_tables(tmp_path) -> None:
    db_path = tmp_path / "test_v1_release_gate.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    try:
        assert db_path.exists()
        tables = set(inspect(engine).get_table_names())
        for required in (
            "users",
            "user_sessions",
            "candidates",
            "jobs",
            "saved_jobs",
            "match_scores",
            "match_evidence",
            "job_requirement_profiles",
            "application_packages",
            "resume_versions",
            "application_tracker",
        ):
            assert required in tables, required
    finally:
        engine.dispose()


def test_health_and_root_are_public(isolated_client) -> None:
    client, _ = isolated_client
    client.cookies.clear()
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    root = client.get("/")
    assert root.status_code == 200
    assert "CareerPilot" in root.json()["name"]


def test_incomplete_user_cannot_scout_or_read_growth(isolated_client, monkeypatch) -> None:
    client, _ = isolated_client
    scout = Mock(side_effect=AssertionError("must not scout"))
    extract = Mock(side_effect=AssertionError("must not extract"))
    generate = Mock(side_effect=AssertionError("must not generate"))
    monkeypatch.setattr("backend.api.routes.jobs.scout_jobs", scout)
    monkeypatch.setattr(
        "backend.services.job_intelligence_service.extract_job_intelligence",
        extract,
    )
    monkeypatch.setattr("backend.services.llm_client.LLMClient.generate", generate)

    scout_response = client.post("/api/scout-jobs")
    growth = client.get("/api/career-growth")
    assert scout_response.status_code == 409
    assert scout_response.json()["detail"]["code"] == "profile_required"
    assert scout_response.json()["detail"]["next_route"] == "/profile"
    assert growth.status_code == 409
    assert growth.json()["detail"]["code"] == "profile_required"
    assert scout.call_count == 0
    assert extract.call_count == 0
    assert generate.call_count == 0


def test_growth_get_is_read_only_after_profile_ready(isolated_client, monkeypatch) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        candidate, _prefs = insert_ready_profile(db, user_id=client.test_user_id)
        stored_job = insert_job(db, public_id="release-gate-job")
        score = insert_score(db, stored_job, candidate)
        before = (score.id, score.overall_score, score.ranking_score)

    scout = Mock(side_effect=AssertionError("must not scout"))
    extract = Mock(side_effect=AssertionError("must not extract"))
    monkeypatch.setattr("backend.services.job_service.scout_jobs", scout)
    monkeypatch.setattr(
        "backend.services.job_intelligence_service.extract_job_intelligence",
        extract,
    )
    monkeypatch.setattr("backend.services.llm_client.LLMClient.generate", Mock(side_effect=AssertionError("llm")))

    body = client.get("/api/career-growth")
    assert body.status_code == 200
    payload = body.json()
    assert payload["jobs_considered"] >= 0
    assert "skill_gaps" in payload
    assert scout.call_count == 0
    assert extract.call_count == 0
    with SessionLocal() as db:
        row = db.get(MatchScoreRecord, before[0])
        assert row is not None
        assert (row.id, row.overall_score, row.ranking_score) == before


def test_wildcard_cors_is_rejected() -> None:
    try:
        validate_origin_settings(Settings(allowed_origins="*"))
        raised = False
    except RuntimeError:
        raised = True
    assert raised is True


def test_production_requires_secure_cookies() -> None:
    from backend.core.config import settings

    original_env = settings.app_env
    original_secure = settings.cookie_secure
    try:
        object.__setattr__(settings, "app_env", "production")
        object.__setattr__(settings, "cookie_secure", False)
        try:
            validate_runtime_settings()
            raised = False
        except RuntimeError as exc:
            raised = True
            assert "COOKIE_SECURE" in str(exc)
        assert raised is True
    finally:
        object.__setattr__(settings, "app_env", original_env)
        object.__setattr__(settings, "cookie_secure", original_secure)


def test_license_is_proprietary_not_open_source() -> None:
    text = Path("LICENSE").read_text(encoding="utf-8")
    assert "PROPRIETARY SOURCE NOTICE" in text
    assert "not open source" in text.lower() or "does not make this software open source" in text
    assert "MIT License" not in text
    assert "Apache License" not in text
