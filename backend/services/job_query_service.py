"""Server-side Jobs query. Filters allowlisted intent fields in Python over stored rows.

Never compiles LLM/output into SQL. Catalog size is hundreds of rows, not millions.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.db.models import JobRecord, JobRequirementProfileRecord
from backend.schemas.schemas import JobListItem, JobListPage, MatchScore
from backend.services.analysis_service import list_stored_match_scores
from backend.services.job_listing_metadata import JobListingMetadata, resolve_job_listing_metadata
from backend.services.job_posting_time import (
    cutoff_for_date_posted_window,
    discovery_datetime,
    parse_posting_time,
    posting_in_window,
)
from backend.services.job_search_parser import JobSearchIntent, JobsTab, SortMode
from backend.services.job_service import record_to_job
from backend.services.opportunity_type import matches_opportunity_filter
from backend.services.saved_job_service import list_saved_job_ids

DEFAULT_PAGE_SIZE = 40
MAX_PAGE_SIZE = 50

_TOKEN_RE = re.compile(r"[a-z0-9]+")

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

# Token/boundary matching for USPS abbreviations. Not a geocoder.
_US_STATE_NAMES = {
    "al": "alabama",
    "ak": "alaska",
    "az": "arizona",
    "ar": "arkansas",
    "ca": "california",
    "co": "colorado",
    "ct": "connecticut",
    "de": "delaware",
    "fl": "florida",
    "ga": "georgia",
    "hi": "hawaii",
    "id": "idaho",
    "il": "illinois",
    "in": "indiana",
    "ia": "iowa",
    "ks": "kansas",
    "ky": "kentucky",
    "la": "louisiana",
    "me": "maine",
    "md": "maryland",
    "ma": "massachusetts",
    "mi": "michigan",
    "mn": "minnesota",
    "ms": "mississippi",
    "mo": "missouri",
    "mt": "montana",
    "ne": "nebraska",
    "nv": "nevada",
    "nh": "new hampshire",
    "nj": "new jersey",
    "nm": "new mexico",
    "ny": "new york",
    "nc": "north carolina",
    "nd": "north dakota",
    "oh": "ohio",
    "ok": "oklahoma",
    "or": "oregon",
    "pa": "pennsylvania",
    "ri": "rhode island",
    "sc": "south carolina",
    "sd": "south dakota",
    "tn": "tennessee",
    "tx": "texas",
    "ut": "utah",
    "vt": "vermont",
    "va": "virginia",
    "wa": "washington",
    "wv": "west virginia",
    "wi": "wisconsin",
    "wy": "wyoming",
    "dc": "district of columbia",
}
_US_NAME_TO_ABBR = {name: abbr for abbr, name in _US_STATE_NAMES.items()}


def _text_blob(job: JobRecord) -> str:
    return f"{job.title} {job.company} {job.location or ''} {job.description or ''}".lower()


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _has_phrase(tokens: list[str], phrase: str) -> bool:
    parts = _tokens(phrase)
    if not parts:
        return False
    n = len(parts)
    return any(tokens[i : i + n] == parts for i in range(len(tokens) - n + 1))


def _matches_bay_area(loc: str) -> bool:
    return any(city in loc for city in _BAY_CITIES)


def _matches_new_york_city(tokens: list[str], loc: str) -> bool:
    return (
        "nyc" in tokens
        or _has_phrase(tokens, "new york")
        or "manhattan" in tokens
        or "brooklyn" in tokens
        or "new york" in loc
    )


def _matches_san_francisco(tokens: list[str], loc: str) -> bool:
    return "sf" in tokens or _has_phrase(tokens, "san francisco") or "san francisco" in loc


def _matches_state_abbrev(tokens: list[str], abbrev: str) -> bool:
    name = _US_STATE_NAMES[abbrev]
    return abbrev in tokens or _has_phrase(tokens, name)


def _one_location_matches(loc: str, tokens: list[str], key: str) -> bool:
    if not key:
        return False
    if "bay area" in key and _matches_bay_area(loc):
        return True
    if key in {"ny"}:
        return "ny" in tokens or _matches_new_york_city(tokens, loc)
    if key in {"nyc", "new york"}:
        return _matches_new_york_city(tokens, loc)
    if key in {"sf", "san francisco"}:
        return _matches_san_francisco(tokens, loc)
    if key in _US_STATE_NAMES:
        return _matches_state_abbrev(tokens, key)
    if key in _US_NAME_TO_ABBR:
        return _matches_state_abbrev(tokens, _US_NAME_TO_ABBR[key]) or key in loc
    if len(key) <= 2:
        return key in tokens
    return key in loc


def _location_matches(location_text: str, wanted: list[str]) -> bool:
    loc = location_text.lower()
    tokens = _tokens(loc)
    return any(_one_location_matches(loc, tokens, label.lower().strip()) for label in wanted)


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
    now: datetime | None = None,
) -> JobListPage:
    size = min(max(page_size, 1), MAX_PAGE_SIZE)
    page = max(page, 1)
    if now is None:
        clock = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        clock = now.replace(tzinfo=timezone.utc)
    else:
        clock = now.astimezone(timezone.utc)
    records = db.query(JobRecord).all()
    scores = {item.job_id: item for item in list_stored_match_scores(db, user_id)}
    saved_ids = list_saved_job_ids(db, user_id)
    profiles = {row.job_id: row for row in db.query(JobRequirementProfileRecord).all()}
    wanted_opportunity = opportunity or (intent.opportunity_types[0] if len(intent.opportunity_types) == 1 else None)
    cutoff = cutoff_for_date_posted_window(intent.date_posted, clock)
    items: list[tuple[JobListItem, datetime | None, datetime | None]] = []

    for record in records:
        profile_row = profiles.get(record.id)
        meta = resolve_job_listing_metadata(record, profile_row)
        job = record_to_job(record, profile_row)
        job.saved = record.id in saved_ids
        match: MatchScore | None = scores.get(job.id or "")
        posting = parse_posting_time(record.date_posted, now=clock)
        posted_at = posting.value if posting else None
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
            if posting is None or not posting_in_window(posting, cutoff, clock):
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
