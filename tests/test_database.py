"""Database initialization tests."""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.database import Base, enable_sqlite_foreign_keys
from backend.db.init_db import REQUIRED_TABLES, init_db
from backend.db.models import UserSession


def test_database_initializes_required_tables(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    init_db_module = importlib.import_module("backend.db.init_db")
    engine = create_engine(f"sqlite:///{tmp_path / 'init.sqlite'}", future=True)
    monkeypatch.setattr(init_db_module, "engine", engine)
    try:
        init_db()
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    missing = [name for name in REQUIRED_TABLES if name not in tables]
    assert missing == [], f"Missing tables: {missing}"


def test_sqlite_foreign_keys_reject_orphaned_rows() -> None:
    engine = create_engine("sqlite://", future=True)
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(bind=engine)
    try:
        with Session(engine) as session:
            session.add(
                UserSession(
                    token="deadbeef",
                    user_id=999999,
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                )
            )
            with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
                session.commit()
    finally:
        engine.dispose()
