"""Explicit legacy owner-claim CLI. Never touches data/careerpilot.db."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.db.database import Base
from backend.db.models import Candidate, JobRecord, TargetPreference, User
from scripts.claim_legacy_ownership import apply_claim, inspect_claim, is_production_database, main

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = ROOT / "data" / "careerpilot.db"


def _engine(tmp_path: Path):
    path = tmp_path / "legacy.sqlite"
    engine = create_engine(f"sqlite:///{path}", future=True)
    Base.metadata.create_all(bind=engine)
    return engine, path


def _user(session, email: str) -> User:
    user = User(email=email, hashed_password="x")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_claim_succeeds_for_single_null_owner_set(tmp_path) -> None:
    engine, _path = _engine(tmp_path)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        user = _user(session, "owner@example.com")
        user_id = user.id
        session.add(Candidate(user_id=None, name="Legacy Candidate", skills=["Python"]))
        session.add(TargetPreference(user_id=None, target_roles=["Intern"]))
        session.commit()
        plan = apply_claim(session, user_id)
    assert not plan.errors
    with SessionLocal() as session:
        candidate = session.query(Candidate).one()
        prefs = session.query(TargetPreference).one()
        assert candidate.user_id == user_id
        assert prefs.user_id == user_id
        second = apply_claim(session, user_id)
    assert second.claimable_total == 0
    assert second.already_owned_total >= 1


def test_claim_refuses_ambiguous_null_candidates(tmp_path) -> None:
    engine, _path = _engine(tmp_path)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        user = _user(session, "owner@example.com")
        session.add(Candidate(user_id=None, name="Legacy A", skills=["Python"]))
        session.add(Candidate(user_id=None, name="Legacy B", skills=["SQL"]))
        session.commit()
        plan = apply_claim(session, user.id)
    assert plan.errors
    with SessionLocal() as session:
        assert all(row.user_id is None for row in session.query(Candidate).all())


def test_claim_is_idempotent_and_cross_user_safe(tmp_path) -> None:
    engine, _path = _engine(tmp_path)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        owner = _user(session, "owner@example.com")
        other = _user(session, "other@example.com")
        owner_id = owner.id
        other_id = other.id
        session.add(Candidate(user_id=None, name="Legacy Candidate", skills=["Python"]))
        session.add(Candidate(user_id=other_id, name="Other Candidate", skills=["Go"]))
        session.add(
            JobRecord(
                public_id="job-1",
                title="Engineer",
                company="Acme",
                url="https://example.com/job",
                description="Python",
                source="manual",
            )
        )
        session.commit()
        first = apply_claim(session, owner_id)
        second = apply_claim(session, owner_id)
    assert not first.errors
    assert not second.errors
    assert second.claimable_total == 0
    with SessionLocal() as session:
        owned = session.query(Candidate).filter(Candidate.user_id == owner_id).one()
        other_row = session.query(Candidate).filter(Candidate.user_id == other_id).one()
        assert owned.name == "Legacy Candidate"
        assert other_row.name == "Other Candidate"


def test_claim_cli_dry_run_does_not_write(tmp_path) -> None:
    engine, path = _engine(tmp_path)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        user = _user(session, "owner@example.com")
        session.add(Candidate(user_id=None, name="Legacy Candidate", skills=["Python"]))
        session.commit()
        user_id = user.id
    code = main(
        [
            "--user-id",
            str(user_id),
            "--database-url",
            f"sqlite:///{path}",
        ]
    )
    assert code == 0
    with SessionLocal() as session:
        assert session.query(Candidate).one().user_id is None


def test_claim_refuses_production_database_without_extra_flag(tmp_path, monkeypatch) -> None:
    assert is_production_database(f"sqlite:///{PRODUCTION.resolve()}") is True
    engine, path = _engine(tmp_path)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        user = _user(session, "owner@example.com")
        user_id = user.id
    monkeypatch.setattr("scripts.claim_legacy_ownership.is_production_database", lambda _url: True)
    code = main(
        [
            "--user-id",
            str(user_id),
            "--database-url",
            f"sqlite:///{path}",
            "--apply",
            "--confirm",
        ]
    )
    assert code == 2


def test_startup_modules_do_not_import_claim_script() -> None:
    for relative in ("backend/main.py", "backend/db/init_db.py"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "claim_legacy_ownership" not in text
