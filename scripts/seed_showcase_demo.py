#!/usr/bin/env python3
"""Seed a synthetic CareerPilot showcase database. Never product runtime.

Requires an explicit SQLite file path that does not already exist. Refuses
data/careerpilot.db, other production-looking names, and any existing file
(including a previous showcase DB). Does not inspect an existing file to decide
it is “safe.” Prints DEMO credentials for local screenshot capture.

This script does not run on startup, does not delete files, and must not be
pointed at a real user's database. Fit scores are calculated by the production
scoring engine. Live resume parse / materials generation is attempted only when
a provider is configured and the process is not under pytest.
"""

from __future__ import annotations

import argparse
import io
import json
import os
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
SHOWCASE_PRIMARY_JOB = "showcase-harborline-intern"
SHOWCASE_SECOND_JOB = "showcase-cedar-backend"
SHOWCASE_COMPANY_PRIMARY = "Harborline Analytics"
SHOWCASE_COMPANY_SECOND = "Cedar & Pine Robotics"

SHOWCASE_RESUME_BANNER = (
    "SYNTHETIC DEMO RÉSUMÉ — fictional candidate for CareerPilot showcase. Not a real person."
)

SHOWCASE_PROFILE_PAYLOAD = {
    "name": SHOWCASE_NAME,
    "email": SHOWCASE_EMAIL,
    "phone": None,
    "skills": ["Python", "SQL", "FastAPI", "pytest", "Git"],
    "projects": [
        {
            "name": "Campus Planner",
            "description": (
                "Python and FastAPI service that uses SQL to schedule campus events. "
                "REST API for event CRUD with SQL storage for rooms and attendees; "
                "automated tests with pytest."
            ),
            "technologies": ["Python", "FastAPI", "SQL", "pytest"],
            "url": None,
        }
    ],
    "experience": [
        {
            "title": "Software Engineering Intern",
            "company": "Northstar Labs",
            "start_date": "2025-05",
            "end_date": "2025-08",
            "highlights": [
                "Built Python services for internal search APIs and reduced p95 latency by 28%.",
                "Wrote SQL queries and Python services that power intern-facing search.",
                "Added pytest coverage for the search API endpoints.",
            ],
        }
    ],
    "education": [
        {
            "institution": "State University",
            "degree": "B.S.",
            "field": "Computer Science",
            "graduation_year": "2027",
        }
    ],
    "certifications": [],
    "strengths": ["Backend APIs"],
    "evidence_links": [],
}

# Illustrative seeded materials for screenshots when live generation is unavailable.
SHOWCASE_COVER_LETTER = """Dear Harborline Analytics hiring team,

I am applying for the Software Engineer Intern role. At Northstar Labs I was a Software Engineering Intern on internal search APIs: I used Python to reduce p95 latency by 28% and wrote SQL for that same search work. I also built Campus Planner, a Python and FastAPI service that uses SQL to schedule campus events.

Harborline's posting asks for Python, SQL, and FastAPI on internal APIs and tests, which matches that stored experience. My profile does not include Docker, so I am not claiming it.

I would welcome the chance to contribute to Harborline's intern engineering work this summer.

Jordan Avery
B.S. Computer Science, State University (2027)"""

SHOWCASE_RECRUITER_MESSAGE = (
    "Hi Harborline recruiting — I'm Jordan Avery, a CS student at State University (B.S., 2027). "
    "I interned at Northstar Labs on Python search APIs (28% p95 latency reduction) and wrote SQL "
    "there, and I built Campus Planner with Python, FastAPI, and SQL. I'd like to be considered "
    "for the Software Engineer Intern role."
)

SHOWCASE_BULLETS = [
    "Built Python APIs at Northstar Labs as Software Engineering Intern and reduced p95 latency by 28%.",
    "Wrote SQL queries and Python services for internal search APIs at Northstar Labs.",
    "Built Campus Planner with Python, FastAPI, and SQL for campus event scheduling.",
]

SHOWCASE_TRACE_NOTES = [
    "Illustrative seeded materials — not produced by the live generation workflow.",
    "Python and 28% p95 latency <- Northstar Labs Software Engineering Intern highlights",
    "SQL <- Northstar Labs highlights and Campus Planner technologies",
    "Campus Planner / FastAPI <- candidate projects",
    "Docker is not claimed; it is not on the stored résumé.",
]

EXISTING_DESTINATION_MESSAGE = (
    "Showcase destination already exists. Choose a new temporary path or "
    "explicitly delete the old showcase file first."
)

_FORBIDDEN_NAMES = {
    "careerpilot.db",
    "careerpilot-prod.db",
    "production.db",
}

HARBORLINE_DESCRIPTION = """
DEMO / SYNTHETIC posting. Not a real employer endorsement. Harborline Analytics is a
fictional company used only for CareerPilot product demonstration.

Harborline Analytics is hiring a Software Engineer Intern for Summer 2027. This is a
remote internship. Interns work with mentors on small, well-scoped backend tickets
for internal analytics tools used by the intern engineering group.

About the role
You will help build internal analytics APIs and tests. The team uses Python services,
SQL reporting, and FastAPI for intern-facing tools. Prior cloud deployment experience
is not required for this internship.

Required:
- Python
- SQL
- FastAPI

Preferred:
- Docker
- pytest
- Git

Responsibilities
- Build internal analytics APIs and tests
- Write SQL queries for intern reporting dashboards
- Add automated tests for API endpoints

This internship is remote. Docker is a plus for local development, not a requirement.
Harborline does not list work-authorization, sponsorship, GPA, or citizenship rules
on this synthetic posting.

Harborline Analytics is not a real employer. This text exists so CareerPilot can
demonstrate résumé-to-job Fit against a complete fictional intern posting with
enough stored description for a full-content snapshot.
""".strip()

CEDAR_DESCRIPTION = """
DEMO / SYNTHETIC posting. Not a real employer endorsement. Cedar & Pine Robotics is a
fictional company used only for CareerPilot product demonstration.

Cedar & Pine Robotics is hiring a Backend Software Engineering Intern, Platform
Reliability for Summer 2027. This is a hybrid internship based in Portland, OR.
Interns help operate intern platform services that already run in containers.

About the role
You will help deploy and operate intern backend services. This posting expects
container and cloud deployment experience in addition to Python. Kubernetes is a
plus. The team does not treat SQL as a required skill for this reliability intern
seat.

Required:
- Python
- Docker
- AWS

Preferred:
- Kubernetes
- Git

Responsibilities
- Deploy services to cloud with Docker
- Operate containerized backend services on AWS
- Help debug intern platform reliability issues

This internship is hybrid in Portland, OR. Cedar & Pine Robotics does not list
work-authorization, sponsorship, GPA, or citizenship rules on this synthetic posting.

Cedar & Pine Robotics is not a real employer. This text exists so CareerPilot can
demonstrate a partial Fit when required Docker and AWS evidence is missing from
the stored résumé, using a complete fictional intern posting.
""".strip()


def refuse_database_path(path: Path) -> Path:
    """Reject production-looking names and any path that already exists.

    Existence is fail-closed: zero-byte files, valid SQLite, CareerPilot DBs,
    and leftover showcase files are all refused. This function must not open
    the destination with SQLAlchemy.
    """
    resolved = path.expanduser().resolve()
    if resolved == PRODUCTION_DATABASE:
        raise SystemExit("Refusing data/careerpilot.db. Showcase seed is isolated SQLite only.")
    if resolved.name.lower() in _FORBIDDEN_NAMES:
        raise SystemExit(f"Refusing production-looking database name: {resolved.name}")
    if "careerpilot.db" in resolved.as_posix().lower() and resolved.parent.name == "data":
        raise SystemExit("Refusing a database under data/ named like the production file.")
    if resolved.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
        raise SystemExit("Showcase database must be a .db/.sqlite/.sqlite3 file.")
    if resolved.exists():
        raise SystemExit(EXISTING_DESTINATION_MESSAGE)
    return resolved


def _xml_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_showcase_resume_pdf() -> bytes:
    """Polished fictional internship résumé, labeled synthetic, extractable as text."""
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("ShowcaseTitle", parent=styles["Title"], fontSize=18, spaceAfter=4)
    banner = ParagraphStyle(
        "ShowcaseBanner",
        parent=styles["Normal"],
        fontSize=9,
        textColor="#6b4f00",
        spaceAfter=10,
    )
    heading = ParagraphStyle("ShowcaseHeading", parent=styles["Heading2"], fontSize=12, spaceBefore=12, spaceAfter=4)
    subhead = ParagraphStyle("ShowcaseSubhead", parent=styles["Heading4"], fontSize=10, spaceBefore=6, spaceAfter=2)
    body = ParagraphStyle("ShowcaseBody", parent=styles["BodyText"], fontSize=10, leading=13)

    def p(text: str, style: ParagraphStyle = body) -> Paragraph:
        return Paragraph(_xml_escape(text), style)

    story = [
        p(SHOWCASE_NAME, title),
        p("Software engineering intern candidate · demo.candidate@example.com"),
        p(SHOWCASE_RESUME_BANNER, banner),
        p("Education", heading),
        p("State University — B.S. Computer Science", subhead),
        p("Expected graduation: May 2027. Coursework: Data Structures, Databases, Web Services."),
        p("Experience", heading),
        p("Software Engineering Intern — Northstar Labs", subhead),
        p("May 2025 – August 2025"),
        p("- Built Python services for internal search APIs and reduced p95 latency by 28%."),
        p("- Wrote SQL queries and Python services that power intern-facing search."),
        p("- Added pytest coverage for the search API endpoints."),
        Spacer(1, 8),
        p("Projects", heading),
        p("Campus Planner", subhead),
        p(
            "Python and FastAPI service that uses SQL to schedule campus events. "
            "REST API for event CRUD with SQL storage for rooms and attendees; "
            "automated tests with pytest. Technologies: Python, FastAPI, SQL, pytest."
        ),
        p("Skills", heading),
        p("Python, SQL, FastAPI, pytest, Git"),
        p("Backend APIs"),
        Spacer(1, 12),
        p(SHOWCASE_RESUME_BANNER, banner),
    ]
    doc.build(story)
    return buffer.getvalue()


def _under_pytest() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


def _should_try_live_providers() -> bool:
    if _under_pytest():
        return False
    if os.environ.get("CAREERPILOT_SHOWCASE_LIVE", "").strip() == "0":
        return False
    from backend.services.llm_provider_sequence import (
        configured_provider_names,
        resume_provider_is_configured,
        resume_provider_names,
    )

    resume_ready = any(resume_provider_is_configured(name) for name in resume_provider_names())
    materials_ready = bool(configured_provider_names())
    return resume_ready or materials_ready


def _faithful_profile_generate(_prompt: str, _system: str | None) -> str:
    return json.dumps(SHOWCASE_PROFILE_PAYLOAD)


def _parse_showcase_resume(session, user_id: int):
    from backend.db.models import Candidate
    from backend.services.candidate_profile_agent import (
        ProfileExtractionError,
        build_candidate_profile_from_upload,
    )
    from backend.services.llm_client import LLMConfigurationError, LLMProviderError

    pdf_bytes = build_showcase_resume_pdf()
    parse_source = "injected_faithful_extract"
    kwargs = {
        "filename": "jordan-avery-synthetic-resume.pdf",
        "content": pdf_bytes,
        "db": session,
        "user_id": user_id,
        "content_type": "application/pdf",
    }

    if _should_try_live_providers():
        try:
            build_candidate_profile_from_upload(**kwargs)
            parse_source = "live_provider"
        except (ProfileExtractionError, LLMConfigurationError, LLMProviderError, Exception):
            build_candidate_profile_from_upload(**kwargs, generate_fn=_faithful_profile_generate)
            parse_source = "injected_faithful_extract"
    else:
        build_candidate_profile_from_upload(**kwargs, generate_fn=_faithful_profile_generate)

    candidate = session.query(Candidate).filter(Candidate.user_id == user_id).one()
    candidate.name = SHOWCASE_NAME
    candidate.email = SHOWCASE_EMAIL
    candidate.phone = None
    session.commit()
    session.refresh(candidate)
    if not (candidate.skills or candidate.projects or candidate.experience):
        raise SystemExit("Showcase resume parse produced no grounded evidence.")
    return candidate, parse_source


def _insert_intelligence(
    session,
    job,
    *,
    required: list[str],
    preferred: list[str],
    tech_stack: list[str],
    responsibilities: list[str],
    interview: list[str],
) -> None:
    from backend.db.models import JobIntelligenceRecord
    from backend.services.extraction_task import INTELLIGENCE_EXTRACTION_VERSION
    from backend.services.job_content import source_fingerprint

    session.add(
        JobIntelligenceRecord(
            job_id=job.id,
            required_skills=list(required),
            preferred_skills=list(preferred),
            years_experience=0,
            education_requirements=["Bachelor's in Computer Science or related field"],
            tech_stack=list(tech_stack),
            seniority="intern",
            responsibilities=list(responsibilities),
            likely_interview_focus=list(interview),
            source_fingerprint=source_fingerprint(job.title, job.description),
            extraction_version=INTELLIGENCE_EXTRACTION_VERSION,
        )
    )
    session.commit()


def _score_job(session, job, user_id: int):
    from backend.services.job_requirement_extractor import extract_requirement_profile
    from backend.services.verified_fit_service import score_job_verified

    extract_requirement_profile(session, job, force=True)
    session.commit()
    session.refresh(job)
    return score_job_verified(session, job, user_id)


def _store_seeded_package(session, intern, user_id: int, candidate) -> None:
    from backend.db.models import ApplicationPackageRecord
    from backend.services.candidate_provenance import fingerprint_for_candidate

    fingerprint = fingerprint_for_candidate(session, candidate, user_id)
    existing = (
        session.query(ApplicationPackageRecord)
        .filter(
            ApplicationPackageRecord.job_id == intern.id,
            ApplicationPackageRecord.user_id == user_id,
        )
        .first()
    )
    if existing is None:
        existing = ApplicationPackageRecord(
            job_id=intern.id,
            user_id=user_id,
            candidate_id=candidate.id,
        )
        session.add(existing)
    existing.candidate_id = candidate.id
    existing.tailored_bullets = list(SHOWCASE_BULLETS)
    existing.cover_letter_draft = SHOWCASE_COVER_LETTER
    existing.recruiter_message = SHOWCASE_RECRUITER_MESSAGE
    existing.source_traceability_notes = list(SHOWCASE_TRACE_NOTES)
    existing.approval_status = "pending_review"
    existing.grounded = True
    existing.grounding_override = False
    existing.candidate_profile_fingerprint = fingerprint
    session.commit()


def _seed_materials(session, intern, user_id: int, candidate) -> tuple[object, str]:
    from backend.db.models import ApplicationPackageRecord
    from backend.schemas.schemas import ApprovalRequest
    from backend.services.application_materials_agent import (
        ApplicationMaterialsGroundingError,
        ApplicationMaterialsParseError,
        MissingJobIntelligenceError,
        generate_grounded_application_materials,
    )
    from backend.services.application_service import apply_approval
    from backend.services.llm_client import LLMConfigurationError, LLMProviderError

    materials_source = "seeded_illustrative"
    if _should_try_live_providers():
        try:
            generate_grounded_application_materials(session, intern.public_id, user_id)
            materials_source = "live_generation"
        except (
            ApplicationMaterialsGroundingError,
            ApplicationMaterialsParseError,
            MissingJobIntelligenceError,
            LLMConfigurationError,
            LLMProviderError,
            Exception,
        ):
            materials_source = "seeded_illustrative"

    if materials_source != "live_generation":
        _store_seeded_package(session, intern, user_id, candidate)

    apply_approval(
        session,
        intern.public_id,
        user_id,
        ApprovalRequest(
            decision="approved",
            eligibility_confirmed=True,
            eligibility_notes="DEMO synthetic eligibility confirmation.",
        ),
    )
    package = (
        session.query(ApplicationPackageRecord)
        .filter(
            ApplicationPackageRecord.job_id == intern.id,
            ApplicationPackageRecord.user_id == user_id,
        )
        .one()
    )
    return package, materials_source


def _seed(session) -> dict[str, str]:
    from backend.core.security import hash_password
    from backend.db.models import (
        ApplicationEventRecord,
        ApplicationTrackerRecord,
        JobRecord,
        SavedJobRecord,
        User,
    )
    from backend.services.resume_version_service import create_resume_version
    from tests.mvp_helpers import insert_target_preference

    existing = session.query(User).filter(User.email == SHOWCASE_EMAIL).first()
    if existing is not None:
        raise SystemExit(f"Showcase user already exists in this database: {SHOWCASE_EMAIL}")

    user = User(email=SHOWCASE_EMAIL, hashed_password=hash_password(SHOWCASE_PASSWORD))
    session.add(user)
    session.commit()
    session.refresh(user)

    candidate, parse_source = _parse_showcase_resume(session, user.id)
    insert_target_preference(
        session,
        user_id=user.id,
        candidate_id=candidate.id,
        target_roles=["Software Engineer Intern"],
        preferred_locations=["Remote"],
        work_mode_preferences=["remote", "hybrid"],
        currently_enrolled_in_program="yes",
        expected_graduation="2027-05",
        degree_pursuing="B.S. Computer Science",
        academic_year="junior",
    )

    intern = JobRecord(
        public_id=SHOWCASE_PRIMARY_JOB,
        title="Software Engineer Intern",
        company=SHOWCASE_COMPANY_PRIMARY,
        location="Remote",
        salary=None,
        url="https://example.com/showcase/harborline-intern",
        description=HARBORLINE_DESCRIPTION,
        source="manual",
        status="verified",
        ats=None,
    )
    cedar = JobRecord(
        public_id=SHOWCASE_SECOND_JOB,
        title="Backend Software Engineering Intern, Platform Reliability",
        company=SHOWCASE_COMPANY_SECOND,
        location="Portland, OR",
        salary=None,
        url="https://example.com/showcase/cedar-backend",
        description=CEDAR_DESCRIPTION,
        source="manual",
        status="verified",
    )
    session.add_all([intern, cedar])
    session.commit()

    _insert_intelligence(
        session,
        intern,
        required=["Python", "SQL", "FastAPI"],
        preferred=["Docker", "pytest", "Git"],
        tech_stack=["Python", "SQL", "FastAPI"],
        responsibilities=[
            "Build internal analytics APIs and tests",
            "Write SQL queries for intern reporting dashboards",
            "Add automated tests for API endpoints",
        ],
        interview=["Python fundamentals", "SQL", "FastAPI"],
    )
    _insert_intelligence(
        session,
        cedar,
        required=["Python", "Docker", "AWS"],
        preferred=["Kubernetes", "Git"],
        tech_stack=["Python", "Docker", "AWS"],
        responsibilities=[
            "Deploy services to cloud with Docker",
            "Operate containerized backend services on AWS",
            "Help debug intern platform reliability issues",
        ],
        interview=["Python fundamentals", "Docker", "AWS"],
    )

    harborline_score = _score_job(session, intern, user.id)
    cedar_score = _score_job(session, cedar, user.id)
    package, materials_source = _seed_materials(session, intern, user.id, candidate)
    create_resume_version(session, intern.public_id, user.id)

    session.add(SavedJobRecord(user_id=user.id, job_id=intern.id))
    session.add(SavedJobRecord(user_id=user.id, job_id=cedar.id))
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
            job_id=cedar.id,
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
        ("saved", cedar.id),
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
        "parse_source": parse_source,
        "materials_source": materials_source,
        "harborline_overall": str(harborline_score.overall_score),
        "cedar_overall": str(cedar_score.overall_score),
        "harborline_matched": ",".join(harborline_score.matched_skills or []),
        "harborline_missing": ",".join(harborline_score.missing_skills or []),
        "cedar_matched": ",".join(cedar_score.matched_skills or []),
        "cedar_missing": ",".join(cedar_score.missing_skills or []),
        "harborline_eligibility": str(harborline_score.eligibility_status or ""),
        "cedar_eligibility": str(cedar_score.eligibility_status or ""),
        "harborline_kind": str(harborline_score.score_kind or ""),
        "cedar_kind": str(cedar_score.score_kind or ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        required=True,
        type=Path,
        help="New isolated SQLite path. Must not already exist. Must not be data/careerpilot.db.",
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
    print(f"parse_source={summary['parse_source']}")
    print(f"materials_source={summary['materials_source']}")
    print(
        f"harborline_fit={summary['harborline_overall']} "
        f"kind={summary['harborline_kind']} eligibility={summary['harborline_eligibility']}"
    )
    print(f"harborline_matched={summary['harborline_matched']}")
    print(f"harborline_missing={summary['harborline_missing']}")
    print(
        f"cedar_fit={summary['cedar_overall']} "
        f"kind={summary['cedar_kind']} eligibility={summary['cedar_eligibility']}"
    )
    print(f"cedar_matched={summary['cedar_matched']}")
    print(f"cedar_missing={summary['cedar_missing']}")
    print("Fit percentage is qualification/preference alignment from Fit V2, not a hire or ATS probability.")
    print("Not a real candidate. Not a real employer. Do not use production databases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
