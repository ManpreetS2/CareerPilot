"""Jobs workspace: structured search, pagination, saved-job isolation."""

from __future__ import annotations

from backend.db.models import Candidate, JobRecord, MatchScoreRecord, SavedJobRecord
from backend.services.opportunity_type import infer_employment_type, infer_opportunity_type, infer_work_mode
from tests.mvp_helpers import insert_candidate


def _job(
    db,
    *,
    public_id: str,
    title: str,
    location: str | None = None,
    description: str = "Python. Hybrid in San Francisco.",
    source: str = "manual",
) -> JobRecord:
    record = JobRecord(
        public_id=public_id,
        title=title,
        company="Acme",
        location=location,
        url=f"https://example.com/jobs/{public_id}",
        description=description,
        source=source,
        status="discovered",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _score(
    db,
    job: JobRecord,
    candidate: Candidate,
    *,
    ranking_score: float,
    score_kind: str = "preliminary",
    overall_score: float | None = None,
    qualification_score: float = 50,
    preference_score: float = 50,
    eligibility_status: str = "eligibility_uncertain",
    confidence_level: str = "medium",
) -> MatchScoreRecord:
    record = MatchScoreRecord(
        job_id=job.id,
        candidate_id=candidate.id,
        overall_score=overall_score if overall_score is not None else ranking_score,
        recommendation="consider",
        rationale="test",
        ranking_score=ranking_score,
        scoring_version=2,
        score_kind=score_kind,
        qualification_score=qualification_score,
        preference_score=preference_score,
        eligibility_status=eligibility_status,
        confidence_level=confidence_level,
        matched_skills=[],
        partial_matches=[],
        missing_skills=[],
    )
    db.add(record)
    db.commit()
    return record


def test_jobs_query_paginates_and_keeps_compat_list(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        _job(db, public_id="j1", title="Software Engineer Intern", location="San Francisco, CA")
        _job(db, public_id="j2", title="Staff Platform Engineer", location="Austin, TX", description="Full-time onsite.")
        _job(db, public_id="j3", title="Data Analyst Intern", location="Oakland, CA")

    compat = client.get("/api/jobs")
    assert compat.status_code == 200
    assert len(compat.json()) == 3

    page1 = client.get("/api/jobs/query", params={"page": 1, "page_size": 2})
    assert page1.status_code == 200
    body = page1.json()
    assert body["total"] == 3
    assert body["page_size"] == 2
    assert len(body["items"]) == 2
    assert len(body["ids"]) == 3

    page2 = client.get("/api/jobs/query", params={"page": 2, "page_size": 2})
    assert page2.status_code == 200
    assert len(page2.json()["items"]) == 1

    oversized = client.get("/api/jobs/query", params={"page_size": 500})
    assert oversized.json()["page_size"] == 50


def test_jobs_query_filters_opportunity_work_mode_and_location(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        _job(
            db,
            public_id="intern-sf",
            title="Software Engineer Intern",
            location="San Francisco, CA",
            description="Summer internship. Hybrid. Fintech payments.",
        )
        _job(
            db,
            public_id="role-austin",
            title="Staff Software Engineer",
            location="Austin, TX",
            description="Full-time. Remote. Backend platform.",
        )
        _job(
            db,
            public_id="unknown-ny",
            title="Engineer",
            location="New York, NY",
            description="Build products.",
        )

    internships = client.get("/api/jobs/query", params={"opportunity": "internship"})
    ids = [item["job"]["id"] for item in internships.json()["items"]]
    assert ids == ["intern-sf"]
    assert internships.json()["items"][0]["job"]["opportunity_type"] == "internship"

    roles = client.get("/api/jobs/query", params={"opportunity": "role"})
    assert [item["job"]["id"] for item in roles.json()["items"]] == ["role-austin"]

    both = client.get("/api/jobs/query", params={"opportunity": "both"})
    assert {item["job"]["id"] for item in both.json()["items"]} == {"intern-sf", "role-austin", "unknown-ny"}

    bay = client.get(
        "/api/jobs/query",
        params=[("q", "software"), ("work_mode", "hybrid"), ("work_mode", "onsite"), ("location", "San Francisco Bay Area")],
    )
    assert [item["job"]["id"] for item in bay.json()["items"]] == ["intern-sf"]

    remote_only = client.get("/api/jobs/query", params={"work_mode": "remote"})
    assert [item["job"]["id"] for item in remote_only.json()["items"]] == ["role-austin"]


def test_jobs_query_sorts_verified_ahead_of_raw_ranking(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        intern = _job(db, public_id="verified-job", title="Software Engineer Intern")
        other = _job(db, public_id="potential-job", title="Software Engineer Intern 2")
        candidate = insert_candidate(db, user_id=client.test_user_id)
        _score(db, intern, candidate, ranking_score=40, score_kind="verified", overall_score=86)
        _score(db, other, candidate, ranking_score=90, score_kind="preliminary", overall_score=90)

    ranked = client.get("/api/jobs/query", params={"sort": "best_match", "tab": "matches"})
    ids = [item["job"]["id"] for item in ranked.json()["items"]]
    assert ids[0] == "verified-job"
    assert ranked.json()["verified_count"] == 1
    assert ranked.json()["potential_count"] == 1


def test_jobs_query_filters_eligibility_and_verified_state(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        eligible = _job(db, public_id="eligible", title="Software Engineer Intern")
        blocked = _job(db, public_id="blocked", title="Software Engineer Intern")
        candidate = insert_candidate(db, user_id=client.test_user_id)
        _score(
            db,
            eligible,
            candidate,
            ranking_score=70,
            score_kind="verified",
            eligibility_status="likely_eligible",
            confidence_level="high",
        )
        _score(
            db,
            blocked,
            candidate,
            ranking_score=20,
            score_kind="verified",
            eligibility_status="likely_ineligible",
            confidence_level="low",
        )

    eligible_only = client.get(
        "/api/jobs/query",
        params={"verified_state": "verified", "eligibility": "likely_eligible"},
    )
    assert [item["job"]["id"] for item in eligible_only.json()["items"]] == ["eligible"]

    potential = client.get("/api/jobs/query", params={"verified_state": "potential"})
    assert potential.json()["items"] == []

    ignored = client.get("/api/jobs/query", params={"work_mode": "SELECT * FROM jobs", "verified_state": "nope"})
    assert ignored.status_code == 200
    assert ignored.json()["total"] == 2


def test_search_intent_route_returns_allowlisted_filters(isolated_client) -> None:
    client, _ = isolated_client
    response = client.post(
        "/api/jobs/search-intent",
        json={
            "query": "Software engineering internships in the Bay Area at fintech companies, hybrid or onsite"
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["roles"] == ["Software Engineering"]
    assert body["locations"] == ["San Francisco Bay Area"]
    assert body["work_modes"] == ["hybrid", "onsite"]
    assert body["industries"] == ["fintech"]
    assert body["parser_ready"] is True


def test_saved_jobs_are_user_scoped_unique_and_idempotent(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        job = _job(db, public_id="save-me", title="Software Engineer Intern")
        job_id = job.public_id

    first = client.post(f"/api/jobs/{job_id}/save")
    second = client.post(f"/api/jobs/{job_id}/save")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["saved"] is True
    listed = client.get("/api/jobs/saved")
    assert [job["id"] for job in listed.json()] == [job_id]
    with SessionLocal() as db:
        assert db.query(SavedJobRecord).count() == 1

    other = client.post("/api/auth/signup", json={"email": "other-save@example.com", "password": "a-real-password"})
    assert other.status_code == 201
    assert client.get("/api/jobs/saved").json() == []
    saved_tab = client.get("/api/jobs/query", params={"tab": "saved"})
    assert saved_tab.json()["items"] == []
    assert client.post(f"/api/jobs/{job_id}/save").status_code == 200
    with SessionLocal() as db:
        assert db.query(SavedJobRecord).count() == 2

    client.cookies.clear()
    login = client.post(
        "/api/auth/login",
        json={"email": "test-user@example.com", "password": "test-password-123"},
    )
    assert login.status_code == 200
    assert client.delete(f"/api/jobs/{job_id}/save").status_code == 204
    assert client.delete(f"/api/jobs/{job_id}/save").status_code == 204
    assert client.get("/api/jobs/saved").json() == []
    other_login = client.post(
        "/api/auth/login",
        json={"email": "other-save@example.com", "password": "a-real-password"},
    )
    assert other_login.status_code == 200
    assert [job["id"] for job in client.get("/api/jobs/saved").json()] == [job_id]


def test_query_does_not_drop_unrelated_stored_jobs_after_filtered_search(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        _job(db, public_id="manual-old", title="Product Manager", location="Boston, MA", description="Full-time onsite.")
        _job(
            db,
            public_id="intern-sf",
            title="Software Engineer Intern",
            location="San Francisco, CA",
            description="Internship hybrid fintech.",
        )

    filtered = client.get("/api/jobs/query", params={"opportunity": "internship"})
    assert [item["job"]["id"] for item in filtered.json()["items"]] == ["intern-sf"]
    catalog = client.get("/api/jobs")
    assert {job["id"] for job in catalog.json()} == {"manual-old", "intern-sf"}


def test_opportunity_type_is_canonical_not_title_guesswork() -> None:
    assert infer_opportunity_type("Software Engineer Intern", "Summer internship.") == "internship"
    assert infer_opportunity_type("Staff Platform Engineer", "Full-time. Remote.") == "role"
    assert infer_opportunity_type("Engineer", "Build products.") == "unknown"
    assert infer_employment_type("New Grad SWE", "New grad program.") == "new_grad"
    assert infer_opportunity_type("New Grad SWE", "New grad program.") == "role"
    assert infer_opportunity_type("Software Engineering Intern", "Summer internship.") == "internship"
    assert infer_opportunity_type("Software Engineering Co-op", "Fall co-op rotation.") == "internship"
    assert infer_work_mode("Engineer", "Hybrid in San Francisco.") == "hybrid"
    assert infer_work_mode("Engineer", "Remote US only.") == "remote"


def test_jobs_query_filters_confidence_and_date_posted(isolated_client) -> None:
    from datetime import datetime, timedelta, timezone

    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        recent = _job(db, public_id="recent", title="Software Engineer Intern")
        old = _job(db, public_id="old", title="Software Engineer Intern")
        recent.date_scraped = datetime.now(timezone.utc)
        old.date_scraped = datetime.now(timezone.utc) - timedelta(days=20)
        candidate = insert_candidate(db, user_id=client.test_user_id)
        _score(db, recent, candidate, ranking_score=70, score_kind="verified", confidence_level="high")
        _score(db, old, candidate, ranking_score=70, score_kind="verified", confidence_level="low")
        db.commit()

    high = client.get("/api/jobs/query", params={"confidence": "high"})
    assert [item["job"]["id"] for item in high.json()["items"]] == ["recent"]

    week = client.get("/api/jobs/query", params={"date_posted": "past_7d"})
    assert week.json()["items"] == []


def test_jobs_query_sorts_qualification_with_verified_authority(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        verified = _job(db, public_id="verified-q", title="Software Engineer Intern")
        potential = _job(db, public_id="potential-q", title="Software Engineer Intern 2")
        candidate = insert_candidate(db, user_id=client.test_user_id)
        _score(
            db,
            verified,
            candidate,
            ranking_score=40,
            score_kind="verified",
            qualification_score=70,
        )
        _score(
            db,
            potential,
            candidate,
            ranking_score=90,
            score_kind="preliminary",
            qualification_score=95,
        )

    ranked = client.get("/api/jobs/query", params={"sort": "qualification", "tab": "matches"})
    ids = [item["job"]["id"] for item in ranked.json()["items"]]
    assert ids[0] == "verified-q"
