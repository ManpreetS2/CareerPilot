"""Batch scoring CLI: dry-run, confirmation, and idempotence."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.database import Base
from scripts.score_all_jobs import run_batch_scoring
from tests.mvp_helpers import insert_job, seed_materials_prerequisites


def _temp_db(tmp_path):
    path = tmp_path / "batch.sqlite"
    url = f"sqlite:///{path}"
    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return url, SessionLocal, engine


def test_batch_dry_run_writes_nothing(tmp_path) -> None:
    url, SessionLocal, engine = _temp_db(tmp_path)
    try:
        with SessionLocal() as db:
            seed_materials_prerequisites(db, public_id="job-a", with_score=False)
            insert_job(db, public_id="job-b")
        from backend.db.models import MatchScoreRecord

        with SessionLocal() as db:
            before = db.query(MatchScoreRecord).count()
        result = run_batch_scoring(database_url=url, dry_run=True)
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
            result = run_batch_scoring(database_url=prod_url, dry_run=False, confirm_production=False)
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
        first = run_batch_scoring(database_url=url, dry_run=False, only_unscored=True)
        second = run_batch_scoring(database_url=url, dry_run=False, only_unscored=True)
        assert first["scored"] >= 1
        assert second["skipped_already_scored"] >= 1
        from backend.db.models import MatchScoreRecord

        with SessionLocal() as db:
            assert db.query(MatchScoreRecord).count() == 1
    finally:
        engine.dispose()
