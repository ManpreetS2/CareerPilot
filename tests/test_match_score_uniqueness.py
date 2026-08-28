"""MatchScore uniqueness: one active row per (job_id, candidate_id)."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.db.models import MatchScoreRecord
from tests.mvp_helpers import insert_candidate, insert_job


def _score_row(job_id: int, candidate_id: int, *, rationale: str) -> MatchScoreRecord:
    return MatchScoreRecord(
        job_id=job_id,
        candidate_id=candidate_id,
        overall_score=50,
        recommendation="consider",
        rationale=rationale,
        matched_skills=[],
        partial_matches=[],
        missing_skills=[],
    )


def test_two_db_sessions_cannot_insert_duplicate_match_scores(isolated_engine) -> None:
    SessionLocal = sessionmaker(bind=isolated_engine, autocommit=False, autoflush=False)
    with SessionLocal() as db:
        job = insert_job(db, public_id="score-race-job")
        candidate = insert_candidate(db, user_id=1)
        job_id = job.id
        candidate_id = candidate.id

    session_a = SessionLocal()
    session_b = SessionLocal()
    try:
        session_a.add(_score_row(job_id, candidate_id, rationale="session-a"))
        session_b.add(_score_row(job_id, candidate_id, rationale="session-b"))
        session_a.commit()
        second_failed = False
        try:
            session_b.commit()
        except IntegrityError:
            session_b.rollback()
            second_failed = True
        with SessionLocal() as db:
            count = (
                db.query(MatchScoreRecord)
                .filter(MatchScoreRecord.job_id == job_id, MatchScoreRecord.candidate_id == candidate_id)
                .count()
            )
        assert count == 1
        assert second_failed is True
    finally:
        session_a.close()
        session_b.close()


def test_init_db_dedupes_legacy_match_scores_then_adds_unique_index(tmp_path, monkeypatch) -> None:
    import importlib

    from sqlalchemy import create_engine, inspect, text

    engine = create_engine(f"sqlite:///{tmp_path / 'match-dupes.sqlite'}", future=True)
    init_db_module = importlib.import_module("backend.db.init_db")
    monkeypatch.setattr(init_db_module, "engine", engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE jobs ("
                "id INTEGER PRIMARY KEY, public_id VARCHAR(64) UNIQUE, title VARCHAR(255) NOT NULL, "
                "company VARCHAR(255) NOT NULL, url TEXT NOT NULL, description TEXT NOT NULL, "
                "source VARCHAR(64) NOT NULL, status VARCHAR(64))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE candidates ("
                "id INTEGER PRIMARY KEY, user_id INTEGER, name VARCHAR(255) NOT NULL, skills JSON, "
                "projects JSON, experience JSON, education JSON, certifications JSON, strengths JSON, "
                "evidence_links JSON)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE match_scores ("
                "id INTEGER PRIMARY KEY, job_id INTEGER, candidate_id INTEGER, overall_score FLOAT NOT NULL, "
                "recommendation VARCHAR(32) NOT NULL, rationale TEXT NOT NULL, matched_skills JSON, "
                "partial_matches JSON, missing_skills JSON)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE match_evidence ("
                "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, job_id INTEGER NOT NULL, "
                "candidate_id INTEGER NOT NULL, match_score_id INTEGER NOT NULL, evidence_version INTEGER NOT NULL, "
                "payload_json JSON)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO jobs (id, public_id, title, company, url, description, source, status) "
                "VALUES (1, 'dup-job', 'Engineer', 'Acme', 'https://example.com/j', 'desc', 'manual', 'discovered')"
            )
        )
        conn.execute(text("INSERT INTO candidates (id, name) VALUES (1, 'Ada')"))
        conn.execute(
            text(
                "INSERT INTO match_scores (id, job_id, candidate_id, overall_score, recommendation, rationale) "
                "VALUES (10, 1, 1, 40, 'consider', 'older'), (20, 1, 1, 90, 'apply', 'newer')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO match_evidence (id, user_id, job_id, candidate_id, match_score_id, evidence_version, payload_json) "
                "VALUES (1, 1, 1, 1, 10, 1, '{}'), (2, 1, 1, 1, 20, 1, '{}')"
            )
        )

    try:
        init_db_module.init_db()
        with engine.connect() as conn:
            ids = [row[0] for row in conn.execute(text("SELECT id FROM match_scores ORDER BY id")).fetchall()]
            evidence_score_ids = [
                row[0] for row in conn.execute(text("SELECT match_score_id FROM match_evidence ORDER BY id")).fetchall()
            ]
        indexes = {idx["name"] for idx in inspect(engine).get_indexes("match_scores")}
    finally:
        engine.dispose()

    assert ids == [20]
    assert evidence_score_ids == [20]
    assert "ux_match_scores_job_candidate" in indexes
