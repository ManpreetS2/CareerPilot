"""Deterministic tracked-secret scanner tests. Never print matched values."""

from __future__ import annotations

from pathlib import Path

from scripts.check_tracked_secrets import _looks_like_database, format_finding, scan_text

ROOT = Path(__file__).resolve().parents[1]


def test_scan_text_detects_modern_token_shapes_without_emitting_values() -> None:
    openai = "sk-proj-" + ("a" * 24)
    github = "ghp_" + ("b" * 36)
    fine_grained = "github_pat_" + ("c" * 22)
    blob = f"openai={openai}\ngithub={github}\nfine={fine_grained}\n"
    found = scan_text(blob)
    assert found["openai_project_key"] == 1
    assert found["github_token"] >= 1
    assert found["github_pat"] == 1
    rendered = " ".join(
        format_finding("demo.env", category, count) for category, count in found.items()
    )
    assert openai not in rendered
    assert github not in rendered
    assert fine_grained not in rendered
    assert "category=" in rendered


def test_example_env_placeholders_are_not_treated_as_secrets() -> None:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert scan_text(example) == {}


def test_backup_suffixed_databases_are_still_detected() -> None:
    """A real data/careerpilot.db.bak-20260824-125107 — a byte-for-byte copy
    of the production database — sat untracked in the repo and would have
    passed this audit, because the check matched only a trailing .db and
    .gitignore only covered data/*.db. Backup and timestamp suffixes are
    exactly what gets appended right before a file is forgotten about."""
    for name in (
        "careerpilot.db",
        "careerpilot.db.bak-20260824-125107",
        "careerpilot.db-journal",
        "app.sqlite3.backup",
        "dump.sqlite.old",
        "careerpilot.db.gz",
    ):
        assert _looks_like_database(name), name


def test_source_files_are_not_mistaken_for_databases() -> None:
    """The check gates commits, so it must not fire on ordinary code whose
    name merely mentions a database."""
    for name in ("database.py", "db.ts", "models.py", "test_db_helpers.py", "notes.md"):
        assert not _looks_like_database(name), name
