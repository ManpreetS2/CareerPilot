"""Database initialization tests."""

from __future__ import annotations

from sqlalchemy import inspect

from backend.db.database import engine
from backend.db.init_db import REQUIRED_TABLES, init_db


def test_database_initializes_required_tables() -> None:
    init_db()
    tables = set(inspect(engine).get_table_names())
    missing = [name for name in REQUIRED_TABLES if name not in tables]
    assert missing == [], f"Missing tables: {missing}"
