"""Merge-gate regressions for grounded application materials."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.db.models import ApplicationPackageRecord, Candidate, MatchScoreRecord, TargetPreference
from backend.services.application_materials_agent import (
    ApplicationMaterialsConflictError,
    ApplicationMaterialsParseError,
    ApplicationMaterialsGroundingError,
    ApplicationMaterialsStructuredOutput,
    StaleApplicationMaterialsError,
    build_application_materials_prompt,
    generate_grounded_application_materials,
    ground_application_materials,
    is_grounded_package_record,
    load_application_materials_context,
    parse_application_materials_json,
)
from backend.services.application_service import (
    get_or_generate_application_package,
    get_stored_application_package,
)
from tests.mvp_helpers import (
    TEST_USER_ID,
    VALID_MATERIALS_JSON,
    fake_grounded_generator,
    insert_candidate,
    insert_grounded_package,
    insert_score,
    seed_materials_prerequisites,
)


def _report(session, **fields):
    if session.query(Candidate).count() == 0:
        seed_materials_prerequisites(
            session,
            public_id="job-materials",
            title=fields.pop("job_title", "Software Engineer Intern"),
        )
    context = load_application_materials_context(session, "manual-abc123", TEST_USER_ID)
    output = ApplicationMaterialsStructuredOutput(
        tailored_bullets=list(fields.get("bullets") or []),
        cover_letter_draft=fields.get("cover") or "",
        recruiter_message=fields.get("recruiter") or "",
        source_traceability_notes=list(fields.get("notes") or []),
    )
    return ground_application_materials(output, context)


def test_target_company_does_not_support_candidate_employment_history(isolated_session) -> None:
    seed_materials_prerequisites(isolated_session, title="Software Engineer Intern")
    context = load_application_materials_context(isolated_session, "manual-abc123", TEST_USER_ID)
    output = ApplicationMaterialsStructuredOutput(
        tailored_bullets=["Worked at Acme."],
        cover_letter_draft="I previously worked at Acme.",
        recruiter_message="Happy to discuss Python.",
        source_traceability_notes=["Acme <- job company"],
    )
    report = ground_application_materials(output, context)
    assert report.grounded is False
    assert report.invented_candidate_claims >= 1


def test_target_role_does_not_support_candidate_title_claim(isolated_session) -> None:
    seed_materials_prerequisites(isolated_session, title="Data Scientist")
    context = load_application_materials_context(isolated_session, "manual-abc123", TEST_USER_ID)
    output = ApplicationMaterialsStructuredOutput(
        tailored_bullets=["I am a Data Scientist."],
        cover_letter_draft="My background as a Data Scientist is a strong match.",
        recruiter_message="Happy to discuss Python.",
        source_traceability_notes=["title <- job"],
    )
    report = ground_application_materials(output, context)
    assert report.grounded is False
    assert report.invented_candidate_claims >= 1


def test_job_interest_statements_may_use_target_company_and_role(isolated_session) -> None:
    seed_materials_prerequisites(isolated_session, title="Data Scientist")
    context = load_application_materials_context(isolated_session, "manual-abc123", TEST_USER_ID)
    output = ApplicationMaterialsStructuredOutput(
        tailored_bullets=["Built Python APIs at Northstar Labs as Software Engineering Intern."],
        cover_letter_draft="I am applying to Acme. I am interested in the Data Scientist role at Acme.",
        recruiter_message="I am interested in the Data Scientist role at Acme.",
        source_traceability_notes=["Python <- candidate skills"],
    )
    report = ground_application_materials(output, context)
    assert report.grounded is True


def test_empty_object_is_not_useful_structured_output() -> None:
    with pytest.raises(ApplicationMaterialsParseError):
        parse_application_materials_json("{}")


def test_whitespace_only_structured_output_is_rejected() -> None:
    with pytest.raises(ApplicationMaterialsParseError):
        parse_application_materials_json(
            '{"tailored_bullets":["  "],"cover_letter_draft":" ","recruiter_message":"\\n",'
            '"source_traceability_notes":["   "]}'
        )


def test_flagged_grounded_empty_record_is_not_treated_as_grounded(isolated_session) -> None:
    job, _candidate = seed_materials_prerequisites(isolated_session)
    record = ApplicationPackageRecord(
        job_id=job.id,
        candidate_id=_candidate.id,
        tailored_bullets=[],
        cover_letter_draft="",
        recruiter_message=" ",
        source_traceability_notes=[],
        approval_status="pending_review",
        grounded=True,
    )
    isolated_session.add(record)
    isolated_session.commit()
    isolated_session.refresh(record)
    assert is_grounded_package_record(record) is False


def test_empty_generator_output_does_not_persist(isolated_session) -> None:
    seed_materials_prerequisites(isolated_session)

    def empty(_prompt: str, _system_prompt: str | None = None) -> str:
        return "{}"

    with pytest.raises(ApplicationMaterialsParseError):
        generate_grounded_application_materials(
            isolated_session, "manual-abc123", TEST_USER_ID, generator=empty
        )
    assert isolated_session.query(ApplicationPackageRecord).count() == 0


def test_typeerror_from_generator_invokes_once_and_persists_nothing(isolated_session) -> None:
    seed_materials_prerequisites(isolated_session)
    calls = {"n": 0}

    def one_arg_contract(prompt: str, system_prompt: str | None = None) -> str:
        calls["n"] += 1
        if system_prompt is not None:
            raise TypeError("generate() takes 1 positional argument")
        return VALID_MATERIALS_JSON

    with pytest.raises(ApplicationMaterialsParseError):
        generate_grounded_application_materials(
            isolated_session, "manual-abc123", TEST_USER_ID, generator=one_arg_contract
        )
    assert calls["n"] == 1
    assert isolated_session.query(ApplicationPackageRecord).count() == 0


def test_get_rejects_package_from_previous_candidate(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        job, first = seed_materials_prerequisites(db)
        insert_grounded_package(db, job, candidate=first)
        second = insert_candidate(db)
        insert_score(db, job, second)
    missing = client.get("/api/jobs/manual-abc123/materials")
    assert missing.status_code == 409
    assert "previous candidate" in missing.json()["detail"].lower()
    assert "acme" not in missing.json()["detail"].lower()


def test_get_rejects_package_after_same_row_profile_update(isolated_client) -> None:
    from backend.schemas.schemas import CandidateProfile
    from backend.services.candidate_profile_agent import persist_candidate_profile

    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        job, first = seed_materials_prerequisites(db)
        insert_grounded_package(db, job, candidate=first)
        original_id = first.id
        persist_candidate_profile(
            CandidateProfile(
                name="Riley Chen",
                email="riley@example.com",
                skills=["Python", "SQL", "Kubernetes"],
                projects=list(first.projects or []),
                experience=list(first.experience or []),
                education=list(first.education or []),
            ),
            db,
            first.user_id,
        )
        assert db.query(Candidate).filter_by(user_id=first.user_id).one().id == original_id
    missing = client.get("/api/jobs/manual-abc123/materials")
    assert missing.status_code == 409
    assert "previous candidate" in missing.json()["detail"].lower()


def test_refresh_reuses_current_candidate_package_without_provider(isolated_session) -> None:
    seed_materials_prerequisites(isolated_session)
    first = get_or_generate_application_package(
        isolated_session, "manual-abc123", TEST_USER_ID, generator=fake_grounded_generator
    )
    calls = {"n": 0}

    def counting(_prompt: str, _system_prompt: str | None = None) -> str:
        calls["n"] += 1
        return VALID_MATERIALS_JSON

    second = get_or_generate_application_package(
        isolated_session, "manual-abc123", TEST_USER_ID, generator=counting
    )
    assert calls["n"] == 0
    assert first.tailored_bullets == second.tailored_bullets


def test_stale_pending_package_is_replaced_after_new_grounded_output(isolated_session) -> None:
    job, first = seed_materials_prerequisites(isolated_session)
    insert_grounded_package(isolated_session, job, candidate=first)
    second = insert_candidate(isolated_session)
    insert_score(isolated_session, job, second)
    package = get_or_generate_application_package(
        isolated_session, "manual-abc123", TEST_USER_ID, generator=fake_grounded_generator
    )
    record = isolated_session.query(ApplicationPackageRecord).one()
    assert record.candidate_id == second.id
    assert package.grounded is True


def test_stale_approved_package_is_protected(isolated_session) -> None:
    job, first = seed_materials_prerequisites(isolated_session)
    record = insert_grounded_package(isolated_session, job, candidate=first)
    record.approval_status = "approved"
    isolated_session.commit()
    second = insert_candidate(isolated_session)
    insert_score(isolated_session, job, second)
    with pytest.raises(HTTPException) as exc_info:
        get_or_generate_application_package(
            isolated_session, "manual-abc123", TEST_USER_ID, generator=fake_grounded_generator
        )
    assert exc_info.value.status_code == 409
    stored = isolated_session.query(ApplicationPackageRecord).one()
    assert stored.candidate_id == first.id
    assert stored.approval_status == "approved"


def test_unique_conflict_does_not_return_ungrounded_winner(isolated_session, monkeypatch) -> None:
    job, candidate = seed_materials_prerequisites(isolated_session)
    winner = ApplicationPackageRecord(
        job_id=job.id,
        user_id=candidate.user_id,
        candidate_id=candidate.id,
        tailored_bullets=[],
        cover_letter_draft="",
        recruiter_message="",
        source_traceability_notes=[],
        approval_status="pending_review",
        grounded=True,
    )
    isolated_session.add(winner)
    isolated_session.commit()

    real_query = isolated_session.query
    calls = {"n": 0}

    class _Empty:
        def filter(self, *_a, **_k):
            return self

        def first(self):
            return None

    def miss_once(model):
        if model is ApplicationPackageRecord:
            calls["n"] += 1
            if calls["n"] == 1:
                return _Empty()
        return real_query(model)

    monkeypatch.setattr(isolated_session, "query", miss_once)
    with pytest.raises(ApplicationMaterialsConflictError):
        generate_grounded_application_materials(
            isolated_session, "manual-abc123", TEST_USER_ID, generator=fake_grounded_generator
        )
    monkeypatch.undo()
    from backend.services.application_service import StoredMaterialsNotFoundError

    with pytest.raises(StoredMaterialsNotFoundError):
        get_stored_application_package(isolated_session, "manual-abc123", TEST_USER_ID)


def test_unsupported_word_quantity_is_rejected(isolated_session) -> None:
    seed_materials_prerequisites(isolated_session)
    context = load_application_materials_context(isolated_session, "manual-abc123", TEST_USER_ID)
    years = ApplicationMaterialsStructuredOutput(
        tailored_bullets=["I have ten years of Python experience."],
        cover_letter_draft="I built Python APIs at Northstar Labs.",
        recruiter_message="Happy to discuss Python.",
        source_traceability_notes=["Python <- skills"],
    )
    dozens = ApplicationMaterialsStructuredOutput(
        tailored_bullets=["I shipped dozens of APIs at Northstar Labs."],
        cover_letter_draft="I built Python APIs at Northstar Labs.",
        recruiter_message="Happy to discuss Python.",
        source_traceability_notes=["Python <- skills"],
    )
    job_words = ApplicationMaterialsStructuredOutput(
        tailored_bullets=["Built Python APIs at Northstar Labs."],
        cover_letter_draft="This role requires ten years of Kubernetes.",
        recruiter_message="Happy to discuss Python.",
        source_traceability_notes=["Kubernetes <- job"],
    )
    for output in (years, dozens, job_words):
        report = ground_application_materials(output, context)
        assert report.grounded is False
        assert report.numeric_literals_rejected >= 1 or report.invented_candidate_claims >= 1 or report.invented_job_requirements >= 1


def test_supported_ten_years_is_retained_when_evidence_matches(isolated_session) -> None:
    job, candidate = seed_materials_prerequisites(isolated_session)
    candidate.experience = [
        {
            "title": "Software Engineering Intern",
            "company": "Northstar Labs",
            "start_date": "2015-05",
            "end_date": "2025-08",
            "highlights": ["10 years of Python API work. Reduced p95 latency by 28%."],
        }
    ]
    isolated_session.commit()
    context = load_application_materials_context(isolated_session, "manual-abc123", TEST_USER_ID)
    output = ApplicationMaterialsStructuredOutput(
        tailored_bullets=["I have ten years of Python experience at Northstar Labs."],
        cover_letter_draft="I built Python APIs at Northstar Labs.",
        recruiter_message="Happy to discuss Python.",
        source_traceability_notes=["Python <- skills"],
    )
    report = ground_application_materials(output, context)
    assert report.grounded is True


def test_one_of_my_strengths_is_not_treated_as_a_quantity(isolated_session) -> None:
    seed_materials_prerequisites(isolated_session)
    context = load_application_materials_context(isolated_session, "manual-abc123", TEST_USER_ID)
    output = ApplicationMaterialsStructuredOutput(
        tailored_bullets=["Backend APIs are one of my strengths, including Python at Northstar Labs."],
        cover_letter_draft="I built Python APIs at Northstar Labs.",
        recruiter_message="Happy to discuss Python.",
        source_traceability_notes=["Python <- skills"],
    )
    report = ground_application_materials(output, context)
    assert report.grounded is True


def test_lowercase_employer_title_and_interest_laundering_attacks_are_rejected(isolated_session) -> None:
    seed_materials_prerequisites(isolated_session, title="Data Scientist")
    context = load_application_materials_context(isolated_session, "manual-abc123", TEST_USER_ID)
    attacks = [
        "worked at globex.",
        "worked at acme.",
        "I work as a data scientist.",
        "I have data scientist experience.",
        "I have twenty years of Python experience.",
        "My accomplishments at Acme make me a fit for this role.",
        "I delivered Python APIs at Acme for this role.",
    ]
    for claim in attacks:
        output = ApplicationMaterialsStructuredOutput(
            tailored_bullets=[claim],
            cover_letter_draft=claim,
            recruiter_message="Happy to discuss Python.",
            source_traceability_notes=["Python <- skills"],
        )
        report = ground_application_materials(output, context)
        assert report.grounded is False, claim
        assert isolated_session.query(ApplicationPackageRecord).count() == 0

        def fake(_prompt: str, _system: str | None = None, *, _claim: str = claim) -> str:
            return json.dumps(
                {
                    "tailored_bullets": [_claim],
                    "cover_letter_draft": _claim,
                    "recruiter_message": "Happy to discuss Python.",
                    "source_traceability_notes": ["Python <- skills"],
                }
            )

        with pytest.raises(
            (ApplicationMaterialsParseError, ApplicationMaterialsConflictError, ApplicationMaterialsGroundingError)
        ):
            generate_grounded_application_materials(
                isolated_session, "manual-abc123", TEST_USER_ID, generator=fake
            )
        assert isolated_session.query(ApplicationPackageRecord).count() == 0


def test_word_quantities_and_fuzzy_magnitudes_are_typed(isolated_session) -> None:
    job, candidate = seed_materials_prerequisites(isolated_session)
    candidate.experience = [
        {
            "title": "Software Engineering Intern",
            "company": "Northstar Labs",
            "start_date": "2024-05",
            "end_date": "2025-08",
            "highlights": ["Shipped 2 APIs and two APIs for campus events serving 100 users."],
        }
    ]
    isolated_session.commit()
    context = load_application_materials_context(isolated_session, "manual-abc123", TEST_USER_ID)
    supported = ApplicationMaterialsStructuredOutput(
        tailored_bullets=["I shipped two APIs at Northstar Labs."],
        cover_letter_draft="I built Python APIs at Northstar Labs.",
        recruiter_message="Happy to discuss Python.",
        source_traceability_notes=["Python <- skills"],
    )
    assert ground_application_materials(supported, context).grounded is True
    rejected = ApplicationMaterialsStructuredOutput(
        tailored_bullets=["I shipped one hundred users of APIs at Northstar Labs."],
        cover_letter_draft="I have a decade of Kubernetes at Northstar Labs.",
        recruiter_message="Happy to discuss Python.",
        source_traceability_notes=["Python <- skills"],
    )
    report = ground_application_materials(rejected, context)
    assert report.grounded is False
    dozens = ApplicationMaterialsStructuredOutput(
        tailored_bullets=["I shipped dozens of APIs at Northstar Labs."],
        cover_letter_draft="I built Python APIs at Northstar Labs.",
        recruiter_message="Happy to discuss Python.",
        source_traceability_notes=["Python <- skills"],
    )
    assert ground_application_materials(dozens, context).grounded is False


def test_production_main_has_no_browser_fake_materials_backdoor() -> None:
    source = Path("backend/main.py").read_text(encoding="utf-8")
    assert "_browser_fake_materials" not in source
    assert "CAREERPILOT_BROWSER_FAKE_MATERIALS" not in source


def _profile_b():
    from backend.schemas.schemas import CandidateProfile

    return CandidateProfile(
        name="Riley Chen",
        email="riley@example.com",
        phone="555-0199",
        skills=["Python", "SQL", "Kubernetes"],
        projects=[
            {
                "name": "Campus Planner",
                "description": "Python API for campus events.",
                "technologies": ["Python", "FastAPI"],
                "url": None,
            }
        ],
        experience=[
            {
                "title": "Software Engineering Intern",
                "company": "Northstar Labs",
                "start_date": "2025-05",
                "end_date": "2025-08",
                "highlights": ["Reduced p95 latency on search endpoints by 28%."],
            }
        ],
        education=[
            {
                "institution": "State University",
                "degree": "B.S.",
                "field": "Computer Science",
                "graduation_year": "2027",
            }
        ],
        certifications=[],
        strengths=["Backend APIs"],
        evidence_links=[],
    )


def test_profile_change_during_generate_fails_closed_without_persist(isolated_session, caplog) -> None:
    from backend.services.candidate_profile_agent import persist_candidate_profile

    caplog.set_level(logging.DEBUG)
    seed_materials_prerequisites(isolated_session)
    original_id = isolated_session.query(Candidate).one().id

    def racing_generator(_prompt: str, _system_prompt: str | None = None) -> str:
        persist_candidate_profile(_profile_b(), isolated_session, TEST_USER_ID)
        isolated_session.expire_all()
        current = isolated_session.query(Candidate).filter_by(user_id=TEST_USER_ID).one()
        assert current.id == original_id
        assert current.name == "Riley Chen"
        return VALID_MATERIALS_JSON

    with pytest.raises(StaleApplicationMaterialsError):
        generate_grounded_application_materials(
            isolated_session, "manual-abc123", TEST_USER_ID, generator=racing_generator
        )
    assert isolated_session.query(ApplicationPackageRecord).count() == 0
    logs = caplog.text
    assert "Riley Chen" not in logs
    assert "Jordan Avery" not in logs
    assert "riley@example.com" not in logs
    assert "You write application materials" not in logs
    assert "Built Python APIs at Northstar Labs" not in logs


def test_profile_change_during_generate_does_not_call_fallback_provider(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.services.candidate_profile_agent import persist_candidate_profile

    seed_materials_prerequisites(isolated_session)
    providers_used: list[str] = []

    monkeypatch.setattr(
        "backend.services.application_materials_agent.configured_provider_names",
        lambda: ["ollama", "gemini"],
    )

    def fake_client(name: str):
        providers_used.append(name)
        return object()

    def fake_invoke(_client, _prompt, _system, _schema):
        persist_candidate_profile(_profile_b(), isolated_session, TEST_USER_ID)
        isolated_session.expire_all()
        return VALID_MATERIALS_JSON

    monkeypatch.setattr("backend.services.application_materials_agent.get_llm_client", fake_client)
    monkeypatch.setattr(
        "backend.services.application_materials_agent.invoke_provider_generate", fake_invoke
    )

    with pytest.raises(StaleApplicationMaterialsError):
        generate_grounded_application_materials(isolated_session, "manual-abc123", TEST_USER_ID)
    assert providers_used == ["ollama"]
    assert isolated_session.query(ApplicationPackageRecord).count() == 0


def test_profile_change_during_generate_http_is_409(isolated_client) -> None:
    from backend.services.candidate_profile_agent import persist_candidate_profile

    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        seed_materials_prerequisites(db, user_id=client.test_user_id)

    def racing_generator(_prompt: str, _system_prompt: str | None = None) -> str:
        with SessionLocal() as db:
            persist_candidate_profile(_profile_b(), db, client.test_user_id)
        return VALID_MATERIALS_JSON

    client.app.state.application_materials_generator = racing_generator
    response = client.post("/api/jobs/manual-abc123/generate-materials")
    assert response.status_code == 409
    detail = response.json()["detail"].lower()
    assert "previous candidate" in detail
    assert "riley" not in detail
    with SessionLocal() as db:
        assert db.query(ApplicationPackageRecord).count() == 0


def _stamp_display_preference(session, candidate: Candidate, *, legal_name: str, linkedin_url: str) -> TargetPreference:
    pref = session.query(TargetPreference).filter_by(user_id=candidate.user_id).one()
    pref.candidate_id = candidate.id
    pref.legal_name = legal_name
    pref.linkedin_url = linkedin_url
    pref.github_url = "https://github.com/example-user"
    pref.portfolio_url = "https://example.com/portfolio"
    session.commit()
    session.refresh(pref)
    return pref


def test_context_fingerprint_matches_prompt_preference_records(isolated_session) -> None:
    from backend.services.candidate_provenance import hash_resume_input_snapshot, snapshot_resume_input

    job, candidate = seed_materials_prerequisites(isolated_session)
    pref = _stamp_display_preference(
        isolated_session,
        candidate,
        legal_name="Jordan Avery",
        linkedin_url="https://linkedin.com/in/jordanavery",
    )
    context = load_application_materials_context(isolated_session, job.public_id, TEST_USER_ID)
    _, user_prompt = build_application_materials_prompt(context)
    expected = hash_resume_input_snapshot(snapshot_resume_input(candidate, pref))
    assert context.resume_input_fingerprint == expected
    assert context.preferences is not None
    assert context.preferences.legal_name == "Jordan Avery"
    assert context.preferences.linkedin_url == "https://linkedin.com/in/jordanavery"
    assert "https://linkedin.com/in/jordanavery" in user_prompt
    assert context.preferences.salary_min is None or "135000" not in user_prompt


def test_newer_preference_insert_during_context_load_cannot_split_prompt_and_fingerprint(
    isolated_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.services import application_materials_agent as ama
    from backend.services.candidate_provenance import hash_resume_input_snapshot, snapshot_resume_input

    job, candidate = seed_materials_prerequisites(isolated_session)
    pref_a = _stamp_display_preference(
        isolated_session,
        candidate,
        legal_name="Jordan Avery",
        linkedin_url="https://linkedin.com/in/jordanavery",
    )
    original = ama._preference_record_to_schema

    def insert_newer_then_convert(record: TargetPreference):
        isolated_session.add(
            TargetPreference(
                user_id=TEST_USER_ID,
                candidate_id=candidate.id,
                legal_name="Riley Chen Legal",
                linkedin_url="https://linkedin.com/in/riley-b",
                github_url="https://github.com/riley-b",
                portfolio_url="https://riley.example.com",
            )
        )
        isolated_session.commit()
        return original(record)

    monkeypatch.setattr(ama, "_preference_record_to_schema", insert_newer_then_convert)
    context = load_application_materials_context(isolated_session, job.public_id, TEST_USER_ID)
    _, user_prompt = build_application_materials_prompt(context)
    expected_a = hash_resume_input_snapshot(snapshot_resume_input(candidate, pref_a))
    assert context.resume_input_fingerprint == expected_a
    assert context.preferences is not None
    assert context.preferences.legal_name == "Jordan Avery"
    assert "Riley Chen Legal" not in user_prompt
    assert "riley-b" not in user_prompt
    assert "riley.example.com" not in user_prompt


def test_display_preference_change_during_generate_fails_closed(
    isolated_session, monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    from sqlalchemy.orm import sessionmaker

    caplog.set_level(logging.DEBUG)
    job, candidate = seed_materials_prerequisites(isolated_session)
    pref = _stamp_display_preference(
        isolated_session,
        candidate,
        legal_name="Jordan Avery",
        linkedin_url="https://linkedin.com/in/jordanavery",
    )
    pref_id = pref.id
    providers_used: list[str] = []
    Other = sessionmaker(bind=isolated_session.get_bind(), autocommit=False, autoflush=False)

    monkeypatch.setattr(
        "backend.services.application_materials_agent.configured_provider_names",
        lambda: ["ollama", "gemini"],
    )

    def fake_client(name: str):
        providers_used.append(name)
        return object()

    def fake_invoke(_client, _prompt, _system, _schema):
        with Other() as other:
            row = other.get(TargetPreference, pref_id)
            assert row is not None
            row.legal_name = "Riley Chen Legal"
            row.linkedin_url = "https://linkedin.com/in/riley-b"
            other.commit()
        return VALID_MATERIALS_JSON

    monkeypatch.setattr("backend.services.application_materials_agent.get_llm_client", fake_client)
    monkeypatch.setattr(
        "backend.services.application_materials_agent.invoke_provider_generate", fake_invoke
    )

    with pytest.raises(StaleApplicationMaterialsError):
        generate_grounded_application_materials(isolated_session, job.public_id, TEST_USER_ID)
    assert providers_used == ["ollama"]
    assert isolated_session.query(ApplicationPackageRecord).count() == 0
    logs = caplog.text
    assert "You write application materials" not in logs
    assert "resume_input_snapshot" not in logs
    assert "jordan@example.com" not in logs
    assert "Riley Chen Legal" not in logs
    assert "https://linkedin.com/in/jordanavery" not in logs
    assert "https://linkedin.com/in/riley-b" not in logs
    assert "+1-555" not in logs and "555-010" not in logs


def test_display_preference_change_during_generate_http_is_409(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        job, candidate = seed_materials_prerequisites(db, user_id=client.test_user_id)
        pref = _stamp_display_preference(
            db,
            candidate,
            legal_name="Jordan Avery",
            linkedin_url="https://linkedin.com/in/jordanavery",
        )
        pref_id = pref.id

    def racing_generator(_prompt: str, _system_prompt: str | None = None) -> str:
        with SessionLocal() as db:
            row = db.get(TargetPreference, pref_id)
            assert row is not None
            row.legal_name = "Riley Chen Legal"
            row.linkedin_url = "https://linkedin.com/in/riley-b"
            db.commit()
        return VALID_MATERIALS_JSON

    client.app.state.application_materials_generator = racing_generator
    response = client.post("/api/jobs/manual-abc123/generate-materials")
    assert response.status_code == 409
    detail = response.json()["detail"].lower()
    assert "previous candidate" in detail
    assert "riley" not in detail
    assert "linkedin.com" not in detail
    with SessionLocal() as db:
        assert db.query(ApplicationPackageRecord).count() == 0
