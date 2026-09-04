"""A safe, human-readable download filename stem from untrusted text.

Shared by every export that builds a Content-Disposition filename out of
scraped, untrusted job postings (resume exports, calendar reminders) — the
allowlist is a real security control against header injection, not cosmetic
cleanup, so it lives in one place rather than being re-authored per export.
"""

from __future__ import annotations

import re

_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9 _.-]")
_MAX_FILENAME_STEM_LENGTH = 80


def safe_filename_stem(parts: list[str], *, default: str, max_length: int = _MAX_FILENAME_STEM_LENGTH) -> str:
    stem = " ".join(part.strip() for part in parts if part and part.strip())
    stem = _UNSAFE_FILENAME_CHARS.sub("", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" .")
    if not stem:
        return default
    return stem[:max_length].strip(" .")
