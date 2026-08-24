"""Create SQLite tables for CareerPilot AI."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateIndex

from backend.db.database import Base, engine
from backend.db import models as _models  # noqa: F401  — register ORM models on Base

logger = logging.getLogger(__name__)

REQUIRED_TABLES = (
    "users",
    "user_sessions",
    "candidates",
    "target_preferences",
    "jobs",
    "job_intelligence",
    "match_scores",
    "application_packages",
    "form_fill_attempts",
    "application_tracker",
    "interview_prep",
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


def _add_missing_indexes() -> None:
    """Create any model-defined indexes missing from an existing table.

    Same gap as _add_missing_columns: create_all() only adds indexes when it
    creates the table itself, not to a table that already existed.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        existing_index_names = {idx["name"] for idx in inspector.get_indexes(table.name)}
        for index in table.indexes:
            if index.name in existing_index_names:
                continue
            ddl = str(CreateIndex(index).compile(dialect=engine.dialect))
            try:
                with engine.begin() as conn:
                    conn.execute(text(ddl))
            except IntegrityError:
                # A unique index can't be created over rows that already
                # violate it (pre-existing duplicates from before this
                # constraint existed). Don't crash startup over it — log
                # loudly so it gets cleaned up, and move on.
                logger.error(
                    "Could not add unique index %s on %s: existing rows violate "
                    "uniqueness. Manual cleanup required.",
                    index.name,
                    table.name,
                )
                continue
            logger.info("Added missing index %s on %s", index.name, table.name)


def _replace_application_packages_job_index() -> None:
    """One-time, idempotent swap: application_packages used to be unique on
    job_id alone (one package per job, system-wide). Multi-user support needs
    it unique on (job_id, user_id) instead, so two different users can each
    have their own package for the same shared job. _add_missing_indexes()
    can only ever add a missing index, never replace one, so the old index
    has to be dropped explicitly before the new composite one (declared on
    the model) gets picked up by the normal diffing pass. Safe to run on
    every startup — a no-op once the old index is gone.
    """
    inspector = inspect(engine)
    if "application_packages" not in inspector.get_table_names():
        return
    existing_index_names = {idx["name"] for idx in inspector.get_indexes("application_packages")}
    if "ux_application_packages_job_id" not in existing_index_names:
        return
    with engine.begin() as conn:
        conn.execute(text('DROP INDEX "ux_application_packages_job_id"'))
    logger.info("Dropped superseded index ux_application_packages_job_id on application_packages")


def _replace_unique_job_indexes() -> None:
    """Drop pre-auth unique-on-job_id indexes so per-user composites can be created."""
    inspector = inspect(engine)
    swaps = (
        ("application_tracker", "ux_application_tracker_job_id"),
        ("interview_prep", "ux_interview_prep_job_id"),
    )
    for table_name, old_index in swaps:
        if table_name not in inspector.get_table_names():
            continue
        existing_index_names = {idx["name"] for idx in inspector.get_indexes(table_name)}
        if old_index not in existing_index_names:
            continue
        with engine.begin() as conn:
            conn.execute(text(f'DROP INDEX "{old_index}"'))
        logger.info("Dropped superseded index %s on %s", old_index, table_name)


def init_db() -> None:
    """Create the data directory, create any missing Day 1 tables, and add
    any columns/indexes missing from tables that already existed."""
    Path("data").mkdir(parents=True, exist_ok=True)
    Path("logs").mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
    _replace_application_packages_job_index()
    _replace_unique_job_indexes()
    _add_missing_indexes()
    logger.info("Database initialized with tables: %s", ", ".join(sorted(Base.metadata.tables)))


if __name__ == "__main__":
    init_db()
    print("Database ready at data/careerpilot.db")
