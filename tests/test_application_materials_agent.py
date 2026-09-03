"""Application Materials Agent foundation tests.

The unfinished student-owned generator must fail closed: no persistence,
no provider calls, and no prompt/provider leakage.
"""

from __future__ import annotations

import inspect

import pytest

from backend.db.models import (
    ApplicationPackageRecord,
    Candidate,
    JobIntelligenceRecord,
    JobRecord,
    MatchScoreRecord,
    TargetPreference,
)
from backend.services import application_service
from tests.mvp_helpers import TEST_USER_ID, ensure_user, insert_candidate
from backend.services.application_materials_agent import (
    _MATERIALS_PROVIDER_ERROR_PRIORITY,
    _should_replace_materials_error,
    ApplicationMaterialsDraft,
    ApplicationMaterialsGroundingError,
    ApplicationMaterialsParseError,
    ApplicationMaterialsStructuredOutput,
    MaterialsClaimEvidence,
    MaterialsGroundingReport,
    MissingCandidateError,
    MissingFitScoreError,
    MissingJobError,
    MissingJobIntelligenceError,
    build_application_materials_prompt,
    build_materials_evidence_catalog,
    draft_to_application_package,
    generate_grounded_application_materials,
    ground_application_materials,
    is_grounded_package_record,
    is_override_package_record,
    load_application_materials_context,
    parse_application_materials_json,
)
from backend.services.llm_client import (
    LLMConfigurationError,
    LLMEmptyResponseError,
    LLMProviderError,
)


def _job(session, *, public_id: str = "job-materials") -> JobRecord:
    record = JobRecord(
        public_id=public_id,
        title="Software Engineer Intern",
        company="Acme",
        url=f"https://example.com/jobs/{public_id}",
        description="Required: Python and SQL. Preferred: Docker.",
        source="manual",
        status="verified",
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _candidate(session) -> Candidate:
    return insert_candidate(session)


def _intelligence(session, job: JobRecord) -> JobIntelligenceRecord:
    record = JobIntelligenceRecord(
        job_id=job.id,
        required_skills=["Python", "SQL"],
        preferred_skills=["Docker"],
        years_experience=0,
        education_requirements=["Bachelor's in CS"],
        tech_stack=["Python", "SQL"],
        seniority="intern",
        responsibilities=["Implement API endpoints with tests"],
        likely_interview_focus=["Python fundamentals", "SQL joins"],
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _score(session, job: JobRecord, candidate: Candidate) -> MatchScoreRecord:
    record = MatchScoreRecord(
        job_id=job.id,
        candidate_id=candidate.id,
        overall_score=82.0,
        skill_score=80.0,
        experience_score=70.0,
        education_score=100.0,
        location_score=None,
        preference_score=None,
        matched_skills=["Python", "SQL"],
        partial_matches=[],
        missing_skills=["Docker", "Kubernetes"],
        recommendation="apply",
        rationale="Matched Python and SQL from stored evidence.",
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _full_context(session):
    candidate = _candidate(session)
    job = _job(session)
    _intelligence(session, job)
    _score(session, job, candidate)
    session.add(
        TargetPreference(
            candidate_id=candidate.id,
            target_roles=["Software Engineer Intern"],
            preferred_locations=["Remote"],
        )
    )
    session.commit()
    return job, candidate


def test_missing_job_fails_sanitized(isolated_session) -> None:
    _candidate(isolated_session)
    with pytest.raises(MissingJobError, match="Job not found"):
        generate_grounded_application_materials(isolated_session, "missing-job", TEST_USER_ID)
    assert isolated_session.query(ApplicationPackageRecord).count() == 0


def test_missing_candidate_fails_sanitized(isolated_session) -> None:
    _job(isolated_session)
    with pytest.raises(MissingCandidateError, match="candidate profile"):
        generate_grounded_application_materials(isolated_session, "job-materials", TEST_USER_ID)
    assert isolated_session.query(ApplicationPackageRecord).count() == 0


def test_missing_job_intelligence_fails_sanitized(isolated_session) -> None:
    candidate = _candidate(isolated_session)
    job = _job(isolated_session)
    _score(isolated_session, job, candidate)
    with pytest.raises(MissingJobIntelligenceError, match="job requirements"):
        generate_grounded_application_materials(isolated_session, "job-materials", TEST_USER_ID)
    assert isolated_session.query(ApplicationPackageRecord).count() == 0


def test_missing_fit_score_fails_sanitized(isolated_session) -> None:
    _candidate(isolated_session)
    job = _job(isolated_session)
    _intelligence(isolated_session, job)
    with pytest.raises(MissingFitScoreError, match="fit score"):
        generate_grounded_application_materials(isolated_session, "job-materials", TEST_USER_ID)
    assert isolated_session.query(ApplicationPackageRecord).count() == 0


def test_grounded_generator_persists_valid_output_and_reuses_it(isolated_session) -> None:
    from tests.mvp_helpers import TEST_USER_ID, VALID_MATERIALS_JSON, fake_grounded_generator

    _full_context(isolated_session)
    first = generate_grounded_application_materials(
        isolated_session, "job-materials", TEST_USER_ID, generator=fake_grounded_generator
    )
    assert isolated_session.query(ApplicationPackageRecord).count() == 1
    called = {"n": 0}

    def counting(prompt: str, system_prompt: str | None = None) -> str:
        called["n"] += 1
        return VALID_MATERIALS_JSON

    second = generate_grounded_application_materials(
        isolated_session, "job-materials", TEST_USER_ID, generator=counting
    )
    assert called["n"] == 0
    assert first.tailored_bullets == second.tailored_bullets


def test_context_loading_uses_stored_grounded_records(isolated_session) -> None:
    job, candidate = _full_context(isolated_session)
    context = load_application_materials_context(isolated_session, job.public_id, TEST_USER_ID)
    assert context.job.title == "Software Engineer Intern"
    assert context.candidate.name == candidate.name
    assert context.intelligence.required_skills == ["Python", "SQL"]
    assert context.fit_score.missing_skills == ["Docker", "Kubernetes"]
    assert context.preferences is not None
    assert context.preferences.target_roles == ["Software Engineer Intern"]
    assert isolated_session.query(ApplicationPackageRecord).count() == 0


def test_no_candidate_claim_invention(isolated_session) -> None:
    _full_context(isolated_session)
    context = load_application_materials_context(isolated_session, "job-materials", TEST_USER_ID)
    invented = ApplicationMaterialsStructuredOutput(
        tailored_bullets=["Led production Kubernetes clusters and improved latency by 40%."],
        cover_letter_draft="I have deep Kubernetes experience at Globex.",
        recruiter_message="I used Kubernetes in production.",
        source_traceability_notes=["Invented Kubernetes claim"],
    )
    report = ground_application_materials(invented, context)
    assert report.grounded is False
    assert report.invented_candidate_claims >= 1
    assert report.numeric_literals_rejected >= 1
    assert "missing_skill_as_strength" in report.rejected_categories

    grounded = ApplicationMaterialsStructuredOutput(
        tailored_bullets=["Built Python APIs at Northstar Labs and reduced p95 latency by 28%."],
        cover_letter_draft="I am applying using stored Python and SQL evidence.",
        recruiter_message="Happy to discuss Python coursework.",
        source_traceability_notes=["Python <- candidate skills"],
    )
    ok = ground_application_materials(grounded, context)
    assert ok.invented_candidate_claims == 0
    assert ok.numeric_literals_rejected == 0
    assert ok.invented_job_requirements == 0
    assert ok.grounded is True


def _report(session, **fields) -> MaterialsGroundingReport:
    if session.query(JobRecord).filter(JobRecord.public_id == "job-materials").first() is None:
        _full_context(session)
    context = load_application_materials_context(session, "job-materials", TEST_USER_ID)
    output = ApplicationMaterialsStructuredOutput(
        tailored_bullets=list(fields.get("bullets") or []),
        cover_letter_draft=fields.get("cover") or "",
        recruiter_message=fields.get("recruiter") or "",
        source_traceability_notes=list(fields.get("notes") or []),
        claim_evidence=list(fields.get("claim_evidence") or []),
    )
    return ground_application_materials(output, context)


def test_invented_employer_is_rejected(isolated_session) -> None:
    report = _report(isolated_session, bullets=["Worked at Globex on backend APIs."])
    assert report.grounded is False
    assert report.invented_candidate_claims >= 1
    assert "invented_employer" in report.rejected_categories


def test_invented_title_or_promotion_is_rejected(isolated_session) -> None:
    report = _report(
        isolated_session,
        bullets=["Promoted to Staff Engineer at Northstar Labs."],
    )
    assert report.grounded is False
    assert report.invented_candidate_claims >= 1
    assert "invented_title" in report.rejected_categories


def test_invented_project_or_product_is_rejected(isolated_session) -> None:
    launched = _report(
        isolated_session,
        bullets=["Launched a healthcare or payments product used worldwide."],
    )
    assert launched.grounded is False
    assert launched.invented_candidate_claims >= 1
    named = _report(isolated_session, bullets=["Built Campus Connect with Python."])
    assert named.grounded is False
    assert "invented_project" in named.rejected_categories


def test_invented_accomplishment_or_leadership_is_rejected(isolated_session) -> None:
    led = _report(isolated_session, bullets=["Led a global engineering team."])
    award = _report(
        isolated_session,
        cover="I produced award-winning leadership results.",
    )
    transformed = _report(
        isolated_session,
        recruiter="I transformed customer retention across the book of business.",
    )
    for report in (led, award, transformed):
        assert report.grounded is False
        assert report.invented_candidate_claims >= 1
        assert "invented_accomplishment" in report.rejected_categories


def test_cross_entry_evidence_combination_is_rejected(isolated_session) -> None:
    report = _report(
        isolated_session,
        bullets=[
            "Built Campus Planner at Northstar Labs and reduced p95 latency by 28%.",
        ],
    )
    assert report.grounded is False
    assert "cross_entry" in report.rejected_categories


def test_unsupported_job_requirement_is_rejected(isolated_session) -> None:
    report = _report(
        isolated_session,
        cover="This role requires Kubernetes and Haskell in production.",
    )
    assert report.grounded is False
    assert report.invented_job_requirements >= 1
    assert "invented_job_requirement" in report.rejected_categories


def test_missing_skill_represented_as_strength_is_rejected(isolated_session) -> None:
    report = _report(
        isolated_session,
        bullets=["Docker is one of my core strengths."],
        cover="I have deep Kubernetes experience.",
    )
    assert report.grounded is False
    assert "missing_skill_as_strength" in report.rejected_categories


def test_numeric_unit_or_type_rewrite_is_rejected(isolated_session) -> None:
    multiplier = _report(isolated_session, bullets=["Reduced p95 latency by 28x at Northstar Labs."])
    money = _report(isolated_session, bullets=["Reduced p95 latency by $28 at Northstar Labs."])
    years = _report(isolated_session, bullets=["Reduced p95 latency by 28 years at Northstar Labs."])
    for report in (multiplier, money, years):
        assert report.grounded is False
        assert report.numeric_literals_rejected >= 1


def test_supported_employer_title_project_skill_metric_retained(isolated_session) -> None:
    report = _report(
        isolated_session,
        bullets=[
            "Built Python APIs at Northstar Labs as Software Engineering Intern and reduced p95 latency by 28%.",
            "Built Campus Planner with Python and FastAPI.",
        ],
        cover="I am applying using stored Python and SQL evidence.",
        recruiter="Happy to discuss Python coursework.",
        notes=["Python <- candidate skills"],
    )
    assert report.grounded is True
    assert report.invented_candidate_claims == 0
    assert report.invented_job_requirements == 0
    assert report.numeric_literals_rejected == 0
    assert report.rejected_claim_count == 0


def test_safe_generic_boilerplate_is_permitted(isolated_session) -> None:
    report = _report(
        isolated_session,
        cover="Thank you for considering my application. I would welcome the chance to discuss this role.",
        recruiter="I am a strong fit for this role.",
    )
    assert report.grounded is True
    assert report.invented_candidate_claims == 0


def test_generic_boilerplate_cannot_smuggle_facts(isolated_session) -> None:
    report = _report(
        isolated_session,
        cover="Thank you for your time. I previously worked at Globex.",
    )
    assert report.grounded is False
    assert report.invented_candidate_claims >= 1


def test_grounding_is_deterministic_and_logs_are_count_only(isolated_session, caplog) -> None:
    import logging

    _full_context(isolated_session)
    context = load_application_materials_context(isolated_session, "job-materials", TEST_USER_ID)
    output = ApplicationMaterialsStructuredOutput(
        tailored_bullets=["Worked at Globex and led a global engineering team."],
        cover_letter_draft="Launched a healthcare product and transformed customer retention.",
        recruiter_message="I produced award-winning leadership results.",
        source_traceability_notes=["Invented Globex claim"],
    )
    with caplog.at_level(logging.INFO, logger="backend.services.application_materials_agent"):
        first = ground_application_materials(output, context)
        second = ground_application_materials(output, context)
    assert first == second
    assert first.grounded is False
    blob = caplog.text.lower()
    assert "globex" not in blob
    assert "jordan" not in blob
    assert "healthcare" not in blob
    assert "accepted=" in blob
    assert "rejected=" in blob


def test_structured_output_is_attempted_at_most_twice(isolated_session) -> None:
    _full_context(isolated_session)
    calls = {"n": 0}

    def bad(_prompt: str, _system_prompt: str | None = None) -> str:
        calls["n"] += 1
        return "not-json"

    with pytest.raises(ApplicationMaterialsParseError):
        generate_grounded_application_materials(
            isolated_session, "job-materials", TEST_USER_ID, generator=bad
        )
    assert calls["n"] == 2
    assert isolated_session.query(ApplicationPackageRecord).count() == 0


def test_provider_claim_evidence_refs_are_verified_not_trusted(isolated_session) -> None:
    wrong = _report(
        isolated_session,
        bullets=["Built Python APIs at Northstar Labs and reduced p95 latency by 28%."],
        claim_evidence=[
            MaterialsClaimEvidence(
                claim_excerpt="28%",
                evidence_kind="project",
                evidence_id="project:0",
            )
        ],
    )
    assert wrong.grounded is False
    assert "invalid_evidence_ref" in wrong.rejected_categories

    right = _report(
        isolated_session,
        bullets=["Built Python APIs at Northstar Labs and reduced p95 latency by 28%."],
        claim_evidence=[
            MaterialsClaimEvidence(
                claim_excerpt="28%",
                evidence_kind="experience",
                evidence_id="experience:0",
            )
        ],
    )
    assert right.grounded is True


def test_supported_job_requirement_statement_is_not_invented(isolated_session) -> None:
    report = _report(
        isolated_session,
        cover="This role requires Python and SQL and prefers Docker.",
    )
    assert report.invented_job_requirements == 0
    assert report.grounded is True


def test_parse_accepts_claim_evidence_without_changing_package_shape(isolated_session) -> None:
    parsed = parse_application_materials_json(
        '{"tailored_bullets":["Used Python"],"cover_letter_draft":"Hello",'
        '"recruiter_message":"Hi","source_traceability_notes":["Python <- skills"],'
        '"claim_evidence":[{"claim_excerpt":"Python","evidence_kind":"skill","evidence_id":"skill:profile"}]}'
    )
    assert parsed.claim_evidence[0].evidence_id == "skill:profile"
    _full_context(isolated_session)
    context = load_application_materials_context(isolated_session, "job-materials", TEST_USER_ID)
    draft = ApplicationMaterialsDraft(
        job_id="job-materials",
        tailored_bullets=["Used Python"],
        cover_letter_draft="Hello",
        recruiter_message="Hi",
        source_traceability_notes=["Python <- skills"],
        grounding=MaterialsGroundingReport(),
    )
    package = draft_to_application_package(draft)
    dumped = package.model_dump()
    assert "claim_evidence" not in dumped


def test_prompt_json_and_persistence_conversion_do_not_write(isolated_session) -> None:
    _full_context(isolated_session)
    context = load_application_materials_context(isolated_session, "job-materials", TEST_USER_ID)
    system_prompt, user_prompt = build_application_materials_prompt(context)
    assert "Never invent" in system_prompt
    assert "Python" in user_prompt
    parsed = parse_application_materials_json(
        '{"tailored_bullets":["Used Python"],"cover_letter_draft":"Hello",'
        '"recruiter_message":"Hi","source_traceability_notes":["Python <- skills"]}'
    )
    assert parsed.tailored_bullets == ["Used Python"]
    with pytest.raises(ApplicationMaterialsParseError):
        parse_application_materials_json("not-json")
    package = draft_to_application_package(
        ApplicationMaterialsDraft(
            job_id="job-materials",
            tailored_bullets=["Used Python"],
            cover_letter_draft="Hello",
            recruiter_message="Hi",
            source_traceability_notes=["Python <- skills"],
            grounding=MaterialsGroundingReport(),
        )
    )
    assert package.job_id == "job-materials"
    assert package.approval_status == "pending_review"
    assert isolated_session.query(ApplicationPackageRecord).count() == 0


def test_production_generate_materials_uses_grounded_generator(isolated_client) -> None:
    from tests.mvp_helpers import fake_grounded_generator, seed_materials_prerequisites

    client, SessionLocal = isolated_client
    client.app.state.application_materials_generator = fake_grounded_generator
    with SessionLocal() as db:
        seed_materials_prerequisites(db, public_id="manual-abc123")
    response = client.post("/api/jobs/manual-abc123/generate-materials")
    assert response.status_code == 200
    body = response.json()
    assert "placeholder" not in " ".join(body["source_traceability_notes"]).lower()
    assert body["grounded"] is True
    source = inspect.getsource(application_service.get_or_generate_application_package)
    assert "generate_grounded_application_materials(" in source
    assert not hasattr(application_service, "_mock_materials")
    import backend.services.application_materials_agent as materials_agent

    assert hasattr(materials_agent, "generate_grounded_application_materials")
    assert not hasattr(materials_agent, "ApplicationMaterialsNotImplementedError")


# ---------------------------------------------------------------------------
# Provider fallback: which failure the user is actually told about
# ---------------------------------------------------------------------------


def test_a_later_unconfigured_provider_does_not_mask_a_real_failure() -> None:
    """With LLM_PROVIDER_ORDER="ollama,gemini" and no Gemini key, Ollama can
    run, produce output, and have it rejected by grounding — and then Gemini's
    "no API key" error would overwrite that as the error the user sees. The
    result was a 503 "generation is not configured" on a system that was
    configured and had just run, sending the user to fix a setting that was
    never wrong. Rank substantive failures above configuration ones.
    """
    grounding = ApplicationMaterialsGroundingError()
    config = LLMConfigurationError("GEMINI_API_KEY is not set.")

    assert _should_replace_materials_error(None, grounding) is True
    # The real failure must survive the unconfigured provider tried after it.
    assert _should_replace_materials_error(grounding, config) is False
    # ...and a real failure still replaces a config error seen first.
    assert _should_replace_materials_error(config, grounding) is True


def test_equal_severity_failures_keep_the_first_provider_error() -> None:
    first = ApplicationMaterialsGroundingError()
    second = ApplicationMaterialsGroundingError()
    assert _should_replace_materials_error(first, second) is False


def test_every_error_the_provider_loop_catches_is_ranked() -> None:
    """An unranked error type defaults to 0, below even a configuration
    error, so it would be the one silently discarded. Anything the loop
    catches must therefore have an explicit rank."""
    for error_type in (
        ApplicationMaterialsParseError,
        ApplicationMaterialsGroundingError,
        LLMProviderError,
        LLMEmptyResponseError,
        LLMConfigurationError,
    ):
        assert error_type in _MATERIALS_PROVIDER_ERROR_PRIORITY, error_type


def test_configuration_error_ranks_below_every_substantive_failure() -> None:
    config_rank = _MATERIALS_PROVIDER_ERROR_PRIORITY[LLMConfigurationError]
    others = [
        rank
        for error_type, rank in _MATERIALS_PROVIDER_ERROR_PRIORITY.items()
        if error_type is not LLMConfigurationError
    ]
    assert others, "expected other ranked provider errors"
    assert all(rank > config_rank for rank in others)


# ---------------------------------------------------------------------------
# Explicit per-job grounding override
# ---------------------------------------------------------------------------


def _ungrounded_record(**overrides) -> ApplicationPackageRecord:
    defaults = dict(
        job_id=1,
        user_id=1,
        candidate_id=1,
        tailored_bullets=["Led a global engineering team of 40."],
        cover_letter_draft="I have ten years of production Spark experience.",
        recruiter_message="Hello,",
        source_traceability_notes=["unverified"],
        approval_status="pending_review",
        grounded=False,
        grounding_override=True,
        unsupported_claims=["experience", "skills"],
    )
    defaults.update(overrides)
    return ApplicationPackageRecord(**defaults)


def test_override_package_is_never_reported_as_grounded() -> None:
    """`grounded` must keep meaning "every claim was verified". An override
    waives the check; it does not turn an unverified package into a
    verified one, and anything reading `grounded` must still see False."""
    record = _ungrounded_record()
    assert is_grounded_package_record(record) is False
    assert is_override_package_record(record) is True


def test_override_does_not_apply_without_the_explicit_flag() -> None:
    """An ungrounded package that was never explicitly overridden — a
    legacy row, or one written by some other path — must not be treated as
    an override and must stay unusable for assisted apply."""
    record = _ungrounded_record(grounding_override=False)
    assert is_grounded_package_record(record) is False
    assert is_override_package_record(record) is False


def test_override_still_requires_real_content() -> None:
    """The override waives evidence verification only. A package with no
    usable content is still not something to fill a form from."""
    record = _ungrounded_record(
        tailored_bullets=[], cover_letter_draft=None, recruiter_message=None
    )
    assert is_override_package_record(record) is False


def test_override_records_which_claims_were_unsupported() -> None:
    """Review is only informed if the reviewer can see what is unverified."""
    record = _ungrounded_record()
    assert record.unsupported_claims == ["experience", "skills"]


def _rich_qa_materials_context(session):
    """Sparse QA profile: skills, one project, one education row. No employment."""

    ensure_user(session)
    previous = session.query(Candidate).filter(Candidate.user_id == TEST_USER_ID).first()
    if previous is not None:
        previous.user_id = None
        session.commit()
    candidate = Candidate(
        user_id=TEST_USER_ID,
        name="QA Test User",
        email=None,
        skills=["Python", "Linux"],
        projects=[
            {
                "name": "Release Validation CLI",
                "description": "Built a Python command-line tool that validates YAML and JSON configuration files.",
                "technologies": ["Python", "Git"],
                "url": None,
            }
        ],
        experience=[],
        education=[
            {
                "institution": "QA Technical College",
                "degree": None,
                "field": "Computer Science coursework",
                "graduation_year": None,
            }
        ],
        certifications=[],
        strengths=[],
        evidence_links=[],
    )
    session.add(candidate)
    job = JobRecord(
        public_id="jobicy-qa-materials",
        title="Software Engineer - Cloud Images",
        company="Canonical",
        url="https://example.com/jobs/jobicy-qa-materials",
        description=(
            "We are hiring a Software Engineer to work on Linux and cloud images. "
            "Preferred: Python, Docker, Kubernetes, Jenkins."
        ),
        source="manual",
        status="verified",
    )
    session.add(job)
    session.commit()
    session.refresh(candidate)
    session.refresh(job)
    session.add(
        JobIntelligenceRecord(
            job_id=job.id,
            required_skills=["Python"],
            preferred_skills=["Linux", "Docker", "Kubernetes", "Jenkins"],
            years_experience=0,
            education_requirements=[],
            tech_stack=["Python", "Linux"],
            seniority="mid",
            responsibilities=["Work on Linux cloud images"],
            likely_interview_focus=["Python"],
        )
    )
    session.add(
        MatchScoreRecord(
            job_id=job.id,
            candidate_id=candidate.id,
            overall_score=50.0,
            skill_score=40.0,
            experience_score=None,
            education_score=0.0,
            location_score=None,
            preference_score=100.0,
            matched_skills=["Python", "Linux"],
            partial_matches=[],
            missing_skills=["Kubernetes", "Jenkins"],
            recommendation="skip",
            rationale="Matched Python and Linux from stored evidence.",
        )
    )
    session.add(
        TargetPreference(
            user_id=TEST_USER_ID,
            candidate_id=candidate.id,
            target_roles=["Software Engineer"],
            preferred_locations=[],
        )
    )
    session.commit()
    return load_application_materials_context(session, job.public_id, TEST_USER_ID)


def test_prompt_exposes_canonical_evidence_ids(isolated_session) -> None:
    context = _rich_qa_materials_context(isolated_session)
    _, user_prompt = build_application_materials_prompt(context)
    catalog = build_materials_evidence_catalog(context)
    ids = {row["evidence_id"] for row in catalog}
    assert ids == {
        "project:0",
        "education:0",
        "skill:profile",
        "candidate:profile",
        "job:posting",
    }
    for evidence_id in ids:
        assert evidence_id in user_prompt
    assert "candidate_evidence_catalog" in user_prompt
    assert "job_evidence" in user_prompt


def test_prompt_explains_claim_evidence_fields(isolated_session) -> None:
    context = _rich_qa_materials_context(isolated_session)
    system_prompt, user_prompt = build_application_materials_prompt(context)
    combined = f"{system_prompt}\n{user_prompt}"
    assert "claim_excerpt" in combined
    assert "evidence_kind" in combined
    assert "evidence_id" in combined
    assert "claim_evidence" in combined
    assert "short span copied from the referenced catalog text" in combined
    assert "claim_evidence_examples" in combined
    assert "interested in" in combined
    assert "express" in combined.lower()
    assert "experience with" in combined.lower()
    assert "one sentence" in combined.lower() or "exactly one" in combined.lower()


def test_prompt_catalog_omits_salary_and_eeo_fields(isolated_session) -> None:
    context = _rich_qa_materials_context(isolated_session)
    pref = isolated_session.query(TargetPreference).filter_by(user_id=TEST_USER_ID).one()
    pref.salary_min = 135000
    pref.gender = "EEO-GENDER"
    pref.race_ethnicity = "EEO-RACE"
    pref.veteran_status = "EEO-VETERAN"
    pref.disability_status = "EEO-DISABILITY"
    isolated_session.commit()
    context = load_application_materials_context(isolated_session, "jobicy-qa-materials", TEST_USER_ID)
    system_prompt, user_prompt = build_application_materials_prompt(context)
    combined = f"{system_prompt}\n{user_prompt}"
    assert "salary_min" not in combined
    assert "135000" not in combined
    assert "EEO-GENDER" not in combined
    assert "EEO-RACE" not in combined
    assert "EEO-VETERAN" not in combined
    assert "EEO-DISABILITY" not in combined
    assert "race_ethnicity" not in combined


def test_modest_catalog_backed_response_grounds(isolated_session) -> None:
    context = _rich_qa_materials_context(isolated_session)
    output = ApplicationMaterialsStructuredOutput(
        tailored_bullets=[
            "Python is included in my current skills.",
            "My Release Validation CLI project used Python and Git.",
        ],
        cover_letter_draft="I am interested in the Software Engineer - Cloud Images role at Canonical.",
        recruiter_message="I am interested in the Software Engineer role at Canonical.",
        source_traceability_notes=[
            "Python is listed in stored skills.",
            "Release Validation CLI is a stored project.",
        ],
        claim_evidence=[
            MaterialsClaimEvidence(
                claim_excerpt="Python",
                evidence_kind="skill",
                evidence_id="skill:profile",
            ),
            MaterialsClaimEvidence(
                claim_excerpt="Release Validation CLI",
                evidence_kind="project",
                evidence_id="project:0",
            ),
            MaterialsClaimEvidence(
                claim_excerpt="Software Engineer",
                evidence_kind="job",
                evidence_id="job:posting",
            ),
        ],
    )
    report = ground_application_materials(output, context)
    assert report.invented_candidate_claims == 0
    assert report.invented_job_requirements == 0
    assert report.numeric_literals_rejected == 0
    assert report.grounded is True


def test_invalid_evidence_id_still_fails(isolated_session) -> None:
    context = _rich_qa_materials_context(isolated_session)
    output = ApplicationMaterialsStructuredOutput(
        tailored_bullets=["Python is included in my current skills."],
        cover_letter_draft="I am interested in the Software Engineer role at Canonical.",
        recruiter_message="I am interested in the Software Engineer role at Canonical.",
        source_traceability_notes=["Python is listed in stored skills."],
        claim_evidence=[
            MaterialsClaimEvidence(
                claim_excerpt="Python",
                evidence_kind="project",
                evidence_id="project:999",
            )
        ],
    )
    report = ground_application_materials(output, context)
    assert report.grounded is False
    assert "invalid_evidence_ref" in report.rejected_categories


def test_long_claim_excerpt_not_in_catalog_is_invalid_ref(isolated_session) -> None:
    context = _rich_qa_materials_context(isolated_session)
    output = ApplicationMaterialsStructuredOutput(
        tailored_bullets=["Python is included in my current skills."],
        cover_letter_draft="I am interested in the Software Engineer role at Canonical.",
        recruiter_message="I am interested in the Software Engineer role at Canonical.",
        source_traceability_notes=["Python is listed in stored skills."],
        claim_evidence=[
            MaterialsClaimEvidence(
                claim_excerpt="Python is included in my current skills.",
                evidence_kind="skill",
                evidence_id="skill:profile",
            )
        ],
    )
    report = ground_application_materials(output, context)
    assert report.grounded is False
    assert "invalid_evidence_ref" in report.rejected_categories


def test_express_my_interest_is_still_rejected(isolated_session) -> None:
    """Prompt forbids 'express'; validator still treats it as the Express skill."""

    context = _rich_qa_materials_context(isolated_session)
    output = ApplicationMaterialsStructuredOutput(
        tailored_bullets=["Python is included in my current skills."],
        cover_letter_draft=(
            "I am writing to express my interest in the Software Engineer - Cloud Images "
            "role at Canonical."
        ),
        recruiter_message="I am interested in the Software Engineer role at Canonical.",
        source_traceability_notes=["Python is listed in stored skills."],
    )
    report = ground_application_materials(output, context)
    assert report.grounded is False
    assert "skill" in report.rejected_categories or "invented_employer" in report.rejected_categories


def test_job_only_kubernetes_cannot_become_candidate_evidence(isolated_session) -> None:
    context = _rich_qa_materials_context(isolated_session)
    output = ApplicationMaterialsStructuredOutput(
        tailored_bullets=["Kubernetes expertise"],
        cover_letter_draft="I am interested in the Software Engineer role at Canonical.",
        recruiter_message="I am interested in the Software Engineer role at Canonical.",
        source_traceability_notes=["Kubernetes <- job posting"],
    )
    report = ground_application_materials(output, context)
    assert report.grounded is False
    assert report.invented_candidate_claims >= 1
    assert "missing_skill_as_strength" in report.rejected_categories or "skill" in report.rejected_categories
