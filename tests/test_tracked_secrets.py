"""Deterministic tracked-secret scanner tests. Never print matched values."""

from __future__ import annotations

from pathlib import Path

from scripts.check_tracked_secrets import format_finding, scan_text

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
