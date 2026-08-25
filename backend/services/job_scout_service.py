"""Job Scout — Adzuna + RemoteOK discovery, manual URL ingestion, normalization,
deduplication, and SQLite persistence. Owned by Developer B (Day 2).
"""

from __future__ import annotations

import html
import ipaddress
import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from urllib.parse import urlparse, urlunparse

import httpx

from backend.core.config import settings
from backend.db.database import SessionLocal
from backend.db.models import JobRecord
from backend.schemas.schemas import Job
from backend.services.job_service import record_to_job

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

GREENHOUSE_API_BASE = "https://boards-api.greenhouse.io/v1"
GREENHOUSE_POSTING_HOSTS = frozenset({"boards.greenhouse.io", "job-boards.greenhouse.io"})
LEVER_POSTING_HOST = "jobs.lever.co"
_MIN_INGEST_DESCRIPTION_LENGTH = 40
_GREENHOUSE_JOB_PATH_RE = re.compile(r"^/([^/]+)/jobs/(\d+)/?$")
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_MAX_INGEST_REDIRECTS = 3


@dataclass(frozen=True)
class GreenhousePostingRef:
    board_token: str
    job_id: str


def parse_greenhouse_posting_url(url: str) -> GreenhousePostingRef | None:
    """Parse a supported Greenhouse posting URL into board token and job ID."""
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if host not in GREENHOUSE_POSTING_HOSTS:
        return None
    match = _GREENHOUSE_JOB_PATH_RE.match(parsed.path or "")
    if not match:
        return None
    board_token, job_id = match.group(1), match.group(2)
    if not board_token or not job_id.isdigit():
        return None
    return GreenhousePostingRef(board_token=board_token, job_id=job_id)


def _is_blocked_host(host: str) -> bool:
    lowered = host.lower()
    if lowered in {"localhost", "::1"}:
        return True
    try:
        ip = ipaddress.ip_address(lowered)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved


def _validate_https_url(url: str) -> tuple[str, str, str]:
    parsed = urlparse(url.strip())
    if parsed.scheme != "https":
        raise JobScoutError("Only HTTPS job URLs are supported.")
    if parsed.username or parsed.password:
        raise JobScoutError("Job URLs with credentials are not supported.")
    host = parsed.hostname
    if not host:
        raise JobScoutError("Job URL is missing a hostname.")
    if parsed.port is not None:
        raise JobScoutError("Job URLs with a non-default port are not supported.")
    if _is_blocked_host(host):
        raise JobScoutError("Job URL hostname is not allowed.")
    return url.strip(), host.lower(), parsed.path or ""


def validate_manual_ingest_url(url: str) -> str:
    """Validate a manual-ingest URL against the supported-host and SSRF policy."""
    normalized, host, _ = _validate_https_url(url)
    if host in GREENHOUSE_POSTING_HOSTS:
        if parse_greenhouse_posting_url(normalized) is None:
            raise JobScoutError("Greenhouse job URL format is not supported.")
        return normalized
    if host == LEVER_POSTING_HOST:
        return normalized
    raise JobScoutError("Job URL host is not supported for manual ingest.")


def _greenhouse_posting_dedupe_key(url: str | None) -> str | None:
    if not url:
        return None
    ref = parse_greenhouse_posting_url(url)
    if ref is None:
        return None
    return f"greenhouse|{ref.board_token}|{ref.job_id}"


def _merge_description(existing: str | None, new: str | None) -> str:
    existing_text = (existing or "").strip()
    new_text = (new or "").strip()
    if not new_text:
        return existing_text
    if new_text == MANUAL_INGEST_PLACEHOLDER_DESCRIPTION:
        if existing_text and existing_text != MANUAL_INGEST_PLACEHOLDER_DESCRIPTION:
            return existing_text
        return new_text
    if (
        existing_text
        and existing_text != MANUAL_INGEST_PLACEHOLDER_DESCRIPTION
        and len(existing_text) >= _MIN_INGEST_DESCRIPTION_LENGTH
        and len(new_text) < _MIN_INGEST_DESCRIPTION_LENGTH
    ):
        return existing_text
    return new_text


def _safe_ingest_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": settings.http_user_agent},
        timeout=settings.http_timeout_seconds,
        follow_redirects=False,
        verify=True,
        trust_env=False,
    )


def _safe_get_with_validated_redirects(
    client: httpx.Client,
    url: str,
    allowed_host: str,
) -> httpx.Response:
    current = url
    for _ in range(_MAX_INGEST_REDIRECTS + 1):
        normalized, host, _ = _validate_https_url(current)
        if host != allowed_host:
            raise JobScoutError("Redirect destination is not supported.")
        response = client.get(current)
        if response.status_code in _REDIRECT_STATUSES:
            location = response.headers.get("Location")
            if not location:
                raise JobScoutError("Redirect response missing a destination.")
            current = str(httpx.URL(current).join(location))
            continue
        return response
    raise JobScoutError("Too many redirects while fetching job URL.")


def _fetch_greenhouse_api(board_token: str, job_id: str) -> dict:
    api_url = f"{GREENHOUSE_API_BASE}/boards/{board_token}/jobs/{job_id}"
    try:
        with _safe_ingest_client() as client:
            response = client.get(api_url)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError:
        raise JobScoutError("Could not load job posting from Greenhouse.") from None
    except httpx.TimeoutException:
        raise JobScoutError("Greenhouse job request timed out.") from None
    except httpx.HTTPError:
        raise JobScoutError("Could not load job posting from Greenhouse.") from None
    except json.JSONDecodeError:
        raise JobScoutError("Greenhouse returned an unreadable job posting.") from None
    if not isinstance(payload, dict):
        raise JobScoutError("Greenhouse returned an unreadable job posting.")
    return payload


def _ingest_greenhouse_url(url: str) -> dict:
    ref = parse_greenhouse_posting_url(url)
    if ref is None:
        raise JobScoutError("Greenhouse job URL format is not supported.")

    payload = _fetch_greenhouse_api(ref.board_token, ref.job_id)
    if str(payload.get("id")) != ref.job_id:
        raise JobScoutError("Greenhouse job posting did not match the requested job.")

    title = _clean_line(payload.get("title"))
    description = _clean_description(payload.get("content"))
    if len(description) < _MIN_INGEST_DESCRIPTION_LENGTH:
        raise JobScoutError("Greenhouse posting did not include enough description text.")

    location = _clean_line((payload.get("location") or {}).get("name")) or None
    absolute_url = (payload.get("absolute_url") or url).strip()
    _, absolute_host, _ = _validate_https_url(absolute_url)
    if absolute_host not in GREENHOUSE_POSTING_HOSTS:
        absolute_url = url

    return {
        "title": title[:255] or "Untitled role",
        "company": _guess_company(absolute_url),
        "url": absolute_url,
        "description": description,
        "location": location,
        "date_posted": _parse_iso_date(payload.get("updated_at")),
        "ats": "greenhouse",
    }


def _ingest_lever_url(url: str) -> dict:
    try:
        with _safe_ingest_client() as client:
            response = _safe_get_with_validated_redirects(client, url, LEVER_POSTING_HOST)
        response.raise_for_status()
    except httpx.HTTPStatusError:
        raise JobScoutError("Could not fetch job URL.") from None
    except httpx.TimeoutException:
        raise JobScoutError("Job URL request timed out.") from None
    except httpx.HTTPError:
        raise JobScoutError("Could not fetch job URL.") from None

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
    return {
        "title": title[:255] or url,
        "company": _guess_company(final_url),
        "url": final_url,
        "description": description,
        "ats": "lever",
    }


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
    """Fetch a single supported job posting URL and return a source-backed record.

    Greenhouse postings are loaded from the public boards API. Lever postings
    use a bounded HTML fetch with SSRF-safe host and redirect validation.
    """
    normalized, host, _ = _validate_https_url(url.strip())
    if host in GREENHOUSE_POSTING_HOSTS:
        return _ingest_greenhouse_url(normalized)
    if host == LEVER_POSTING_HOST:
        return _ingest_lever_url(normalized)
    raise JobScoutError("Job URL host is not supported for manual ingest.")


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
        date_posted = raw.get("date_posted")
        if isinstance(date_posted, date):
            posted = date_posted
        elif isinstance(date_posted, str):
            posted = _parse_iso_date(date_posted)
        else:
            posted = None
        return Job(
            title=_clean_line(raw.get("title")) or "Untitled role",
            company=_clean_line(raw.get("company")) or "Unknown",
            location=_clean_line(raw.get("location")) or None,
            salary=None,
            url=raw.get("url") or "",
            description=raw.get("description") or "",
            source="manual",
            date_posted=posted,
            date_scraped=now,
            status="discovered",
            ats=raw.get("ats"),
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
    greenhouse_key = _greenhouse_posting_dedupe_key(job.url)
    if greenhouse_key:
        return greenhouse_key
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
        by_greenhouse = {
            key: record
            for record in existing_records
            for key in [_greenhouse_posting_dedupe_key(record.url)]
            if key
        }
        by_fingerprint = {
            _fingerprint(record.title, record.company, record.location): record
            for record in existing_records
        }

        for job in jobs:
            key = _dedupe_key(job)
            normalized_url = _normalize_url(job.url)
            greenhouse_key = _greenhouse_posting_dedupe_key(job.url)
            existing = (
                (by_greenhouse.get(greenhouse_key) if greenhouse_key else None)
                or (by_url.get(normalized_url) if normalized_url else None)
                or by_fingerprint.get(key)
            )

            if existing:
                existing.title = job.title
                existing.company = job.company
                existing.location = job.location or existing.location
                existing.salary = job.salary or existing.salary
                existing.description = _merge_description(existing.description, job.description)
                if job.url:
                    existing.url = job.url
                if job.date_posted:
                    existing.date_posted = job.date_posted.isoformat()
                existing.date_scraped = job.date_scraped
                existing.ats = job.ats or existing.ats
                record = existing
                if normalized_url:
                    by_url[normalized_url] = record
                if greenhouse_key:
                    by_greenhouse[greenhouse_key] = record
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
                if greenhouse_key:
                    by_greenhouse[greenhouse_key] = record
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
