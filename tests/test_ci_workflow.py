"""CI workflow YAML must parse as GitHub Actions documents, including the ``on`` key."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.github_actions_yaml import load_github_actions_yaml, load_github_actions_yaml_file

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def test_ci_workflow_parses_with_github_actions_on_key() -> None:
    raw = WORKFLOW.read_text(encoding="utf-8")
    loaded = load_github_actions_yaml(raw)
    assert "on" in loaded
    assert True not in loaded
    assert "push" in loaded["on"]
    assert "pull_request" in loaded["on"]
    env = loaded["jobs"]["verify"]["env"]
    assert env["DATABASE_URL"] == "sqlite:///:memory:"
    assert 'DATABASE_URL: "sqlite:///:memory:"' in raw
    assert "fetch-depth: 0" in raw
    assert "PR_BASE_SHA" in raw
    assert "PUSH_BEFORE_SHA" in raw
    assert "git diff --check" in raw
    assert "run: git diff --check" not in raw


def test_ci_workflow_plain_safe_load_must_not_be_used_for_on_key() -> None:
    raw = WORKFLOW.read_text(encoding="utf-8")
    broken = yaml.safe_load(raw)
    assert True in broken
    assert "on" not in broken


def test_malformed_workflow_yaml_fails_parse() -> None:
    with pytest.raises(yaml.YAMLError):
        load_github_actions_yaml("jobs:\n  verify: [\n")


def test_committed_range_whitespace_check_against_main() -> None:
    result = subprocess.run(
        ["git", "diff", "--check", "origin/main...HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
