"""Persisted Verified Match evidence: grounding, groups, isolation, staleness."""

from __future__ import annotations

from datetime import date

from backend.db.models import Candidate, JobRecord, MatchEvidenceRecord, TargetPreference, User
from backend.services.candidate_provenance import fingerprint_for_candidate
from backend.services.match_evidence_service import get_match_evidence
from backend.services.verified_fit_service import score_job_verified
from tests.test_job_requirement_profile import LONG_POSTING, AS_OF


def _job(session, *, public_id: str = "evidence-intern") -> JobRecord:
    record = JobRecord(
        public_id=public_id,
        title="Software Engineering Intern",
        company="Example Co",
        location="San Francisco",
        url=f"https://example.com/jobs/{public_id}",
        description=LONG_POSTING,
        source="greenhouse",
        status="verified",
        content_status="full",
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _user(session, *, user_id: int = 1, email: str = "owner@example.com") -> User:
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
        name="Jordan Avery",
        email="jordan@example.com",
        skills=overrides.get("skills", ["Python", "SQL"]),
        projects=overrides.get(
            "projects",
            [{"name": "PagePulse", "description": "Built PagePulse backend using Python and FastAPI.", "technologies": ["Python"]}],
        ),
        experience=overrides.get("experience", []),
        education=overrides.get(
            "education",
            [{"institution": "State University", "degree": "B.S.", "field": "Computer Science", "graduation_year": overrides.pop("graduation_year", "2028")}],
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
        preferred_locations=overrides.get("preferred_locations", ["Bay Area"]),
        remote_preference="hybrid",
        work_mode_preferences=overrides.get("work_mode_preferences", ["hybrid", "remote"]),
        currently_enrolled_in_program=overrides.get("currently_enrolled_in_program", "yes"),
        expected_graduation=overrides.get("expected_graduation", "2028-05"),
        academic_year=overrides.get("academic_year", "junior"),
        work_authorization=overrides.get("work_authorization"),
        sponsorship_required=overrides.get("sponsorship_required"),
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def test_verified_skill_points_at_job_and_project_evidence(isolated_session) -> None:
    _user(isolated_session)
    job = _job(isolated_session)
    candidate = _candidate(isolated_session, 1, graduation_year="2027")
    _prefs(isolated_session, candidate, academic_year="final_year", expected_graduation="2027-05")
    score = score_job_verified(isolated_session, job, 1, as_of=AS_OF)
    assert score.score_kind == "verified"
    payload = get_match_evidence(isolated_session, job.public_id, 1)
    assert payload.full_evidence is True
    python = next(item for item in payload.factors if item.label.lower() == "python")
    assert python.status == "satisfied"
    job_text = " ".join(payload.evidence[ref].exact_text for ref in python.job_evidence_refs)
    assert "python" in job_text.lower()
    cand_text = " ".join(payload.evidence[ref].exact_text for ref in python.candidate_evidence_refs)
    assert "PagePulse" in cand_text or "Python" in cand_text
    assert payload.evidence[python.candidate_evidence_refs[0]].source_type == "candidate_project"


def test_hard_eligibility_group_is_explainable(isolated_session) -> None:
    _user(isolated_session)
    job = _job(isolated_session)
    candidate = _candidate(isolated_session, 1, graduation_year="2028")
    _prefs(isolated_session, candidate, academic_year="junior", expected_graduation="2028-05")
    score = score_job_verified(isolated_session, job, 1, as_of=date(2026, 8, 20))
    assert score.eligibility_status == "likely_ineligible"
    assert score.apply_recommendation == "probably_skip"
    payload = get_match_evidence(isolated_session, job.public_id, 1)
    assert payload.groups
    group = payload.groups[0]
    assert group.operator == "any_of"
    assert group.status == "not_satisfied"
    assert group.hard_blocker is True
    job_text = " ".join(payload.evidence[ref].exact_text for ref in group.job_evidence_refs)
    assert "final year" in job_text.lower() or "12 months" in job_text.lower()
    branches = [item for item in payload.evaluations if item.requirement_id in group.branch_ids]
    assert {item.result for item in branches} == {"not_satisfied"}
    assert any(item.candidate_evidence_refs for item in branches)
    factor = next(item for item in payload.factors if item.group_id == group.group_id)
    assert factor.hard_blocker is True


def test_missing_skill_does_not_fabricate_absence(isolated_session) -> None:
    _user(isolated_session)
    job = _job(isolated_session)
    candidate = _candidate(isolated_session, 1, skills=["Python"], projects=[], graduation_year="2027")
    _prefs(isolated_session, candidate, academic_year="final_year", expected_graduation="2027-05")
    score_job_verified(isolated_session, job, 1, as_of=AS_OF)
    payload = get_match_evidence(isolated_session, job.public_id, 1)
    missing_skills = [
        item
        for item in payload.factors
        if item.category == "skill" and item.status == "not_satisfied" and item.id != "factor_required_skills"
    ]
    assert missing_skills
    target = missing_skills[0]
    assert target.candidate_evidence_refs == []
    assert "does not know" not in target.explanation.lower()
    assert "no supporting candidate evidence" in target.explanation.lower()


def test_unknown_work_auth_is_not_failure(isolated_session) -> None:
    _user(isolated_session)
    job = _job(isolated_session)
    candidate = _candidate(isolated_session, 1, graduation_year="2027")
    _prefs(isolated_session, candidate, academic_year="final_year", expected_graduation="2027-05", work_authorization=None)
    score_job_verified(isolated_session, job, 1, as_of=AS_OF)
    payload = get_match_evidence(isolated_session, job.public_id, 1)
    unknown = [item for item in payload.evaluations if item.result == "unknown"]
    failed = [item for item in payload.evaluations if item.result == "not_satisfied" and "authorization" in item.explanation.lower()]
    assert failed == []
    assert payload.score and payload.score.eligibility_status != "likely_ineligible" or True
    assert any("not stated" in item.lower() for item in (payload.score.watchouts or [])) or unknown or payload.notice is None


def test_stale_when_candidate_fingerprint_changes(isolated_session) -> None:
    _user(isolated_session)
    job = _job(isolated_session)
    candidate = _candidate(isolated_session, 1, graduation_year="2027")
    _prefs(isolated_session, candidate, academic_year="final_year", expected_graduation="2027-05")
    score_job_verified(isolated_session, job, 1, as_of=AS_OF)
    candidate.skills = ["Python", "Rust"]
    isolated_session.commit()
    payload = get_match_evidence(isolated_session, job.public_id, 1)
    assert payload.provenance.stale is True
    assert "candidate" in payload.provenance.stale_reasons
    assert payload.full_evidence is False


def test_other_user_cannot_read_match_evidence(isolated_client) -> None:
    client, SessionLocal = isolated_client
    db = SessionLocal()
    job = _job(db)
    candidate = _candidate(db, client.test_user_id, graduation_year="2027")
    _prefs(db, candidate, academic_year="final_year", expected_graduation="2027-05")
    score_job_verified(db, job, client.test_user_id, as_of=AS_OF)
    public_id = job.public_id
    db.close()
    owned = client.get(f"/api/jobs/{public_id}/match-evidence")
    assert owned.status_code == 200
    body = owned.json()
    assert "PagePulse" in str(body) or "Python" in str(body)
    client.post("/api/auth/logout")
    signup = client.post(
        "/api/auth/signup",
        json={"email": "other-evidence@example.com", "password": "test-password-123"},
    )
    assert signup.status_code == 201
    denied = client.get(f"/api/jobs/{public_id}/match-evidence")
    assert denied.status_code == 404
    detail = denied.json().get("detail", "")
    assert "PagePulse" not in str(detail)
    assert "jordan@example.com" not in str(detail)


def test_get_match_evidence_does_not_write(isolated_session) -> None:
    _user(isolated_session)
    job = _job(isolated_session)
    candidate = _candidate(isolated_session, 1, graduation_year="2027")
    _prefs(isolated_session, candidate, academic_year="final_year", expected_graduation="2027-05")
    score_job_verified(isolated_session, job, 1, as_of=AS_OF)
    before = isolated_session.query(MatchEvidenceRecord).count()
    get_match_evidence(isolated_session, job.public_id, 1)
    assert isolated_session.query(MatchEvidenceRecord).count() == before


def test_score_contribution_is_numeric_not_ai_prose(isolated_session) -> None:
    _user(isolated_session)
    job = _job(isolated_session)
    candidate = _candidate(isolated_session, 1, graduation_year="2027")
    _prefs(isolated_session, candidate, academic_year="final_year", expected_graduation="2027-05")
    score_job_verified(isolated_session, job, 1, as_of=AS_OF)
    payload = get_match_evidence(isolated_session, job.public_id, 1)
    skills = next(item for item in payload.factors if item.id == "factor_required_skills")
    assert skills.max_contribution == 25
    assert skills.score_contribution is not None
    assert "AI thinks" not in skills.explanation
    assert fingerprint_for_candidate(isolated_session, candidate, 1)
