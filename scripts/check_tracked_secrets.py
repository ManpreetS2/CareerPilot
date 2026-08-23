#!/usr/bin/env python3
"""Fail CI if real secrets, resume PDFs, or SQLite databases are tracked.

Allowed example files such as .env.example stay permitted. Production
``data/careerpilot.db`` must never be tracked.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ENV_NAMES = {".env.example", "frontend/.env.example"}
FORBIDDEN_DB_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
KEY_PATTERNS = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"sk-ant-[A-Za-z0-9-]{20,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
)


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
        if relative in ALLOWED_ENV_NAMES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in KEY_PATTERNS:
            if pattern.search(text):
                failures.append(f"tracked secret-like token in {relative}")
                break

    if failures:
        print("Tracked secret/artifact audit failed:")
        for item in failures:
            print(f" - {item}")
        return 1
    print("Tracked secret/artifact audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
