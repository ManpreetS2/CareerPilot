"""SQLAlchemy engine, session, and declarative base."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.core.config import settings


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


def _connect_args(url: str) -> dict[str, bool]:
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


def enable_sqlite_foreign_keys(target_engine) -> None:
    """Enforce declared FK relationships on every new SQLite connection.

    This is a per-connection PRAGMA, not a database-file setting, so it must
    run on every new DBAPI connection rather than once at startup. Call this
    on any SQLite engine that should reject orphaned rows, including test
    fixtures — production enforcement is meaningless if the test suite runs
    against an engine that never applies it.
    """
    if not str(target_engine.url).startswith("sqlite"):
        return

    @event.listens_for(target_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


engine = create_engine(
    settings.database_url,
    connect_args=_connect_args(settings.database_url),
    future=True,
)
enable_sqlite_foreign_keys(engine)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
