"""Saved Searches: filter predicate, CRUD, and the scheduler tick logic."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest

from backend.core.rate_limit import guard_expensive
from backend.db.models import JobRecord, SavedSearchMatchRecord, SavedSearchRecord
from backend.schemas.saved_search import SavedSearchCreate, SavedSearchUpdate
from backend.schemas.schemas import Job
from backend.services.saved_search_service import (
    MAX_SEARCHES_PER_TICK,
    MIN_CADENCE_HOURS,
    SavedSearchNotFoundError,
    create_saved_search,
    delete_saved_search,
    job_matches_search_filters,
    list_matches,
    list_saved_searches,
    mark_matches_seen,
    run_due_saved_searches,
    update_saved_search,
)
from tests.mvp_helpers import TEST_USER_ID, ensure_user, insert_job, insert_ready_profile


def _job(**overrides) -> Job:
    defaults = dict(
        id="job-1",
        title="Software Engineer Intern",
        company="Acme",
        url="https://example.com/jobs/job-1",
        description="Build things.",
        source="manual",
        opportunity_type="internship",
        employment_type="internship",
        work_mode="remote",
        date_posted=None,
    )
    defaults.update(overrides)
    return Job(**defaults)


class TestJobMatchesSearchFilters:
    def test_no_filters_always_matches(self) -> None:
        job = _job()
        assert job_matches_search_filters(
            job, opportunity=None, employment_type=[], work_mode=[], date_posted=None, today=date(2026, 1, 1)
        )

    def test_opportunity_filter(self) -> None:
        job = _job(opportunity_type="role")
        assert not job_matches_search_filters(
            job, opportunity="internship", employment_type=[], work_mode=[], date_posted=None, today=date(2026, 1, 1)
        )
        assert job_matches_search_filters(
            job, opportunity="role", employment_type=[], work_mode=[], date_posted=None, today=date(2026, 1, 1)
        )

    def test_employment_type_filter(self) -> None:
        job = _job(employment_type="full_time")
        assert not job_matches_search_filters(
            job, opportunity=None, employment_type=["part_time"], work_mode=[], date_posted=None, today=date(2026, 1, 1)
        )
        assert job_matches_search_filters(
            job, opportunity=None, employment_type=["full_time"], work_mode=[], date_posted=None, today=date(2026, 1, 1)
        )

    def test_work_mode_filter(self) -> None:
        job = _job(work_mode="onsite")
        assert not job_matches_search_filters(
            job, opportunity=None, employment_type=[], work_mode=["remote"], date_posted=None, today=date(2026, 1, 1)
        )
        assert job_matches_search_filters(
            job, opportunity=None, employment_type=[], work_mode=["onsite", "hybrid"], date_posted=None, today=date(2026, 1, 1)
        )

    def test_date_posted_window(self) -> None:
        today = date(2026, 9, 20)
        recent = _job(date_posted=date(2026, 9, 15))
        old = _job(date_posted=date(2026, 8, 1))
        assert job_matches_search_filters(
            recent, opportunity=None, employment_type=[], work_mode=[], date_posted="past_7d", today=today
        )
        assert not job_matches_search_filters(
            old, opportunity=None, employment_type=[], work_mode=[], date_posted="past_7d", today=today
        )

    def test_date_posted_window_excludes_unknown_posting_date(self) -> None:
        job = _job(date_posted=None)
        assert not job_matches_search_filters(
            job, opportunity=None, employment_type=[], work_mode=[], date_posted="past_7d", today=date(2026, 1, 1)
        )


class TestSavedSearchCrud:
    def test_create_enforces_minimum_cadence(self, isolated_session) -> None:
        ensure_user(isolated_session, TEST_USER_ID)
        record = create_saved_search(
            isolated_session,
            TEST_USER_ID,
            SavedSearchCreate(label="Interns", query_text="software engineer intern", cadence_hours=1),
        )
        assert record.cadence_hours == MIN_CADENCE_HOURS

    def test_list_includes_unseen_match_count(self, isolated_session) -> None:
        ensure_user(isolated_session, TEST_USER_ID)
        search = create_saved_search(
            isolated_session, TEST_USER_ID, SavedSearchCreate(label="Interns", query_text="intern")
        )
        job = insert_job(isolated_session, public_id="job-a")
        isolated_session.add(SavedSearchMatchRecord(saved_search_id=search.id, job_id=job.id))
        isolated_session.commit()

        results = list_saved_searches(isolated_session, TEST_USER_ID)
        assert len(results) == 1
        _record, unseen = results[0]
        assert unseen == 1

    def test_update_and_delete(self, isolated_session) -> None:
        ensure_user(isolated_session, TEST_USER_ID)
        search = create_saved_search(
            isolated_session, TEST_USER_ID, SavedSearchCreate(label="Interns", query_text="intern")
        )
        updated = update_saved_search(
            isolated_session, search.id, TEST_USER_ID, SavedSearchUpdate(enabled=False)
        )
        assert updated.enabled is False

        delete_saved_search(isolated_session, search.id, TEST_USER_ID)
        with pytest.raises(SavedSearchNotFoundError):
            update_saved_search(isolated_session, search.id, TEST_USER_ID, SavedSearchUpdate(enabled=True))

    def test_cannot_read_another_users_saved_search(self, isolated_session) -> None:
        ensure_user(isolated_session, TEST_USER_ID)
        other_user_id = TEST_USER_ID + 1
        ensure_user(isolated_session, other_user_id)
        search = create_saved_search(
            isolated_session, other_user_id, SavedSearchCreate(label="Interns", query_text="intern")
        )
        with pytest.raises(SavedSearchNotFoundError):
            list_matches(isolated_session, search.id, TEST_USER_ID)

    def test_mark_matches_seen(self, isolated_session) -> None:
        ensure_user(isolated_session, TEST_USER_ID)
        search = create_saved_search(
            isolated_session, TEST_USER_ID, SavedSearchCreate(label="Interns", query_text="intern")
        )
        job = insert_job(isolated_session, public_id="job-a")
        isolated_session.add(SavedSearchMatchRecord(saved_search_id=search.id, job_id=job.id))
        isolated_session.commit()

        updated = mark_matches_seen(isolated_session, search.id, TEST_USER_ID)
        assert updated == 1
        _record, unseen = list_saved_searches(isolated_session, TEST_USER_ID)[0]
        assert unseen == 0


class TestSchedulerTick:
    def test_creates_matches_for_newly_scouted_jobs(self, isolated_session, monkeypatch) -> None:
        ensure_user(isolated_session, TEST_USER_ID)
        search = create_saved_search(
            isolated_session, TEST_USER_ID, SavedSearchCreate(label="Interns", query_text="intern")
        )
        insert_job(isolated_session, public_id="job-a")

        def fake_scout_jobs(queries, location):
            assert queries == ["intern"]
            return [_job(id="job-a")]

        monkeypatch.setattr("backend.services.saved_search_service.scout_jobs", fake_scout_jobs)
        monkeypatch.setattr(
            "backend.services.saved_search_service.SessionLocal", lambda: isolated_session
        )
        # SessionLocal() normally opens a fresh connection; isolated_session
        # is already one, and its own fixture handles closing it — avoid
        # closing it early via the `with SessionLocal() as db:` context exit.
        monkeypatch.setattr(isolated_session, "close", lambda: None)

        asyncio.run(run_due_saved_searches())

        matches = list_matches(isolated_session, search.id, TEST_USER_ID)
        assert len(matches) == 1
        assert matches[0][1].public_id == "job-a"
        refreshed = isolated_session.get(SavedSearchRecord, search.id)
        assert refreshed.last_run_at is not None

    def test_does_not_duplicate_matches_on_a_second_run(self, isolated_session, monkeypatch) -> None:
        ensure_user(isolated_session, TEST_USER_ID)
        search = create_saved_search(
            isolated_session,
            TEST_USER_ID,
            SavedSearchCreate(label="Interns", query_text="intern", cadence_hours=MIN_CADENCE_HOURS),
        )
        insert_job(isolated_session, public_id="job-a")

        monkeypatch.setattr(
            "backend.services.saved_search_service.scout_jobs", lambda queries, location: [_job(id="job-a")]
        )
        monkeypatch.setattr("backend.services.saved_search_service.SessionLocal", lambda: isolated_session)
        monkeypatch.setattr(isolated_session, "close", lambda: None)

        asyncio.run(run_due_saved_searches())
        # Force the search overdue again for a second tick.
        search.last_run_at = datetime.now(timezone.utc) - timedelta(hours=MIN_CADENCE_HOURS + 1)
        isolated_session.commit()
        asyncio.run(run_due_saved_searches())

        matches = list_matches(isolated_session, search.id, TEST_USER_ID)
        assert len(matches) == 1

    def test_skips_a_search_not_yet_due(self, isolated_session, monkeypatch) -> None:
        ensure_user(isolated_session, TEST_USER_ID)
        search = create_saved_search(
            isolated_session, TEST_USER_ID, SavedSearchCreate(label="Interns", query_text="intern", cadence_hours=12)
        )
        search.last_run_at = datetime.now(timezone.utc)
        isolated_session.commit()

        scout_called = {"n": 0}

        def fake_scout_jobs(queries, location):
            scout_called["n"] += 1
            return []

        monkeypatch.setattr("backend.services.saved_search_service.scout_jobs", fake_scout_jobs)
        monkeypatch.setattr("backend.services.saved_search_service.SessionLocal", lambda: isolated_session)
        monkeypatch.setattr(isolated_session, "close", lambda: None)

        asyncio.run(run_due_saved_searches())
        assert scout_called["n"] == 0

    def test_a_disabled_search_is_never_run(self, isolated_session, monkeypatch) -> None:
        ensure_user(isolated_session, TEST_USER_ID)
        create_saved_search(
            isolated_session, TEST_USER_ID, SavedSearchCreate(label="Interns", query_text="intern")
        )
        search = isolated_session.query(SavedSearchRecord).one()
        search.enabled = False
        isolated_session.commit()

        scout_called = {"n": 0}
        monkeypatch.setattr(
            "backend.services.saved_search_service.scout_jobs",
            lambda queries, location: (scout_called.__setitem__("n", scout_called["n"] + 1) or []),
        )
        monkeypatch.setattr("backend.services.saved_search_service.SessionLocal", lambda: isolated_session)
        monkeypatch.setattr(isolated_session, "close", lambda: None)

        asyncio.run(run_due_saved_searches())
        assert scout_called["n"] == 0

    def test_one_failing_search_does_not_block_the_others(self, isolated_session, monkeypatch) -> None:
        ensure_user(isolated_session, TEST_USER_ID)
        failing = create_saved_search(
            isolated_session, TEST_USER_ID, SavedSearchCreate(label="Fails", query_text="fails")
        )
        working = create_saved_search(
            isolated_session, TEST_USER_ID, SavedSearchCreate(label="Works", query_text="works")
        )
        insert_job(isolated_session, public_id="job-a")

        def fake_scout_jobs(queries, location):
            if queries == ["fails"]:
                raise RuntimeError("source outage")
            return [_job(id="job-a")]

        monkeypatch.setattr("backend.services.saved_search_service.scout_jobs", fake_scout_jobs)
        monkeypatch.setattr("backend.services.saved_search_service.SessionLocal", lambda: isolated_session)
        monkeypatch.setattr(isolated_session, "close", lambda: None)

        asyncio.run(run_due_saved_searches())

        assert isolated_session.get(SavedSearchRecord, failing.id).last_run_at is None
        assert isolated_session.get(SavedSearchRecord, working.id).last_run_at is not None
        assert len(list_matches(isolated_session, working.id, TEST_USER_ID)) == 1

    def test_caps_searches_processed_per_tick(self, isolated_session, monkeypatch) -> None:
        ensure_user(isolated_session, TEST_USER_ID)
        for i in range(MAX_SEARCHES_PER_TICK + 2):
            create_saved_search(
                isolated_session, TEST_USER_ID, SavedSearchCreate(label=f"Search {i}", query_text=f"q{i}")
            )

        run_count = {"n": 0}

        def fake_scout_jobs(queries, location):
            run_count["n"] += 1
            return []

        monkeypatch.setattr("backend.services.saved_search_service.scout_jobs", fake_scout_jobs)
        monkeypatch.setattr("backend.services.saved_search_service.SessionLocal", lambda: isolated_session)
        monkeypatch.setattr(isolated_session, "close", lambda: None)

        asyncio.run(run_due_saved_searches())
        assert run_count["n"] == MAX_SEARCHES_PER_TICK

    def test_rate_limited_search_is_retried_next_tick_not_marked_run(self, isolated_session, monkeypatch) -> None:
        ensure_user(isolated_session, TEST_USER_ID)
        search = create_saved_search(
            isolated_session, TEST_USER_ID, SavedSearchCreate(label="Interns", query_text="intern")
        )
        # Exhaust the scheduled_scout bucket for this user ahead of time.
        for _ in range(6):
            with guard_expensive(TEST_USER_ID, "scheduled_scout"):
                pass

        scout_called = {"n": 0}
        monkeypatch.setattr(
            "backend.services.saved_search_service.scout_jobs",
            lambda queries, location: (scout_called.__setitem__("n", scout_called["n"] + 1) or []),
        )
        monkeypatch.setattr("backend.services.saved_search_service.SessionLocal", lambda: isolated_session)
        monkeypatch.setattr(isolated_session, "close", lambda: None)

        asyncio.run(run_due_saved_searches())

        assert scout_called["n"] == 0
        assert isolated_session.get(SavedSearchRecord, search.id).last_run_at is None


class TestSavedSearchRoutes:
    def test_create_requires_a_ready_profile(self, isolated_client) -> None:
        client, SessionLocal = isolated_client
        response = client.post(
            "/api/saved-searches", json={"label": "Interns", "query_text": "software engineer intern"}
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "profile_required"

    def test_create_and_list(self, isolated_client) -> None:
        client, SessionLocal = isolated_client
        with SessionLocal() as db:
            insert_ready_profile(db, user_id=client.test_user_id)

        created = client.post(
            "/api/saved-searches",
            json={"label": "Interns", "query_text": "software engineer intern", "cadence_hours": 6},
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["label"] == "Interns"
        assert body["cadence_hours"] == 6
        assert body["unseen_match_count"] == 0

        listed = client.get("/api/saved-searches")
        assert listed.status_code == 200
        assert len(listed.json()) == 1

    def test_update_and_delete(self, isolated_client) -> None:
        client, SessionLocal = isolated_client
        with SessionLocal() as db:
            insert_ready_profile(db, user_id=client.test_user_id)
        search_id = client.post(
            "/api/saved-searches", json={"label": "Interns", "query_text": "intern"}
        ).json()["id"]

        updated = client.patch(f"/api/saved-searches/{search_id}", json={"enabled": False})
        assert updated.status_code == 200
        assert updated.json()["enabled"] is False

        deleted = client.delete(f"/api/saved-searches/{search_id}")
        assert deleted.status_code == 204
        assert client.get("/api/saved-searches").json() == []

    def test_update_unknown_search_is_a_404(self, isolated_client) -> None:
        client, SessionLocal = isolated_client
        response = client.patch("/api/saved-searches/999999", json={"enabled": False})
        assert response.status_code == 404

    def test_matches_route_and_mark_seen(self, isolated_client) -> None:
        client, SessionLocal = isolated_client
        with SessionLocal() as db:
            insert_ready_profile(db, user_id=client.test_user_id)
            job = insert_job(db, public_id="job-a", title="Backend Intern")
        search_id = client.post(
            "/api/saved-searches", json={"label": "Interns", "query_text": "intern"}
        ).json()["id"]
        with SessionLocal() as db:
            db.add(SavedSearchMatchRecord(saved_search_id=search_id, job_id=job.id))
            db.commit()

        matches = client.get(f"/api/saved-searches/{search_id}/matches")
        assert matches.status_code == 200
        assert len(matches.json()) == 1
        assert matches.json()[0]["job_id"] == "job-a"
        assert matches.json()[0]["seen_at"] is None

        listed = client.get("/api/saved-searches").json()
        assert listed[0]["unseen_match_count"] == 1

        seen = client.post(f"/api/saved-searches/{search_id}/matches/seen")
        assert seen.status_code == 200
        assert seen.json()["updated"] == 1

        listed_after = client.get("/api/saved-searches").json()
        assert listed_after[0]["unseen_match_count"] == 0

    def test_matches_route_404s_for_another_users_search(self, isolated_client) -> None:
        client, SessionLocal = isolated_client
        with SessionLocal() as db:
            other_user_id = client.test_user_id + 1
            ensure_user(db, other_user_id)
            search = create_saved_search(
                db, other_user_id, SavedSearchCreate(label="Interns", query_text="intern")
            )
            search_id = search.id

        response = client.get(f"/api/saved-searches/{search_id}/matches")
        assert response.status_code == 404

    def test_routes_require_authentication(self, isolated_client) -> None:
        client, SessionLocal = isolated_client
        client.cookies.clear()
        assert client.get("/api/saved-searches").status_code == 401
        assert client.post("/api/saved-searches", json={"label": "x", "query_text": "x"}).status_code == 401
