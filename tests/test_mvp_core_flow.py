"""Read-only page-load APIs, grounded generation, and recommendation filters."""

from __future__ import annotations

import json

from backend.db.models import ApplicationPackageRecord, MatchScoreRecord
from tests.mvp_helpers import (
    VALID_MATERIALS_JSON,
    fake_grounded_generator,
    insert_grounded_package,
    insert_job,
    insert_score,
    seed_materials_prerequisites,
)


def test_stored_score_get_is_read_only(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        job, _candidate = seed_materials_prerequisites(db)
        public_id = job.public_id
        before = db.query(MatchScoreRecord).count()
    missing = client.get("/api/jobs/missing-job/score")
    assert missing.status_code == 404
    found = client.get(f"/api/jobs/{public_id}/score")
    assert found.status_code == 200
    with SessionLocal() as db:
        job2 = insert_job(db, public_id="unscored-job")
    unscored = client.get("/api/jobs/unscored-job/score")
    assert unscored.status_code == 404
    with SessionLocal() as db:
        assert db.query(MatchScoreRecord).count() == before
        assert db.query(MatchScoreRecord).filter(MatchScoreRecord.job_id == job2.id).count() == 0


def test_stored_score_get_does_not_create_provisional_rows(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        insert_job(db, public_id="no-score")
    response = client.get("/api/jobs/no-score/score")
    assert response.status_code == 404
    with SessionLocal() as db:
        assert db.query(MatchScoreRecord).count() == 0


def test_bulk_stored_scores_are_read_only(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        seed_materials_prerequisites(db, public_id="scored-job")
        insert_job(db, public_id="unscored-job")
    response = client.get("/api/jobs/scores")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["job_id"] == "scored-job"
    assert body[0]["recommendation"] == "apply"


def test_stored_materials_get_is_read_only_and_hides_placeholders(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        job, candidate = seed_materials_prerequisites(db)
        insert_grounded_package(db, job, candidate=candidate)
    found = client.get("/api/jobs/manual-abc123/materials")
    assert found.status_code == 200
    assert found.json()["grounded"] is True
    with SessionLocal() as db:
        placeholder_job = insert_job(db, public_id="placeholder-job")
        db.add(
            ApplicationPackageRecord(
                job_id=placeholder_job.id,
                tailored_bullets=["Placeholder bullet"],
                cover_letter_draft="Placeholder draft",
                recruiter_message="hi",
                source_traceability_notes=["placeholder bullet"],
                approval_status="pending_review",
                grounded=False,
            )
        )
        db.commit()
    hidden = client.get("/api/jobs/placeholder-job/materials")
    assert hidden.status_code == 404
    absent = client.get("/api/jobs/no-such-job/materials")
    assert absent.status_code == 404


def test_generate_materials_requires_explicit_post_and_reuses_grounded_package(isolated_client) -> None:
    client, SessionLocal = isolated_client
    client.app.state.application_materials_generator = fake_grounded_generator
    with SessionLocal() as db:
        seed_materials_prerequisites(db)
    first = client.post("/api/jobs/manual-abc123/generate-materials")
    assert first.status_code == 200
    body = first.json()
    assert "placeholder" not in " ".join(body["source_traceability_notes"]).lower()
    with SessionLocal() as db:
        assert db.query(ApplicationPackageRecord).count() == 1
    calls = {"n": 0}

    def counting(prompt: str, system_prompt: str | None = None) -> str:
        calls["n"] += 1
        return VALID_MATERIALS_JSON

    client.app.state.application_materials_generator = counting
    second = client.post("/api/jobs/manual-abc123/generate-materials")
    assert second.status_code == 200
    assert calls["n"] == 0
    refresh = client.get("/api/jobs/manual-abc123/materials")
    assert refresh.status_code == 200
    assert refresh.json()["tailored_bullets"] == first.json()["tailored_bullets"]


def test_generate_materials_missing_prerequisites_are_conflicts(isolated_client) -> None:
    client, SessionLocal = isolated_client
    client.app.state.application_materials_generator = fake_grounded_generator
    with SessionLocal() as db:
        insert_job(db)
    response = client.post("/api/jobs/manual-abc123/generate-materials")
    assert response.status_code == 409
    with SessionLocal() as db:
        assert db.query(ApplicationPackageRecord).count() == 0


def test_invalid_json_persists_nothing(isolated_client) -> None:
    client, SessionLocal = isolated_client
    client.app.state.application_materials_generator = lambda *_a, **_k: "not-json"
    with SessionLocal() as db:
        seed_materials_prerequisites(db)
    response = client.post("/api/jobs/manual-abc123/generate-materials")
    assert response.status_code == 502
    with SessionLocal() as db:
        assert db.query(ApplicationPackageRecord).count() == 0


def test_ungrounded_output_persists_nothing(isolated_client) -> None:
    client, SessionLocal = isolated_client
    client.app.state.application_materials_generator = lambda *_a, **_k: json.dumps(
        {
            "tailored_bullets": ["Led production Kubernetes clusters at Globex."],
            "cover_letter_draft": "I have deep Kubernetes experience.",
            "recruiter_message": "I used Kubernetes in production.",
            "source_traceability_notes": ["invented"],
        }
    )
    with SessionLocal() as db:
        seed_materials_prerequisites(db)
    response = client.post("/api/jobs/manual-abc123/generate-materials")
    assert response.status_code == 409
    with SessionLocal() as db:
        assert db.query(ApplicationPackageRecord).count() == 0


def test_approved_package_is_not_silently_replaced(isolated_client) -> None:
    client, SessionLocal = isolated_client
    client.app.state.application_materials_generator = fake_grounded_generator
    with SessionLocal() as db:
        job, candidate = seed_materials_prerequisites(db)
        package = insert_grounded_package(db, job, candidate=candidate)
        package.approval_status = "approved"
        db.commit()
    response = client.post("/api/jobs/manual-abc123/generate-materials")
    assert response.status_code == 200
    assert response.json()["approval_status"] == "approved"
    with SessionLocal() as db:
        assert db.query(ApplicationPackageRecord).one().approval_status == "approved"


def test_recommendation_filters_separate_stored_scores(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        _job, candidate = seed_materials_prerequisites(db, public_id="apply-job")
        job_consider = insert_job(db, public_id="consider-job")
        insert_score(db, job_consider, candidate, recommendation="consider", overall_score=70.0)
        job_skip = insert_job(db, public_id="skip-job")
        insert_score(db, job_skip, candidate, recommendation="skip", overall_score=40.0)
        insert_job(db, public_id="unscored-job")
    scores = {item["job_id"]: item["recommendation"] for item in client.get("/api/jobs/scores").json()}
    assert scores["apply-job"] == "apply"
    assert scores["consider-job"] == "consider"
    assert scores["skip-job"] == "skip"
    assert "unscored-job" not in scores
    with SessionLocal() as db:
        from backend.db.models import JobRecord

        public_ids = {row.public_id for row in db.query(JobRecord).all()}
    assert "unscored-job" in public_ids


def test_explicit_score_post_persists_one_row(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        job, _candidate = seed_materials_prerequisites(db, public_id="score-now", with_score=False)
        public_id = job.public_id
        before = db.query(MatchScoreRecord).count()
    response = client.post(f"/api/jobs/{public_id}/score")
    assert response.status_code == 200
    with SessionLocal() as db:
        assert db.query(MatchScoreRecord).count() == before + 1
    stored = client.get(f"/api/jobs/{public_id}/score")
    assert stored.status_code == 200
    assert stored.json()["job_id"] == public_id


def test_jobs_and_application_gets_do_not_score_or_generate(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        job, _candidate = seed_materials_prerequisites(db, public_id="load-job", with_score=False)
        public_id = job.public_id
        scores_before = db.query(MatchScoreRecord).count()
        packages_before = db.query(ApplicationPackageRecord).count()
    assert client.get("/api/jobs/scores").status_code == 200
    assert client.get(f"/api/jobs/{public_id}/score").status_code == 404
    assert client.get(f"/api/jobs/{public_id}/materials").status_code == 404
    with SessionLocal() as db:
        assert db.query(MatchScoreRecord).count() == scores_before
        assert db.query(ApplicationPackageRecord).count() == packages_before
