"""Merge-gate regressions for grounded application materials."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.db.models import ApplicationPackageRecord, Candidate, MatchScoreRecord
from backend.services.application_materials_agent import (
    ApplicationMaterialsConflictError,
    ApplicationMaterialsParseError,
    ApplicationMaterialsStructuredOutput,
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
    job_id = session.query(type(seed_materials_prerequisites(session)[0])).first()
    context = load_application_materials_context(session, "manual-abc123")
    output = ApplicationMaterialsStructuredOutput(
        tailored_bullets=list(fields.get("bullets") or []),
        cover_letter_draft=fields.get("cover") or "",
        recruiter_message=fields.get("recruiter") or "",
        source_traceability_notes=list(fields.get("notes") or []),
    )
    return ground_application_materials(output, context)


def test_target_company_does_not_support_candidate_employment_history(isolated_session) -> None:
    seed_materials_prerequisites(isolated_session, title="Software Engineer Intern")
    context = load_application_materials_context(isolated_session, "manual-abc123")
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
    context = load_application_materials_context(isolated_session, "manual-abc123")
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
    context = load_application_materials_context(isolated_session, "manual-abc123")
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
            isolated_session, "manual-abc123", generator=empty
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
            isolated_session, "manual-abc123", generator=one_arg_contract
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


def test_refresh_reuses_current_candidate_package_without_provider(isolated_session) -> None:
    seed_materials_prerequisites(isolated_session)
    first = get_or_generate_application_package(
        isolated_session, "manual-abc123", generator=fake_grounded_generator
    )
    calls = {"n": 0}

    def counting(_prompt: str, _system_prompt: str | None = None) -> str:
        calls["n"] += 1
        return VALID_MATERIALS_JSON

    second = get_or_generate_application_package(
        isolated_session, "manual-abc123", generator=counting
    )
    assert calls["n"] == 0
    assert first.tailored_bullets == second.tailored_bullets


def test_stale_pending_package_is_replaced_after_new_grounded_output(isolated_session) -> None:
    job, first = seed_materials_prerequisites(isolated_session)
    insert_grounded_package(isolated_session, job, candidate=first)
    second = insert_candidate(isolated_session)
    insert_score(isolated_session, job, second)
    package = get_or_generate_application_package(
        isolated_session, "manual-abc123", generator=fake_grounded_generator
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
    with pytest.raises((ApplicationMaterialsConflictError, Exception)):
        get_or_generate_application_package(
            isolated_session, "manual-abc123", generator=fake_grounded_generator
        )
    stored = isolated_session.query(ApplicationPackageRecord).one()
    assert stored.candidate_id == first.id
    assert stored.approval_status == "approved"


def test_unique_conflict_does_not_return_ungrounded_winner(isolated_session, monkeypatch) -> None:
    job, candidate = seed_materials_prerequisites(isolated_session)
    winner = ApplicationPackageRecord(
        job_id=job.id,
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
    with pytest.raises((ApplicationMaterialsConflictError, ApplicationMaterialsParseError)):
        generate_grounded_application_materials(
            isolated_session, "manual-abc123", generator=fake_grounded_generator
        )
    monkeypatch.undo()
    stored = get_stored_application_package
    with pytest.raises(Exception):
        stored(isolated_session, "manual-abc123")


def test_unsupported_word_quantity_is_rejected(isolated_session) -> None:
    seed_materials_prerequisites(isolated_session)
    context = load_application_materials_context(isolated_session, "manual-abc123")
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
    context = load_application_materials_context(isolated_session, "manual-abc123")
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
    context = load_application_materials_context(isolated_session, "manual-abc123")
    output = ApplicationMaterialsStructuredOutput(
        tailored_bullets=["Backend APIs are one of my strengths, including Python at Northstar Labs."],
        cover_letter_draft="I built Python APIs at Northstar Labs.",
        recruiter_message="Happy to discuss Python.",
        source_traceability_notes=["Python <- skills"],
    )
    report = ground_application_materials(output, context)
    assert report.grounded is True


def test_production_main_has_no_browser_fake_materials_backdoor() -> None:
    source = Path("backend/main.py").read_text(encoding="utf-8")
    assert "_browser_fake_materials" not in source
    assert "CAREERPILOT_BROWSER_FAKE_MATERIALS" not in source
