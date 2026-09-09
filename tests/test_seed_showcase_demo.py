"""Showcase seed helper: isolated SQLite only, never production."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.seed_showcase_demo import SHOWCASE_EMAIL, refuse_database_path


def test_refuses_production_careerpilot_db(tmp_path: Path) -> None:
    production = Path("data/careerpilot.db")
    with pytest.raises(SystemExit, match="careerpilot.db"):
        refuse_database_path(production)


def test_refuses_forbidden_filename(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="production-looking"):
        refuse_database_path(tmp_path / "careerpilot.db")


def test_accepts_temp_sqlite(tmp_path: Path) -> None:
    dest = tmp_path / "showcase.sqlite"
    assert refuse_database_path(dest) == dest.resolve()


def test_seed_creates_synthetic_user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "showcase.sqlite"
    monkeypatch.setattr("sys.argv", ["seed_showcase_demo.py", "--database", str(dest)])
    from scripts import seed_showcase_demo

    assert seed_showcase_demo.main() == 0
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
        assert {job.company for job in jobs} == {"Harborline Analytics", "Cedar & Pine Robotics"}
        assert all("DEMO" in (job.description or "") or "example.com/showcase" in job.url for job in jobs)
    finally:
        session.close()
        engine.dispose()
