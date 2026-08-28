"""Classify whether a stored job description is a full posting, and fingerprint it."""

from __future__ import annotations

import hashlib
import re

from backend.schemas.job_requirements import CanonicalJobContent, ContentStatus

_ELLIPSIS_TAIL = re.compile(r"(\.\.\.|…)\s*$")
_ADZUNA_SNIPPET = re.compile(r"\*\s*\.\.\.\s*$")


def normalize_posting_text(value: str | None) -> str:
    return " ".join((value or "").split()).strip().lower()


def source_fingerprint(title: str | None, description: str | None) -> str:
    payload = f"{normalize_posting_text(title)}\n{normalize_posting_text(description)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def content_hash(title: str | None, description: str | None) -> str:
    return source_fingerprint(title, description)


def classify_content_status(
    source: str | None,
    description: str | None,
    *,
    used_excerpt: bool = False,
) -> ContentStatus:
    """Heuristic completeness. Never claims full for a known excerpt."""
    text = (description or "").strip()
    if not text:
        return "unknown"
    if used_excerpt:
        return "partial"
    length = len(text)
    source_name = (source or "").strip().lower()
    if _ELLIPSIS_TAIL.search(text) and length < 1600:
        return "partial"
    if source_name == "adzuna" and length < 1800:
        return "partial"
    if source_name in {"greenhouse", "lever"} and length >= 200:
        return "full"
    if source_name in {"remotive", "remoteok"} and length >= 500:
        return "full"
    if source_name == "manual" and length >= 400:
        return "full"
    if length >= 1200:
        return "full"
    if length >= 400:
        return "unknown"
    return "partial"


def canonical_from_job(
    *,
    title: str,
    company: str,
    description: str,
    source: str,
    url: str,
    source_job_id: str | None = None,
    posted_at: str | None = None,
    fetched_at=None,
    content_status: ContentStatus | None = None,
    used_excerpt: bool = False,
) -> CanonicalJobContent:
    status = content_status or classify_content_status(source, description, used_excerpt=used_excerpt)
    fingerprint = source_fingerprint(title, description)
    return CanonicalJobContent(
        title=title,
        company=company,
        full_description=description or "",
        source=source,
        canonical_url=url or "",
        source_job_id=source_job_id,
        posted_at=posted_at,
        fetched_at=fetched_at,
        content_status=status,
        content_hash=fingerprint,
        source_fingerprint=fingerprint,
    )
