"""Deterministic interview-prep foundation tests."""

from __future__ import annotations

import pytest

from tests.mvp_helpers import TEST_USER_ID, ensure_user, insert_candidate

from backend.db.models import (
    Candidate,
    InterviewPrepRecord,
    JobIntelligenceRecord,
    JobRecord,
    MatchScoreRecord,
)
from backend.services.interview_service import (
    InterviewAnswerEmptyError,
    InterviewIntelligenceMissingError,
    InterviewJobNotFoundError,
    InterviewPrepContext,
    InterviewQuestionNotFoundError,
    build_deterministic_interview_prep,
    generate_and_store_interview_prep,
    get_interview_answer_feedback,
    get_interview_prep,
    unfinished_llm_interview_improver,
)
from backend.schemas.schemas import JobIntelligence


def _job(session, *, public_id: str = "job-interview") -> JobRecord:
    record = JobRecord(
        public_id=public_id,
        title="Software Engineer Intern",
        company="Acme",
        url=f"https://example.com/jobs/{public_id}",
        description="Required: Python. Preferred: Kubernetes.",
        source="manual",
        status="verified",
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _candidate(session):
    return insert_candidate(session, user_id=TEST_USER_ID)



def _intelligence(session, job: JobRecord) -> JobIntelligenceRecord:
    record = JobIntelligenceRecord(
        job_id=job.id,
        required_skills=["Python", "Kubernetes"],
        preferred_skills=["Docker"],
        years_experience=0,
        education_requirements=[],
        tech_stack=["Python"],
        seniority="intern",
        responsibilities=["Implement API endpoints"],
        likely_interview_focus=["Python fundamentals", "SQL joins"],
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def test_interview_missing_job(isolated_session) -> None:
    with pytest.raises(InterviewJobNotFoundError):
        get_interview_prep(isolated_session, "missing", TEST_USER_ID)
    with pytest.raises(InterviewJobNotFoundError):
        generate_and_store_interview_prep(isolated_session, "missing", TEST_USER_ID)


def test_interview_missing_intelligence(isolated_session) -> None:
    job = _job(isolated_session)
    with pytest.raises(InterviewIntelligenceMissingError):
        generate_and_store_interview_prep(isolated_session, job.public_id, TEST_USER_ID)
    assert isolated_session.query(InterviewPrepRecord).count() == 0


def test_interview_get_is_read_only(isolated_session) -> None:
    job = _job(isolated_session)
    assert get_interview_prep(isolated_session, job.public_id, TEST_USER_ID) is None
    assert isolated_session.query(InterviewPrepRecord).count() == 0


def test_interview_generation_uses_grounded_topics_only(isolated_session) -> None:
    candidate = _candidate(isolated_session)
    job = _job(isolated_session)
    _intelligence(isolated_session, job)
    isolated_session.add(
        MatchScoreRecord(
            job_id=job.id,
            candidate_id=candidate.id,
            overall_score=70.0,
            skill_score=60.0,
            matched_skills=["Python"],
            partial_matches=["SQL"],
            missing_skills=["Kubernetes", "Docker"],
            recommendation="consider",
            rationale="Python matched; Kubernetes is missing.",
        )
    )
    isolated_session.commit()

    prep = generate_and_store_interview_prep(isolated_session, job.public_id, TEST_USER_ID)
    blob = " ".join(prep.likely_questions)
    assert "Python fundamentals" in blob
    assert "SQL joins" in blob
    talking = " ".join(prep.talking_points).lower()
    gaps = " ".join(prep.gaps_to_address).lower()
    assert "python" in talking
    assert "kubernetes" not in talking
    assert "campus connect" not in talking
    assert "kubernetes" in gaps
    assert "docker" in gaps
    assert "not a current candidate strength" in gaps
    assert isolated_session.query(InterviewPrepRecord).count() == 1

    again = generate_and_store_interview_prep(isolated_session, job.public_id, TEST_USER_ID)
    assert again.job_id == prep.job_id
    assert isolated_session.query(InterviewPrepRecord).count() == 1


def test_missing_skills_are_gaps_not_strengths_without_fit_score(isolated_session) -> None:
    _candidate(isolated_session)
    job = _job(isolated_session)
    _intelligence(isolated_session, job)
    prep = generate_and_store_interview_prep(isolated_session, job.public_id, TEST_USER_ID)
    talking = " ".join(prep.talking_points).lower()
    gaps = " ".join(prep.gaps_to_address).lower()
    assert "kubernetes" in gaps
    assert "kubernetes" not in talking
    assert "python" in talking


def test_llm_improver_boundary_is_not_used_by_default(isolated_session) -> None:
    _candidate(isolated_session)
    job = _job(isolated_session)
    _intelligence(isolated_session, job)
    called = {"n": 0}

    def boom(_context, _prep):
        called["n"] += 1
        raise AssertionError("improver must not run")

    generate_and_store_interview_prep(isolated_session, job.public_id, TEST_USER_ID)
    assert called["n"] == 0
    with pytest.raises(Exception, match="not implemented"):
        unfinished_llm_interview_improver(None, None)  # type: ignore[arg-type]


def _fake_feedback_generator(prompt: str, system_prompt: str | None = None) -> str:
    return "Solid structure — mention a specific outcome next time."


def test_answer_feedback_missing_job_404s(isolated_session) -> None:
    with pytest.raises(InterviewJobNotFoundError):
        get_interview_answer_feedback(isolated_session, "missing", TEST_USER_ID, "Q?", "answer")


def test_answer_feedback_requires_prep_generated_first(isolated_session) -> None:
    """No InterviewPrepRecord at all yet — practicing before generating prep
    must be rejected, not silently accepted with an ungrounded question."""
    job = _job(isolated_session)
    _intelligence(isolated_session, job)
    with pytest.raises(InterviewQuestionNotFoundError):
        get_interview_answer_feedback(isolated_session, job.public_id, TEST_USER_ID, "Any question", "answer")


def test_answer_feedback_rejects_a_question_not_in_stored_prep(isolated_session) -> None:
    _candidate(isolated_session)
    job = _job(isolated_session)
    _intelligence(isolated_session, job)
    generate_and_store_interview_prep(isolated_session, job.public_id, TEST_USER_ID)
    with pytest.raises(InterviewQuestionNotFoundError):
        get_interview_answer_feedback(
            isolated_session,
            job.public_id,
            TEST_USER_ID,
            "This question was never generated for this job",
            "answer",
        )


def test_answer_feedback_rejects_empty_or_whitespace_answer(isolated_session) -> None:
    _candidate(isolated_session)
    job = _job(isolated_session)
    _intelligence(isolated_session, job)
    prep = generate_and_store_interview_prep(isolated_session, job.public_id, TEST_USER_ID)
    question = prep.likely_questions[0]
    with pytest.raises(InterviewAnswerEmptyError):
        get_interview_answer_feedback(isolated_session, job.public_id, TEST_USER_ID, question, "")
    with pytest.raises(InterviewAnswerEmptyError):
        get_interview_answer_feedback(isolated_session, job.public_id, TEST_USER_ID, question, "   ")


def test_answer_feedback_happy_path_uses_injected_generator(isolated_session) -> None:
    _candidate(isolated_session)
    job = _job(isolated_session)
    _intelligence(isolated_session, job)
    prep = generate_and_store_interview_prep(isolated_session, job.public_id, TEST_USER_ID)
    question = prep.likely_questions[0]

    result = get_interview_answer_feedback(
        isolated_session,
        job.public_id,
        TEST_USER_ID,
        question,
        "I built a Python API and wrote tests for it.",
        generate_fn=_fake_feedback_generator,
    )
    assert result.question == question
    assert result.answer == "I built a Python API and wrote tests for it."
    assert result.feedback == "Solid structure — mention a specific outcome next time."


def test_answer_feedback_is_never_persisted(isolated_session) -> None:
    """Ephemeral by design — no new InterviewPrepRecord (or any row) should
    appear just from requesting practice feedback."""
    _candidate(isolated_session)
    job = _job(isolated_session)
    _intelligence(isolated_session, job)
    prep = generate_and_store_interview_prep(isolated_session, job.public_id, TEST_USER_ID)
    before = isolated_session.query(InterviewPrepRecord).count()

    get_interview_answer_feedback(
        isolated_session,
        job.public_id,
        TEST_USER_ID,
        prep.likely_questions[0],
        "An answer.",
        generate_fn=_fake_feedback_generator,
    )
    assert isolated_session.query(InterviewPrepRecord).count() == before


def test_answer_feedback_prompt_includes_question_answer_and_grounding_instruction(isolated_session) -> None:
    """The generator receives the actual question/answer (not something
    reconstructed), and the system prompt explicitly forbids inventing new
    candidate facts — the same safety bar the rest of the app holds to."""
    candidate = _candidate(isolated_session)
    job = _job(isolated_session)
    _intelligence(isolated_session, job)
    prep = generate_and_store_interview_prep(isolated_session, job.public_id, TEST_USER_ID)
    question = prep.likely_questions[0]
    answer = "I used FastAPI for the backend and wrote pytest coverage."

    captured: dict[str, str | None] = {}

    def capturing_generator(prompt: str, system_prompt: str | None = None) -> str:
        captured["prompt"] = prompt
        captured["system_prompt"] = system_prompt
        return "feedback text"

    get_interview_answer_feedback(
        isolated_session, job.public_id, TEST_USER_ID, question, answer, generate_fn=capturing_generator
    )

    assert question in captured["prompt"]
    assert answer in captured["prompt"]
    assert candidate.skills[0] in captured["prompt"] if candidate.skills else True
    system_prompt = captured["system_prompt"] or ""
    assert "never invent" in system_prompt.lower() or "do not invent" in system_prompt.lower() or "never" in system_prompt.lower()


def test_answer_feedback_http_route_with_injected_generator(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        job = _job(db)
        _intelligence(db, job)
        _candidate(db)

    prepared = client.post("/api/jobs/job-interview/prepare-interview")
    question = prepared.json()["likely_questions"][0]

    client.app.state.interview_answer_generator = _fake_feedback_generator
    response = client.post(
        "/api/jobs/job-interview/interview-prep/feedback",
        json={"question": question, "answer": "I led a small backend project."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["question"] == question
    assert body["feedback"] == "Solid structure — mention a specific outcome next time."


def test_answer_feedback_http_route_rejects_unknown_question(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        job = _job(db)
        _intelligence(db, job)
        _candidate(db)
    client.post("/api/jobs/job-interview/prepare-interview")

    client.app.state.interview_answer_generator = _fake_feedback_generator
    response = client.post(
        "/api/jobs/job-interview/interview-prep/feedback",
        json={"question": "Not a real stored question", "answer": "answer"},
    )
    assert response.status_code == 400


def test_answer_feedback_http_route_rejects_empty_answer(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        job = _job(db)
        _intelligence(db, job)
        _candidate(db)
    prepared = client.post("/api/jobs/job-interview/prepare-interview")
    question = prepared.json()["likely_questions"][0]

    client.app.state.interview_answer_generator = _fake_feedback_generator
    response = client.post(
        "/api/jobs/job-interview/interview-prep/feedback",
        json={"question": question, "answer": "   "},
    )
    assert response.status_code == 400


def test_answer_feedback_http_route_missing_job_404s(isolated_client) -> None:
    client, _SessionLocal = isolated_client
    client.app.state.interview_answer_generator = _fake_feedback_generator
    response = client.post(
        "/api/jobs/does-not-exist/interview-prep/feedback",
        json={"question": "Q?", "answer": "answer"},
    )
    assert response.status_code == 404


def test_interview_http_get_read_only_and_explicit_generate(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        job = _job(db)
        _intelligence(db, job)
        _candidate(db)

    missing = client.get("/api/jobs/nope/interview-prep")
    assert missing.status_code == 404

    unread = client.get("/api/jobs/job-interview/interview-prep")
    assert unread.status_code == 404
    assert unread.json()["detail"] == "Interview prep has not been generated."
    with SessionLocal() as db:
        assert db.query(InterviewPrepRecord).count() == 0

    created = client.post("/api/jobs/job-interview/prepare-interview")
    assert created.status_code == 200
    body = created.json()
    assert body["likely_questions"]
    assert any("gap" in item.lower() or "not a current" in item.lower() for item in body["gaps_to_address"])

    stored = client.get("/api/jobs/job-interview/interview-prep")
    assert stored.status_code == 200
    assert stored.json()["job_id"] == "job-interview"

    with SessionLocal() as db:
        _job(db, public_id="job-no-intel")
    no_intel = client.post("/api/jobs/job-no-intel/prepare-interview")
    assert no_intel.status_code == 409
    assert "job requirements" in no_intel.json()["detail"].lower()


def test_interview_questions_use_internship_wording_only_for_intern_roles() -> None:
    intern = build_deterministic_interview_prep(
        InterviewPrepContext(
            job_id="intern-job",
            job_pk=1,
            job_title="Software Engineer Intern",
            company="Acme",
            intelligence=JobIntelligence(
                required_skills=["Python"],
                likely_interview_focus=["Testing"],
                seniority="intern",
            ),
            fit_score=None,
            candidate_skills=["Python"],
            candidate_has_profile=True,
        )
    )
    intern_blob = " ".join(intern.likely_questions).lower()
    assert "in this internship" in intern_blob

    full_time = build_deterministic_interview_prep(
        InterviewPrepContext(
            job_id="fte-job",
            job_pk=2,
            job_title="Software Engineer",
            company="Acme",
            intelligence=JobIntelligence(
                required_skills=["Python"],
                likely_interview_focus=["Testing"],
                seniority="mid",
            ),
            fit_score=None,
            candidate_skills=["Python"],
            candidate_has_profile=True,
        )
    )
    fte_blob = " ".join(full_time.likely_questions).lower()
    assert "for this role" in fte_blob
    assert "internship" not in fte_blob

    internal = build_deterministic_interview_prep(
        InterviewPrepContext(
            job_id="internal-job",
            job_pk=3,
            job_title="Internal Tools Engineer",
            company="Acme",
            intelligence=JobIntelligence(
                required_skills=["Python"],
                likely_interview_focus=[],
                seniority="mid",
            ),
            fit_score=None,
            candidate_skills=["Python"],
            candidate_has_profile=True,
        )
    )
    assert "internship" not in " ".join(internal.likely_questions).lower()
