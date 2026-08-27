"""POST /api/scout-jobs automatically persists deterministic fit scores."""

from __future__ import annotations

import logging
from unittest.mock import Mock

from backend.db.models import MatchScoreRecord
from backend.schemas.schemas import Job
from backend.services.analysis_service import RequirementsUnavailableError
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

    def _fake_score(db, job_id, user_id):
        scored.append(job_id)
        return Mock()

    monkeypatch.setattr("backend.api.routes.jobs.score_job", _fake_score)
    intelligence = Mock()
    monkeypatch.setattr(
        "backend.services.scoring_orchestrator.score_job_with_intelligence", intelligence
    )

    response = client.post("/api/scout-jobs")
    assert response.status_code == 202
    assert scored == ["jobicy-one", "himalayas-two"]
    assert "Auto-scored 2" in response.json()["note"]
    intelligence.assert_not_called()


def test_one_scoring_failure_does_not_fail_scout(isolated_client, monkeypatch) -> None:
    client, _ = isolated_client
    jobs = [_job("good-job"), _job("bad-job")]
    monkeypatch.setattr("backend.api.routes.jobs.scout_jobs", lambda **_: jobs)
    scored: list[str] = []

    def _fake_score(db, job_id, user_id):
        if job_id == "bad-job":
            raise RequirementsUnavailableError()
        scored.append(job_id)
        return Mock()

    monkeypatch.setattr("backend.api.routes.jobs.score_job", _fake_score)

    response = client.post("/api/scout-jobs")
    assert response.status_code == 202
    assert scored == ["good-job"]
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
    monkeypatch.setattr(
        "backend.api.routes.jobs.score_job",
        lambda *a, **k: (_ for _ in ()).throw(RequirementsUnavailableError()),
    )

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
