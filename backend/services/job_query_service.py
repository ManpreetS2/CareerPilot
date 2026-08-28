"""Server-side Jobs query. Filters allowlisted intent fields in Python over stored rows.

Never compiles LLM/output into SQL. Catalog size is hundreds of rows, not millions.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.db.models import JobRecord, JobRequirementProfileRecord
from backend.schemas.schemas import JobListItem, JobListPage, MatchScore
from backend.services.analysis_service import list_stored_match_scores
from backend.services.job_listing_metadata import JobListingMetadata, resolve_job_listing_metadata
from backend.services.job_posting_time import discovery_datetime, job_posting_datetime
from backend.services.job_search_parser import JobSearchIntent, JobsTab, SortMode
from backend.services.job_service import record_to_job
from backend.services.opportunity_type import matches_opportunity_filter
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


def _text_blob(job: JobRecord) -> str:
    return f"{job.title} {job.company} {job.location or ''} {job.description or ''}".lower()


def _location_matches(location_text: str, wanted: list[str]) -> bool:
    loc = location_text.lower()
    for label in wanted:
        key = label.lower()
        if key in loc:
            return True
        if "bay area" in key and any(city in loc for city in _BAY_CITIES):
            return True
        if key in {"new york"} and any(token in loc for token in ("new york", "nyc", "manhattan", "brooklyn")):
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


def _experience_matches(meta: JobListingMetadata, levels: list[str]) -> bool:
    current = (meta.experience_level or "").lower()
    emp = (meta.employment_type or "").lower()
    for level in levels:
        if current == level:
            return True
        if level == "intern" and emp == "internship":
            return True
        if level == "new_grad" and emp == "new_grad":
            return True
        if level in {"entry", "junior"} and current in {"entry", "junior"}:
            return True
    return False


def _sort_key(
    item: JobListItem,
    sort: SortMode,
    posted_at: datetime | None,
    discovered_at: datetime | None,
) -> tuple:
    match = item.match
    if sort == "newest":
        posted_ts = posted_at.timestamp() if posted_at is not None else 0.0
        discovered_ts = discovered_at.timestamp() if discovered_at is not None else 0.0
        return (1 if posted_at is not None else 0, posted_ts, discovered_ts)
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
    profiles = {row.job_id: row for row in db.query(JobRequirementProfileRecord).all()}
    wanted_opportunity = opportunity or (intent.opportunity_types[0] if len(intent.opportunity_types) == 1 else None)
    cutoff = _posted_cutoff(intent.date_posted)
    items: list[tuple[JobListItem, datetime | None, datetime | None]] = []

    for record in records:
        profile_row = profiles.get(record.id)
        meta = resolve_job_listing_metadata(record, profile_row)
        job = record_to_job(record, profile_row)
        job.saved = record.id in saved_ids
        match: MatchScore | None = scores.get(job.id or "")
        posted_at = job_posting_datetime(record.date_posted, record.date_scraped)
        discovered_at = discovery_datetime(record.date_scraped)

        if tab == "saved" and not job.saved:
            continue
        if tab == "matches" and match is None:
            continue
        if wanted_opportunity in {"internship", "role"}:
            if not matches_opportunity_filter(job.opportunity_type or "unknown", wanted_opportunity):
                continue
        if intent.employment_types and job.employment_type not in intent.employment_types:
            continue
        if intent.work_modes and meta.work_mode not in intent.work_modes:
            continue
        if intent.locations and not _location_matches(meta.location_text, intent.locations):
            continue
        if intent.industries:
            blob = _text_blob(record)
            if not any(item.lower() in blob for item in intent.industries):
                continue
        search_bits = [*(intent.roles or []), intent.query or ""]
        tokens = _role_match_tokens(search_bits)
        if tokens:
            if not any(token in meta.role_text for token in tokens):
                continue
        if intent.experience_levels and not _experience_matches(meta, intent.experience_levels):
            continue
        if cutoff:
            if posted_at is None or posted_at < cutoff:
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

        items.append((JobListItem(job=job, match=match, saved=job.saved), posted_at, discovered_at))

    items.sort(key=lambda pair: _sort_key(pair[0], sort, pair[1], pair[2]), reverse=True)
    ranked = [pair[0] for pair in items]
    verified_count = sum(1 for item in ranked if item.match and item.match.score_kind == "verified")
    potential_count = sum(1 for item in ranked if item.match is None or item.match.score_kind != "verified")
    if tab == "matches":
        verified = [item for item in ranked if item.match and item.match.score_kind == "verified"]
        potential = [item for item in ranked if not item.match or item.match.score_kind != "verified"]
        ranked = [*verified, *potential]
        potential_count = len(potential)
        verified_count = len(verified)

    total = len(ranked)
    start = (page - 1) * size
    page_items = ranked[start : start + size]
    return JobListPage(
        items=page_items,
        total=total,
        page=page,
        page_size=size,
        verified_count=verified_count,
        potential_count=potential_count,
        ids=[item.job.id for item in ranked if item.job.id],
    )
