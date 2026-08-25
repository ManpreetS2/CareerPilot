"""Job Verification — "still open" checks, suspicious-posting heuristics, and
the discovered/verified/flagged/stale status lifecycle. Owned by Developer B (Day 3).

Every check here is a heuristic, not a guarantee. Uncertain or unreachable
postings get flagged for human review rather than silently dropped or marked
verified — the whole point is surfacing doubt, not resolving it automatically.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException, status as http_status

from backend.core.config import settings
from backend.db.database import SessionLocal
from backend.db.models import JobRecord
from backend.schemas.schemas import Job
from backend.services.job_scout_service import MANUAL_INGEST_PLACEHOLDER_DESCRIPTION
from backend.services.job_service import record_to_job
from backend.services.url_safety import UnsafeURLError, fetch_url_safely

logger = logging.getLogger(__name__)

DEFAULT_STALE_AFTER_DAYS = 45

# Phrases a job board shows on an expired/filled/removed posting. Checked as
# case-insensitive substrings of the fetched page body.
CLOSED_POSTING_PHRASES = (
    "no longer accepting applications",
    "position has been filled",
    "this job is no longer available",
    "job posting has expired",
    "this posting has expired",
    "posting has closed",
    "no longer active",
    "applications are now closed",
    "this position is closed",
    "job not found",
    "page not found",
    "position has been closed",
)

# Phrases strongly associated with job-scam postings (upfront payment,
# off-platform payment collection, reshipping/mule schemes). Flags, never
# auto-rejects — legitimate postings should not trip these.
SCAM_PATTERN_PHRASES = (
    "wire transfer",
    "western union",
    "moneygram",
    "processing fee",
    "registration fee",
    "application fee",
    "pay to apply",
    "starter kit fee",
    "purchase your own equipment before starting",
    "reshipping",
    "reship packages",
    "cash the check",
    "cash this check",
    "buy gift cards",
    "gift cards to",
    "telegram only",
    "whatsapp only",
    "no interview necessary",
    "guaranteed income",
    "send us your bank details",
)

MIN_DESCRIPTION_LENGTH = 40

_GENERIC_REACH_FAILURE = (
    "Could not reach the posting URL to verify whether it is still live."
)


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": settings.http_user_agent},
        timeout=settings.http_timeout_seconds,
        follow_redirects=True,
    )


def detect_suspicious_signals(job: Job) -> list[str]:
    """Flag data-quality and scam-pattern red flags. Pure function, no I/O."""
    reasons: list[str] = []

    if not job.company or job.company.strip().lower() == "unknown":
        reasons.append("Company name is missing or unverified.")

    description = (job.description or "").strip()
    if not description or len(description) < MIN_DESCRIPTION_LENGTH:
        reasons.append("Description is missing or too short to evaluate.")
    elif description == MANUAL_INGEST_PLACEHOLDER_DESCRIPTION:
        reasons.append("Description was never extracted — manually added URL needs review.")

    haystack = f"{job.title} {job.description}".lower()
    matched = [phrase for phrase in SCAM_PATTERN_PHRASES if phrase in haystack]
    if matched:
        reasons.append(f"Contains common scam-posting language: {', '.join(matched)}.")

    return reasons


def check_staleness(job: Job, max_age_days: int = DEFAULT_STALE_AFTER_DAYS) -> bool:
    """True if the posting's date_posted is older than max_age_days. Pure function."""
    if not job.date_posted:
        return False
    age_days = (datetime.now(timezone.utc).date() - job.date_posted).days
    return age_days > max_age_days


def check_still_open(url: str) -> tuple[bool | None, str]:
    """Lightweight liveness check for a posting URL.

    Returns (True, reason) if it looks live, (False, reason) if it looks
    closed/gone, or (None, reason) if we genuinely can't tell (network error,
    or the site blocked automated access — common on major ATS platforms and
    not itself a sign the job is closed).
    """
    if not url:
        return None, "No URL to verify."

    # fetch_url_safely, not the plain _client() below: this URL was already
    # stored (via manual ingestion or a scout provider), but re-fetching it
    # here is server-side just the same — an unsafe target (private/loopback/
    # link-local, or a redirect into one) must stay "uncertain", never a
    # crash, so is_open is never inferred from a request that never happened.
    try:
        response = fetch_url_safely(
            url, user_agent=settings.http_user_agent, timeout_seconds=settings.http_timeout_seconds
        )
    except UnsafeURLError as exc:
        return None, f"Posting URL is not safe to verify: {exc}"
    except httpx.HTTPError:
        return None, _GENERIC_REACH_FAILURE

    if response.status_code in (404, 410):
        return False, f"Posting URL returned HTTP {response.status_code} (not found/gone)."
    if response.status_code in (401, 403, 429):
        return None, f"Posting URL blocked automated access (HTTP {response.status_code})."
    if response.status_code >= 500:
        return None, f"Posting site returned a server error (HTTP {response.status_code})."

    body_lower = response.text.lower()
    for phrase in CLOSED_POSTING_PHRASES:
        if phrase in body_lower:
            return False, f'Posting page text suggests it\'s closed ("{phrase}").'

    return True, "Posting URL responded normally with no closed-posting language detected."


def _decide_verification(
    *,
    suspicious: list[str],
    is_open: bool | None,
    open_check_reason: str,
    stale_by_age: bool,
    max_age_days: int = DEFAULT_STALE_AFTER_DAYS,
) -> tuple[str, str]:
    """Merge signals into a final (status, notes) pair. Pure function — the
    core decision logic, kept separate from I/O so it's directly testable.

    Priority: suspicious content > confirmed closed > uncertain (flag, don't
    silently drop) > stale-by-age > verified.
    """
    if suspicious:
        return "flagged", "Flagged for review: " + " ".join(suspicious)

    if is_open is False:
        if stale_by_age:
            return "stale", f"{open_check_reason} Also posted over {max_age_days} days ago."
        return "stale", open_check_reason

    if is_open is None:
        if stale_by_age:
            return "stale", f"{open_check_reason} Also posted over {max_age_days} days ago."
        return "flagged", f"Could not confirm posting is still live: {open_check_reason}"

    # is_open is True
    if stale_by_age:
        return "stale", f"Posting responded normally, but was posted over {max_age_days} days ago."
    return "verified", "Posting looks live and well-formed; no red flags detected."


def verify_job(job: Job, max_age_days: int = DEFAULT_STALE_AFTER_DAYS) -> tuple[str, str]:
    """Run every check for one job and return (status, notes)."""
    suspicious = detect_suspicious_signals(job)
    # Suspicious postings short-circuit before the network call — no reason to
    # spend the request, and the reason stays specific to what tripped it.
    if suspicious:
        return "flagged", "Flagged for review: " + " ".join(suspicious)

    is_open, reason = check_still_open(job.url)
    stale_by_age = check_staleness(job, max_age_days)
    return _decide_verification(
        suspicious=suspicious,
        is_open=is_open,
        open_check_reason=reason,
        stale_by_age=stale_by_age,
        max_age_days=max_age_days,
    )


def verify_and_store(job_id: str) -> Job:
    """Verify one job by public_id and persist the resulting status/notes."""
    with SessionLocal() as db:
        record = db.query(JobRecord).filter(JobRecord.public_id == job_id).first()
        if record is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found"
            )

        job = record_to_job(record)
        new_status, notes = verify_job(job)

        record.status = new_status
        record.verification_notes = notes
        record.verified_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(record)
        return record_to_job(record)


def verify_all(status_filter: str | None = "discovered") -> list[Job]:
    """Verify every job matching status_filter (default: only newly
    discovered ones). Pass None to re-verify every job in the DB.

    Reads the candidate jobs, closes that session, then runs every (slow,
    network-bound) verify_job check before opening a second, short-lived
    session to write the results in one batch. Deliberately not one session
    held open across N sequential HTTP checks — on SQLite that turns a bulk
    verify into a multi-minute write-transaction, raising the odds a
    concurrent scout/ingest request hits "database is locked" while it runs.
    """
    with SessionLocal() as db:
        query = db.query(JobRecord)
        if status_filter:
            query = query.filter(JobRecord.status == status_filter)
        jobs_to_verify = [(record.public_id, record_to_job(record)) for record in query.all()]

    verified_at = None
    results_by_id: dict[str, tuple[str, str]] = {}
    for public_id, job in jobs_to_verify:
        results_by_id[public_id] = verify_job(job)

    if not results_by_id:
        return []

    verified_at = datetime.now(timezone.utc)
    with SessionLocal() as db:
        records = db.query(JobRecord).filter(JobRecord.public_id.in_(results_by_id.keys())).all()
        results: list[Job] = []
        for record in records:
            new_status, notes = results_by_id[record.public_id]
            record.status = new_status
            record.verification_notes = notes
            record.verified_at = verified_at
            results.append(record_to_job(record))
        db.commit()
        return results
