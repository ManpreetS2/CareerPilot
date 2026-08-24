#!/usr/bin/env python3
"""Fail CI if real secrets, resume PDFs, or SQLite databases are tracked.

Example env filenames such as .env.example remain allowed, but their
contents are still scanned. Production ``data/careerpilot.db`` must never
be tracked. Findings print filename/category/count only — never the value.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ENV_NAMES = {".env.example", "frontend/.env.example"}
FORBIDDEN_DB_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("openai_project_key", re.compile(r"sk-proj-[A-Za-z0-9]{20,}")),
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9-]{20,}")),
    ("openai_key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("google_api_key", re.compile(r"AIza[0-9A-Za-z_-]{20,}")),
    ("github_pat", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("github_token", re.compile(r"gh[pours]_[A-Za-z0-9]{36,}")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----")),
)


def scan_text(text: str) -> dict[str, int]:
    """Return category -> match count. Never includes matched values."""

    found: dict[str, int] = {}
    for category, pattern in SECRET_PATTERNS:
        count = len(pattern.findall(text))
        if count:
            found[category] = count
    return found


def format_finding(relative: str, category: str, count: int) -> str:
    return f"{relative} category={category} count={count}"


def _tracked_files() -> list[str]:
    output = subprocess.check_output(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        text=False,
    )
    return [item.decode("utf-8") for item in output.split(b"\0") if item]


def main() -> int:
    failures: list[str] = []
    for relative in _tracked_files():
        path = ROOT / relative
        name = Path(relative).name
        if relative in {"data/careerpilot.db", "data/careerpilot.db-journal"}:
            failures.append(f"tracked production database: {relative}")
            continue
        if name == ".env" or relative.endswith("/.env"):
            failures.append(f"tracked env file: {relative}")
            continue
        if name.endswith(tuple(FORBIDDEN_DB_SUFFIXES)):
            failures.append(f"tracked sqlite database: {relative}")
            continue
        if name.lower().endswith(".pdf") and not relative.startswith("tests/"):
            failures.append(f"tracked resume/pdf artifact: {relative}")
            continue
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for category, count in scan_text(text).items():
            failures.append(format_finding(relative, category, count))

    if failures:
        print("Tracked secret/artifact audit failed:")
        for item in failures:
            print(f" - {item}")
        return 1
    print("Tracked secret/artifact audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
