"""Showcase seed helper: isolated SQLite only, never an existing file."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from scripts.seed_showcase_demo import (
    EXISTING_DESTINATION_MESSAGE,
    SHOWCASE_COMPANY_PRIMARY,
    SHOWCASE_COMPANY_SECOND,
    SHOWCASE_EMAIL,
    refuse_database_path,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_seed(monkeypatch: pytest.MonkeyPatch, dest: Path) -> int:
    monkeypatch.setattr("sys.argv", ["seed_showcase_demo.py", "--database", str(dest)])
    from scripts import seed_showcase_demo

    return seed_showcase_demo.main()


def test_refuses_production_careerpilot_db(tmp_path: Path) -> None:
    production = Path("data/careerpilot.db")
    with pytest.raises(SystemExit, match="careerpilot.db"):
        refuse_database_path(production)


def test_refuses_forbidden_filename(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="production-looking"):
        refuse_database_path(tmp_path / "careerpilot.db")


def test_accepts_brand_new_temp_sqlite(tmp_path: Path) -> None:
    dest = tmp_path / "showcase.sqlite"
    assert not dest.exists()
    assert refuse_database_path(dest) == dest.resolve()


def test_refuses_random_existing_sqlite_without_modifying_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "my-real-user.sqlite"
    dest.write_bytes(b"not-a-careerpilot-database")
    digest = _sha256(dest)
    with pytest.raises(SystemExit, match="already exists"):
        refuse_database_path(dest)
    with pytest.raises(SystemExit, match="already exists"):
        _run_seed(monkeypatch, dest)
    assert dest.read_bytes() == b"not-a-careerpilot-database"
    assert _sha256(dest) == digest


def test_refuses_zero_byte_existing_sqlite_without_modifying_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "empty.sqlite"
    dest.write_bytes(b"")
    assert dest.stat().st_size == 0
    with pytest.raises(SystemExit, match="already exists"):
        _run_seed(monkeypatch, dest)
    assert dest.exists()
    assert dest.stat().st_size == 0
    assert dest.read_bytes() == b""


def test_refuses_existing_sqlite_with_unrelated_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "other-app.sqlite"
    conn = sqlite3.connect(dest)
    try:
        conn.execute("CREATE TABLE keep_me (id INTEGER PRIMARY KEY, note TEXT)")
        conn.execute("INSERT INTO keep_me (id, note) VALUES (42, 'untouched')")
        conn.commit()
    finally:
        conn.close()
    digest = _sha256(dest)
    with pytest.raises(SystemExit, match="already exists"):
        _run_seed(monkeypatch, dest)
    assert _sha256(dest) == digest
    conn = sqlite3.connect(dest)
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables == {"keep_me"}
        assert conn.execute("SELECT id, note FROM keep_me").fetchone() == (42, "untouched")
    finally:
        conn.close()


def test_refuses_existing_careerpilot_db_with_harmless_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "career.db"
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.core.security import hash_password
    from backend.db.database import Base
    from backend.db import models as _models  # noqa: F401
    from backend.db.models import User

    engine = create_engine(f"sqlite:///{dest.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    session = SessionLocal()
    try:
        session.add(
            User(email="real.user@example.com", hashed_password=hash_password("Not-The-Showcase-Pass-1!"))
        )
        session.commit()
        assert session.query(User).count() == 1
    finally:
        session.close()
        engine.dispose()
    digest = _sha256(dest)
    with pytest.raises(SystemExit, match="already exists"):
        _run_seed(monkeypatch, dest)
    assert _sha256(dest) == digest
    engine = create_engine(f"sqlite:///{dest.as_posix()}", future=True)
    SessionLocal = sessionmaker(bind=engine, future=True)
    session = SessionLocal()
    try:
        emails = {user.email for user in session.query(User).all()}
        assert emails == {"real.user@example.com"}
        assert SHOWCASE_EMAIL not in emails
    finally:
        session.close()
        engine.dispose()


def test_seed_creates_synthetic_user_on_brand_new_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "showcase.sqlite"
    assert not dest.exists()
    assert _run_seed(monkeypatch, dest) == 0
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.db.models import JobRecord, User

    engine = create_engine(f"sqlite:///{dest.as_posix()}", future=True)
    SessionLocal = sessionmaker(bind=engine, future=True)
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.email == SHOWCASE_EMAIL).one()
        assert user.email == SHOWCASE_EMAIL
        jobs = session.query(JobRecord).all()
        assert {job.company for job in jobs} == {SHOWCASE_COMPANY_PRIMARY, SHOWCASE_COMPANY_SECOND}
        assert all("DEMO" in (job.description or "") or "example.com/showcase" in job.url for job in jobs)
    finally:
        session.close()
        engine.dispose()


def test_refuse_message_is_operator_actionable() -> None:
    assert "already exists" in EXISTING_DESTINATION_MESSAGE
    assert "delete" in EXISTING_DESTINATION_MESSAGE.lower()
