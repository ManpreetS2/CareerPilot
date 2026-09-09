#!/usr/bin/env python3
"""Seed a synthetic CareerPilot showcase database. Never product runtime.

Requires an explicit SQLite file path. Refuses data/careerpilot.db and other
production-looking paths. Prints DEMO credentials for local screenshot capture.

This script does not run on startup, does not call live providers, and must not
be pointed at a real user's database.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PRODUCTION_DATABASE = (ROOT / "data" / "careerpilot.db").resolve()

SHOWCASE_EMAIL = "demo.candidate@example.com"
SHOWCASE_PASSWORD = "Showcase-Demo-Pass-1!"
SHOWCASE_NAME = "Jordan Avery"

_FORBIDDEN_NAMES = {
    "careerpilot.db",
    "careerpilot-prod.db",
    "production.db",
}


def refuse_database_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == PRODUCTION_DATABASE:
        raise SystemExit("Refusing data/careerpilot.db. Showcase seed is isolated SQLite only.")
    if resolved.name.lower() in _FORBIDDEN_NAMES:
        raise SystemExit(f"Refusing production-looking database name: {resolved.name}")
    if "careerpilot.db" in resolved.as_posix().lower() and resolved.parent.name == "data":
        raise SystemExit("Refusing a database under data/ named like the production file.")
    if resolved.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
        raise SystemExit("Showcase database must be a .db/.sqlite/.sqlite3 file.")
    return resolved


def _seed(session) -> dict[str, str]:
    from backend.core.security import hash_password
    from backend.db.models import (
        ApplicationEventRecord,
        ApplicationTrackerRecord,
        JobRecord,
        SavedJobRecord,
        User,
    )
    from backend.schemas.schemas import ApprovalRequest
    from backend.services.analysis_service import score_job
    from backend.services.application_service import apply_approval
    from backend.services.resume_version_service import create_resume_version
    from tests.mvp_helpers import (
        insert_candidate,
        insert_grounded_package,
        insert_intelligence,
        insert_target_preference,
    )

    existing = session.query(User).filter(User.email == SHOWCASE_EMAIL).first()
    if existing is not None:
        raise SystemExit(f"Showcase user already exists in this database: {SHOWCASE_EMAIL}")

    user = User(email=SHOWCASE_EMAIL, hashed_password=hash_password(SHOWCASE_PASSWORD))
    session.add(user)
    session.commit()
    session.refresh(user)

    candidate = insert_candidate(session, user_id=user.id)
    candidate.name = SHOWCASE_NAME
    candidate.email = SHOWCASE_EMAIL
    candidate.phone = None
    session.commit()
    insert_target_preference(
        session,
        user_id=user.id,
        candidate_id=candidate.id,
        target_roles=["Software Engineer Intern"],
        preferred_locations=["Remote"],
    )

    intern = JobRecord(
        public_id="showcase-harborline-intern",
        title="Software Engineer Intern",
        company="Harborline Analytics",
        location="Remote",
        salary=None,
        url="https://example.com/showcase/harborline-intern",
        description=(
            "DEMO / SYNTHETIC posting. Required: Python and SQL. Preferred: Docker. "
            "Build internal APIs and tests. Not a real employer endorsement."
        ),
        source="manual",
        status="verified",
        ats=None,
    )
    long_title = JobRecord(
        public_id="showcase-cedar-backend",
        title="Backend Software Engineering Intern, Platform Reliability",
        company="Cedar & Pine Robotics",
        location="Hybrid — Portland, OR",
        salary=None,
        url="https://example.com/showcase/cedar-backend",
        description=(
            "DEMO / SYNTHETIC posting. Required: Python. Preferred: SQL. "
            "Not a real employer endorsement."
        ),
        source="manual",
        status="verified",
    )
    session.add_all([intern, long_title])
    session.commit()
    insert_intelligence(session, intern)
    insert_intelligence(session, long_title)

    score_job(session, intern.public_id, user.id)
    score_job(session, long_title.public_id, user.id)

    package = insert_grounded_package(session, intern, candidate=candidate, user_id=user.id)
    apply_approval(
        session,
        intern.public_id,
        user.id,
        ApprovalRequest(
            decision="approved",
            eligibility_confirmed=True,
            eligibility_notes="DEMO synthetic eligibility confirmation.",
        ),
    )
    create_resume_version(session, intern.public_id, user.id)

    session.add(SavedJobRecord(user_id=user.id, job_id=intern.id))
    session.add(SavedJobRecord(user_id=user.id, job_id=long_title.id))
    now = datetime.now(timezone.utc)
    session.add(
        ApplicationTrackerRecord(
            job_id=intern.id,
            user_id=user.id,
            status="ready_to_apply",
            status_note="DEMO: approved materials; human still presses Submit.",
            reminder_date=date.today() + timedelta(days=7),
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        ApplicationTrackerRecord(
            job_id=long_title.id,
            user_id=user.id,
            status="saved",
            status_note="DEMO synthetic tracker row.",
            created_at=now,
            updated_at=now,
        )
    )
    events = [
        ("saved", intern.id),
        ("materials_generated", intern.id),
        ("materials_approved", intern.id),
        ("saved", long_title.id),
    ]
    for event_type, job_pk in events:
        session.add(
            ApplicationEventRecord(
                job_id=job_pk,
                user_id=user.id,
                event_type=event_type,
                occurred_at=now,
            )
        )
    session.commit()

    return {
        "email": SHOWCASE_EMAIL,
        "password": SHOWCASE_PASSWORD,
        "name": SHOWCASE_NAME,
        "primary_job": intern.public_id,
        "package_status": package.approval_status,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        required=True,
        type=Path,
        help="Isolated SQLite path. Must not be data/careerpilot.db.",
    )
    args = parser.parse_args()
    dest = refuse_database_path(args.database)
    dest.parent.mkdir(parents=True, exist_ok=True)

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.db.database import Base
    from backend.db import models as _models  # noqa: F401

    engine = create_engine(f"sqlite:///{dest.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
    session = SessionLocal()
    try:
        summary = _seed(session)
    finally:
        session.close()
        engine.dispose()

    print("DEMO / SYNTHETIC DATA")
    print(f"database={dest}")
    print(f"DATABASE_URL=sqlite:///{dest.as_posix()}")
    print(f"email={summary['email']}")
    print(f"password={summary['password']}")
    print(f"primary_job={summary['primary_job']}")
    print("Not a real candidate. Not a real employer. Do not use production databases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
