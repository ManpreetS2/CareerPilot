"""Job discovery — DB-backed listing. Scouting/normalization/persistence
logic lives in job_scout_service.py; this module reads what's been stored."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from fastapi import HTTPException, status

from backend.db.database import SessionLocal
from backend.db.models import Candidate, JobRecord
from backend.schemas.schemas import Job, JobIntelligence
from backend.services.analysis_service import _candidate_work_modes, _city_state
from backend.services.application_tracker_service import latest_preference

logger = logging.getLogger(__name__)

# Must match Job.status's Literal in schemas.py. JobRecord.status is an
# unconstrained DB column (no CHECK constraint), so a row can in principle
# hold a value outside this set (manual edit, future writer, partial
# migration) — coalescing here means one bad row degrades to "flagged"
# instead of a Pydantic ValidationError taking down the whole jobs list.
_VALID_JOB_STATUSES = {"discovered", "verified", "flagged", "stale"}


def record_to_job(record: JobRecord) -> Job:
    job_status = record.status
    if job_status not in _VALID_JOB_STATUSES:
        logger.warning(
            "Job %s has out-of-domain status %r — coalescing to 'flagged'",
            record.public_id,
            job_status,
        )
        job_status = "flagged"

    return Job(
        id=record.public_id,
        title=record.title,
        company=record.company,
        location=record.location,
        salary=record.salary,
        url=record.url,
        description=record.description,
        source=record.source,
        date_posted=date.fromisoformat(record.date_posted) if record.date_posted else None,
        date_scraped=record.date_scraped,
        ats=record.ats,
        status=job_status,
        verification_notes=record.verification_notes,
        verified_at=record.verified_at,
    )


def list_jobs() -> list[Job]:
    with SessionLocal() as db:
        records = db.query(JobRecord).order_by(JobRecord.date_scraped.desc()).all()
        return [record_to_job(record) for record in records]


def get_job(job_id: str) -> Job:
    with SessionLocal() as db:
        record = db.query(JobRecord).filter(JobRecord.public_id == job_id).first()
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found")
        return record_to_job(record)


DEFAULT_SCOUT_QUERY = "software engineer intern"

# Bounds the cost of a scout run. Adzuna and Remotive are called once per
# role, so this is a direct multiplier on outbound requests. Three covers the
# realistic case (a candidate targeting a couple of adjacent titles) without
# letting a long preferences list turn one click into dozens of API calls.
MAX_SCOUT_QUERIES = 3

# Search terms go into an outbound query string. No real role title or place
# name approaches this, so it only ever truncates junk.
MAX_SEARCH_TERM_CHARS = 120


@dataclass(frozen=True)
class ScoutCriteria:
    """What a scout run should actually search for."""

    queries: list[str]
    location: str | None
    derived_from_preferences: bool


def clean_search_term(value: str) -> str:
    """Collapse internal whitespace and bound the length.

    These values are written straight into an outbound query string, so a
    5,000-character role produces a 5KB URL that proxies may reject outright
    and that no job board could match anyway. Collapsing whitespace also
    means "Cloud  Engineer" and "Cloud Engineer" dedupe against each other,
    and a role containing a stray newline searches for something sensible.
    """
    return " ".join(value.split())[:MAX_SEARCH_TERM_CHARS].strip()


def _deduped_roles(target_roles: object) -> list[str]:
    """Cleaned, case-insensitively deduped, order preserved."""
    if not isinstance(target_roles, list):
        return []
    seen: set[str] = set()
    roles: list[str] = []
    for entry in target_roles:
        # bool is an int, not a str, so it is excluded here along with
        # dicts, nested lists, and None — anything a hand-edited or
        # future-written preferences row might contain.
        if not isinstance(entry, str):
            continue
        role = clean_search_term(entry)
        if not role:
            continue
        key = role.lower()
        if key in seen:
            continue
        seen.add(key)
        roles.append(role)
    return roles


def _preferred_location(preference) -> str | None:
    """The first saved location that is actually a place.

    Reuses analysis_service's parser rather than adding a second one: scoring
    uses it to decide whether a job's location matches the candidate's, so
    discovery searching by something scoring would not recognize as a place
    would surface jobs it then penalizes. Entries like "Remote" are work
    modes, not locations, and are skipped here — the remote preference is
    handled separately below.
    """
    # If remote is acceptable at all, send no location. Adzuna's "where" is
    # the only place a location is used, and narrowing it to a city can only
    # remove remote listings the candidate would have taken — including ones
    # they are strictly more interested in than a far-away onsite role.
    # Searching broadly and letting _location_score rank the results loses
    # nothing; narrowing loses matches outright. Note this reads remote-ness
    # from _candidate_work_modes, which counts a "Remote" entry in
    # preferred_locations as well as an explicit remote_preference, so
    # ["Remote", "Austin, TX"] is treated as remote-capable.
    if "remote" in _candidate_work_modes(preference):
        return None

    locations = preference.preferred_locations
    if not isinstance(locations, list):
        return None
    for entry in locations:
        if isinstance(entry, str) and _city_state(entry) is not None:
            return clean_search_term(entry)
    return None


def derive_scout_criteria(db, user_id: int) -> ScoutCriteria:
    """Turn the user's saved preferences into what discovery should search.

    Falls back to the historic hardcoded query when the user has saved no
    usable target roles, so discovery keeps working for a brand-new account
    that has not filled anything in yet.
    """
    candidate = db.query(Candidate).filter(Candidate.user_id == user_id).first()
    preference = latest_preference(db, candidate, user_id)
    if preference is None:
        return ScoutCriteria([DEFAULT_SCOUT_QUERY], None, derived_from_preferences=False)

    roles = _deduped_roles(preference.target_roles)
    if not roles:
        # Preferences exist but name no role — still honor a saved location.
        return ScoutCriteria(
            [DEFAULT_SCOUT_QUERY], _preferred_location(preference), derived_from_preferences=False
        )

    return ScoutCriteria(
        roles[:MAX_SCOUT_QUERIES], _preferred_location(preference), derived_from_preferences=True
    )


def scout_jobs(queries: list[str] | None = None, location: str | None = None) -> list[Job]:
    # Deferred import: job_scout_service imports record_to_job from this module,
    # so the reverse import must happen at call time to avoid a circular import.
    from backend.services.job_scout_service import run_scout

    return run_scout(queries=queries or [DEFAULT_SCOUT_QUERY], location=location)


def mock_job_intelligence(job_id: str) -> JobIntelligence:
    get_job(job_id)
    return JobIntelligence(
        job_id=job_id,
        required_skills=["Python", "SQL", "REST APIs"],
        preferred_skills=["FastAPI", "Docker", "React"],
        years_experience=0,
        education_requirements=["Bachelor's in CS or equivalent intern experience"],
        tech_stack=["Python", "FastAPI", "PostgreSQL", "React"],
        seniority="intern",
        responsibilities=[
            "Implement API endpoints with tests",
            "Write SQL queries and small schema changes",
            "Collaborate in weekly sprint reviews",
        ],
        likely_interview_focus=["Python fundamentals", "SQL joins", "API design"],
    )
