"""Showcase seed helper: isolated SQLite only, never an existing file."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from scripts.seed_showcase_demo import (
    CEDAR_DESCRIPTION,
    EXISTING_DESTINATION_MESSAGE,
    HARBORLINE_DESCRIPTION,
    SHOWCASE_COMPANY_PRIMARY,
    SHOWCASE_COMPANY_SECOND,
    SHOWCASE_EMAIL,
    SHOWCASE_NAME,
    SHOWCASE_RESUME_BANNER,
    SHOWCASE_SECOND_JOB,
    build_showcase_resume_pdf,
    refuse_database_path,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_seed(monkeypatch: pytest.MonkeyPatch, dest: Path) -> int:
    monkeypatch.setattr("sys.argv", ["seed_showcase_demo.py", "--database", str(dest)])
    from scripts import seed_showcase_demo

    return seed_showcase_demo.main()


def test_refuses_production_careerpilot_db(tmp_path: Path) -> None:
    production = Path("data/careerpilot.db")
    with pytest.raises(SystemExit, match="careerpilot.db"):
        refuse_database_path(production)


def test_refuses_forbidden_filename(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="production-looking"):
        refuse_database_path(tmp_path / "careerpilot.db")


def test_accepts_brand_new_temp_sqlite(tmp_path: Path) -> None:
    dest = tmp_path / "showcase.sqlite"
    assert not dest.exists()
    assert refuse_database_path(dest) == dest.resolve()


def test_refuses_random_existing_sqlite_without_modifying_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "my-real-user.sqlite"
    dest.write_bytes(b"not-a-careerpilot-database")
    digest = _sha256(dest)
    with pytest.raises(SystemExit, match="already exists"):
        refuse_database_path(dest)
    with pytest.raises(SystemExit, match="already exists"):
        _run_seed(monkeypatch, dest)
    assert dest.read_bytes() == b"not-a-careerpilot-database"
    assert _sha256(dest) == digest


def test_refuses_zero_byte_existing_sqlite_without_modifying_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "empty.sqlite"
    dest.write_bytes(b"")
    assert dest.stat().st_size == 0
    with pytest.raises(SystemExit, match="already exists"):
        _run_seed(monkeypatch, dest)
    assert dest.exists()
    assert dest.stat().st_size == 0
    assert dest.read_bytes() == b""


def test_refuses_existing_sqlite_with_unrelated_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "other-app.sqlite"
    conn = sqlite3.connect(dest)
    try:
        conn.execute("CREATE TABLE keep_me (id INTEGER PRIMARY KEY, note TEXT)")
        conn.execute("INSERT INTO keep_me (id, note) VALUES (42, 'untouched')")
        conn.commit()
    finally:
        conn.close()
    digest = _sha256(dest)
    with pytest.raises(SystemExit, match="already exists"):
        _run_seed(monkeypatch, dest)
    assert _sha256(dest) == digest
    conn = sqlite3.connect(dest)
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables == {"keep_me"}
        assert conn.execute("SELECT id, note FROM keep_me").fetchone() == (42, "untouched")
    finally:
        conn.close()


def test_refuses_existing_careerpilot_db_with_harmless_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "career.db"
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.core.security import hash_password
    from backend.db.database import Base
    from backend.db import models as _models  # noqa: F401
    from backend.db.models import User

    engine = create_engine(f"sqlite:///{dest.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    session = SessionLocal()
    try:
        session.add(
            User(email="real.user@example.com", hashed_password=hash_password("Not-The-Showcase-Pass-1!"))
        )
        session.commit()
        assert session.query(User).count() == 1
    finally:
        session.close()
        engine.dispose()
    digest = _sha256(dest)
    with pytest.raises(SystemExit, match="already exists"):
        _run_seed(monkeypatch, dest)
    assert _sha256(dest) == digest
    engine = create_engine(f"sqlite:///{dest.as_posix()}", future=True)
    SessionLocal = sessionmaker(bind=engine, future=True)
    session = SessionLocal()
    try:
        emails = {user.email for user in session.query(User).all()}
        assert emails == {"real.user@example.com"}
        assert SHOWCASE_EMAIL not in emails
    finally:
        session.close()
        engine.dispose()


def test_seed_creates_synthetic_user_on_brand_new_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "showcase.sqlite"
    assert not dest.exists()
    assert _run_seed(monkeypatch, dest) == 0
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.db.models import JobRecord, JobRequirementProfileRecord, User

    engine = create_engine(f"sqlite:///{dest.as_posix()}", future=True)
    SessionLocal = sessionmaker(bind=engine, future=True)
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.email == SHOWCASE_EMAIL).one()
        assert user.email == SHOWCASE_EMAIL
        jobs = session.query(JobRecord).all()
        assert {job.company for job in jobs} == {SHOWCASE_COMPANY_PRIMARY, SHOWCASE_COMPANY_SECOND}
        assert all("DEMO" in (job.description or "") or "example.com/showcase" in job.url for job in jobs)
        cedar = session.query(JobRecord).filter(JobRecord.public_id == SHOWCASE_SECOND_JOB).one()
        assert cedar.location == "Portland, OR"
        profile = (
            session.query(JobRequirementProfileRecord).filter(JobRequirementProfileRecord.job_id == cedar.id).one()
        )
        assert profile.profile_json.get("work_mode") == "hybrid"
        assert profile.profile_json.get("employment_type") == "internship"

        from backend.db.models import (
            ApplicationPackageRecord,
            Candidate,
            JobIntelligenceRecord,
            MatchScoreRecord,
            ResumeVersionRecord,
        )

        candidate = session.query(Candidate).filter(Candidate.user_id == user.id).one()
        assert candidate.name == SHOWCASE_NAME
        assert candidate.email == SHOWCASE_EMAIL
        skills = {str(item).lower() for item in (candidate.skills or [])}
        assert "python" in skills
        assert "docker" not in skills
        assert "aws" not in skills
        project_blob = json.dumps(candidate.projects or []).lower()
        assert "campus planner" in project_blob
        assert "fastapi" in project_blob or "fastapi" in skills
        experience_blob = json.dumps(candidate.experience or []).lower()
        assert "northstar labs" in experience_blob
        assert "28%" in experience_blob

        harborline = session.query(JobRecord).filter(JobRecord.company == SHOWCASE_COMPANY_PRIMARY).one()
        harbor_intel = (
            session.query(JobIntelligenceRecord).filter(JobIntelligenceRecord.job_id == harborline.id).one()
        )
        cedar_intel = session.query(JobIntelligenceRecord).filter(JobIntelligenceRecord.job_id == cedar.id).one()
        assert "Docker" not in (harbor_intel.required_skills or [])
        assert "Docker" in (harbor_intel.preferred_skills or [])
        assert "FastAPI" in (harbor_intel.required_skills or [])
        assert "Docker" in (cedar_intel.required_skills or [])
        assert "AWS" in (cedar_intel.required_skills or [])
        assert "docker" in CEDAR_DESCRIPTION.lower()
        assert "aws" in CEDAR_DESCRIPTION.lower()
        assert "fastapi" in HARBORLINE_DESCRIPTION.lower()

        scores = session.query(MatchScoreRecord).all()
        assert len(scores) == 2
        by_job = {row.job_id: row for row in scores}
        harbor_score = by_job[harborline.id]
        cedar_score = by_job[cedar.id]
        assert harbor_score.overall_score > cedar_score.overall_score
        harbor_matched = {item.lower() for item in (harbor_score.matched_skills or [])}
        harbor_missing = {item.lower() for item in (harbor_score.missing_skills or [])}
        cedar_missing = {item.lower() for item in (cedar_score.missing_skills or [])}
        assert "python" in harbor_matched
        assert "docker" in harbor_missing
        assert "docker" in cedar_missing
        assert "aws" in cedar_missing
        assert harbor_score.eligibility_status in {None, "eligibility_uncertain", "likely_eligible"}
        if harbor_score.eligibility_status == "likely_eligible":
            watchouts = " ".join(harbor_score.watchouts or []).lower()
            assert "authorization" in watchouts or "sponsorship" in watchouts

        package = session.query(ApplicationPackageRecord).one()
        assert package.approval_status == "approved"
        assert package.eligibility_confirmed is True
        assert package.grounded is True
        assert package.candidate_profile_fingerprint
        letter = package.cover_letter_draft or ""
        recruiter = package.recruiter_message or ""
        notes = " ".join(package.source_traceability_notes or []).lower()
        assert "I am applying using stored Python and SQL evidence." not in letter
        assert "Happy to discuss Python." not in recruiter
        assert "Harborline Analytics" in letter
        assert "Northstar Labs" in letter
        assert "Campus Planner" in letter
        assert "28%" in letter
        assert "Docker" not in letter or "not claiming" in letter.lower()
        assert "Harborline" in recruiter
        assert "illustrative seeded" in notes
        assert session.query(ResumeVersionRecord).count() == 1
    finally:
        session.close()
        engine.dispose()


def test_showcase_live_provider_calls_are_explicit_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import seed_showcase_demo

    monkeypatch.delenv("CAREERPILOT_SHOWCASE_LIVE", raising=False)
    assert seed_showcase_demo._should_try_live_providers() is False
    monkeypatch.setenv("CAREERPILOT_SHOWCASE_LIVE", "0")
    assert seed_showcase_demo._should_try_live_providers() is False
    monkeypatch.setenv("CAREERPILOT_SHOWCASE_LIVE", "1")
    # pytest is a hard guard: even explicit opt-in cannot make test runs call providers.
    assert seed_showcase_demo._should_try_live_providers() is False


def test_refuse_message_is_operator_actionable() -> None:
    assert "already exists" in EXISTING_DESTINATION_MESSAGE
    assert "delete" in EXISTING_DESTINATION_MESSAGE.lower()


def test_showcase_resume_pdf_is_labeled_synthetic_and_extractable() -> None:
    from backend.services.candidate_profile_agent import extract_resume_text

    pdf = build_showcase_resume_pdf()
    assert pdf.startswith(b"%PDF")
    extracted = extract_resume_text(pdf).text
    assert SHOWCASE_NAME in extracted
    assert SHOWCASE_EMAIL in extracted
    assert SHOWCASE_RESUME_BANNER in extracted
    assert "Northstar Labs" in extracted
    assert "Campus Planner" in extracted
    assert "Python" in extracted
    assert "FastAPI" in extracted
    assert "Docker" not in extracted
    assert "AWS" not in extracted
