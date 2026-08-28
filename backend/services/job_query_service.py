"""Server-side Jobs query. Filters allowlisted intent fields in Python over stored rows.

Never compiles LLM/output into SQL. Catalog size is hundreds of rows, not millions.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

from sqlalchemy.orm import Session

from backend.db.models import JobRecord, JobRequirementProfileRecord
from backend.schemas.schemas import JobListItem, JobListPage, MatchScore
from backend.services.analysis_service import list_stored_match_scores
from backend.services.job_posting_time import job_posting_datetime
from backend.services.job_search_parser import JobSearchIntent, JobsTab, SortMode
from backend.services.job_service import record_to_job
from backend.services.opportunity_type import (
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
    return job_posting_datetime(job.date_posted, job.date_scraped)


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

_TITLE_INTERN = re.compile(r"\bintern(?:s|ship)?\b", re.I)
_TITLE_NEW_GRAD = re.compile(r"\bnew[\s-]?grad(?:uate)?s?\b", re.I)
_TITLE_JUNIOR = re.compile(
    r"\b(?:junior|jr\.?|entry[\s-]?level|(?:software\s+)?(?:engineer|developer)\s+(?:i|1))\b",
    re.I,
)
_OCCUPATION = (
    r"(?:software\s+)?(?:engineer|developer|scientist|architect|designer|"
    r"product(?:\s+manager)?|manager|analyst|researcher|consultant|specialist)"
)
_EXPERIENCE_TITLE = {
    "senior": re.compile(rf"\b(?:senior|sr\.?)\s+{_OCCUPATION}", re.I),
    "staff": re.compile(rf"\bstaff\s+{_OCCUPATION}", re.I),
    "lead": re.compile(rf"\blead\s+{_OCCUPATION}", re.I),
    "principal": re.compile(rf"\bprincipal\s+{_OCCUPATION}", re.I),
    "mid": re.compile(r"\b(?:mid[\s-]?level|mid[\s-]?career)\b", re.I),
    "manager": re.compile(r"\b(?:engineering\s+)?manager\b", re.I),
}


def _profile_dict(profile_json: object) -> dict:
    return profile_json if isinstance(profile_json, dict) else {}


def _canonical_location_text(job: JobRecord, profile_json: object) -> str:
    parts = [job.location or ""]
    profile = _profile_dict(profile_json)
    remote_scope = profile.get("remote_scope")
    if remote_scope:
        parts.append(str(remote_scope))
    for loc in profile.get("locations") or []:
        if isinstance(loc, dict):
            parts.append(str(loc.get("label") or ""))
        elif isinstance(loc, str):
            parts.append(loc)
    return " ".join(parts).lower()


def _canonical_role_text(job: JobRecord, profile_json: object) -> str:
    parts = [job.title or ""]
    profile = _profile_dict(profile_json)
    parts.append(str(profile.get("role_title") or ""))
    parts.append(str(profile.get("role_family") or ""))
    return " ".join(parts).lower()


def _location_matches(job: JobRecord, wanted: list[str], profile_json: object = None) -> bool:
    loc = _canonical_location_text(job, profile_json)
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


def _experience_matches(
    job: JobRecord,
    employment_type: str | None,
    levels: list[str],
    profile_json: object = None,
) -> bool:
    title = (job.title or "").lower()
    emp = (employment_type or "").lower()
    profile_level = str(_profile_dict(profile_json).get("experience_level") or "").lower()
    for level in levels:
        if level == "intern":
            if emp == "internship" or profile_level == "intern" or _TITLE_INTERN.search(title):
                return True
            continue
        if level == "new_grad":
            if emp == "new_grad" or profile_level == "new_grad" or _TITLE_NEW_GRAD.search(title):
                return True
            continue
        if level in {"entry", "junior"}:
            if profile_level in {"entry", "junior"} or _TITLE_JUNIOR.search(title):
                return True
            continue
        if profile_level == level:
            return True
        pattern = _EXPERIENCE_TITLE.get(level)
        if pattern is not None and pattern.search(job.title or ""):
            return True
    return False


def _work_mode_for(job: JobRecord, profile_json: dict | None) -> str:
    if isinstance(profile_json, dict):
        mode = profile_json.get("work_mode")
        if mode in {"remote", "hybrid", "onsite"}:
            return mode
    return infer_work_mode(job.title, job.description, job.location)


def _sort_key(item: JobListItem, sort: SortMode, posted_at: datetime | None) -> tuple:
    match = item.match
    if sort == "newest":
        stamp = posted_at.timestamp() if posted_at is not None else 0.0
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
    items: list[tuple[JobListItem, datetime | None]] = []

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
        if intent.locations and not _location_matches(record, intent.locations, profiles.get(record.id)):
            continue
        if intent.industries:
            blob = _text_blob(record)
            if not any(item.lower() in blob for item in intent.industries):
                continue
        search_bits = [*(intent.roles or []), intent.query or ""]
        tokens = _role_match_tokens(search_bits)
        if tokens:
            role_text = _canonical_role_text(record, profiles.get(record.id))
            if not any(token in role_text for token in tokens):
                continue
        if intent.experience_levels and not _experience_matches(
            record, job.employment_type, intent.experience_levels, profiles.get(record.id)
        ):
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

        items.append((JobListItem(job=job, match=match, saved=job.saved), _job_datetime(record)))

    items.sort(key=lambda pair: _sort_key(pair[0], sort, pair[1]), reverse=True)
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
