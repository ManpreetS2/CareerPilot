"""Contradiction matrix: Fit status, contribution, evidence refs, and groups must agree."""

from __future__ import annotations

from datetime import date

import pytest

from backend.db.models import Candidate, JobIntelligenceRecord, JobRecord, MatchEvidenceRecord, TargetPreference, User
from backend.schemas.job_requirements import JobRequirementProfile, Requirement, RequirementGroup
from backend.services.analysis_service import _canonical_skill_key, canonicalize_skill, skill_concepts_in_label
from backend.services.eligibility_engine import _combine_group, evaluate_eligibility
from backend.services.match_evidence_service import (
    MatchEvidenceConsistencyError,
    _align_status_to_contribution,
    _component_status,
    _status_from_membership,
    get_match_evidence,
    validate_match_evidence_payload,
)
from backend.services.verified_fit_service import score_job_verified

AS_OF = date(2026, 8, 20)

ALIAS_POSTING = """
Software Engineering Intern

Requirements
Python or Java required
JavaScript
Experience with Node.js / NodeJS
React.js preferred

Currently enrolled in a bachelor's program
Must be authorized to work in the United States
Security clearance required
""" + ("Program details, interview process, and team rituals. " * 40)


def _user(session, *, user_id: int = 1, email: str = "invariants@example.com") -> User:
    existing = session.get(User, user_id)
    if existing:
        return existing
    user = User(id=user_id, email=email, hashed_password="x")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _candidate(session, user_id: int, **overrides) -> Candidate:
    record = Candidate(
        user_id=user_id,
        name="Invariant Candidate",
        email="invariant@example.com",
        skills=overrides.get("skills", ["Python", "JavaScript", "Node.js", "React"]),
        projects=overrides.get("projects", []),
        experience=overrides.get("experience", []),
        education=overrides.get(
            "education",
            [{"institution": "State University", "degree": "B.S.", "field": "Computer Science", "graduation_year": "2027"}],
        ),
        certifications=[],
        strengths=[],
        evidence_links=[],
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _prefs(session, candidate: Candidate, **overrides) -> TargetPreference:
    record = TargetPreference(
        user_id=candidate.user_id,
        candidate_id=candidate.id,
        target_roles=["Software Engineer Intern"],
        preferred_locations=["Remote"],
        remote_preference="hybrid",
        work_mode_preferences=["hybrid", "remote"],
        currently_enrolled_in_program=overrides.get("currently_enrolled_in_program", "yes"),
        expected_graduation=overrides.get("expected_graduation", "2027-05"),
        academic_year=overrides.get("academic_year", "final_year"),
        work_authorization=overrides.get("work_authorization", "Authorized to work in the United States"),
        sponsorship_required=overrides.get("sponsorship_required", False),
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _job(session, **overrides) -> JobRecord:
    record = JobRecord(
        public_id=overrides.get("public_id", "invariant-job"),
        title=overrides.get("title", "Software Engineering Intern"),
        company="Example Co",
        location="Remote",
        url=f"https://example.com/jobs/{overrides.get('public_id', 'invariant-job')}",
        description=overrides.get("description", ALIAS_POSTING),
        source=overrides.get("source", "manual"),
        status="verified",
        content_status=overrides.get("content_status", "full"),
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _intel(session, job: JobRecord, **overrides) -> None:
    session.add(
        JobIntelligenceRecord(
            job_id=job.id,
            required_skills=overrides.get("required_skills", ["Python", "Java"]),
            preferred_skills=overrides.get("preferred_skills", ["React.js"]),
            years_experience=None,
            education_requirements=[],
            tech_stack=overrides.get("tech_stack", ["Node.js"]),
            seniority="intern",
            responsibilities=["Build APIs"],
            likely_interview_focus=[],
        )
    )
    session.commit()


def _payload_dict(payload) -> dict:
    return {
        "factors": [item.model_dump() for item in payload.factors],
        "evaluations": [item.model_dump() for item in payload.evaluations],
        "groups": [item.model_dump() for item in payload.groups],
        "evidence": {key: value.model_dump() for key, value in payload.evidence.items()},
    }


def assert_coherent_evidence(payload) -> None:
    validate_match_evidence_payload(_payload_dict(payload))
    for factor in payload.factors:
        if (
            factor.status == "satisfied"
            and factor.score_contribution == 0
            and (factor.max_contribution or 0) > 0
        ):
            raise AssertionError(f"{factor.id} is satisfied with 0 / {factor.max_contribution}")
        if factor.status == "not_applicable":
            assert factor.score_contribution is None
        if factor.importance == "preferred":
            assert factor.hard_blocker is False
        for ref in factor.candidate_evidence_refs:
            assert ref in payload.evidence
            assert payload.evidence[ref].source_type.startswith("candidate")
        for ref in factor.job_evidence_refs:
            assert ref in payload.evidence
            assert payload.evidence[ref].source_type.startswith("job")
    eval_by_id = {item.requirement_id: item for item in payload.evaluations}
    for factor in payload.factors:
        if factor.requirement_id and factor.requirement_id in eval_by_id:
            assert factor.status == eval_by_id[factor.requirement_id].result
    group_by_id = {item.group_id: item for item in payload.groups}
    for factor in payload.factors:
        if factor.group_id and factor.group_id in group_by_id:
            assert factor.status == group_by_id[factor.group_id].status


def _factor(**overrides) -> dict:
    body = {
        "id": "factor_required_skills",
        "job_id": "job-1",
        "category": "skill",
        "section": "required_skills",
        "label": "Required skills",
        "importance": "required",
        "status": "satisfied",
        "rule_id": "required_skills_v2",
        "rule_version": "v2",
        "explanation": "ok",
        "job_evidence_refs": [],
        "candidate_evidence_refs": [],
    }
    body.update(overrides)
    return body


def _req(req_id: str, kind: str, text: str, *, importance: str = "required", **extra) -> Requirement:
    return Requirement(
        id=req_id,
        category=kind,
        text=text,
        importance=importance,  # type: ignore[arg-type]
        evidence_text=text,
        structured_condition={"kind": kind, **extra},
    )


def _group_profile(operator: str, requirements: list[Requirement], *, importance: str = "required") -> JobRequirementProfile:
    return JobRequirementProfile(
        source_fingerprint="test-group",
        requirements=requirements,
        requirement_groups=[
            RequirementGroup(
                id="grp-1",
                operator=operator,  # type: ignore[arg-type]
                requirement_ids=[item.id for item in requirements],
                text="group",
                evidence_text="group",
                importance=importance,  # type: ignore[arg-type]
            )
        ],
    )


def test_canonical_aliases_are_conservative() -> None:
    assert canonicalize_skill("javascript") == "JavaScript"
    assert skill_concepts_in_label("React.js") == ["React"]
    assert "JavaScript" not in skill_concepts_in_label("React.js")
    assert canonicalize_skill("nodejs") == "Node.js"
    assert canonicalize_skill("node js") == "Node.js"
    assert _canonical_skill_key("Java") != _canonical_skill_key("JavaScript")
    assert _status_from_membership("React.js", ["React"], [], []) == "satisfied"
    assert _status_from_membership("NodeJS", ["Node.js"], [], []) == "satisfied"
    assert _status_from_membership("javascript", ["JavaScript"], [], []) == "satisfied"
    assert _status_from_membership("Java", ["JavaScript"], [], []) == "unknown"


def test_empty_scored_dimension_is_not_satisfied_zero() -> None:
    assert _component_status(0.0, [], [], [], []) == "not_applicable"
    assert _align_status_to_contribution("satisfied", 0.0, 25.0) == "not_satisfied"
    assert _align_status_to_contribution("not_satisfied", 25.0, 25.0) == "satisfied"
    assert _align_status_to_contribution("satisfied", 12.0, 25.0) == "partially_satisfied"


def test_validator_rejects_satisfied_zero_contribution() -> None:
    payload = {
        "factors": [_factor(status="satisfied", score_contribution=0, max_contribution=25)],
        "evidence": {},
    }
    with pytest.raises(MatchEvidenceConsistencyError) as exc:
        validate_match_evidence_payload(payload)
    assert "satisfied_zero_contribution" in exc.value.reasons


def test_validator_rejects_cross_source_refs() -> None:
    payload = {
        "factors": [
            _factor(
                id="factor_skill_python",
                label="Python",
                status="satisfied",
                job_evidence_refs=["ev_cand"],
                candidate_evidence_refs=["ev_job"],
            )
        ],
        "evidence": {
            "ev_job": {"id": "ev_job", "source_type": "job_posting", "exact_text": "Python required"},
            "ev_cand": {"id": "ev_cand", "source_type": "candidate_profile", "exact_text": "Python"},
        },
    }
    with pytest.raises(MatchEvidenceConsistencyError) as exc:
        validate_match_evidence_payload(payload)
    assert "job_ref_wrong_source" in exc.value.reasons
    assert "candidate_ref_wrong_source" in exc.value.reasons


def test_validator_rejects_preferred_hard_blocker() -> None:
    payload = {
        "factors": [_factor(id="factor_skill_python", label="Python", importance="preferred", status="unknown", hard_blocker=True)],
        "evidence": {},
    }
    with pytest.raises(MatchEvidenceConsistencyError) as exc:
        validate_match_evidence_payload(payload)
    assert "preferred_hard_blocker" in exc.value.reasons


def test_validator_rejects_factor_evaluation_mismatch() -> None:
    payload = {
        "factors": [_factor(id="factor_req_1", requirement_id="req-1", status="satisfied")],
        "evaluations": [
            {
                "requirement_id": "req-1",
                "result": "not_satisfied",
                "explanation": "no",
                "rule_id": "required_skills_v2",
                "job_evidence_refs": [],
                "candidate_evidence_refs": [],
            }
        ],
        "evidence": {},
    }
    with pytest.raises(MatchEvidenceConsistencyError) as exc:
        validate_match_evidence_payload(payload)
    assert "factor_evaluation_status_mismatch" in exc.value.reasons


def test_group_operator_matrix() -> None:
    assert _combine_group(["satisfied", "not_satisfied"], "any_of") == "satisfied"
    assert _combine_group(["not_satisfied", "not_satisfied"], "any_of") == "not_satisfied"
    assert _combine_group(["unknown", "not_satisfied"], "any_of") == "unknown"
    assert _combine_group(["satisfied", "satisfied"], "all_of") == "satisfied"
    assert _combine_group(["satisfied", "not_satisfied"], "all_of") == "not_satisfied"
    assert _combine_group(["satisfied", "unknown"], "all_of") == "unknown"


def test_any_of_skill_group_one_satisfied(isolated_session) -> None:
    candidate = Candidate(
        user_id=1,
        name="A",
        email="a@example.com",
        skills=["Python"],
        projects=[],
        experience=[],
        education=[],
        certifications=[],
        strengths=[],
        evidence_links=[],
    )
    profile = _group_profile(
        "any_of",
        [
            _req("r-python", "skill", "Python or Java required", name="Python"),
            _req("r-java", "skill", "Python or Java required", name="Java"),
        ],
    )
    report = evaluate_eligibility(profile, candidate, None, as_of=AS_OF)
    assert report.groups[0].status == "satisfied"
    by_id = {item.requirement_id: item.status for item in report.comparisons}
    assert by_id["r-python"] == "satisfied"
    assert by_id["r-java"] == "unknown"
    assert report.status != "likely_ineligible"


def test_any_of_all_unknown_is_unknown() -> None:
    candidate = Candidate(
        user_id=1,
        name="A",
        email="a@example.com",
        skills=[],
        projects=[],
        experience=[],
        education=[],
        certifications=[],
        strengths=[],
        evidence_links=[],
    )
    profile = _group_profile(
        "any_of",
        [
            _req("r-python", "skill", "Python or Java required", name="Python"),
            _req("r-java", "skill", "Python or Java required", name="Java"),
        ],
    )
    report = evaluate_eligibility(profile, candidate, None, as_of=AS_OF)
    assert report.groups[0].status == "unknown"


def test_all_of_one_unknown_and_duplicate_alias() -> None:
    candidate = Candidate(
        user_id=1,
        name="A",
        email="a@example.com",
        skills=["React"],
        projects=[],
        experience=[],
        education=[],
        certifications=[],
        strengths=[],
        evidence_links=[],
    )
    alias_profile = _group_profile(
        "all_of",
        [
            _req("r-react", "skill", "React.js preferred", importance="preferred", name="React.js"),
            _req("r-react-alias", "skill", "React", importance="preferred", name="React"),
        ],
        importance="preferred",
    )
    report = evaluate_eligibility(alias_profile, candidate, None, as_of=AS_OF)
    assert {item.status for item in report.comparisons} == {"satisfied"}
    assert report.groups[0].status == "satisfied"

    unknown_profile = _group_profile(
        "all_of",
        [
            _req("r-enrolled", "currently_enrolled", "Currently enrolled in a bachelor's program", importance="hard_required"),
            _req("r-auth", "work_authorization", "Must be authorized to work in the United States", importance="hard_required", region="us"),
        ],
        importance="hard_required",
    )
    report = evaluate_eligibility(unknown_profile, candidate, None, as_of=AS_OF)
    assert report.groups[0].status == "unknown"
    assert report.status == "eligibility_uncertain"


def test_hard_required_enrollment_is_not_softened() -> None:
    candidate = Candidate(
        user_id=1,
        name="A",
        email="a@example.com",
        skills=["Python"],
        projects=[],
        experience=[],
        education=[],
        certifications=[],
        strengths=[],
        evidence_links=[],
    )
    prefs = TargetPreference(
        user_id=1,
        currently_enrolled_in_program="no",
        academic_year="junior",
        expected_graduation="2028-05",
    )
    profile = JobRequirementProfile(
        source_fingerprint="block",
        requirements=[
            _req("r-enrolled", "currently_enrolled", "Currently enrolled in a bachelor's program", importance="hard_required")
        ],
    )
    report = evaluate_eligibility(profile, candidate, prefs, as_of=AS_OF)
    assert report.status == "likely_ineligible"
    assert report.comparisons[0].status == "not_satisfied"


def test_alias_and_duplicate_skills_do_not_split_cards(isolated_session) -> None:
    _user(isolated_session)
    job = _job(isolated_session, public_id="alias-dupes")
    _intel(
        isolated_session,
        job,
        required_skills=["JavaScript", "javascript", "Node.js", "NodeJS"],
        preferred_skills=["React.js", "React"],
        tech_stack=["Node.js"],
    )
    candidate = _candidate(isolated_session, 1)
    _prefs(isolated_session, candidate)
    score_job_verified(isolated_session, job, 1, as_of=AS_OF)
    payload = get_match_evidence(isolated_session, job.public_id, 1)
    assert_coherent_evidence(payload)

    skill_rows = [
        item
        for item in payload.factors
        if item.category == "skill" and item.id not in {"factor_required_skills", "factor_preferred_skills"}
    ]
    labels = [item.label.lower() for item in skill_rows]
    assert labels.count("javascript") == 1
    assert sum(1 for item in labels if item in {"node.js", "nodejs"}) == 1
    assert labels.count("react") == 1
    assert not any(item.status == "not_satisfied" and item.label.lower() in {"javascript", "react", "node.js"} for item in skill_rows)
    required = next(item for item in payload.factors if item.id == "factor_required_skills")
    assert required.status == "satisfied"
    assert required.score_contribution == required.max_contribution
    assert required.score_contribution != 0


def test_project_only_and_experience_only_skills(isolated_session) -> None:
    _user(isolated_session)
    job = _job(
        isolated_session,
        public_id="grounded-skills",
        description="Python required. SQL preferred.\n" + ("Team rituals. " * 40),
    )
    _intel(isolated_session, job, required_skills=["Python"], preferred_skills=["SQL"], tech_stack=[])
    candidate = _candidate(
        isolated_session,
        1,
        skills=[],
        projects=[{"name": "PagePulse", "description": "Built PagePulse using Python.", "technologies": ["Python"]}],
        experience=[{"title": "Intern", "company": "Northwind", "highlights": ["Wrote SQL reports"]}],
    )
    _prefs(isolated_session, candidate)
    score_job_verified(isolated_session, job, 1, as_of=AS_OF)
    payload = get_match_evidence(isolated_session, job.public_id, 1)
    assert_coherent_evidence(payload)
    python = next(item for item in payload.factors if item.label.lower() == "python")
    sql = next(item for item in payload.factors if item.label.lower() == "sql")
    assert python.status == "satisfied"
    assert payload.evidence[python.candidate_evidence_refs[0]].source_type == "candidate_project"
    assert sql.status == "satisfied"
    assert payload.evidence[sql.candidate_evidence_refs[0]].source_type == "candidate_experience"


def test_missing_required_is_unknown_while_component_earns_zero(isolated_session) -> None:
    _user(isolated_session)
    job = _job(
        isolated_session,
        public_id="missing-required",
        description="Docker required. Python preferred.\n" + ("Team rituals. " * 40),
    )
    _intel(isolated_session, job, required_skills=["Docker"], preferred_skills=["Python"], tech_stack=[])
    candidate = _candidate(isolated_session, 1, skills=["Python"], projects=[])
    _prefs(isolated_session, candidate)
    score_job_verified(isolated_session, job, 1, as_of=AS_OF)
    payload = get_match_evidence(isolated_session, job.public_id, 1)
    assert_coherent_evidence(payload)
    docker = next(item for item in payload.factors if item.label.lower() == "docker")
    required = next(item for item in payload.factors if item.id == "factor_required_skills")
    python = next(item for item in payload.factors if item.label.lower() == "python")
    assert docker.status == "unknown"
    assert docker.candidate_evidence_refs == []
    assert "does not have enough evidence" in docker.explanation.lower()
    assert required.status == "not_satisfied"
    assert required.score_contribution == 0
    assert required.max_contribution == 25
    assert python.importance == "preferred"
    assert python.hard_blocker is False
    assert python.status == "satisfied"


def test_partial_posting_is_not_verified_evidence(isolated_session) -> None:
    _user(isolated_session)
    job = _job(
        isolated_session,
        public_id="partial-adzuna",
        source="adzuna",
        content_status="partial",
        description="Python intern. Short snippet.",
    )
    _intel(isolated_session, job, required_skills=["Python"], preferred_skills=[], tech_stack=[])
    candidate = _candidate(isolated_session, 1, skills=["Python"])
    _prefs(isolated_session, candidate)
    score = score_job_verified(isolated_session, job, 1, as_of=AS_OF)
    payload = get_match_evidence(isolated_session, job.public_id, 1)
    assert score.score_kind != "verified"
    assert payload.full_evidence is False
    assert payload.provenance.stale is False


def test_stale_preferences_and_requirements(isolated_session) -> None:
    _user(isolated_session)
    job = _job(isolated_session, public_id="stale-fps")
    _intel(isolated_session, job, required_skills=["Python"], preferred_skills=[], tech_stack=[])
    candidate = _candidate(isolated_session, 1, skills=["Python"])
    prefs = _prefs(isolated_session, candidate, academic_year="final_year")
    score_job_verified(isolated_session, job, 1, as_of=AS_OF)

    prefs.academic_year = "junior"
    isolated_session.commit()
    payload = get_match_evidence(isolated_session, job.public_id, 1)
    assert payload.provenance.stale is True
    assert "preferences" in payload.provenance.stale_reasons
    assert payload.full_evidence is False

    row = isolated_session.query(MatchEvidenceRecord).one()
    row.candidate_fingerprint = row.candidate_fingerprint
    row.preference_fingerprint = row.preference_fingerprint
    prefs.academic_year = "final_year"
    isolated_session.commit()
    row.requirement_fingerprint = "stale-requirements"
    isolated_session.commit()
    payload = get_match_evidence(isolated_session, job.public_id, 1)
    assert payload.provenance.stale is True
    assert "job_requirements" in payload.provenance.stale_reasons
    assert payload.full_evidence is False
