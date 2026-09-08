#!/usr/bin/env python3
"""Check backtick path-like tokens in the AI repo map against the Git tree."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP_FILES = (
    ROOT / "AGENTS.md",
    ROOT / "docs" / "AI_REPO_MAP.md",
    ROOT / ".cursor" / "rules" / "repo-map.mdc",
)
TOKEN_RE = re.compile(r"`([^`]+)`")
PATHISH_RE = re.compile(
    r"(/)|(\.(py|ts|tsx|md|mdc|yml|toml|json|css)$)",
    re.IGNORECASE,
)
SEARCH_PREFIXES = (
    "",
    "backend/services/",
    "backend/api/routes/",
    "backend/core/",
    "backend/db/",
    "backend/schemas/",
    "frontend/src/pages/",
    "frontend/src/components/",
    "frontend/src/lib/",
    "tests/",
    "browser-extension/src/",
    "browser-extension/tests/",
    "scripts/",
    "docs/",
    ".github/workflows/",
)

CONCEPTUAL = {
    "data/careerpilot.db",
    "main",
    "GET /api/analytics/summary",
    "GET /api/jobs/{job_id}/match-evidence",
    "GET /api/applications/{job_id}/reminder.ics",
    "approved_materials_hash",
    "grounding_override",
    "grounded=true",
    "careerpilot_session",
    "find_job_by_url",
    "parse_greenhouse_posting_url",
    "canonical_greenhouse_posting_url",
    "parse_lever_posting_url",
    "canonical_lever_posting_url",
    "form_fill_service.py::find_job_by_url",
    "fillFormInPage",
    "Task → files",
    "/analytics",
    "/track",
    "/applications",
    "/privacy",
    "/dashboard",
    "/growth",
}

COMMANDISH_RE = re.compile(r"\s")
ROUTEISH_RE = re.compile(r"^(GET|POST|PATCH|DELETE|PUT)\s", re.I)


def git_files() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return {line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}


def resolve(token: str, tracked: set[str]) -> str | None:
    normalized = token.strip().replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    if COMMANDISH_RE.search(normalized) or ROUTEISH_RE.match(normalized):
        return "conceptual"
    if normalized in CONCEPTUAL or normalized.startswith("/"):
        return "conceptual"
    if not PATHISH_RE.search(normalized):
        return "conceptual"
    candidates = [normalized, f"backend/{normalized}", f"frontend/src/{normalized}"]
    if "/" not in normalized:
        candidates.extend(f"{prefix}{normalized}" for prefix in SEARCH_PREFIXES)
    else:
        for prefix in SEARCH_PREFIXES:
            candidates.append(f"{prefix}{normalized}")
    for candidate in candidates:
        if candidate in tracked:
            return candidate
        for suffix in (".py", ".ts", ".tsx"):
            with_suffix = f"{candidate}{suffix}"
            if with_suffix in tracked:
                return with_suffix
    return None


def main() -> int:
    tracked = git_files()
    missing: list[tuple[str, str]] = []
    valid = 0
    conceptual = 0
    for map_file in MAP_FILES:
        text = map_file.read_text(encoding="utf-8")
        for token in TOKEN_RE.findall(text):
            if "\n" in token:
                continue
            result = resolve(token, tracked)
            if result == "conceptual":
                conceptual += 1
                continue
            if result is None:
                missing.append((str(map_file.relative_to(ROOT)).replace("\\", "/"), token.encode("ascii", "backslashreplace").decode("ascii")))
            else:
                valid += 1
    print(f"valid_paths={valid} conceptual={conceptual} missing={len(missing)}")
    for path, token in missing:
        print(f"MISSING {path}: `{token}`")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
