"""POST /api/scout-jobs automatically persists deterministic fit scores."""

from __future__ import annotations

import logging
from unittest.mock import Mock

from backend.db.models import MatchScoreRecord
from backend.schemas.schemas import Job
from backend.services.job_service import record_to_job
from tests.mvp_helpers import insert_candidate, insert_job


def _job(job_id: str, *, description: str = "Required: Python") -> Job:
    return Job(
        id=job_id,
        title="Engineer",
        company="Acme",
        url=f"https://example.com/jobs/{job_id}",
        description=description,
        source="jobicy",
        status="discovered",
    )


def test_scout_route_auto_scores_each_returned_job(isolated_client, monkeypatch) -> None:
    client, _ = isolated_client
    jobs = [_job("jobicy-one"), _job("himalayas-two")]
    monkeypatch.setattr("backend.api.routes.jobs.scout_jobs", lambda **_: jobs)
    scored: list[str] = []
    seen_users: set[int] = set()

    def _fake_batch(db, job_ids, user_id, as_of=None):
        scored.extend(job_ids)
        seen_users.add(user_id)
        return len(job_ids), 0

    monkeypatch.setattr("backend.api.routes.jobs.score_jobs_batch", _fake_batch)
    intelligence = Mock()
    monkeypatch.setattr(
        "backend.services.scoring_orchestrator.score_job_with_intelligence", intelligence
    )

    response = client.post("/api/scout-jobs")
    assert response.status_code == 202
    body = response.json()
    assert scored == ["jobicy-one", "himalayas-two"]
    assert seen_users == {client.test_user_id}
    assert "Auto-scored 2" in body["note"]
    assert body["jobs_found"] == 2
    assert body["matched_count"] == 2
    intelligence.assert_not_called()


def test_one_scoring_failure_does_not_fail_scout(isolated_client, monkeypatch) -> None:
    client, _ = isolated_client
    jobs = [_job("good-job"), _job("bad-job")]
    monkeypatch.setattr("backend.api.routes.jobs.scout_jobs", lambda **_: jobs)

    def _fake_batch(db, job_ids, user_id, as_of=None):
        scored = sum(1 for job_id in job_ids if job_id != "bad-job")
        skipped = len(job_ids) - scored
        return scored, skipped

    monkeypatch.setattr("backend.api.routes.jobs.score_jobs_batch", _fake_batch)

    response = client.post("/api/scout-jobs")
    assert response.status_code == 202
    note = response.json()["note"]
    assert "Auto-scored 1" in note
    assert "Scouted and stored 2 job(s)" in note


def test_scout_auto_score_logs_ids_not_job_text(isolated_client, monkeypatch, caplog) -> None:
    client, _ = isolated_client
    secret = "SECRET_SSN_999-99-9999_DO_NOT_LOG"
    monkeypatch.setattr(
        "backend.api.routes.jobs.scout_jobs",
        lambda **_: [_job("job-secret", description=secret)],
    )

    def _fake_batch(db, job_ids, user_id, as_of=None):
        logging.getLogger("backend.services.analysis_service").info(
            "batch score skipped job_id=%s reason=%s",
            job_ids[0],
            "RequirementsUnavailableError",
        )
        return 0, len(job_ids)

    monkeypatch.setattr("backend.api.routes.jobs.score_jobs_batch", _fake_batch)

    with caplog.at_level(logging.INFO):
        response = client.post("/api/scout-jobs")

    assert response.status_code == 202
    assert "Auto-scored 0" in response.json()["note"]
    assert secret not in caplog.text
    assert "job-secret" in caplog.text
    assert "RequirementsUnavailableError" in caplog.text


def test_scout_auto_score_uses_deterministic_score_job_not_llm(
    isolated_client, monkeypatch
) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        insert_candidate(db, user_id=client.test_user_id)
        record = insert_job(db, public_id="jobicy-fit-1")
        stored = record_to_job(record)

    monkeypatch.setattr("backend.api.routes.jobs.scout_jobs", lambda **_: [stored])
    extract_intelligence = Mock()
    score_with_intelligence = Mock()
    llm_client = Mock()
    monkeypatch.setattr(
        "backend.services.job_intelligence_service.extract_job_intelligence",
        extract_intelligence,
    )
    monkeypatch.setattr(
        "backend.services.scoring_orchestrator.score_job_with_intelligence",
        score_with_intelligence,
    )
    monkeypatch.setattr(
        "backend.services.job_intelligence_service.get_llm_client",
        llm_client,
    )
    monkeypatch.setattr("backend.services.llm_client.get_llm_client", llm_client)

    response = client.post("/api/scout-jobs")
    assert response.status_code == 202
    assert "Auto-scored 1" in response.json()["note"]
    extract_intelligence.assert_not_called()
    score_with_intelligence.assert_not_called()
    llm_client.assert_not_called()

    with SessionLocal() as db:
        assert db.query(MatchScoreRecord).count() == 1


def test_score_jobs_batch_persists_multiple_and_skips_missing(isolated_client) -> None:
    client, SessionLocal = isolated_client
    from backend.services.analysis_service import score_jobs_batch

    with SessionLocal() as db:
        insert_candidate(db, user_id=client.test_user_id)
        first = insert_job(db, public_id="batch-one")
        second = insert_job(db, public_id="batch-two")
        scored, skipped = score_jobs_batch(
            db,
            [first.public_id, "missing-job", second.public_id],
            client.test_user_id,
        )
        assert scored == 2
        assert skipped == 1
        assert db.query(MatchScoreRecord).count() == 2
        rows = db.query(MatchScoreRecord).all()
        assert all(row.scoring_version == 2 for row in rows)
