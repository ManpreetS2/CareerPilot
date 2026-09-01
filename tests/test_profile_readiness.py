"""Deterministic profile-readiness contract. No LLM, no network."""

from __future__ import annotations

from backend.schemas.schemas import CandidateProfile, Education, Experience, Project, TargetPreferences
from backend.services.profile_readiness import (
    MISSING_CANDIDATE_EVIDENCE,
    MISSING_CANDIDATE_PROFILE,
    MISSING_TARGET_ROLES,
    PROFILE_REQUIRED_CODE,
    evaluate_candidate_grounding,
    evaluate_profile_readiness,
)


def _candidate(**overrides) -> CandidateProfile:
    data = dict(
        name="Ada Lovelace",
        skills=["Python"],
        projects=[],
        experience=[],
        education=[],
        certifications=[],
        strengths=[],
        evidence_links=[],
    )
    data.update(overrides)
    return CandidateProfile(**data)


def _prefs(**overrides) -> TargetPreferences:
    data = dict(target_roles=["Software Engineer"], preferred_locations=[], constraints=[])
    data.update(overrides)
    return TargetPreferences(**data)


def test_no_candidate_is_not_ready() -> None:
    readiness = evaluate_profile_readiness(None, None)
    assert readiness.ready is False
    assert readiness.code == PROFILE_REQUIRED_CODE
    assert readiness.next_route == "/profile"
    assert readiness.missing == (
        MISSING_CANDIDATE_PROFILE,
        MISSING_CANDIDATE_EVIDENCE,
        MISSING_TARGET_ROLES,
    )


def test_candidate_with_no_evidence_is_not_ready() -> None:
    candidate = _candidate(skills=[], education=[], experience=[], projects=[])
    readiness = evaluate_profile_readiness(candidate, _prefs())
    assert readiness.ready is False
    assert MISSING_CANDIDATE_EVIDENCE in readiness.missing
    assert MISSING_CANDIDATE_PROFILE not in readiness.missing
    assert MISSING_TARGET_ROLES not in readiness.missing


def test_whitespace_name_is_not_a_usable_profile() -> None:
    candidate = _candidate(name="   ", skills=["Python"])
    readiness = evaluate_profile_readiness(candidate, _prefs())
    assert readiness.ready is False
    assert MISSING_CANDIDATE_PROFILE in readiness.missing


def test_education_evidence_is_enough() -> None:
    candidate = _candidate(
        skills=[],
        education=[Education(institution="State University", degree="B.S.", field="Computer Science")],
    )
    readiness = evaluate_profile_readiness(candidate, _prefs())
    assert readiness.ready is True
    assert readiness.missing == ()
    assert readiness.code is None
    assert readiness.next_route is None


def test_skills_evidence_is_enough() -> None:
    candidate = _candidate(skills=["SQL"], education=[], experience=[], projects=[])
    assert evaluate_profile_readiness(candidate, _prefs()).ready is True


def test_experience_evidence_is_enough() -> None:
    candidate = _candidate(
        skills=[],
        experience=[Experience(title="Intern", company="Labs", highlights=["Built APIs"])],
    )
    assert evaluate_profile_readiness(candidate, _prefs()).ready is True


def test_project_evidence_is_enough() -> None:
    candidate = _candidate(
        skills=[],
        projects=[Project(name="Campus Planner", description="Events API", technologies=["Python"])],
    )
    assert evaluate_profile_readiness(candidate, _prefs()).ready is True


def test_empty_education_dicts_are_not_evidence() -> None:
    candidate = _candidate(skills=[], education=[Education(institution="", degree=None, field=None)])
    readiness = evaluate_profile_readiness(candidate, _prefs())
    assert readiness.ready is False
    assert MISSING_CANDIDATE_EVIDENCE in readiness.missing


def test_candidate_without_target_roles_is_not_ready() -> None:
    readiness = evaluate_profile_readiness(_candidate(), _prefs(target_roles=[]))
    assert readiness.ready is False
    assert readiness.missing == (MISSING_TARGET_ROLES,)


def test_blank_target_roles_are_not_ready() -> None:
    readiness = evaluate_profile_readiness(_candidate(), _prefs(target_roles=["  ", ""]))
    assert readiness.ready is False
    assert MISSING_TARGET_ROLES in readiness.missing


def test_valid_target_role_with_evidence_is_ready() -> None:
    readiness = evaluate_profile_readiness(_candidate(), _prefs(target_roles=["Solutions Engineer"]))
    assert readiness.ready is True


def test_locations_are_optional_for_readiness() -> None:
    readiness = evaluate_profile_readiness(
        _candidate(),
        _prefs(preferred_locations=[], work_mode_preferences=[], opportunity_preference=None),
    )
    assert readiness.ready is True


def test_readiness_never_invents_defaults() -> None:
    payload = evaluate_profile_readiness(None, None).as_dict()
    assert payload["ready"] is False
    assert payload["missing"] == [
        MISSING_CANDIDATE_PROFILE,
        MISSING_CANDIDATE_EVIDENCE,
        MISSING_TARGET_ROLES,
    ]
    assert "preferred_locations" not in payload["missing"]


def test_grounded_candidate_without_roles_is_not_discovery_ready() -> None:
    candidate = _candidate()
    assert evaluate_candidate_grounding(candidate).ready is True
    assert evaluate_profile_readiness(candidate, _prefs(target_roles=[])).ready is False
    assert evaluate_profile_readiness(candidate, None).missing == (MISSING_TARGET_ROLES,)
