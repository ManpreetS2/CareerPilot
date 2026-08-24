"""Batch scoring CLI: dry-run, confirmation, and idempotence."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.database import Base
from scripts.score_all_jobs import run_batch_scoring
from tests.mvp_helpers import TEST_USER_ID, insert_job, seed_materials_prerequisites


def _temp_db(tmp_path):
    path = tmp_path / "batch.sqlite"
    url = f"sqlite:///{path}"
    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return url, SessionLocal, engine


def test_batch_refuses_without_explicit_user(tmp_path) -> None:
    url, SessionLocal, engine = _temp_db(tmp_path)
    try:
        with SessionLocal() as db:
            seed_materials_prerequisites(db, public_id="job-a", with_score=False)
        result = run_batch_scoring(database_url=url, dry_run=True)
        assert result["refused"] == 1
        assert result["written"] == 0
    finally:
        engine.dispose()


def test_batch_refuses_ambiguous_user(tmp_path) -> None:
    url, SessionLocal, engine = _temp_db(tmp_path)
    try:
        with SessionLocal() as db:
            seed_materials_prerequisites(db, public_id="job-a", with_score=False)
        result = run_batch_scoring(
            database_url=url,
            dry_run=True,
            user_id=TEST_USER_ID,
            user_email="user1@example.com",
        )
        assert result["refused"] == 1
    finally:
        engine.dispose()


def test_batch_dry_run_writes_nothing(tmp_path) -> None:
    url, SessionLocal, engine = _temp_db(tmp_path)
    try:
        with SessionLocal() as db:
            seed_materials_prerequisites(db, public_id="job-a", with_score=False)
            insert_job(db, public_id="job-b")
        from backend.db.models import MatchScoreRecord

        with SessionLocal() as db:
            before = db.query(MatchScoreRecord).count()
        result = run_batch_scoring(database_url=url, dry_run=True, user_id=TEST_USER_ID)
        assert result["written"] == 0
        assert result["refused"] == 0
        with SessionLocal() as db:
            assert db.query(MatchScoreRecord).count() == before
    finally:
        engine.dispose()


def test_production_batch_without_confirmation_is_refused(tmp_path) -> None:
    url, SessionLocal, engine = _temp_db(tmp_path)
    try:
        from scripts import score_all_jobs as mod

        original = mod.PRODUCTION_SQLITE
        fake_prod = tmp_path / "careerpilot.db"
        mod.PRODUCTION_SQLITE = fake_prod.resolve()
        prod_url = f"sqlite:///{fake_prod}"
        try:
            result = run_batch_scoring(
                database_url=prod_url,
                dry_run=False,
                confirm_production=False,
                user_id=TEST_USER_ID,
            )
            assert result["refused"] == 1
            assert result["written"] == 0
        finally:
            mod.PRODUCTION_SQLITE = original
    finally:
        engine.dispose()


def test_batch_execution_is_idempotent(tmp_path) -> None:
    url, SessionLocal, engine = _temp_db(tmp_path)
    try:
        with SessionLocal() as db:
            seed_materials_prerequisites(db, public_id="job-a", with_score=False)
        first = run_batch_scoring(
            database_url=url, dry_run=False, only_unscored=True, user_id=TEST_USER_ID
        )
        second = run_batch_scoring(
            database_url=url, dry_run=False, only_unscored=True, user_id=TEST_USER_ID
        )
        assert first["scored"] >= 1
        assert second["skipped_already_scored"] >= 1
        from backend.db.models import MatchScoreRecord

        with SessionLocal() as db:
            assert db.query(MatchScoreRecord).count() == 1
    finally:
        engine.dispose()


def test_batch_only_unscored_is_scoped_to_current_candidate(tmp_path) -> None:
    url, SessionLocal, engine = _temp_db(tmp_path)
    try:
        from tests.mvp_helpers import insert_candidate, insert_score

        with SessionLocal() as db:
            job, first = seed_materials_prerequisites(db, public_id="job-a", with_score=False)
            insert_score(db, job, first)
            insert_candidate(db)
        result = run_batch_scoring(
            database_url=url, dry_run=False, only_unscored=True, user_id=TEST_USER_ID
        )
        assert result["scored"] >= 1
        from backend.db.models import MatchScoreRecord

        with SessionLocal() as db:
            assert db.query(MatchScoreRecord).count() == 2
    finally:
        engine.dispose()


def test_batch_dry_run_reports_eligible_not_scored(tmp_path) -> None:
    url, SessionLocal, engine = _temp_db(tmp_path)
    try:
        with SessionLocal() as db:
            seed_materials_prerequisites(db, public_id="job-a", with_score=False)
        result = run_batch_scoring(
            database_url=url, dry_run=True, only_unscored=True, user_id=TEST_USER_ID
        )
        assert result["written"] == 0
        assert result["scored"] == 0
        assert result.get("eligible") or result.get("would_score")
        from backend.db.models import MatchScoreRecord

        with SessionLocal() as db:
            assert db.query(MatchScoreRecord).count() == 0
    finally:
        engine.dispose()


def test_batch_without_current_candidate_skips_before_scoring(tmp_path) -> None:
    url, SessionLocal, engine = _temp_db(tmp_path)
    try:
        from tests.mvp_helpers import ensure_user

        with SessionLocal() as db:
            ensure_user(db, TEST_USER_ID)
            insert_job(db, public_id="job-a")
        result = run_batch_scoring(
            database_url=url, dry_run=False, only_unscored=True, user_id=TEST_USER_ID
        )
        assert result["written"] == 0
        assert result["scored"] == 0
        assert result["refused"] == 0
    finally:
        engine.dispose()
