"""Create SQLite tables for CareerPilot AI."""

from __future__ import annotations

import logging
from pathlib import Path

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


def init_db() -> None:
    """Create the data directory and all Day 1 tables if they do not exist."""
    Path("data").mkdir(parents=True, exist_ok=True)
    Path("logs").mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized with tables: %s", ", ".join(sorted(Base.metadata.tables)))


if __name__ == "__main__":
    init_db()
    print("Database ready at data/careerpilot.db")
