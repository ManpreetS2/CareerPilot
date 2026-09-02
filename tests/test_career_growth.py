"""Read-only Career Growth aggregation regressions."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from backend.db.models import (
    Candidate,
    JobRequirementProfileRecord,
    MatchEvidenceRecord,
    MatchScoreRecord,
    SavedJobRecord,
    TargetPreference,
)
from backend.schemas.job_requirements import EXTRACTION_VERSION
from backend.schemas.match_evidence import EVIDENCE_VERSION, MatchFactor
from backend.services.candidate_provenance import fingerprint_for_candidate
from backend.services.career_growth_service import COHORT_MAX_JOBS, build_career_growth
from backend.services.job_content import source_fingerprint
from backend.services.match_evidence_service import preference_fingerprint
from backend.services.profile_readiness import ProfileNotReadyError
from tests.mvp_helpers import (
    TEST_USER_ID,
    insert_job,
    insert_ready_profile,
    insert_score,
)


def _save(session, user_id: int, job) -> None:
    session.add(SavedJobRecord(user_id=user_id, job_id=job.id))
    session.commit()


def _skill_factor(
    job_id: str,
    label: str,
    *,
    importance: str = "required",
    status: str = "unknown",
    refs: list[str] | None = None,
) -> dict:
    if refs is None and status in {"satisfied", "partially_satisfied"}:
        refs = ["cand-ref-1"]
    factor = MatchFactor(
        id=f"factor_{label.lower().replace(' ', '_')}_{importance}_{status}",
        job_id=job_id,
        category="skill",
        section="required_skills" if importance == "required" else "preferred_skills",
        label=label,
        importance=importance,
        status=status,  # type: ignore[arg-type]
        rule_id="skill_row_v2",
        rule_version="v2",
        explanation="test",
        candidate_evidence_refs=list(refs or []),
        job_evidence_refs=["job-ref-1"],
    )
    return factor.model_dump()


def _insert_evidence(
    session,
    *,
    user_id: int,
    job,
    candidate,
    score,
    factors: list[dict],
    candidate_fp: str | None = None,
    preference_fp: str | None = None,
    requirement_fp: str | None = None,
) -> MatchEvidenceRecord:
    prefs = (
        session.query(TargetPreference)
        .filter(TargetPreference.user_id == user_id)
        .first()
    )
    row = MatchEvidenceRecord(
        user_id=user_id,
        job_id=job.id,
        candidate_id=candidate.id,
        match_score_id=score.id,
        score_kind="verified",
        scoring_version=2,
        evidence_version=EVIDENCE_VERSION,
        candidate_fingerprint=candidate_fp or fingerprint_for_candidate(session, candidate, user_id),
        preference_fingerprint=preference_fp or preference_fingerprint(prefs),
        requirement_fingerprint=requirement_fp or source_fingerprint(job.title, job.description),
        payload_json={"factors": factors, "evaluations": [], "groups": [], "evidence": {}},
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _job_with_skills(
    session,
    candidate,
    *,
    public_id: str,
    skills: list[tuple[str, str, str]],
    save: bool = True,
    ranking: float = 50.0,
    extra_factors: list[dict] | None = None,
):
    job = insert_job(session, public_id=public_id, title=f"Role {public_id}")
    score = insert_score(session, job, candidate)
    score.ranking_score = ranking
    score.score_kind = "verified"
    session.commit()
    factors = [
        _skill_factor(job.public_id, label, importance=importance, status=status)
        for label, importance, status in skills
    ]
    if extra_factors:
        factors.extend(extra_factors)
    _insert_evidence(session, user_id=candidate.user_id, job=job, candidate=candidate, score=score, factors=factors)
    if save:
        _save(session, candidate.user_id, job)
    return job


def _block_expensive_work(monkeypatch: pytest.MonkeyPatch) -> dict[str, Mock]:
    blocked = {
        "scout": Mock(side_effect=AssertionError("must not scout")),
        "extract": Mock(side_effect=AssertionError("must not extract")),
        "score": Mock(side_effect=AssertionError("must not score")),
        "slot": Mock(side_effect=AssertionError("must not call provider slot")),
        "gemini": Mock(side_effect=AssertionError("must not call Gemini")),
        "ollama": Mock(side_effect=AssertionError("must not call Ollama")),
        "openai": Mock(side_effect=AssertionError("must not call OpenAI")),
        "anthropic": Mock(side_effect=AssertionError("must not call Anthropic")),
    }
    monkeypatch.setattr("backend.services.job_service.scout_jobs", blocked["scout"])
    monkeypatch.setattr(
        "backend.services.job_intelligence_service.extract_job_intelligence",
        blocked["extract"],
    )
    monkeypatch.setattr(
        "backend.services.scoring_orchestrator.score_job_with_intelligence",
        blocked["score"],
    )
    monkeypatch.setattr("backend.services.verified_fit_service.score_job_verified", blocked["score"])
    monkeypatch.setattr(
        "backend.services.extraction_pool.generate_with_provider_slot",
        blocked["slot"],
    )
    monkeypatch.setattr("backend.services.llm_client.LLMClient.generate", blocked["gemini"])
    return blocked


def test_incomplete_profile_does_not_aggregate(isolated_session) -> None:
    with pytest.raises(ProfileNotReadyError):
        build_career_growth(isolated_session, TEST_USER_ID)


def test_sql_frequency_aliases_and_duplicate_mentions(isolated_session) -> None:
    candidate, _prefs = insert_ready_profile(isolated_session)
    for index in range(1, 9):
        label = "SQL" if index % 2 else "sql"
        extra = [_skill_factor(f"sql-{index}", "SQL", importance="required", status="unknown")]
        _job_with_skills(
            isolated_session,
            candidate,
            public_id=f"sql-{index}",
            skills=[(label, "required" if index <= 5 else "preferred", "unknown")],
            extra_factors=extra if index == 1 else None,
        )
    _job_with_skills(
        isolated_session,
        candidate,
        public_id="py-only",
        skills=[("Python", "required", "satisfied")],
    )
    _job_with_skills(
        isolated_session,
        candidate,
        public_id="docker-only",
        skills=[("Docker", "preferred", "unknown")],
    )

    summary = build_career_growth(isolated_session, TEST_USER_ID)
    sql = next(item for item in summary.skill_gaps if item.label == "SQL")
    assert sql.jobs_count == 8
    assert sql.denominator == 10
    assert sql.required_count == 5
    assert sql.preferred_count == 3
    assert sql.candidate_evidence_state == "unknown"
    assert sql.priority == "high"
    assert "does not currently have evidence" in sql.reason
    assert "You don't know" not in sql.reason
    assert "You don't know" not in sql.suggested_action
    assert "If you already use SQL" in sql.suggested_action
    assert summary.jobs_considered == 10
    assert summary.jobs_with_current_evidence == 10


def test_preferred_is_never_promoted_to_required(isolated_session) -> None:
    candidate, _prefs = insert_ready_profile(isolated_session)
    for index in range(3):
        _job_with_skills(
            isolated_session,
            candidate,
            public_id=f"docker-{index}",
            skills=[("Docker", "preferred", "unknown")],
        )
    summary = build_career_growth(isolated_session, TEST_USER_ID)
    docker = next(item for item in summary.skill_gaps if item.label == "Docker")
    assert docker.required_count == 0
    assert docker.preferred_count == 3
    assert docker.jobs_count == 3
    assert "Optional" in docker.suggested_action or "If you already use Docker" in docker.suggested_action


def test_react_and_node_aliases_collapse(isolated_session) -> None:
    candidate, _prefs = insert_ready_profile(isolated_session)
    _job_with_skills(
        isolated_session,
        candidate,
        public_id="react-a",
        skills=[("React.js", "required", "unknown")],
    )
    _job_with_skills(
        isolated_session,
        candidate,
        public_id="react-b",
        skills=[("React", "required", "unknown")],
    )
    _job_with_skills(
        isolated_session,
        candidate,
        public_id="node-a",
        skills=[("NodeJS", "preferred", "unknown")],
    )
    _job_with_skills(
        isolated_session,
        candidate,
        public_id="node-b",
        skills=[("Node.js", "preferred", "unknown")],
    )
    summary = build_career_growth(isolated_session, TEST_USER_ID)
    react_items = [item for item in summary.skill_gaps if item.label == "React"]
    node_items = [item for item in summary.skill_gaps if item.label == "Node.js"]
    assert len(react_items) == 1
    assert react_items[0].jobs_count == 2
    assert len(node_items) == 1
    assert node_items[0].jobs_count == 2
    assert "node_js" not in node_items[0].label.lower()


def test_evidence_states_are_preserved(isolated_session) -> None:
    candidate, _prefs = insert_ready_profile(isolated_session)
    _job_with_skills(isolated_session, candidate, public_id="sat", skills=[("Python", "required", "satisfied")])
    _job_with_skills(isolated_session, candidate, public_id="part", skills=[("AWS", "required", "partially_satisfied")])
    _job_with_skills(isolated_session, candidate, public_id="unk", skills=[("Kubernetes", "required", "unknown")])
    _job_with_skills(isolated_session, candidate, public_id="ns", skills=[("Go", "required", "not_satisfied")])
    summary = build_career_growth(isolated_session, TEST_USER_ID)
    by_label = {item.label: item for item in [*summary.skill_gaps, *summary.strengths]}
    assert by_label["Python"].candidate_evidence_state == "satisfied"
    assert by_label["Python"] in summary.strengths
    assert by_label["AWS"].candidate_evidence_state == "partial"
    assert "Strengthen" in by_label["AWS"].suggested_action
    assert "from zero" not in by_label["AWS"].suggested_action.lower()
    assert by_label["Kubernetes"].candidate_evidence_state == "unknown"
    assert by_label["Go"].candidate_evidence_state == "not_satisfied"
    assert all("Missing." != item.reason for item in summary.skill_gaps)
    assert "You're perfect" not in (summary.notice or "")


def test_stale_candidate_and_preference_evidence_excluded(isolated_session) -> None:
    candidate, prefs = insert_ready_profile(isolated_session)
    current = _job_with_skills(
        isolated_session, candidate, public_id="current-sql", skills=[("SQL", "required", "unknown")]
    )
    stale_candidate = insert_job(isolated_session, public_id="stale-cand", title="Stale candidate")
    stale_prefs = insert_job(isolated_session, public_id="stale-prefs", title="Stale prefs")
    stale_reqs = insert_job(isolated_session, public_id="stale-reqs", title="Stale requirements")
    for job, kwargs in (
        (stale_candidate, {"candidate_fp": "not-the-current-candidate-fingerprint"}),
        (stale_prefs, {"preference_fp": "not-the-current-preference-fingerprint"}),
        (stale_reqs, {"requirement_fp": "not-the-current-requirement-fingerprint"}),
    ):
        score = insert_score(isolated_session, job, candidate)
        score.ranking_score = 90
        score.score_kind = "verified"
        isolated_session.commit()
        _insert_evidence(
            isolated_session,
            user_id=candidate.user_id,
            job=job,
            candidate=candidate,
            score=score,
            factors=[_skill_factor(job.public_id, "SQL", importance="required", status="unknown")],
            **kwargs,
        )
        _save(isolated_session, candidate.user_id, job)

    summary = build_career_growth(isolated_session, TEST_USER_ID)
    assert summary.stale_jobs_excluded == 3
    assert summary.jobs_with_current_evidence == 1
    sql = next(item for item in summary.skill_gaps if item.label == "SQL")
    assert sql.jobs_count == 1
    assert sql.denominator == 1
    assert current.public_id in {ref.job_id for ref in sql.related_jobs}


def test_saved_and_matched_overlap_is_deduped(isolated_session) -> None:
    candidate, _prefs = insert_ready_profile(isolated_session)
    job = _job_with_skills(
        isolated_session,
        candidate,
        public_id="both",
        skills=[("Python", "required", "satisfied")],
        save=True,
        ranking=99,
    )
    summary = build_career_growth(isolated_session, TEST_USER_ID)
    assert summary.jobs_considered == 1
    assert summary.saved_jobs_considered == 1
    assert summary.matched_jobs_considered == 0
    assert job.public_id == summary.strengths[0].related_jobs[0].job_id


def test_matches_only_uses_stored_ranking(isolated_session) -> None:
    candidate, _prefs = insert_ready_profile(isolated_session)
    _job_with_skills(
        isolated_session,
        candidate,
        public_id="match-sql",
        skills=[("SQL", "required", "unknown")],
        save=False,
        ranking=88,
    )
    summary = build_career_growth(isolated_session, TEST_USER_ID)
    assert summary.saved_jobs_considered == 0
    assert summary.matched_jobs_considered == 1
    assert summary.jobs_with_current_evidence == 1


def test_cohort_prefers_saved_then_top_matches_and_bounds(isolated_session) -> None:
    candidate, _prefs = insert_ready_profile(isolated_session)
    for index in range(COHORT_MAX_JOBS + 5):
        _job_with_skills(
            isolated_session,
            candidate,
            public_id=f"saved-{index}",
            skills=[("Python", "required", "satisfied")],
            save=True,
            ranking=float(index),
        )
    summary = build_career_growth(isolated_session, TEST_USER_ID)
    assert summary.jobs_considered == COHORT_MAX_JOBS
    assert summary.saved_jobs_considered == COHORT_MAX_JOBS


def test_score_fallback_when_evidence_row_is_absent(isolated_session) -> None:
    candidate, _prefs = insert_ready_profile(isolated_session)
    job = insert_job(isolated_session, public_id="score-only", title="Score only")
    score = insert_score(
        isolated_session,
        job,
        candidate,
        matched_skills=["Python"],
        missing_skills=["Kubernetes"],
    )
    score.ranking_score = 70
    score.score_kind = "verified"
    isolated_session.commit()
    fingerprint = source_fingerprint(job.title, job.description)
    isolated_session.add(
        JobRequirementProfileRecord(
            job_id=job.id,
            source_fingerprint=fingerprint,
            extraction_version=EXTRACTION_VERSION,
            profile_json={
                "source_fingerprint": fingerprint,
                "extraction_version": EXTRACTION_VERSION,
                "required_skills": ["Python", "Kubernetes"],
                "preferred_skills": ["Docker"],
            },
        )
    )
    isolated_session.commit()
    _save(isolated_session, candidate.user_id, job)
    summary = build_career_growth(isolated_session, TEST_USER_ID)
    labels = {item.label: item for item in [*summary.skill_gaps, *summary.strengths]}
    assert labels["Python"].candidate_evidence_state == "satisfied"
    assert labels["Kubernetes"].candidate_evidence_state == "unknown"
    assert labels["Docker"].required_count == 0
    assert labels["Docker"].preferred_count == 1


def test_eligibility_and_eeo_are_excluded(isolated_session) -> None:
    candidate, prefs = insert_ready_profile(isolated_session)
    prefs.gender = "SENTINEL_GENDER_VALUE"
    prefs.race_ethnicity = "SENTINEL_RACE_VALUE"
    prefs.veteran_status = "SENTINEL_VETERAN_VALUE"
    prefs.disability_status = "SENTINEL_DISABILITY_VALUE"
    isolated_session.commit()
    job = insert_job(isolated_session, public_id="elig", title="Auth role")
    score = insert_score(isolated_session, job, candidate)
    score.score_kind = "verified"
    isolated_session.commit()
    factors = [
        _skill_factor(job.public_id, "Python", importance="required", status="satisfied"),
        MatchFactor(
            id="factor_work_auth",
            job_id=job.public_id,
            category="work_authorization",
            section="eligibility",
            label="US work authorization",
            importance="required",
            status="not_satisfied",
            rule_id="work_auth",
            rule_version="v2",
            explanation="authorization",
        ).model_dump(),
        MatchFactor(
            id="factor_clearance",
            job_id=job.public_id,
            category="other_requirement",
            section="eligibility",
            label="Security clearance",
            importance="required",
            status="unknown",
            rule_id="clearance",
            rule_version="v2",
            explanation="clearance",
        ).model_dump(),
        MatchFactor(
            id="factor_salary",
            job_id=job.public_id,
            category="salary",
            section="preferences",
            label="Improve your salary",
            importance="preferred",
            status="unknown",
            rule_id="salary",
            rule_version="v2",
            explanation="salary",
        ).model_dump(),
    ]
    _insert_evidence(
        isolated_session,
        user_id=candidate.user_id,
        job=job,
        candidate=candidate,
        score=score,
        factors=factors,
    )
    _save(isolated_session, candidate.user_id, job)
    summary = build_career_growth(isolated_session, TEST_USER_ID)
    blob = summary.model_dump_json()
    assert "SENTINEL_GENDER_VALUE" not in blob
    assert "SENTINEL_RACE_VALUE" not in blob
    assert "SENTINEL_VETERAN_VALUE" not in blob
    assert "SENTINEL_DISABILITY_VALUE" not in blob
    assert "US work authorization" not in blob
    assert "Security clearance" not in blob
    assert "Learn work authorization" not in blob
    assert "Improve your salary" not in blob
    labels = [item.label for item in [*summary.skill_gaps, *summary.strengths]]
    assert "Python" in labels


def test_cross_user_isolation(isolated_session) -> None:
    candidate_a, _prefs_a = insert_ready_profile(isolated_session, user_id=1)
    candidate_b, _prefs_b = insert_ready_profile(isolated_session, user_id=2)
    _job_with_skills(
        isolated_session,
        candidate_a,
        public_id="a-sql",
        skills=[("SQL", "required", "unknown")],
    )
    _job_with_skills(
        isolated_session,
        candidate_b,
        public_id="b-ruby",
        skills=[("Ruby", "required", "unknown")],
    )
    summary_a = build_career_growth(isolated_session, 1)
    summary_b = build_career_growth(isolated_session, 2)
    labels_a = {item.label for item in summary_a.skill_gaps}
    labels_b = {item.label for item in summary_b.skill_gaps}
    assert "SQL" in labels_a
    assert "Ruby" not in labels_a
    assert "Ruby" in labels_b
    assert "SQL" not in labels_b


def test_get_does_not_mutate_scores_or_call_providers(isolated_session, monkeypatch) -> None:
    candidate, _prefs = insert_ready_profile(isolated_session)
    _job_with_skills(
        isolated_session,
        candidate,
        public_id="stable",
        skills=[("Python", "required", "satisfied")],
    )
    before = [
        (row.id, row.overall_score, row.ranking_score, list(row.matched_skills or []))
        for row in isolated_session.query(MatchScoreRecord).all()
    ]
    blocked = _block_expensive_work(monkeypatch)
    summary = build_career_growth(isolated_session, TEST_USER_ID)
    after = [
        (row.id, row.overall_score, row.ranking_score, list(row.matched_skills or []))
        for row in isolated_session.query(MatchScoreRecord).all()
    ]
    assert before == after
    assert all(mock.call_count == 0 for mock in blocked.values())
    assert summary.jobs_with_current_evidence == 1
    assert isolated_session.query(Candidate).filter_by(user_id=TEST_USER_ID).one().skills == [
        "Python",
        "SQL",
    ]


def test_growth_route_requires_auth_and_profile(isolated_client, monkeypatch) -> None:
    client, SessionLocal = isolated_client
    blocked = _block_expensive_work(monkeypatch)
    response = client.get("/api/career-growth")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "profile_required"
    assert all(mock.call_count == 0 for mock in blocked.values())
    with SessionLocal() as db:
        insert_ready_profile(db, user_id=client.test_user_id)
    ok = client.get("/api/career-growth")
    assert ok.status_code == 200
    body = ok.json()
    assert body["jobs_considered"] == 0
    assert body["notice"] == "Discover or save some jobs first."
    assert all(mock.call_count == 0 for mock in blocked.values())


def test_growth_route_is_user_scoped_and_read_only(isolated_client, monkeypatch) -> None:
    client, SessionLocal = isolated_client
    blocked = _block_expensive_work(monkeypatch)
    with SessionLocal() as db:
        candidate, _ = insert_ready_profile(db, user_id=client.test_user_id)
        _job_with_skills(
            db,
            candidate,
            public_id="mine-sql",
            skills=[("SQL", "required", "unknown")],
        )
        before = [
            (row.id, row.overall_score, row.ranking_score)
            for row in db.query(MatchScoreRecord).all()
        ]
    body = client.get("/api/career-growth").json()
    labels = [item["label"] for item in body["skill_gaps"]]
    assert "SQL" in labels
    assert body["skill_gaps"][0]["jobs_count"] == 1
    assert all(mock.call_count == 0 for mock in blocked.values())
    with SessionLocal() as db:
        after = [
            (row.id, row.overall_score, row.ranking_score)
            for row in db.query(MatchScoreRecord).all()
        ]
        assert before == after
    client.post("/api/auth/logout")
    other = client.post(
        "/api/auth/signup",
        json={"email": "other-growth@example.com", "password": "test-password-123"},
    )
    assert other.status_code == 201
    with SessionLocal() as db:
        insert_ready_profile(db, user_id=other.json()["id"])
    other_body = client.get("/api/career-growth").json()
    other_labels = [item["label"] for item in other_body["skill_gaps"]]
    assert "SQL" not in other_labels
    assert all(mock.call_count == 0 for mock in blocked.values())
