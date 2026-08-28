"""Server-side Jobs query. Filters allowlisted intent fields in Python over stored rows.

Never compiles LLM/output into SQL. Catalog size is hundreds of rows, not millions.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.db.models import JobRecord, JobRequirementProfileRecord
from backend.schemas.schemas import JobListItem, JobListPage, MatchScore
from backend.services.analysis_service import list_stored_match_scores
from backend.services.job_search_parser import JobSearchIntent, JobsTab, SortMode
from backend.services.job_service import record_to_job
from backend.services.opportunity_type import (
    INTERNSHIP_EMPLOYMENT,
    infer_work_mode,
    matches_opportunity_filter,
)
from backend.services.saved_job_service import list_saved_job_ids

DEFAULT_PAGE_SIZE = 40
MAX_PAGE_SIZE = 50


def _posted_cutoff(window: str | None) -> datetime | None:
    if not window:
        return None
    now = datetime.now(timezone.utc)
    mapping = {
        "past_24h": timedelta(hours=24),
        "past_3d": timedelta(days=3),
        "past_7d": timedelta(days=7),
        "past_14d": timedelta(days=14),
        "past_30d": timedelta(days=30),
    }
    delta = mapping.get(window)
    return now - delta if delta else None


def _job_datetime(job: JobRecord) -> datetime | None:
    if job.date_scraped is not None:
        value = job.date_scraped
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if job.date_posted:
        try:
            parsed = datetime.fromisoformat(job.date_posted[:10])
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _text_blob(job: JobRecord) -> str:
    return f"{job.title} {job.company} {job.location or ''} {job.description or ''}".lower()


_BAY_CITIES = (
    "san francisco",
    "oakland",
    "berkeley",
    "palo alto",
    "mountain view",
    "san jose",
    "sunnyvale",
    "cupertino",
    "bay area",
)


def _location_matches(job: JobRecord, wanted: list[str]) -> bool:
    loc = (job.location or "").lower()
    blob = _text_blob(job)
    for label in wanted:
        key = label.lower()
        if key in loc or key in blob:
            return True
        if "bay area" in key and any(city in loc or city in blob for city in _BAY_CITIES):
            return True
        if key in {"new york"} and any(token in loc or token in blob for token in ("new york", "nyc", "manhattan", "brooklyn")):
            return True
    return False


def _role_match_tokens(bits: list[str]) -> list[str]:
    tokens: list[str] = []
    for bit in bits:
        value = bit.strip().lower()
        if not value:
            continue
        tokens.append(value)
        if "engineering" in value:
            tokens.append(value.replace("engineering", "engineer"))
        if "engineer" in value and "engineering" not in value:
            tokens.append(value.replace("engineer", "engineering"))
    return tokens


def _experience_matches(job: JobRecord, employment_type: str | None, levels: list[str]) -> bool:
    blob = _text_blob(job)
    emp = (employment_type or "").lower()
    for level in levels:
        needle = level.replace("_", " ")
        if level == "intern" and (emp in INTERNSHIP_EMPLOYMENT or "intern" in blob):
            return True
        if level == "new_grad" and (emp == "new_grad" or "new grad" in blob or "new-grad" in blob):
            return True
        if needle in blob or level in blob:
            return True
    return False


def _work_mode_for(job: JobRecord, profile_json: dict | None) -> str:
    if isinstance(profile_json, dict):
        mode = profile_json.get("work_mode")
        if mode in {"remote", "hybrid", "onsite"}:
            return mode
    return infer_work_mode(job.title, job.description)


def _sort_key(item: JobListItem, sort: SortMode) -> tuple:
    match = item.match
    job = item.job
    if sort == "newest":
        stamp = job.date_scraped.timestamp() if job.date_scraped else 0.0
        return (stamp,)
    if sort == "qualification":
        value = match.qualification_score if match and match.qualification_score is not None else -1
        return (1 if match and match.score_kind == "verified" else 0, value)
    if sort == "preference":
        value = match.preference_score if match and match.preference_score is not None else -1
        return (1 if match and match.score_kind == "verified" else 0, value)
    rank = match.ranking_score if match and match.ranking_score is not None else -1
    verified = 1 if match and match.score_kind == "verified" else 0
    return (verified, rank)


def query_jobs(
    db: Session,
    user_id: int,
    intent: JobSearchIntent,
    *,
    tab: JobsTab = "discover",
    opportunity: str | None = None,
    sort: SortMode = "best_match",
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> JobListPage:
    size = min(max(page_size, 1), MAX_PAGE_SIZE)
    page = max(page, 1)
    records = db.query(JobRecord).all()
    scores = {item.job_id: item for item in list_stored_match_scores(db, user_id)}
    saved_ids = list_saved_job_ids(db, user_id)
    profiles = {
        row.job_id: row.profile_json
        for row in db.query(JobRequirementProfileRecord).all()
        if row.profile_json
    }
    wanted_opportunity = opportunity or (intent.opportunity_types[0] if len(intent.opportunity_types) == 1 else None)
    cutoff = _posted_cutoff(intent.date_posted)
    items: list[JobListItem] = []

    for record in records:
        job = record_to_job(record)
        job.saved = record.id in saved_ids
        mode = _work_mode_for(record, profiles.get(record.id))
        job.work_mode = mode  # type: ignore[assignment]
        match: MatchScore | None = scores.get(job.id or "")

        if tab == "saved" and not job.saved:
            continue
        if tab == "matches" and match is None:
            continue
        if wanted_opportunity in {"internship", "role"}:
            if not matches_opportunity_filter(job.opportunity_type or "unknown", wanted_opportunity):
                continue
        if intent.employment_types and job.employment_type not in intent.employment_types:
            continue
        if intent.work_modes and mode not in intent.work_modes:
            continue
        if intent.locations and not _location_matches(record, intent.locations):
            continue
        if intent.industries:
            blob = _text_blob(record)
            if not any(item.lower() in blob for item in intent.industries):
                continue
        search_bits = [*(intent.roles or []), intent.query or ""]
        tokens = _role_match_tokens(search_bits)
        if tokens:
            blob = _text_blob(record)
            if not any(token in blob for token in tokens):
                continue
        if intent.experience_levels and not _experience_matches(record, job.employment_type, intent.experience_levels):
            continue
        if cutoff:
            when = _job_datetime(record)
            if when is None or when < cutoff:
                continue
        if intent.verified_state == "verified" and (match is None or match.score_kind != "verified"):
            continue
        if intent.verified_state == "potential" and match is not None and match.score_kind == "verified":
            continue
        if intent.eligibility_state != "all":
            if match is None or match.eligibility_status != intent.eligibility_state:
                continue
        if intent.confidence_state != "all":
            if match is None or match.confidence_level != intent.confidence_state:
                continue

        items.append(JobListItem(job=job, match=match, saved=job.saved))

    items.sort(key=lambda item: _sort_key(item, sort), reverse=True)
    verified_count = sum(1 for item in items if item.match and item.match.score_kind == "verified")
    potential_count = sum(1 for item in items if item.match is None or item.match.score_kind != "verified")
    if tab == "matches":
        verified = [item for item in items if item.match and item.match.score_kind == "verified"]
        potential = [item for item in items if not item.match or item.match.score_kind != "verified"]
        items = [*verified, *potential]
        potential_count = len(potential)
        verified_count = len(verified)

    total = len(items)
    start = (page - 1) * size
    page_items = items[start : start + size]
    return JobListPage(
        items=page_items,
        total=total,
        page=page,
        page_size=size,
        verified_count=verified_count,
        potential_count=potential_count,
        ids=[item.job.id for item in items if item.job.id],
    )
