"""skill_preferences must not become resume-grounded Candidate.skills evidence."""

from __future__ import annotations

from backend.db.models import Candidate
from backend.services.analysis_service import score_job
from tests.mvp_helpers import insert_candidate, insert_job


def test_saving_skill_preferences_does_not_merge_into_candidate_skills(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        candidate = insert_candidate(db, user_id=client.test_user_id)
        assert "Kubernetes" not in (candidate.skills or [])

    response = client.post(
        "/api/preferences",
        json={
            "target_roles": ["Software Engineer"],
            "skill_preferences": ["Kubernetes"],
            "opportunity_preference": "internships",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["skill_preferences"] == ["Kubernetes"]

    profile = client.get("/api/profile").json()
    assert profile["preferences"]["skill_preferences"] == ["Kubernetes"]
    assert "Kubernetes" not in (profile["candidate"]["skills"] or [])

    with SessionLocal() as db:
        stored = db.query(Candidate).filter(Candidate.user_id == client.test_user_id).one()
        assert "Kubernetes" not in (stored.skills or [])


def test_preference_only_skill_does_not_inflate_fit_matched_skills(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        insert_candidate(db, user_id=client.test_user_id)
        job = insert_job(db, public_id="pref-skill-job")
        job.description = "Requirements: Kubernetes and Python."
        db.commit()

    response = client.post(
        "/api/preferences",
        json={
            "target_roles": ["Software Engineer"],
            "skill_preferences": ["Kubernetes"],
            "opportunity_preference": "internships",
        },
    )
    assert response.status_code == 201, response.text

    with SessionLocal() as db:
        result = score_job(db, "pref-skill-job", client.test_user_id)
        assert "Kubernetes" not in result.matched_skills
        assert "Kubernetes" in result.missing_skills
        assert "Python" in result.matched_skills
