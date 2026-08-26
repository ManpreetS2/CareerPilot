"""Grounded job-requirement extraction and API regressions."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from unittest.mock import Mock, patch

import pytest

from backend.db.models import JobIntelligenceRecord, JobRecord
from backend.services.analysis_service import JobNotFoundError, score_job
from backend.services.job_intelligence_service import (
    EmptyGroundedIntelligenceError,
    JobIntelligenceNotFoundError,
    PostingEvidenceError,
    StructuredIntelligenceError,
    extract_job_intelligence,
    get_stored_job_intelligence,
    ground_job_intelligence,
)
from backend.services.llm_client import LLMProviderError
from backend.services.llm_client import LLMConfigurationError


def _job(
    session,
    *,
    public_id: str = "job-intelligence-001",
    title: str = "Senior Platform Engineer",
    description: str = (
        "Requirements:\n"
        "- Python\n"
        "- Terraform\n"
        "- 4 years of professional experience\n"
        "- Bachelor's degree in Computer Science\n"
        "Preferred:\n"
        "- PostgreSQL\n"
        "Technology stack:\n"
        "- Docker\n"
        "Responsibilities:\n"
        "- Improve API latency by 20%.\n"
        "Interview topics:\n"
        "- Distributed systems"
    ),
) -> JobRecord:
    record = JobRecord(
        public_id=public_id,
        title=title,
        company="Fictional Meridian Systems",
        location="Remote",
        salary=None,
        url=f"https://example.invalid/jobs/{public_id}",
        description=description,
        source="test",
        status="verified",
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _payload(**overrides) -> dict:
    payload = {
        "job_id": None,
        "required_skills": ["Python", "Terraform"],
        "preferred_skills": ["PostgreSQL"],
        "years_experience": 4,
        "education_requirements": ["Bachelor's degree in Computer Science"],
        "tech_stack": ["Docker"],
        "seniority": "Senior",
        "responsibilities": ["Improve API latency by 20%."],
        "likely_interview_focus": ["Distributed systems"],
    }
    payload.update(overrides)
    return payload


def _json_generator(payload: dict) -> Callable[[str, str | None], str]:
    return lambda _prompt, _system: json.dumps(payload)


class SequenceGenerator:
    def __init__(self, *responses: str | Exception) -> None:
        self.responses = list(responses)
        self.prompts: list[tuple[str, str | None]] = []

    def __call__(self, prompt: str, system: str | None) -> str:
        self.prompts.append((prompt, system))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_valid_structured_extraction_is_grounded_and_persisted(isolated_session) -> None:
    job = _job(isolated_session)
    prompts = SequenceGenerator(json.dumps(_payload()))

    result = extract_job_intelligence(
        isolated_session,
        job.public_id,
        generate_fn=prompts,
    )

    assert result.job_id == job.public_id
    assert result.required_skills == ["Python", "Terraform"]
    assert result.preferred_skills == ["PostgreSQL"]
    assert result.tech_stack == ["Docker"]
    assert result.years_experience == 4
    assert result.education_requirements == ["Bachelor's degree in Computer Science"]
    assert result.seniority == "Senior"
    assert result.responsibilities == ["Improve API latency by 20%."]
    assert result.likely_interview_focus == ["Distributed systems"]
    assert isolated_session.query(JobIntelligenceRecord).count() == 1
    prompt = prompts.prompts[0][0]
    assert job.title in prompt and job.description in prompt
    assert "candidate" not in prompt.lower()
    assert "preference" not in prompt.lower()
    assert '"job_id"' not in prompt


def test_invalid_json_gets_one_structured_correction_attempt(isolated_session) -> None:
    job = _job(isolated_session)
    generator = SequenceGenerator("not json", json.dumps(_payload()))

    result = extract_job_intelligence(
        isolated_session,
        job.public_id,
        generate_fn=generator,
    )

    assert result.required_skills == ["Python", "Terraform"]
    assert len(generator.prompts) == 2
    assert "previous output was invalid" in generator.prompts[1][0].lower()


@pytest.mark.parametrize(
    "responses",
    [
        ("not json", "still not json"),
        ("[]", "[]"),
        ('{"required_skills": 7}', '{"required_skills": false}'),
    ],
)
def test_two_invalid_structured_responses_fail_without_persistence(
    isolated_session,
    responses: tuple[str, str],
) -> None:
    job = _job(isolated_session)
    generator = SequenceGenerator(*responses)

    with pytest.raises(StructuredIntelligenceError):
        extract_job_intelligence(
            isolated_session,
            job.public_id,
            generate_fn=generator,
        )

    assert len(generator.prompts) == 2
    assert isolated_session.query(JobIntelligenceRecord).count() == 0


def test_two_empty_structured_objects_exhaust_the_provider_without_grounding(
    isolated_client,
) -> None:
    """{} is schema-invalid as a complete extraction. Both attempts must
    exhaust structured retries as a 502, not slip into grounding as 409."""
    client, SessionLocal = isolated_client
    with SessionLocal() as session:
        job = _job(session)
    fake_client = Mock()
    fake_client.generate.side_effect = ["{}", "{}"]

    with patch(
        "backend.services.job_intelligence_service.get_llm_client",
        return_value=fake_client,
    ):
        response = client.post(f"/api/jobs/{job.public_id}/intelligence")

    assert response.status_code == 502
    assert response.json() == {"detail": "Unable to extract structured job requirements."}
    assert fake_client.generate.call_count == 2
    with SessionLocal() as session:
        assert session.query(JobIntelligenceRecord).count() == 0


def test_all_output_keys_present_but_empty_is_unusable_on_both_attempts(
    isolated_session,
) -> None:
    all_empty = json.dumps(
        _payload(
            required_skills=[],
            preferred_skills=[],
            years_experience=None,
            education_requirements=[],
            tech_stack=[],
            seniority=None,
            responsibilities=[],
            likely_interview_focus=[],
        )
    )
    job = _job(isolated_session)
    generator = SequenceGenerator(all_empty, all_empty)

    with pytest.raises(StructuredIntelligenceError):
        extract_job_intelligence(
            isolated_session,
            job.public_id,
            generate_fn=generator,
        )

    assert len(generator.prompts) == 2
    assert isolated_session.query(JobIntelligenceRecord).count() == 0


def test_invalid_first_then_empty_second_exhausts_the_provider(
    isolated_session,
) -> None:
    job = _job(isolated_session)
    generator = SequenceGenerator("not json", "{}")

    with pytest.raises(StructuredIntelligenceError):
        extract_job_intelligence(
            isolated_session,
            job.public_id,
            generate_fn=generator,
        )

    assert len(generator.prompts) == 2
    assert isolated_session.query(JobIntelligenceRecord).count() == 0


def test_prompt_and_raw_schema_agree_and_exclude_job_id(isolated_session) -> None:
    from backend.services.job_intelligence_service import build_extraction_prompts
    from backend.services.llm_structured_schemas import job_intelligence_llm_schema

    job = _job(isolated_session)
    _system, user_prompt = build_extraction_prompts(job)
    schema = job_intelligence_llm_schema()
    expected = {
        "required_skills",
        "preferred_skills",
        "years_experience",
        "education_requirements",
        "tech_stack",
        "seniority",
        "responsibilities",
        "likely_interview_focus",
    }
    assert set(schema["properties"].keys()) == expected
    assert set(schema["required"]) == expected
    assert schema["additionalProperties"] is False
    assert "job_id" not in schema["properties"]
    assert '"job_id"' not in user_prompt
    for key in expected:
        assert f'"{key}"' in user_prompt


def test_provider_failure_creates_no_row_and_does_not_retry_structured_output(
    isolated_session,
) -> None:
    job = _job(isolated_session)
    generator = SequenceGenerator(LLMProviderError("provider payload must stay private"))

    with pytest.raises(LLMProviderError):
        extract_job_intelligence(
            isolated_session,
            job.public_id,
            generate_fn=generator,
        )

    assert len(generator.prompts) == 1
    assert isolated_session.query(JobIntelligenceRecord).count() == 0


def test_unknown_job_and_empty_description_fail_before_provider(isolated_session) -> None:
    generator = Mock(side_effect=AssertionError("provider must not run"))
    with pytest.raises(JobNotFoundError):
        extract_job_intelligence(
            isolated_session,
            "missing-job",
            generate_fn=generator,
        )
    job = _job(isolated_session, description="   ")
    with pytest.raises(PostingEvidenceError):
        extract_job_intelligence(
            isolated_session,
            job.public_id,
            generate_fn=generator,
        )
    generator.assert_not_called()
    assert isolated_session.query(JobIntelligenceRecord).count() == 0


def test_hallucinations_are_dropped_and_source_classification_wins(isolated_session) -> None:
    job = _job(
        isolated_session,
        title="Platform Engineer",
        description=(
            "Requirements:\nPython\n"
            "Preferred:\nTerraform\n"
            "Technology stack:\nDocker"
        ),
    )
    raw = _payload(
        required_skills=["Python", "Terraform", "Quantum Teleportation"],
        preferred_skills=["Docker", "Warp Drive"],
        tech_stack=["Python"],
        years_experience=None,
        education_requirements=[],
        seniority=None,
        responsibilities=[],
        likely_interview_focus=[],
    )

    grounded, counts = ground_job_intelligence(raw, job)

    assert grounded.required_skills == ["Python"]
    assert grounded.preferred_skills == ["Terraform"]
    assert grounded.tech_stack == ["Docker"]
    assert "Quantum Teleportation" not in grounded.required_skills
    assert "Warp Drive" not in grounded.preferred_skills
    assert counts["skills"] == 3


def test_required_and_preferred_clauses_on_one_line_stay_distinct(
    isolated_session,
) -> None:
    job = _job(
        isolated_session,
        title="Platform Engineer",
        description="Python is required; Terraform is preferred; the stack uses Docker.",
    )
    raw = _payload(
        required_skills=["Python", "Terraform", "Docker"],
        preferred_skills=[],
        tech_stack=[],
        years_experience=None,
        education_requirements=[],
        seniority=None,
        responsibilities=[],
        likely_interview_focus=[],
    )

    grounded, _counts = ground_job_intelligence(raw, job)

    assert grounded.required_skills == ["Python"]
    assert grounded.preferred_skills == ["Terraform"]
    assert grounded.tech_stack == ["Docker"]


def test_preferred_qualifications_and_sentence_clauses_remain_preferred(
    isolated_session,
) -> None:
    job = _job(
        isolated_session,
        title="Platform Engineer",
        description=(
            "Preferred Skills\n"
            "Terraform\n"
            "Python is required. iOS is preferred."
        ),
    )
    raw = _payload(
        required_skills=["Python", "Terraform", "iOS"],
        preferred_skills=[],
        tech_stack=[],
        years_experience=None,
        education_requirements=[],
        seniority=None,
        responsibilities=[],
        likely_interview_focus=[],
    )

    grounded, _counts = ground_job_intelligence(raw, job)

    assert grounded.required_skills == ["Python"]
    assert grounded.preferred_skills == ["Terraform", "iOS"]


def test_alias_duplicates_are_canonicalized_across_categories(isolated_session) -> None:
    job = _job(
        isolated_session,
        title="Database Engineer",
        description="Requirements:\nPostgres\nPreferred:\nPostgreSQL",
    )
    raw = _payload(
        required_skills=["PostgreSQL"],
        preferred_skills=["Postgres"],
        tech_stack=[],
        years_experience=None,
        education_requirements=[],
        seniority=None,
        responsibilities=[],
        likely_interview_focus=[],
    )

    grounded, _counts = ground_job_intelligence(raw, job)

    assert grounded.required_skills == ["PostgreSQL"]
    assert grounded.preferred_skills == []
    assert grounded.tech_stack == []


def test_unknown_exact_technology_requires_complete_bounded_evidence(isolated_session) -> None:
    job = _job(
        isolated_session,
        title="Infrastructure Engineer",
        description="Requirements:\nTerraform and Terragrunt.",
    )
    raw = _payload(
        required_skills=["Terraform", "Terra", "Terragrunt"],
        preferred_skills=[],
        tech_stack=[],
        years_experience=None,
        education_requirements=[],
        seniority=None,
        responsibilities=[],
        likely_interview_focus=[],
    )

    grounded, _counts = ground_job_intelligence(raw, job)

    assert grounded.required_skills == ["Terraform", "Terragrunt"]
    assert "Terra" not in grounded.required_skills


def test_role_words_are_not_retained_as_unknown_technologies(isolated_session) -> None:
    job = _job(
        isolated_session,
        title="Senior Terraform Engineer",
        description="Requirements:\nTerraform",
    )
    raw = _payload(
        required_skills=["Senior", "Terraform", "Engineer"],
        preferred_skills=[],
        tech_stack=[],
        years_experience=None,
        education_requirements=[],
        seniority="Senior",
        responsibilities=[],
        likely_interview_focus=[],
    )

    grounded, _counts = ground_job_intelligence(raw, job)

    assert grounded.required_skills == ["Terraform"]
    assert grounded.tech_stack == []
    assert grounded.seniority == "Senior"


def test_ordinary_posting_words_are_not_retained_as_unknown_technologies(
    isolated_session,
) -> None:
    job = _job(
        isolated_session,
        title="Platform Engineer",
        description="Join our collaborative team.\nRequirements:\nPython",
    )
    raw = _payload(
        required_skills=["team", "collaborative", "Python"],
        preferred_skills=[],
        tech_stack=[],
        years_experience=None,
        education_requirements=[],
        seniority=None,
        responsibilities=[],
        likely_interview_focus=[],
    )

    grounded, _counts = ground_job_intelligence(raw, job)

    assert grounded.required_skills == ["Python"]
    assert grounded.tech_stack == []


def test_colonless_section_heading_resets_unknown_technology_context(
    isolated_session,
) -> None:
    job = _job(
        isolated_session,
        title="Platform Engineer",
        description=(
            "Requirements:\n"
            "Terraform\n"
            "About Us\n"
            "Join our collaborative team."
        ),
    )
    raw = _payload(
        required_skills=["Terraform", "team", "collaborative"],
        preferred_skills=[],
        tech_stack=[],
        years_experience=None,
        education_requirements=[],
        seniority=None,
        responsibilities=[],
        likely_interview_focus=[],
    )

    grounded, _counts = ground_job_intelligence(raw, job)

    assert grounded.required_skills == ["Terraform"]


def test_colonless_section_heading_resets_known_skill_category(
    isolated_session,
) -> None:
    job = _job(
        isolated_session,
        title="Platform Engineer",
        description=(
            "Requirements:\n"
            "Python\n"
            "Why Join Us\n"
            "Our product is deployed with Docker."
        ),
    )
    raw = _payload(
        required_skills=["Python", "Docker"],
        preferred_skills=[],
        tech_stack=[],
        years_experience=None,
        education_requirements=[],
        seniority=None,
        responsibilities=[],
        likely_interview_focus=[],
    )

    grounded, _counts = ground_job_intelligence(raw, job)

    assert grounded.required_skills == ["Python"]
    assert grounded.tech_stack == ["Docker"]


@pytest.mark.parametrize(
    ("description", "claims", "kept"),
    [
        ("Requirements: JavaScript", ["Java", "JavaScript"], ["JavaScript"]),
        ("We use Google Cloud and Django for ongoing work.", ["Go"], []),
        ("Requirements: C++ and C#", ["C", "C++", "C#"], ["C++", "C#"]),
        ("Requirements: React Native", ["React"], []),
        ("Requirements: Node.js", ["Node", "Node.js"], ["Node.js"]),
    ],
)
def test_short_token_and_substring_attacks_are_rejected(
    isolated_session,
    description: str,
    claims: list[str],
    kept: list[str],
) -> None:
    job = _job(isolated_session, title="Engineer", description=description)
    raw = _payload(
        required_skills=claims,
        preferred_skills=[],
        tech_stack=[],
        years_experience=None,
        education_requirements=[],
        seniority=None,
        responsibilities=[],
        likely_interview_focus=[],
    )

    grounded, _counts = ground_job_intelligence(raw, job)

    assert grounded.required_skills == kept


@pytest.mark.parametrize(
    ("description", "model_years", "expected"),
    [
        ("Requirements: 4 years of professional experience.", 4, 4),
        ("Requirements: 4 years of professional experience.", 5, None),
        ("Founded in 2019. Requirements: Python.", 19, None),
        ("Requirements: Python.", 4, None),
        ("Requirements: 4 years of professional experience.", True, None),
        ("Requirements: 1 year of professional experience.", True, None),
        ("Requirements: 99 years of professional experience.", 99, None),
        ("Requirements: 4 years of professional experience.", -4, None),
        ("Candidates do not need 4 years of professional experience.", 4, None),
        ("Requirements: Up to 5 years of professional experience.", 5, None),
        ("Requirements: 4 years of experience is not required.", 4, None),
        ("No 4 years of experience are required.", 4, None),
        ("Four years are optional; 4 years of experience are optional.", 4, None),
        ("Candidates need not have 4 years of experience.", 4, None),
        ("Requirements: 4 years of experience are not necessary.", 4, None),
        ("Requirements: 4 years of experience are unnecessary.", 4, None),
        (
            "Requirements: 4 years of experience required, not including internships.",
            4,
            4,
        ),
    ],
)
def test_years_require_exact_plausible_work_experience_evidence(
    isolated_session,
    description: str,
    model_years: int | bool,
    expected: int | None,
) -> None:
    job = _job(isolated_session, title="Engineer", description=description)
    raw = _payload(
        required_skills=[],
        preferred_skills=[],
        tech_stack=[],
        years_experience=model_years,
        education_requirements=[],
        seniority=None,
        responsibilities=[],
        likely_interview_focus=[],
    )

    grounded, _counts = ground_job_intelligence(raw, job)

    assert grounded.years_experience == expected


def test_education_uses_closed_aliases_and_drops_unsupported_claims(isolated_session) -> None:
    job = _job(
        isolated_session,
        title="Engineer",
        description=(
            "Qualifications:\n"
            "Bachelor of Science degree in Computer Science required."
        ),
    )
    raw = _payload(
        required_skills=[],
        preferred_skills=[],
        tech_stack=[],
        years_experience=None,
        education_requirements=[
            "Bachelor's degree in Computer Science",
            "Bachelor's degree in History",
            "Master's degree in Physics",
            "BS in CS",
        ],
        seniority=None,
        responsibilities=[],
        likely_interview_focus=[],
    )

    grounded, _counts = ground_job_intelligence(raw, job)

    assert grounded.education_requirements == ["Bachelor's degree in Computer Science"]


def test_distinct_exact_unknown_education_fields_are_not_deduplicated(
    isolated_session,
) -> None:
    job = _job(
        isolated_session,
        title="Research Editor",
        description=(
            "Qualifications:\n"
            "Bachelor's degree in History\n"
            "Bachelor's degree in English"
        ),
    )
    raw = _payload(
        required_skills=[],
        preferred_skills=[],
        tech_stack=[],
        years_experience=None,
        education_requirements=[
            "Bachelor's degree in History",
            "Bachelor's degree in English",
        ],
        seniority=None,
        responsibilities=[],
        likely_interview_focus=[],
    )

    grounded, _counts = ground_job_intelligence(raw, job)

    assert grounded.education_requirements == [
        "Bachelor's degree in History",
        "Bachelor's degree in English",
    ]


@pytest.mark.parametrize(
    ("title", "model_seniority", "expected"),
    [
        ("Senior Platform Engineer", "Senior", "Senior"),
        ("Senior Staff Platform Engineer", "Senior", None),
        ("Senior Staff Platform Engineer", "Senior Staff", "Senior Staff"),
        ("Platform Engineer", "Senior", None),
        ("Platform Engineer", "Staff", None),
        ("Mid-level Platform Engineer", "Mid-level", "Mid-level"),
        ("Entry-level Platform Engineer", "Entry-level", "Entry-level"),
    ],
)
def test_seniority_preserves_meaningful_modifiers(
    isolated_session,
    title: str,
    model_seniority: str,
    expected: str | None,
) -> None:
    job = _job(isolated_session, title=title, description="Requirements:\nPython")
    raw = _payload(
        required_skills=["Python"],
        preferred_skills=[],
        tech_stack=[],
        years_experience=None,
        education_requirements=[],
        seniority=model_seniority,
        responsibilities=[],
        likely_interview_focus=[],
    )

    grounded, _counts = ground_job_intelligence(raw, job)

    assert grounded.seniority == expected


def test_seniority_is_not_inferred_from_stakeholder_wording(isolated_session) -> None:
    job = _job(
        isolated_session,
        title="Platform Engineer",
        description="Requirements: Python. Collaborate with senior stakeholders.",
    )
    raw = _payload(
        required_skills=["Python"],
        preferred_skills=[],
        tech_stack=[],
        years_experience=None,
        education_requirements=[],
        seniority="Senior",
        responsibilities=[],
        likely_interview_focus=[],
    )

    grounded, _counts = ground_job_intelligence(raw, job)

    assert grounded.seniority is None


def test_seniority_is_not_inferred_from_action_wording(isolated_session) -> None:
    job = _job(
        isolated_session,
        title="Platform Engineer",
        description=(
            "You will lead projects and partner with the product manager.\n"
            "Requirements: Python"
        ),
    )
    raw = _payload(
        required_skills=["Python"],
        preferred_skills=[],
        tech_stack=[],
        years_experience=None,
        education_requirements=[],
        seniority="Lead",
        responsibilities=[],
        likely_interview_focus=[],
    )

    grounded, _counts = ground_job_intelligence(raw, job)

    assert grounded.seniority is None


def test_explicit_lead_role_wording_is_retained(isolated_session) -> None:
    job = _job(
        isolated_session,
        title="Platform Engineer",
        description="You will be the lead engineer for the platform.\nRequirements: Python",
    )
    raw = _payload(
        required_skills=["Python"],
        preferred_skills=[],
        tech_stack=[],
        years_experience=None,
        education_requirements=[],
        seniority="Lead",
        responsibilities=[],
        likely_interview_focus=[],
    )

    grounded, _counts = ground_job_intelligence(raw, job)

    assert grounded.seniority == "Lead"


@pytest.mark.parametrize(
    ("title", "description", "claim"),
    [
        ("Lead Generation Engineer", "Requirements: Python", "Lead"),
        (
            "Platform Engineer",
            "Associate's degree required for this engineer role.",
            "Associate",
        ),
        ("Data Entry Engineer", "Requirements: Python", "Entry"),
    ],
)
def test_seniority_rejects_non_level_role_context(
    isolated_session,
    title: str,
    description: str,
    claim: str,
) -> None:
    job = _job(isolated_session, title=title, description=description)
    raw = _payload(
        required_skills=["Python"] if "Python" in description else [],
        preferred_skills=[],
        tech_stack=[],
        years_experience=None,
        education_requirements=[],
        seniority=claim,
        responsibilities=[],
        likely_interview_focus=[],
    )

    grounded, _counts = ground_job_intelligence(raw, job)

    assert grounded.seniority is None


def test_responsibilities_and_interview_topics_require_traceable_exact_evidence(
    isolated_session,
) -> None:
    job = _job(
        isolated_session,
        title="Platform Engineer",
        description=(
            "At Fictional Meridian, you will enjoy comprehensive benefits.\n"
            "Requirements:\nPython\n"
            "Responsibilities:\nImprove API latency by 20%.\n"
            "Interview topics:\nDistributed systems\n"
            "Benefits & Perks\n"
            "Equal opportunity employer\n"
            "Compensation\n"
            "$150,000-$180,000\n"
            "Benefits:\n"
            "\n"
            "At Fictional Meridian you will enjoy comprehensive benefits."
        ),
    )
    raw = _payload(
        required_skills=["Python"],
        preferred_skills=[],
        tech_stack=[],
        years_experience=None,
        education_requirements=[],
        seniority=None,
        responsibilities=[
            "Improve API latency by 20%.",
            "Improve API latency",
            "Improve API latency by 50%.",
            "Double revenue.",
            "Python",
            "At Fictional Meridian, you will enjoy comprehensive benefits.",
            "At Fictional Meridian you will enjoy comprehensive benefits.",
        ],
        likely_interview_focus=[
            "Python",
            "Distributed systems",
            "systems",
            "Leadership psychology",
            "Equal opportunity employer",
            "Compensation",
            "$150,000-$180,000",
        ],
    )

    grounded, _counts = ground_job_intelligence(raw, job)

    assert grounded.responsibilities == ["Improve API latency by 20%."]
    assert grounded.likely_interview_focus == ["Python", "Distributed systems"]


def test_responsibility_sentence_grounds_from_an_unbulleted_paragraph(
    isolated_session,
) -> None:
    job = _job(
        isolated_session,
        title="Software Engineer Intern",
        description=(
            "Role Summary/Purpose: At Fictional Meridian, a software engineer "
            "internship allows you to gain real-world experience. You will learn "
            "how to code, test, and document changes for new product features. "
            "You will also learn the overall technology landscape and collaborate "
            "with a cross-functional team."
        ),
    )
    raw = _payload(
        required_skills=[],
        preferred_skills=[],
        tech_stack=[],
        years_experience=None,
        education_requirements=[],
        seniority=None,
        responsibilities=[
            "You will learn how to code, test, and document changes for new product features.",
            "Learn to code and ship features.",
            "Own the product roadmap end to end.",
        ],
        likely_interview_focus=[],
    )

    grounded, counts = ground_job_intelligence(raw, job)

    assert grounded.responsibilities == [
        "You will learn how to code, test, and document changes for new product features."
    ]
    assert counts["responsibilities"] == 2


def test_responsibility_sentence_grounds_across_multiple_real_line_breaks(
    isolated_session,
) -> None:
    job = _job(
        isolated_session,
        title="Platform Engineer",
        description=(
            "Responsibilities:\n"
            "Design and operate internal deployment tooling.\n"
            "On-call rotation for production incidents.\n"
            "Requirements:\nPython"
        ),
    )
    raw = _payload(
        required_skills=["Python"],
        preferred_skills=[],
        tech_stack=[],
        years_experience=None,
        education_requirements=[],
        seniority=None,
        responsibilities=[
            "Design and operate internal deployment tooling.",
            "On-call rotation for production incidents.",
        ],
        likely_interview_focus=[],
    )

    grounded, counts = ground_job_intelligence(raw, job)

    assert grounded.responsibilities == [
        "Design and operate internal deployment tooling.",
        "On-call rotation for production incidents.",
    ]
    assert counts["responsibilities"] == 0


def test_realistic_model_shaped_paragraph_output_grounds_end_to_end(
    isolated_session,
) -> None:
    job = _job(
        isolated_session,
        title="Software Engineer Intern - Fall 2026",
        description=(
            "Role Summary/Purpose: At Fictional Meridian, a software engineer "
            "internship allows you to gain experience while you are still "
            "pursuing your degree. You will learn how to code, test, and "
            "document changes for enhancements to existing software.\n"
            "Requirements:\nExperience with Python\n3 years of professional "
            "experience\nPreferred: Familiarity with Docker"
        ),
    )
    raw = json.dumps(
        {
            "required_skills": ["  Python ", "Python", "Quantum Blockchain AI"],
            "preferred_skills": ["Docker"],
            "years_experience": 3,
            "education_requirements": [],
            "tech_stack": [],
            "seniority": None,
            "responsibilities": [
                "You will learn how to code, test, and document changes for enhancements to existing software.",
                "Single-handedly rebuild the platform from scratch.",
            ],
            "likely_interview_focus": [],
        }
    )

    result = extract_job_intelligence(
        isolated_session,
        job.public_id,
        generate_fn=lambda _prompt, _system: raw,
    )

    assert result.required_skills == ["Python"]
    assert result.preferred_skills == ["Docker"]
    assert result.years_experience == 3
    assert result.responsibilities == [
        "You will learn how to code, test, and document changes for enhancements to existing software."
    ]
    assert isolated_session.query(JobIntelligenceRecord).count() == 1


def test_empty_grounded_result_returns_409_and_persists_nothing(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as session:
        job = _job(session, title="Engineer", description="Join our fictional team.")
    hallucination = _payload(
        required_skills=["Quantum Teleportation"],
        preferred_skills=[],
        tech_stack=[],
        years_experience=None,
        education_requirements=[],
        seniority=None,
        responsibilities=[],
        likely_interview_focus=[],
    )
    fake_client = Mock()
    fake_client.generate.return_value = json.dumps(hallucination)

    with patch(
        "backend.services.job_intelligence_service.get_llm_client",
        return_value=fake_client,
    ):
        response = client.post(f"/api/jobs/{job.public_id}/intelligence")

    assert response.status_code == 409
    assert response.json() == {"detail": "No supported job requirements were found."}
    with SessionLocal() as session:
        assert session.query(JobIntelligenceRecord).count() == 0


def test_successful_reextraction_upserts_one_row(isolated_session) -> None:
    job = _job(isolated_session)
    first = extract_job_intelligence(
        isolated_session,
        job.public_id,
        generate_fn=_json_generator(_payload()),
    )
    second_payload = _payload(
        required_skills=["Python"],
        preferred_skills=["Postgres"],
        tech_stack=[],
    )
    second = extract_job_intelligence(
        isolated_session,
        job.public_id,
        generate_fn=_json_generator(second_payload),
    )

    assert first.job_id == second.job_id
    assert second.required_skills == ["Python"]
    assert isolated_session.query(JobIntelligenceRecord).count() == 1


def test_failed_reextraction_preserves_prior_valid_record(isolated_session) -> None:
    job = _job(isolated_session)
    original = extract_job_intelligence(
        isolated_session,
        job.public_id,
        generate_fn=_json_generator(_payload()),
    )

    with pytest.raises(StructuredIntelligenceError):
        extract_job_intelligence(
            isolated_session,
            job.public_id,
            generate_fn=SequenceGenerator("invalid", "invalid again"),
        )

    stored = get_stored_job_intelligence(isolated_session, job.public_id)
    assert stored == original
    assert isolated_session.query(JobIntelligenceRecord).count() == 1


def test_commit_failure_rolls_back_new_and_existing_records(isolated_session) -> None:
    job = _job(isolated_session)
    with patch.object(isolated_session, "commit", side_effect=RuntimeError("private SQL error")):
        with pytest.raises(RuntimeError):
            extract_job_intelligence(
                isolated_session,
                job.public_id,
                generate_fn=_json_generator(_payload()),
            )
    isolated_session.rollback()
    assert isolated_session.query(JobIntelligenceRecord).count() == 0


def test_failed_update_commit_preserves_prior_valid_record(isolated_session) -> None:
    job = _job(isolated_session)
    original = extract_job_intelligence(
        isolated_session,
        job.public_id,
        generate_fn=_json_generator(_payload()),
    )
    replacement = _payload(required_skills=["Python"], preferred_skills=[], tech_stack=[])

    with patch.object(isolated_session, "commit", side_effect=RuntimeError("private SQL error")):
        with pytest.raises(RuntimeError):
            extract_job_intelligence(
                isolated_session,
                job.public_id,
                generate_fn=_json_generator(replacement),
            )
    isolated_session.rollback()

    assert get_stored_job_intelligence(isolated_session, job.public_id) == original
    assert isolated_session.query(JobIntelligenceRecord).count() == 1


def test_success_response_does_not_depend_on_post_commit_refresh(isolated_session) -> None:
    job = _job(isolated_session)

    with patch.object(
        isolated_session,
        "refresh",
        side_effect=RuntimeError("post-commit refresh failure"),
    ):
        result = extract_job_intelligence(
            isolated_session,
            job.public_id,
            generate_fn=_json_generator(_payload()),
        )

    assert result.job_id == job.public_id
    assert result.required_skills == ["Python", "Terraform"]
    assert isolated_session.query(JobIntelligenceRecord).count() == 1


def test_get_endpoint_never_calls_provider_and_reports_not_generated(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as session:
        job = _job(session)

    with patch(
        "backend.services.job_intelligence_service.get_llm_client",
        side_effect=AssertionError("GET must not call a provider"),
    ):
        response = client.get(f"/api/jobs/{job.public_id}/intelligence")

    assert response.status_code == 404
    assert response.json() == {"detail": "Job requirements have not been extracted."}


def test_post_is_the_only_provider_triggering_route(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as session:
        job = _job(session)
    fake_client = Mock()
    fake_client.generate.return_value = json.dumps(_payload())

    with patch(
        "backend.services.job_intelligence_service.get_llm_client",
        return_value=fake_client,
    ):
        assert client.get(f"/api/jobs/{job.public_id}/intelligence").status_code == 404
        response = client.post(f"/api/jobs/{job.public_id}/intelligence")
        assert client.get(f"/api/jobs/{job.public_id}/intelligence").status_code == 200

    assert response.status_code == 200
    assert fake_client.generate.call_count == 1


def test_api_statuses_are_sanitized(isolated_client) -> None:
    client, SessionLocal = isolated_client
    unknown = client.get("/api/jobs/not-there/intelligence")
    assert unknown.status_code == 404
    with SessionLocal() as session:
        job = _job(session, description="")
    missing = client.post(f"/api/jobs/{job.public_id}/intelligence")
    assert missing.status_code == 409
    assert "description" not in missing.json()["detail"].lower()


@pytest.mark.parametrize(
    ("failure", "expected_status", "expected_detail"),
    [
        (
            LLMConfigurationError("GEMINI_API_KEY=secret-value"),
            503,
            "Job requirement extraction is not configured.",
        ),
        (
            LLMProviderError("private provider payload"),
            502,
            "Unable to extract structured job requirements.",
        ),
    ],
)
def test_provider_and_configuration_failures_are_sanitized(
    isolated_client,
    failure: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as session:
        job = _job(session)
    fake_client = Mock()
    fake_client.generate.side_effect = failure

    with patch(
        "backend.services.job_intelligence_service.get_llm_client",
        return_value=fake_client,
    ):
        response = client.post(f"/api/jobs/{job.public_id}/intelligence")

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    assert "secret-value" not in response.text
    assert "provider payload" not in response.text
    with SessionLocal() as session:
        assert session.query(JobIntelligenceRecord).count() == 0


def test_api_commit_failure_is_sanitized_and_leaves_no_row(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as session:
        job = _job(session)
    fake_client = Mock()
    fake_client.generate.return_value = json.dumps(_payload())

    with patch(
        "backend.services.job_intelligence_service.get_llm_client",
        return_value=fake_client,
    ):
        with patch(
            "sqlalchemy.orm.Session.commit",
            side_effect=RuntimeError("private database statement"),
        ):
            response = client.post(f"/api/jobs/{job.public_id}/intelligence")

    assert response.status_code == 500
    assert response.json() == {"detail": "Unable to save extracted job requirements."}
    assert "private database statement" not in response.text
    with SessionLocal() as session:
        assert session.query(JobIntelligenceRecord).count() == 0


def test_logs_contain_only_ids_attempts_and_counts(
    isolated_session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    job = _job(isolated_session)
    private_marker = "PRIVATE_POSTING_MARKER"
    private_payload = _payload(
        required_skills=["Python", private_marker],
        responsibilities=[private_marker],
    )

    with caplog.at_level(logging.INFO, logger="backend.services.job_intelligence_service"):
        extract_job_intelligence(
            isolated_session,
            job.public_id,
            generate_fn=_json_generator(private_payload),
        )

    assert private_marker not in caplog.text
    assert job.description not in caplog.text
    assert "job_pk=" in caplog.text
    assert "counts=" in caplog.text


def test_scoring_uses_stored_intelligence_without_provider_or_mutation(
    isolated_session,
) -> None:
    from tests.test_fit_scoring import TEST_USER_ID, _candidate

    _candidate(
        isolated_session,
        skills=["Python"],
        experience=[],
        education=[],
        projects=[],
        certifications=[],
    )
    job = _job(
        isolated_session,
        title="Backend Engineer",
        description="Python is required. Docker is preferred.",
    )
    fallback = score_job(isolated_session, job.public_id, TEST_USER_ID)
    assert "provisional" in fallback.rationale.lower()
    assert fallback.skill_score == 75.0
    extracted = extract_job_intelligence(
        isolated_session,
        job.public_id,
        generate_fn=_json_generator(
            _payload(
                required_skills=["Python", "Hallucinated Skill"],
                preferred_skills=["Docker"],
                tech_stack=[],
                years_experience=None,
                education_requirements=[],
                seniority=None,
                responsibilities=[],
                likely_interview_focus=[],
            )
        ),
    )
    before = isolated_session.query(JobIntelligenceRecord).one()
    snapshot = (
        list(before.required_skills),
        list(before.preferred_skills),
        list(before.tech_stack),
    )

    with patch(
        "backend.services.job_intelligence_service.get_llm_client",
        side_effect=AssertionError("scoring must not call a provider"),
    ):
        full = score_job(isolated_session, job.public_id, TEST_USER_ID)

    assert "full Job Intelligence" in full.rationale
    assert full.skill_score == 75.0
    assert extracted.required_skills == ["Python"]
    isolated_session.refresh(before)
    assert snapshot == (
        list(before.required_skills),
        list(before.preferred_skills),
        list(before.tech_stack),
    )


def test_grounding_retains_skills_when_model_adds_trailing_punctuation(isolated_session) -> None:
    job = _job(
        isolated_session,
        description=(
            "Requirements:\n"
            "Python\n"
            "Node.js\n"
            "Docker\n"
            "C++\n"
            "C#\n"
            ".NET"
        ),
    )
    raw = _payload(
        required_skills=["Python.", "Node.js,", "Docker;", "C++.", "C#,", ".NET."],
        preferred_skills=[],
        tech_stack=[],
        years_experience=None,
        education_requirements=[],
        seniority=None,
        responsibilities=[],
        likely_interview_focus=[],
    )

    grounded, counts = ground_job_intelligence(raw, job)

    assert grounded.required_skills == ["Python", "Node.js", "Docker", "C++", "C#", ".NET"]
    assert counts["skills"] == 0


@pytest.mark.parametrize(
    ("description", "claims", "kept"),
    [
        (
            "Requirements:\nC++\nC#\n.NET\nNode.js\nReact.js\nCI/CD\nREST APIs",
            ["C++.", "C#,", ".NET;", "Node.js.", "React.js,", "CI/CD;", "REST APIs."],
            ["C++", "C#", ".NET", "Node.js", "React.js", "CI/CD", "REST APIs"],
        ),
    ],
)
def test_grounding_retains_punctuation_technical_skills_from_source(
    isolated_session,
    description: str,
    claims: list[str],
    kept: list[str],
) -> None:
    job = _job(isolated_session, description=description)
    raw = _payload(
        required_skills=claims,
        preferred_skills=[],
        tech_stack=[],
        years_experience=None,
        education_requirements=[],
        seniority=None,
        responsibilities=[],
        likely_interview_focus=[],
    )

    grounded, _counts = ground_job_intelligence(raw, job)

    assert grounded.required_skills == kept


def test_grounding_retains_responsibilities_from_bullet_and_html_source(isolated_session) -> None:
    job = _job(
        isolated_session,
        description=(
            "<h3>About the role</h3>"
            "<p>Build APIs &amp; services.</p>"
            "Requirements:\nPython\n"
            "Responsibilities:\n"
            "- Improve API latency by 20%.\n"
            "- Write unit tests."
        ),
    )
    raw = _payload(
        required_skills=["Python"],
        preferred_skills=[],
        tech_stack=[],
        years_experience=None,
        education_requirements=[],
        seniority=None,
        responsibilities=[
            "Improve API latency by 20%.",
            "Write unit tests.",
            "Invent warp drive.",
        ],
        likely_interview_focus=[],
    )

    grounded, _counts = ground_job_intelligence(raw, job)

    assert grounded.required_skills == ["Python"]
    assert grounded.responsibilities == [
        "Improve API latency by 20%.",
        "Write unit tests.",
    ]


def test_grounding_rejects_paraphrased_responsibilities(isolated_session) -> None:
    job = _job(
        isolated_session,
        description="Responsibilities:\nImprove API latency by 20%.",
    )
    raw = _payload(
        required_skills=[],
        preferred_skills=[],
        tech_stack=[],
        years_experience=None,
        education_requirements=[],
        seniority=None,
        responsibilities=["Reduce API latency by twenty percent."],
        likely_interview_focus=[],
    )

    grounded, _counts = ground_job_intelligence(raw, job)

    assert grounded.responsibilities == []


def test_grounding_preserves_required_vs_preferred_local_context(isolated_session) -> None:
    job = _job(
        isolated_session,
        description=(
            "Requirements:\nPython\n"
            "Preferred:\nKubernetes\n"
            "Technology stack:\nDocker"
        ),
    )
    raw = _payload(
        required_skills=["Python.", "Kubernetes.", "Docker."],
        preferred_skills=[],
        tech_stack=[],
        years_experience=None,
        education_requirements=[],
        seniority=None,
        responsibilities=[],
        likely_interview_focus=[],
    )

    grounded, _counts = ground_job_intelligence(raw, job)

    assert grounded.required_skills == ["Python"]
    assert grounded.preferred_skills == ["Kubernetes"]
    assert grounded.tech_stack == ["Docker"]


def test_grounding_retains_source_backed_education_and_experience(isolated_session) -> None:
    job = _job(
        isolated_session,
        description=(
            "Requirements:\n"
            "Python\n"
            "4 years of professional experience\n"
            "Bachelor's degree in Computer Science"
        ),
    )
    raw = _payload(
        required_skills=["Python."],
        preferred_skills=[],
        tech_stack=[],
        years_experience=4,
        education_requirements=["Bachelor's degree in Computer Science"],
        seniority=None,
        responsibilities=[],
        likely_interview_focus=[],
    )

    grounded, _counts = ground_job_intelligence(raw, job)

    assert grounded.required_skills == ["Python"]
    assert grounded.years_experience == 4
    assert grounded.education_requirements == ["Bachelor's degree in Computer Science"]
