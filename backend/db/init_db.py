"""Create SQLite tables for CareerPilot AI."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import inspect, text

from backend.db.database import Base, engine
from backend.db import models as _models  # noqa: F401  — register ORM models on Base

logger = logging.getLogger(__name__)

REQUIRED_TABLES = (
    "candidates",
    "target_preferences",
    "jobs",
    "job_intelligence",
    "match_scores",
    "application_packages",
)


def _add_missing_columns() -> None:
    """Add any model columns missing from an existing table.

    Base.metadata.create_all only creates tables that don't exist yet — it's
    a no-op for a table that already exists with an older shape. Without
    this, pulling a branch that adds a column (as this one does) breaks
    every read against a DB file created before that column existed.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing_columns:
                continue
            column_type = column.type.compile(engine.dialect)
            with engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {column_type}'))
            logger.info("Added missing column %s.%s", table.name, column.name)


def init_db() -> None:
    """Create the data directory, create any missing Day 1 tables, and add
    any columns missing from tables that already existed."""
    Path("data").mkdir(parents=True, exist_ok=True)
    Path("logs").mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
    logger.info("Database initialized with tables: %s", ", ".join(sorted(Base.metadata.tables)))


if __name__ == "__main__":
    init_db()
    print("Database ready at data/careerpilot.db")
