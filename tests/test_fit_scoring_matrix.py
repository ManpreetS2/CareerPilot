"""Executable adversarial matrix harness for the real scoring API."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts import test_fit_scoring_matrix as matrix

MANIFESTS = matrix.load_manifests()
REQUIRED_SCENARIOS = {
    "exact-required-skill",
    "required-preferred-weighting",
    "documented-partial-aliases",
    "java-javascript-boundary-attack",
    "go-c-r-short-token-boundary-attacks",
    "duplicate-and-reordered-requirements",
    "missing-component-renormalization",
    "overlapping-experience-intervals",
    "unknown-and-malformed-experience-dates",
    "explicit-education-match",
    "explicit-education-mismatch",
    "missing-job-education-requirement",
    "remote-location-preference-match",
    "onsite-city-preference-mismatch",
    "annual-salary-range-match",
    "annual-salary-maximum-mismatch",
    "hourly-salary-ignored",
    "provisional-description-fallback",
    "no-explicit-requirements-409",
    "repeat-recalculation-upserts-one-row",
    "database-commit-failure-rolls-back",
}
COMPONENTS = {"skill", "experience", "education", "location", "preference"}


def test_matrix_covers_required_adversarial_scenarios() -> None:
    scenario_ids = {manifest["scenario_id"] for manifest in MANIFESTS}
    assert len(MANIFESTS) >= 18
    assert REQUIRED_SCENARIOS <= scenario_ids


@pytest.mark.parametrize(
    "manifest",
    MANIFESTS,
    ids=[manifest["scenario_id"] for manifest in MANIFESTS],
)
def test_fit_scoring_matrix_scenario(manifest: dict, tmp_path: Path) -> None:
    expected = manifest["expected"]
    assert set(expected["component_scores"]) == COMPONENTS
    assert set(expected["available_components"]).isdisjoint(expected["null_components"])
    assert set(expected["available_components"]) | set(expected["null_components"]) == COMPONENTS

    result = matrix.run_scenario(manifest, tmp_path / "scenario.sqlite")

    assert result.passed, result.failures
    assert result.status == expected["http_status"]
    assert result.row_count == expected["row_count"]
    assert not (tmp_path / "scenario.sqlite").exists()


def test_matrix_refuses_production_database_path() -> None:
    with pytest.raises(ValueError, match="production database"):
        matrix.assert_safe_database_path(matrix.PRODUCTION_DATABASE)


def test_cli_report_is_privacy_safe_and_machine_readable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert matrix.main([]) == 0
    output = capsys.readouterr().out
    lines = output.splitlines()
    assert len(lines) == len(MANIFESTS) + 1
    scenario_line = re.compile(
        r"^scenario=[a-z0-9-]+ http=\d{3} score=(?:na|\d+\.\d) "
        r"recommendation=(?:na|apply|consider|skip) rows=\d+ result=(?:pass|fail)$"
    )
    assert all(scenario_line.fullmatch(line) for line in lines[:-1])
    assert lines[-1] == f"scenarios={len(MANIFESTS)} passed={len(MANIFESTS)} failed=0"
    for manifest in MANIFESTS:
        candidate = manifest.get("candidate") or {}
        job = manifest.get("job") or {}
        for private_value in (
            candidate.get("name"),
            candidate.get("email"),
            candidate.get("phone"),
            job.get("company"),
            job.get("description"),
        ):
            if private_value:
                assert str(private_value) not in output
