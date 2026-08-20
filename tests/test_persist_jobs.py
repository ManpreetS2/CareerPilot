"""DB-backed tests for job_scout_service.persist_jobs, run against an
isolated in-memory SQLite engine (monkeypatched in) rather than the app's
real data/careerpilot.db — persist_jobs previously had zero test coverage."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.database import Base
from backend.db.models import JobRecord
from backend.schemas.schemas import Job
from backend.services import job_scout_service


@pytest.fixture
def isolated_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(job_scout_service, "SessionLocal", session_factory)
    return session_factory


def _job(**overrides) -> Job:
    defaults = dict(
        title="Software Engineer Intern",
        company="Acme",
        url="",
        description="Build things.",
        source="manual",
        date_scraped=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return Job(**defaults)


def test_two_blank_url_jobs_persist_as_two_separate_rows(isolated_db) -> None:
    job_a = _job(title="Job A", company="Acme", location="Remote")
    job_b = _job(title="Job B", company="Other Co", location="NYC")

    stored = job_scout_service.persist_jobs([job_a, job_b])

    assert len(stored) == 2
    assert {job.title for job in stored} == {"Job A", "Job B"}
    with isolated_db() as db:
        assert db.query(JobRecord).count() == 2


def test_rescout_does_not_clobber_known_salary_with_none(isolated_db) -> None:
    first = _job(url="https://example.com/jobs/1", salary="$40,000–$60,000")
    job_scout_service.persist_jobs([first])

    second = _job(url="https://example.com/jobs/1", salary=None)
    stored = job_scout_service.persist_jobs([second])

    assert len(stored) == 1
    assert stored[0].salary == "$40,000–$60,000"


def test_rescout_does_not_clobber_known_location_with_none(isolated_db) -> None:
    first = _job(url="https://example.com/jobs/2", location="San Francisco, CA")
    job_scout_service.persist_jobs([first])

    second = _job(url="https://example.com/jobs/2", location=None)
    stored = job_scout_service.persist_jobs([second])

    assert len(stored) == 1
    assert stored[0].location == "San Francisco, CA"


def test_rescout_still_applies_a_real_new_salary(isolated_db) -> None:
    first = _job(url="https://example.com/jobs/3", salary="$40,000")
    job_scout_service.persist_jobs([first])

    second = _job(url="https://example.com/jobs/3", salary="$55,000")
    stored = job_scout_service.persist_jobs([second])

    assert stored[0].salary == "$55,000"


def test_rescout_same_url_upserts_one_row_not_two(isolated_db) -> None:
    job_scout_service.persist_jobs([_job(url="https://example.com/jobs/4", title="v1")])
    job_scout_service.persist_jobs([_job(url="https://example.com/jobs/4", title="v2")])

    with isolated_db() as db:
        records = db.query(JobRecord).all()
        assert len(records) == 1
        assert records[0].title == "v2"
