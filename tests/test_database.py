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
from backend.db.models import (
    ApplicationEventRecord,
    JobRecord,
    SavedSearchMatchRecord,
    SavedSearchRecord,
    User,
    UserSession,
)
from backend.services.account_deletion import delete_user_account


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


def test_delete_user_account_does_not_orphan_saved_search_or_event_rows() -> None:
    """Regression test: delete_user_account must clean up SavedSearchRecord,
    SavedSearchMatchRecord, and ApplicationEventRecord before deleting the
    User row, or a real (foreign-key-enforcing) engine raises IntegrityError
    on the final DELETE FROM users and account deletion breaks for any user
    who ever saved a search or triggered an analytics event (e.g. saved a
    job)."""
    engine = create_engine("sqlite://", future=True)
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(bind=engine)
    try:
        with Session(engine) as session:
            user = User(email="fk-delete@example.com", hashed_password="x")
            session.add(user)
            session.commit()
            session.refresh(user)

            job = JobRecord(
                public_id="fk-delete-job-1",
                title="Backend Engineering Intern",
                company="Acme",
                url="https://example.com/jobs/1",
                description="A role.",
                source="manual",
            )
            session.add(job)
            session.commit()
            session.refresh(job)

            session.add(
                ApplicationEventRecord(job_id=job.id, user_id=user.id, event_type="saved")
            )
            search = SavedSearchRecord(
                user_id=user.id, label="Backend intern roles", query_text="backend engineer intern"
            )
            session.add(search)
            session.commit()
            session.refresh(search)
            session.add(SavedSearchMatchRecord(saved_search_id=search.id, job_id=job.id))
            session.commit()

            user_id = user.id
            delete_user_account(session, user)

            assert session.query(User).filter(User.id == user_id).first() is None
            assert session.query(ApplicationEventRecord).count() == 0
            assert session.query(SavedSearchRecord).count() == 0
            assert session.query(SavedSearchMatchRecord).count() == 0
    finally:
        engine.dispose()
