"""Job Scout — Adzuna + RemoteOK discovery, manual URL ingestion, normalization,
deduplication, and SQLite persistence. Owned by Developer B (Day 2).
"""

from __future__ import annotations

import html
import logging
import re
import uuid
from datetime import date, datetime, timezone
from urllib.parse import urlparse, urlunparse

import httpx

from backend.core.config import settings
from backend.db.database import SessionLocal
from backend.db.models import JobRecord
from backend.schemas.schemas import Job
from backend.services.job_service import record_to_job
from backend.services.url_safety import fetch_url_safely

logger = logging.getLogger(__name__)

ADZUNA_SEARCH_URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/1"
REMOTEOK_URL = "https://remoteok.com/api"

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_DESCRIPTION_RE = re.compile(
    r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', re.IGNORECASE
)
_WHITESPACE_RE = re.compile(r"\s+")
_BLOCK_BOUNDARY_RE = re.compile(r"</(p|div|li|ul|ol|h[1-6])\s*>|<br\s*/?>", re.IGNORECASE)
_ANY_TAG_RE = re.compile(r"<[^>]+>")

# Placeholder used when a manually-ingested URL has no extractable meta
# description. Exported so job_verification_service can recognize it as
# "not actually a description" rather than judging it on length alone.
MANUAL_INGEST_PLACEHOLDER_DESCRIPTION = (
    "Manually added via job URL. Description not auto-extracted — verify and edit."
)


def _fix_mojibake(text: str) -> str:
    """Recover text double-encoded as UTF-8 (RemoteOK does this — an en-dash
    comes through as "â€“"). Round-tripping through latin1 undoes it; falls
    back to the original string if that round-trip fails, which is what
    happens harmlessly for text that was never double-encoded."""
    try:
        return text.encode("latin1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def _clean_line(value: str | None) -> str:
    """Fix mojibake, unescape HTML entities, and collapse whitespace for a
    single-line field.

    Some sources (RemoteOK) return HTML-escaped text even in plain JSON string
    fields, e.g. company "Larsen &amp; Toubro" — unescape before display.
    """
    if not value:
        return ""
    return _WHITESPACE_RE.sub(" ", html.unescape(_fix_mojibake(value))).strip()


def _clean_description(value: str | None) -> str:
    """Strip HTML markup from a job description into readable plain text.

    RemoteOK descriptions are HTML fragments (<strong>, <ul><li>, <br>); the
    frontend renders description as plain text, so raw tags would otherwise
    show up literally instead of rendering.
    """
    if not value:
        return ""
    text = html.unescape(_fix_mojibake(value))
    text = _BLOCK_BOUNDARY_RE.sub("\n", text)
    text = _ANY_TAG_RE.sub("", text)
    text = html.unescape(text)
    lines = [_WHITESPACE_RE.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


class JobScoutError(RuntimeError):
    """Raised when a job source can't be reached, isn't configured, or returns nothing usable."""


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": settings.http_user_agent},
        timeout=settings.http_timeout_seconds,
        follow_redirects=True,
    )


def scout_adzuna(query: str, location: str | None = None) -> list[dict]:
    """Call Adzuna's job search API and return raw listing dicts."""
    if not settings.adzuna_app_id or not settings.adzuna_app_key:
        raise JobScoutError(
            "Adzuna is not configured. Add ADZUNA_APP_ID and ADZUNA_APP_KEY to .env "
            "(free signup at https://developer.adzuna.com/)."
        )
    params = {
        "app_id": settings.adzuna_app_id,
        "app_key": settings.adzuna_app_key,
        "results_per_page": settings.scout_results_per_source,
        "what": query,
        "content-type": "application/json",
    }
    if location:
        params["where"] = location
    url = ADZUNA_SEARCH_URL.format(country=settings.adzuna_country)
    try:
        with _client() as client:
            response = client.get(url, params=params)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise JobScoutError(f"Adzuna request failed: {exc}") from exc
    return response.json().get("results", [])


def scout_remoteok(query: str | None = None) -> list[dict]:
    """Pull RemoteOK's public listings feed and return raw listing dicts."""
    try:
        with _client() as client:
            response = client.get(REMOTEOK_URL)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise JobScoutError(f"RemoteOK request failed: {exc}") from exc

    payload = response.json()
    # RemoteOK's first array element is a legal notice, not a job — every real
    # listing carries an "id", so filter on that rather than slicing [1:].
    listings = [item for item in payload if isinstance(item, dict) and item.get("id")]

    if query:
        # Any-word (not exact-phrase) match: a literal "software engineer intern"
        # substring almost never appears verbatim in a title and returned zero
        # results in testing. Title only, not tags — RemoteOK's "tags" field is
        # noisy in practice (e.g. an unrelated "Store Manager" listing carrying
        # an "engineer" tag), so matching against it produces false positives.
        words = [w for w in query.lower().split() if w]
        listings = [
            item for item in listings if any(w in (item.get("position") or "").lower() for w in words)
        ]
    return listings[: settings.scout_results_per_source]


# Free-tier ATS platforms where the subdomain is a fixed platform word
# ("boards", "jobs") and the real company is the URL's first path segment
# instead — the opposite of the Workday-style pattern (company.wd5....) that
# the plain subdomain guess below handles correctly.
_ATS_PATH_COMPANY_HOSTS = ("greenhouse.io", "lever.co")


def _guess_company(url: str) -> str:
    """Best-effort company name guessed from a job posting URL."""
    parsed = urlparse(url)
    host = parsed.netloc.removeprefix("www.")
    if not host:
        return "Unknown"

    if any(host == ats or host.endswith(f".{ats}") for ats in _ATS_PATH_COMPANY_HOSTS):
        segment = next((part for part in parsed.path.split("/") if part), "")
        if segment:
            return segment.replace("-", " ").title()

    return host.split(".")[0].replace("-", " ").title()


def ingest_job_url(url: str) -> dict:
    """Fetch a single job posting URL and return a best-effort raw record.

    The free feed has no scraper for arbitrary ATS pages, so this pulls only
    what's cheaply and reliably available (page <title>, meta description) —
    users can edit the rest once verification lands (Day 3).

    Unlike scout_adzuna/scout_remoteok, `url` here comes from the user, not a
    hardcoded trusted API endpoint — fetch_url_safely (not the plain _client()
    the other two use) rejects non-https, credentialed, localhost, and
    private/loopback/link-local targets before the server ever requests them,
    and validates each redirect hop the same way. See url_safety.py.
    """
    try:
        response = fetch_url_safely(
            url, user_agent=settings.http_user_agent, timeout_seconds=settings.http_timeout_seconds
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise JobScoutError(f"Could not fetch job URL: {exc}") from exc

    body = response.text
    title_match = _TITLE_RE.search(body)
    description_match = _DESCRIPTION_RE.search(body)

    title = html.unescape(title_match.group(1)).strip() if title_match else url
    title = _WHITESPACE_RE.sub(" ", title)
    description = (
        _WHITESPACE_RE.sub(" ", html.unescape(description_match.group(1)).strip())
        if description_match
        else MANUAL_INGEST_PLACEHOLDER_DESCRIPTION
    )

    final_url = str(response.url)
    company = _guess_company(final_url)

    return {
        "title": title[:255] or url,
        "company": company,
        "url": final_url,
        "description": description,
    }


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _format_salary(min_value: float | None, max_value: float | None) -> str | None:
    min_value = min_value or 0
    max_value = max_value or 0
    if not min_value and not max_value:
        return None
    if min_value and max_value and min_value != max_value:
        return f"${min_value:,.0f}–${max_value:,.0f}"
    return f"${(max_value or min_value):,.0f}"


def normalize_job(raw: dict, source: str) -> Job:
    """Map a provider payload into the shared Job schema."""
    now = datetime.now(timezone.utc)

    if source == "adzuna":
        company = _clean_line((raw.get("company") or {}).get("display_name")) or "Unknown"
        location = _clean_line((raw.get("location") or {}).get("display_name")) or None
        return Job(
            title=_clean_line(raw.get("title")) or "Untitled role",
            company=company,
            location=location,
            salary=_format_salary(raw.get("salary_min"), raw.get("salary_max")),
            url=raw.get("redirect_url") or "",
            description=_clean_description(raw.get("description")),
            source="adzuna",
            date_posted=_parse_iso_date(raw.get("created")),
            date_scraped=now,
            status="discovered",
        )

    if source == "remoteok":
        return Job(
            title=_clean_line(raw.get("position")) or "Untitled role",
            company=_clean_line(raw.get("company")) or "Unknown",
            location=_clean_line(raw.get("location")) or "Remote",
            salary=_format_salary(raw.get("salary_min"), raw.get("salary_max")),
            url=raw.get("url") or raw.get("apply_url") or "",
            description=_clean_description(raw.get("description")),
            source="remoteok",
            date_posted=_parse_iso_date(raw.get("date")),
            date_scraped=now,
            status="discovered",
        )

    if source == "manual":
        return Job(
            title=_clean_line(raw.get("title")) or "Untitled role",
            company=_clean_line(raw.get("company")) or "Unknown",
            location=_clean_line(raw.get("location")) or None,
            salary=None,
            url=raw.get("url") or "",
            description=raw.get("description") or "",
            source="manual",
            date_posted=None,
            date_scraped=now,
            status="discovered",
        )

    raise ValueError(f"Unknown job source '{source}'")


def _normalize_url(url: str | None) -> str:
    """Strip scheme/www/query/fragment/trailing-slash noise for dedup comparison."""
    if not url:
        return ""
    parsed = urlparse(url.strip().lower())
    netloc = parsed.netloc.removeprefix("www.")
    path = parsed.path.rstrip("/")
    return urlunparse(("", netloc, path, "", "", ""))


def _fingerprint(title: str, company: str, location: str | None) -> str:
    return f"{title.strip().lower()}|{company.strip().lower()}|{(location or '').strip().lower()}"


def _dedupe_key(job: Job) -> str:
    normalized_url = _normalize_url(job.url)
    if normalized_url:
        return normalized_url
    return _fingerprint(job.title, job.company, job.location)


def deduplicate_jobs(jobs: list[Job]) -> list[Job]:
    """Dedupe by normalized URL, falling back to a title+company+location fingerprint."""
    seen: dict[str, Job] = {}
    for job in jobs:
        seen.setdefault(_dedupe_key(job), job)
    return list(seen.values())


def persist_jobs(jobs: list[Job]) -> list[Job]:
    """Upsert normalized jobs into SQLite (matched by normalized URL, else
    title+company+location) and return the stored records."""
    if not jobs:
        return []

    stored: list[Job] = []
    with SessionLocal() as db:
        existing_records = db.query(JobRecord).all()
        # Blank-URL records are deliberately excluded here (matching
        # deduplicate_jobs's own fallback-to-fingerprint behavior) — without
        # this guard, every blank-URL record would collide on the same ""
        # key and silently overwrite each other.
        by_url = {_normalize_url(record.url): record for record in existing_records if record.url}
        by_fingerprint = {
            _fingerprint(record.title, record.company, record.location): record
            for record in existing_records
        }

        for job in jobs:
            key = _dedupe_key(job)
            normalized_url = _normalize_url(job.url)
            existing = (by_url.get(normalized_url) if normalized_url else None) or by_fingerprint.get(key)

            if existing:
                existing.title = job.title
                existing.company = job.company
                existing.location = job.location or existing.location
                existing.salary = job.salary or existing.salary
                existing.description = job.description or existing.description
                if job.date_posted:
                    existing.date_posted = job.date_posted.isoformat()
                existing.date_scraped = job.date_scraped
                existing.ats = job.ats or existing.ats
                record = existing
            else:
                record = JobRecord(
                    public_id=f"{job.source}-{uuid.uuid4().hex[:10]}",
                    title=job.title,
                    company=job.company,
                    location=job.location,
                    salary=job.salary,
                    url=job.url,
                    description=job.description,
                    source=job.source,
                    date_posted=job.date_posted.isoformat() if job.date_posted else None,
                    date_scraped=job.date_scraped,
                    ats=job.ats,
                    status=job.status,
                )
                db.add(record)
                if normalized_url:
                    by_url[normalized_url] = record
                by_fingerprint[key] = record

            db.flush()
            stored.append(record_to_job(record))

        db.commit()

    return stored


def _normalize_listings(raw_listings: list[dict], source: str) -> list[Job]:
    """Normalize each raw listing, skipping (and logging) any single
    malformed one instead of letting it take down the whole batch — a
    provider feed having one weird record is routine, not fatal."""
    jobs: list[Job] = []
    for raw in raw_listings:
        try:
            jobs.append(normalize_job(raw, source))
        except Exception as exc:  # noqa: BLE001 — deliberately broad, see docstring
            logger.warning("Skipping malformed %s listing: %s", source, exc)
    return jobs


def run_scout(query: str, location: str | None = None) -> list[Job]:
    """Query every configured source, normalize, dedupe, and persist. Missing
    or failing sources are skipped (logged), not fatal — a scout run should
    still return whatever sources are actually reachable/configured."""
    raw_jobs: list[Job] = []

    try:
        raw_jobs.extend(_normalize_listings(scout_remoteok(query), "remoteok"))
    except JobScoutError as exc:
        logger.warning("RemoteOK scout skipped: %s", exc)

    try:
        raw_jobs.extend(_normalize_listings(scout_adzuna(query, location), "adzuna"))
    except JobScoutError as exc:
        logger.warning("Adzuna scout skipped: %s", exc)

    return persist_jobs(deduplicate_jobs(raw_jobs))
