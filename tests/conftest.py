"""Shared test fixtures for isolated SQLite sessions (never touch data/careerpilot.db)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Generator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.database import Base, get_db
from backend.main import app

# Capture once at import so restorations return to FastAPI's wrapped lifespan.
ORIGINAL_APP_LIFESPAN = app.router.lifespan_context


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
    """TestClient with isolated DB and a no-op lifespan (no production init_db)."""
    SessionLocal = sessionmaker(bind=isolated_engine, autocommit=False, autoflush=False)

    def _override_get_db() -> Generator[Session, None, None]:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    @asynccontextmanager
    async def _noop_lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield

    def _forbidden_init_db(*_args, **_kwargs):
        raise AssertionError("production init_db must not run during isolated API tests")

    previous_lifespan = app.router.lifespan_context
    app.dependency_overrides[get_db] = _override_get_db
    app.router.lifespan_context = _noop_lifespan

    try:
        with patch("backend.main.init_db", side_effect=_forbidden_init_db):
            with patch("backend.db.init_db.init_db", side_effect=_forbidden_init_db):
                with TestClient(app) as client:
                    yield client, SessionLocal
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.router.lifespan_context = previous_lifespan
        assert get_db not in app.dependency_overrides
        assert app.router.lifespan_context is previous_lifespan


_PRODUCTION_DB = Path(__file__).resolve().parents[1] / "data" / "careerpilot.db"


@pytest.fixture(scope="session", autouse=True)
def _never_touch_production_database() -> Generator[None, None, None]:
    existed = _PRODUCTION_DB.exists()
    before = _PRODUCTION_DB.stat().st_mtime if existed else None
    yield
    if not existed and _PRODUCTION_DB.exists():
        raise AssertionError("tests created data/careerpilot.db")
    if existed and _PRODUCTION_DB.exists() and _PRODUCTION_DB.stat().st_mtime != before:
        raise AssertionError("tests mutated data/careerpilot.db")


@pytest.fixture(autouse=True)
def _block_llm_generate_during_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*_args, **_kwargs):
        raise AssertionError("LLMClient.generate must not be called during automated tests")

    monkeypatch.setattr("backend.services.llm_client.LLMClient.generate", _blocked)
