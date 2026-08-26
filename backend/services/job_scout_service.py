"""Job Scout — Adzuna, RemoteOK, Greenhouse, Lever, and Remotive discovery,
manual URL ingestion, normalization, deduplication, and SQLite persistence.
Owned by Developer B (Day 2).
"""

from __future__ import annotations

import html
import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from urllib.parse import urlencode, urlparse, urlunparse

import httpx

from backend.core.config import settings
from backend.db.database import SessionLocal
from backend.db.models import JobRecord
from backend.schemas.schemas import Job
from backend.services.job_service import record_to_job
from backend.services.url_safety import UnsafeURLError, assert_safe_outbound_url, fetch_url_safely

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
GREENHOUSE_POSTING_URL_BASE = "https://boards.greenhouse.io"
GREENHOUSE_POSTING_HOSTS = frozenset({"boards.greenhouse.io", "job-boards.greenhouse.io"})
GREENHOUSE_API_HOSTS = frozenset({"boards-api.greenhouse.io"})
LEVER_POSTING_HOSTS = frozenset({"jobs.lever.co"})
LEVER_API_BASE = "https://api.lever.co/v0"
LEVER_API_HOSTS = frozenset({"api.lever.co"})
REMOTIVE_SEARCH_URL = "https://remotive.com/api/remote-jobs"
REMOTIVE_API_HOSTS = frozenset({"remotive.com"})
_MIN_INGEST_DESCRIPTION_LENGTH = 40
_GREENHOUSE_JOB_PATH_RE = re.compile(r"^/([^/]+)/jobs/(\d+)/?$")
_LEVER_JOB_PATH_RE = re.compile(
    r"^/([^/]+)/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})/?$"
)
_BOARD_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]+$")


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
    if parsed.query or parsed.fragment:
        return None
    host = (parsed.hostname or "").lower()
    if host not in GREENHOUSE_POSTING_HOSTS:
        return None
    match = _GREENHOUSE_JOB_PATH_RE.match(parsed.path or "")
    if not match:
        return None
    board_token, job_id = match.group(1), match.group(2)
    if not job_id.isdigit() or not _BOARD_TOKEN_RE.fullmatch(board_token):
        return None
    return GreenhousePostingRef(board_token=board_token, job_id=job_id)


def _board_token_company_name(board_token: str) -> str:
    return board_token.replace("-", " ").title()


def validate_manual_ingest_url(url: str) -> str:
    """Validate a manual-ingest URL against the supported-host and SSRF policy."""
    normalized = url.strip()
    if parse_greenhouse_posting_url(normalized) is not None:
        assert_safe_outbound_url(normalized, allowed_hosts=GREENHOUSE_POSTING_HOSTS)
        return normalized
    host = (urlparse(normalized).hostname or "").lower()
    if host in LEVER_POSTING_HOSTS:
        assert_safe_outbound_url(normalized, allowed_hosts=LEVER_POSTING_HOSTS)
        return normalized
    raise UnsafeURLError("Job URL host is not supported for manual ingest.")


def _greenhouse_posting_dedupe_key(url: str | None) -> str | None:
    if not url:
        return None
    ref = parse_greenhouse_posting_url(url)
    if ref is None:
        return None
    return f"greenhouse|{ref.board_token}|{ref.job_id}"


def parse_lever_posting_url(url: str) -> tuple[str, str] | None:
    """Parse a jobs.lever.co posting URL into (company_slug, posting_id)."""
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None
    if parsed.query or parsed.fragment:
        return None
    host = (parsed.hostname or "").lower()
    if host not in LEVER_POSTING_HOSTS:
        return None
    match = _LEVER_JOB_PATH_RE.match(parsed.path or "")
    if not match:
        return None
    return match.group(1), match.group(2)


def _lever_posting_dedupe_key(url: str | None) -> str | None:
    """Independent of `source` — same shape as the Greenhouse key, so a
    manually-pasted Lever URL and a bulk-discovered Lever posting for the
    same job collapse into one row."""
    if not url:
        return None
    ref = parse_lever_posting_url(url)
    if ref is None:
        return None
    company_slug, posting_id = ref
    return f"lever|{company_slug}|{posting_id}"


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


def _resolve_greenhouse_public_url(
    absolute_url: str | None,
    validated_input_url: str,
    ref: GreenhousePostingRef,
) -> str:
    """Accept API absolute_url only when it is safe and matches the same posting."""
    if not absolute_url or not str(absolute_url).strip():
        return validated_input_url
    candidate = str(absolute_url).strip()
    parsed_ref = parse_greenhouse_posting_url(candidate)
    if parsed_ref is None:
        return validated_input_url
    if parsed_ref.board_token != ref.board_token or parsed_ref.job_id != ref.job_id:
        return validated_input_url
    try:
        assert_safe_outbound_url(candidate, allowed_hosts=GREENHOUSE_POSTING_HOSTS)
    except UnsafeURLError:
        return validated_input_url
    return candidate


def _fetch_greenhouse_api(board_token: str, job_id: str) -> dict:
    api_url = f"{GREENHOUSE_API_BASE}/boards/{board_token}/jobs/{job_id}"
    try:
        response = fetch_url_safely(
            api_url,
            user_agent=settings.http_user_agent,
            timeout_seconds=settings.http_timeout_seconds,
            allowed_hosts=GREENHOUSE_API_HOSTS,
        )
        response.raise_for_status()
        payload = response.json()
    except UnsafeURLError:
        raise
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


def _ingest_greenhouse_url(validated_url: str, ref: GreenhousePostingRef) -> dict:
    payload = _fetch_greenhouse_api(ref.board_token, ref.job_id)
    if str(payload.get("id")) != ref.job_id:
        raise JobScoutError("Greenhouse job posting did not match the requested job.")

    title = _clean_line(payload.get("title"))
    description = _clean_description(payload.get("content"))
    if len(description) < _MIN_INGEST_DESCRIPTION_LENGTH:
        raise JobScoutError("Greenhouse posting did not include enough description text.")

    location = _clean_line((payload.get("location") or {}).get("name")) or None
    public_url = _resolve_greenhouse_public_url(payload.get("absolute_url"), validated_url, ref)

    company_name = _clean_line(payload.get("company_name"))
    company = company_name or _board_token_company_name(ref.board_token)

    return {
        "title": title[:255] or "Untitled role",
        "company": company,
        "url": public_url,
        "description": description,
        "location": location,
        "date_posted": _parse_iso_date(payload.get("first_published")),
        "ats": "greenhouse",
    }


def _ingest_lever_url(url: str) -> dict:
    try:
        response = fetch_url_safely(
            url,
            user_agent=settings.http_user_agent,
            timeout_seconds=settings.http_timeout_seconds,
            allowed_hosts=LEVER_POSTING_HOSTS,
        )
        response.raise_for_status()
    except UnsafeURLError:
        raise
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

    final_url = str(response.request.url)
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
        listings = [item for item in listings if _title_matches_query(item.get("position"), query)]
    return listings[: settings.scout_results_per_source]


def _default_greenhouse_boards() -> list[str]:
    return [token.strip() for token in (settings.greenhouse_board_tokens or "").split(",") if token.strip()]


def _default_lever_companies() -> list[str]:
    return [slug.strip() for slug in (settings.lever_company_slugs or "").split(",") if slug.strip()]


def _fetch_greenhouse_board_jobs(board_token: str) -> list[dict]:
    """One list call per board (content=true inlines full descriptions) —
    not the existing per-job single endpoint, which would be one HTTP call
    per opening on a board that can have hundreds."""
    url = f"{GREENHOUSE_API_BASE}/boards/{board_token}/jobs?content=true"
    try:
        response = fetch_url_safely(
            url,
            user_agent=settings.http_user_agent,
            timeout_seconds=settings.http_timeout_seconds,
            allowed_hosts=GREENHOUSE_API_HOSTS,
        )
        response.raise_for_status()
        payload = response.json()
    except UnsafeURLError:
        raise
    except httpx.HTTPStatusError:
        raise JobScoutError("Could not load board listing from Greenhouse.") from None
    except httpx.TimeoutException:
        raise JobScoutError("Greenhouse board request timed out.") from None
    except httpx.HTTPError:
        raise JobScoutError("Could not load board listing from Greenhouse.") from None
    except json.JSONDecodeError:
        raise JobScoutError("Greenhouse returned an unreadable board listing.") from None
    if not isinstance(payload, dict):
        raise JobScoutError("Greenhouse returned an unreadable board listing.")
    return payload.get("jobs") or []


def scout_greenhouse(query: str | None = None) -> list[dict]:
    """Discover current openings across every configured Greenhouse board.

    Greenhouse has no cross-company search — each board must be listed
    individually — so a single dead/renamed board token must not take down
    every other configured board (per-token isolation, not just
    per-provider, since one "source" now fans out over N boards).
    """
    listings: list[dict] = []
    for token in _default_greenhouse_boards():
        try:
            raw_jobs = _fetch_greenhouse_board_jobs(token)
        except JobScoutError as exc:
            logger.warning("Greenhouse board '%s' skipped: %s", token, exc)
            continue
        for item in raw_jobs:
            if query and not _title_matches_query(item.get("title"), query):
                continue
            enriched = dict(item)
            enriched["_board_token"] = token
            listings.append(enriched)
    return listings[: settings.scout_results_per_source]


def _fetch_lever_company_postings(company_slug: str) -> list[dict]:
    url = f"{LEVER_API_BASE}/postings/{company_slug}?mode=json"
    try:
        response = fetch_url_safely(
            url,
            user_agent=settings.http_user_agent,
            timeout_seconds=settings.http_timeout_seconds,
            allowed_hosts=LEVER_API_HOSTS,
        )
        response.raise_for_status()
        payload = response.json()
    except UnsafeURLError:
        raise
    except httpx.HTTPStatusError:
        raise JobScoutError("Could not load company postings from Lever.") from None
    except httpx.TimeoutException:
        raise JobScoutError("Lever postings request timed out.") from None
    except httpx.HTTPError:
        raise JobScoutError("Could not load company postings from Lever.") from None
    except json.JSONDecodeError:
        raise JobScoutError("Lever returned an unreadable postings list.") from None
    if not isinstance(payload, list):
        raise JobScoutError("Lever returned an unreadable postings list.")
    return payload


def scout_lever(query: str | None = None) -> list[dict]:
    """Discover current openings across every configured Lever company.

    Same board-scoped constraint as Greenhouse — Lever's public API lists
    one company's postings at a time, no cross-company search — so each
    company slug gets its own try/except (per-company isolation).
    """
    listings: list[dict] = []
    for slug in _default_lever_companies():
        try:
            raw_jobs = _fetch_lever_company_postings(slug)
        except JobScoutError as exc:
            logger.warning("Lever company '%s' skipped: %s", slug, exc)
            continue
        for item in raw_jobs:
            if query and not _title_matches_query(item.get("text"), query):
                continue
            enriched = dict(item)
            enriched["_company_slug"] = slug
            listings.append(enriched)
    return listings[: settings.scout_results_per_source]


def scout_remotive(query: str | None = None) -> list[dict]:
    """Remotive's public API: keyless, but rate-limited and attribution-
    gated by its own terms (linking back to the original remotive.com URL
    and crediting Remotive as the source — both already satisfied here,
    since job.url stores the Remotive URL and job.source="remotive" drives
    the UI's source badge; and no more than a few requests a day, satisfied
    by only ever calling this from a user-triggered "Find Jobs" click, never
    a schedule)."""
    params: dict[str, object] = {"limit": settings.scout_results_per_source}
    if query:
        params["search"] = query
    try:
        response = fetch_url_safely(
            f"{REMOTIVE_SEARCH_URL}?{urlencode(params)}",
            user_agent=settings.http_user_agent,
            timeout_seconds=settings.http_timeout_seconds,
            allowed_hosts=REMOTIVE_API_HOSTS,
        )
        response.raise_for_status()
        payload = response.json()
    except UnsafeURLError:
        raise
    except httpx.HTTPStatusError:
        raise JobScoutError("Could not reach Remotive.") from None
    except httpx.TimeoutException:
        raise JobScoutError("Remotive request timed out.") from None
    except httpx.HTTPError:
        raise JobScoutError("Could not reach Remotive.") from None
    except json.JSONDecodeError:
        raise JobScoutError("Remotive returned an unreadable response.") from None
    if not isinstance(payload, dict):
        raise JobScoutError("Remotive returned an unreadable response.")
    return payload.get("jobs") or []


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
    use a bounded HTML fetch. User-supplied URLs are validated through the
    shared url_safety guard before any server-side request is made.
    """
    normalized = url.strip()
    greenhouse_ref = parse_greenhouse_posting_url(normalized)
    if greenhouse_ref is not None:
        validated = validate_manual_ingest_url(normalized)
        return _ingest_greenhouse_url(validated, greenhouse_ref)

    host = (urlparse(normalized).hostname or "").lower()
    if host in LEVER_POSTING_HOSTS:
        validated = validate_manual_ingest_url(normalized)
        return _ingest_lever_url(validated)

    raise UnsafeURLError("Job URL host is not supported for manual ingest.")


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _parse_epoch_millis(value: object) -> date | None:
    """Lever's createdAt is epoch milliseconds, not an ISO string."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).date()
    except (ValueError, OverflowError, OSError):
        return None


def _title_matches_query(title: str | None, query: str) -> bool:
    """Any-word (not exact-phrase) match against a listing title — a literal
    multi-word query almost never appears verbatim in a title. Used by every
    full-feed source (RemoteOK, and the board-scoped Greenhouse/Lever APIs,
    which have no server-side search of their own) to filter relevance
    client-side. Title only, not tags/categories — noisy in practice (an
    unrelated listing can carry a misleadingly matching tag)."""
    words = [w for w in query.lower().split() if w]
    if not words:
        return True
    return any(w in (title or "").lower() for w in words)


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

    if source == "greenhouse":
        board_token = raw.get("_board_token") or ""
        job_id = raw.get("id")
        company = _clean_line(raw.get("company_name")) or _board_token_company_name(board_token)
        url = f"{GREENHOUSE_POSTING_URL_BASE}/{board_token}/jobs/{job_id}" if board_token and job_id else ""
        return Job(
            title=_clean_line(raw.get("title")) or "Untitled role",
            company=company,
            location=_clean_line((raw.get("location") or {}).get("name")) or None,
            salary=None,
            url=url,
            description=_clean_description(raw.get("content")),
            source="greenhouse",
            date_posted=_parse_iso_date(raw.get("first_published")),
            date_scraped=now,
            status="discovered",
            ats="greenhouse",
        )

    if source == "lever":
        categories = raw.get("categories") or {}
        company_slug = raw.get("_company_slug") or ""
        return Job(
            title=_clean_line(raw.get("text")) or "Untitled role",
            company=_board_token_company_name(company_slug) if company_slug else "Unknown",
            location=_clean_line(categories.get("location")) or None,
            salary=None,
            url=raw.get("hostedUrl") or "",
            description=_clean_description(raw.get("descriptionPlain") or raw.get("description")),
            source="lever",
            date_posted=_parse_epoch_millis(raw.get("createdAt")),
            date_scraped=now,
            status="discovered",
            ats="lever",
        )

    if source == "remotive":
        return Job(
            title=_clean_line(raw.get("title")) or "Untitled role",
            company=_clean_line(raw.get("company_name")) or "Unknown",
            location=_clean_line(raw.get("candidate_required_location")) or "Remote",
            salary=_clean_line(raw.get("salary")) or None,
            url=raw.get("url") or "",
            description=_clean_description(raw.get("description")),
            source="remotive",
            date_posted=_parse_iso_date(raw.get("publication_date")),
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
    greenhouse_key = _greenhouse_posting_dedupe_key(job.url)
    if greenhouse_key:
        return greenhouse_key
    lever_key = _lever_posting_dedupe_key(job.url)
    if lever_key:
        return lever_key
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
        by_lever = {
            key: record
            for record in existing_records
            for key in [_lever_posting_dedupe_key(record.url)]
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
            lever_key = _lever_posting_dedupe_key(job.url)
            existing = (
                (by_greenhouse.get(greenhouse_key) if greenhouse_key else None)
                or (by_lever.get(lever_key) if lever_key else None)
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
                # A job reappearing in a scout run is live again — a stale
                # mark must not be permanent. Leave flagged/verified alone:
                # those carry a human/content verdict that mere reappearance
                # shouldn't silently overwrite.
                if existing.status == "stale":
                    existing.status = "discovered"
                record = existing
                if normalized_url:
                    by_url[normalized_url] = record
                if greenhouse_key:
                    by_greenhouse[greenhouse_key] = record
                if lever_key:
                    by_lever[lever_key] = record
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
                if lever_key:
                    by_lever[lever_key] = record
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

    try:
        raw_jobs.extend(_normalize_listings(scout_greenhouse(query), "greenhouse"))
    except JobScoutError as exc:
        logger.warning("Greenhouse scout skipped: %s", exc)

    try:
        raw_jobs.extend(_normalize_listings(scout_lever(query), "lever"))
    except JobScoutError as exc:
        logger.warning("Lever scout skipped: %s", exc)

    try:
        raw_jobs.extend(_normalize_listings(scout_remotive(query), "remotive"))
    except JobScoutError as exc:
        logger.warning("Remotive scout skipped: %s", exc)

    stored = persist_jobs(deduplicate_jobs(raw_jobs))

    # Deferred import: job_verification_service imports
    # MANUAL_INGEST_PLACEHOLDER_DESCRIPTION from this module, so the reverse
    # import must happen at call time to avoid a circular import (same
    # pattern already used between job_service.py and this module).
    from backend.services.job_verification_service import mark_stale_if_unseen

    mark_stale_if_unseen()

    return stored
