"""Shared test fixtures for isolated SQLite sessions (never touch data/careerpilot.db)."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.database import Base, get_db
from backend.main import app


@pytest.fixture
def isolated_engine():
    """Per-test in-memory SQLite engine with tables created."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def isolated_session(isolated_engine) -> Generator[Session, None, None]:
    SessionLocal = sessionmaker(bind=isolated_engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def isolated_client(isolated_engine) -> Generator[tuple[TestClient, sessionmaker], None, None]:
    """TestClient with get_db overridden to the isolated engine."""
    SessionLocal = sessionmaker(bind=isolated_engine, autocommit=False, autoflush=False)

    def _override_get_db() -> Generator[Session, None, None]:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as client:
            yield client, SessionLocal
    finally:
        app.dependency_overrides.pop(get_db, None)
