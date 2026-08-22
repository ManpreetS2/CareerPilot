"""Database initialization tests."""

from __future__ import annotations

import importlib

import pytest
from sqlalchemy import create_engine, inspect

from backend.db.init_db import REQUIRED_TABLES, init_db


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
