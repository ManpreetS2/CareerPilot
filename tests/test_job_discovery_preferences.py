"""Discovery searches for the roles the user actually saved.

Before this, the scout query was a fixed string and the user's saved
target_roles were read by scoring, materials, and the tracker but never by
discovery — so "Find Jobs" searched "software engineer intern" no matter what
the user had asked for. Everything downstream (requirements extraction, fit
scoring, materials) is an LLM call costing minutes, so feeding it the wrong
jobs wastes all of it.

No live network: source calls are counted through monkeypatched scout
functions rather than by mocking HTTP, since what these tests pin is which
sources are called and how many times.
"""

from __future__ import annotations

import pytest

from backend.db.models import Candidate, TargetPreference
from backend.services import job_scout_service
from backend.services.job_scout_service import _title_matches_any_query, _title_matches_query
from backend.services.job_service import (
    DEFAULT_SCOUT_QUERY,
    MAX_SCOUT_QUERIES,
    MAX_SEARCH_TERM_CHARS,
    derive_scout_criteria,
)
from tests.mvp_helpers import TEST_USER_ID, ensure_user


def _preference(session, *, user_id=TEST_USER_ID, candidate_id=None, **overrides) -> TargetPreference:
    defaults = dict(
        user_id=user_id,
        candidate_id=candidate_id,
        target_roles=[],
        preferred_locations=[],
        remote_preference=None,
    )
    defaults.update(overrides)
    record = TargetPreference(**defaults)
    session.add(record)
    session.commit()
    return record


def _candidate(session, *, user_id=TEST_USER_ID) -> Candidate:
    record = Candidate(user_id=user_id, name="Jordan Quill", email="jordan@example.com")
    session.add(record)
    session.commit()
    return record


# ---------------------------------------------------------------------------
# Which roles get searched
# ---------------------------------------------------------------------------


def test_saved_target_roles_become_the_search_queries(isolated_session) -> None:
    ensure_user(isolated_session)
    _preference(isolated_session, target_roles=["Cloud Engineer", "DevOps Engineer"])

    criteria = derive_scout_criteria(isolated_session, TEST_USER_ID)
    assert criteria.queries == ["Cloud Engineer", "DevOps Engineer"]
    assert criteria.derived_from_preferences is True


def test_roles_are_deduped_case_insensitively_preserving_order(isolated_session) -> None:
    ensure_user(isolated_session)
    _preference(
        isolated_session,
        target_roles=["Backend Engineer", "  backend engineer  ", "SRE", "BACKEND ENGINEER"],
    )

    criteria = derive_scout_criteria(isolated_session, TEST_USER_ID)
    assert criteria.queries == ["Backend Engineer", "SRE"]


def test_query_count_is_capped(isolated_session) -> None:
    """Adzuna and Remotive are called once per role, so an unbounded list
    would turn one click into dozens of outbound requests."""
    ensure_user(isolated_session)
    _preference(isolated_session, target_roles=[f"Role {n}" for n in range(10)])

    criteria = derive_scout_criteria(isolated_session, TEST_USER_ID)
    assert len(criteria.queries) == MAX_SCOUT_QUERIES
    assert criteria.queries == ["Role 0", "Role 1", "Role 2"]


@pytest.mark.parametrize("roles", [[], ["", "   "], None, "not a list", [None, 42]])
def test_unusable_roles_fall_back_to_the_default_query(isolated_session, roles) -> None:
    ensure_user(isolated_session)
    _preference(isolated_session, target_roles=roles)

    criteria = derive_scout_criteria(isolated_session, TEST_USER_ID)
    assert criteria.queries == [DEFAULT_SCOUT_QUERY]
    assert criteria.derived_from_preferences is False


def test_no_preferences_at_all_falls_back(isolated_session) -> None:
    """A brand-new account that has filled nothing in must still discover."""
    ensure_user(isolated_session)

    criteria = derive_scout_criteria(isolated_session, TEST_USER_ID)
    assert criteria.queries == [DEFAULT_SCOUT_QUERY]
    assert criteria.location is None
    assert criteria.derived_from_preferences is False


def test_preferences_saved_before_any_resume_upload_still_resolve(isolated_session) -> None:
    """Preferences can be saved before a Candidate row exists — the model
    comments on TargetPreference.user_id say so explicitly."""
    ensure_user(isolated_session)
    _preference(isolated_session, candidate_id=None, target_roles=["Data Engineer"])

    assert isolated_session.query(Candidate).count() == 0
    criteria = derive_scout_criteria(isolated_session, TEST_USER_ID)
    assert criteria.queries == ["Data Engineer"]


def test_one_users_preferences_do_not_leak_into_another_search(isolated_session) -> None:
    ensure_user(isolated_session, user_id=TEST_USER_ID)
    ensure_user(isolated_session, user_id=TEST_USER_ID + 1, email="other@example.com")
    _preference(isolated_session, user_id=TEST_USER_ID, target_roles=["Cloud Engineer"])

    other = derive_scout_criteria(isolated_session, TEST_USER_ID + 1)
    assert other.queries == [DEFAULT_SCOUT_QUERY]


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------


def test_first_real_place_becomes_the_search_location(isolated_session) -> None:
    ensure_user(isolated_session)
    _preference(
        isolated_session,
        target_roles=["Cloud Engineer"],
        preferred_locations=["Austin, TX", "Denton, TX"],
    )

    criteria = derive_scout_criteria(isolated_session, TEST_USER_ID)
    assert criteria.location == "Austin, TX"


def test_a_place_listed_alongside_remote_still_searches_broadly(isolated_session) -> None:
    """["Remote", "Austin, TX"] means "remote, or Austin" — narrowing the
    search to Austin would drop the remote half of what they asked for."""
    ensure_user(isolated_session)
    _preference(
        isolated_session,
        target_roles=["Cloud Engineer"],
        preferred_locations=["Remote", "Austin, TX"],
    )

    assert derive_scout_criteria(isolated_session, TEST_USER_ID).location is None


def test_work_mode_only_locations_yield_no_location(isolated_session) -> None:
    ensure_user(isolated_session)
    _preference(
        isolated_session, target_roles=["Cloud Engineer"], preferred_locations=["Remote"]
    )

    assert derive_scout_criteria(isolated_session, TEST_USER_ID).location is None


def test_remote_preference_sends_no_location(isolated_session) -> None:
    """Adzuna's "where" would exclude the remote listings a remote-only
    candidate actually wants."""
    ensure_user(isolated_session)
    _preference(
        isolated_session,
        target_roles=["Cloud Engineer"],
        remote_preference="remote",
        preferred_locations=["Austin, TX"],
    )

    assert derive_scout_criteria(isolated_session, TEST_USER_ID).location is None


def test_a_strictly_onsite_or_hybrid_candidate_keeps_the_location(isolated_session) -> None:
    """Only remote-capable candidates search broadly — someone who will not
    take a remote job still cares where it is."""
    ensure_user(isolated_session)
    for mode in ("hybrid", "onsite"):
        _preference(
            isolated_session,
            target_roles=["Cloud Engineer"],
            remote_preference=mode,
            preferred_locations=["Austin, TX"],
        )
        assert derive_scout_criteria(isolated_session, TEST_USER_ID).location == "Austin, TX", mode


# ---------------------------------------------------------------------------
# Where the network calls go
# ---------------------------------------------------------------------------


@pytest.fixture
def counted_sources(monkeypatch: pytest.MonkeyPatch):
    """Replaces each source with a counter. What matters here is the call
    pattern, not the payloads."""
    calls: dict[str, list] = {
        name: []
        for name in ("remoteok", "greenhouse", "lever", "adzuna", "remotive", "jobicy", "himalayas")
    }

    def _record(name, returns=None):
        def _fake(*args, **kwargs):
            calls[name].append((args, kwargs))
            return returns or []

        return _fake

    for name in ("remoteok", "greenhouse", "lever", "remotive", "jobicy", "himalayas"):
        monkeypatch.setattr(job_scout_service, f"scout_{name}", _record(name))
    monkeypatch.setattr(job_scout_service, "scout_adzuna", _record("adzuna"))
    monkeypatch.setattr(job_scout_service, "persist_jobs", lambda jobs: list(jobs))
    monkeypatch.setattr(
        "backend.services.job_verification_service.mark_stale_if_unseen", lambda *a, **k: 0
    )
    return calls


def test_feed_sources_are_fetched_once_for_many_roles(counted_sources) -> None:
    """The reason this design is not "run the whole scout once per role".

    RemoteOK, Greenhouse and Lever return a fixed feed filtered locally, so
    three roles must not mean three refetches — Greenhouse and Lever would
    re-walk every configured board each time for listings already in hand.
    Adzuna, Remotive, Jobicy, and Himalayas search server-side and genuinely
    need one call each.
    """
    job_scout_service.run_scout(["Cloud Engineer", "DevOps Engineer", "SRE"])

    assert len(counted_sources["remoteok"]) == 1
    assert len(counted_sources["greenhouse"]) == 1
    assert len(counted_sources["lever"]) == 1
    assert len(counted_sources["adzuna"]) == 3
    assert len(counted_sources["remotive"]) == 3
    assert len(counted_sources["jobicy"]) == 3
    assert len(counted_sources["himalayas"]) == 3


def test_feed_sources_receive_every_role_to_match_against(counted_sources) -> None:
    roles = ["Cloud Engineer", "DevOps Engineer"]
    job_scout_service.run_scout(roles)

    for name in ("remoteok", "greenhouse", "lever"):
        args, _ = counted_sources[name][0]
        assert args[0] == roles, name


def test_search_sources_receive_one_role_each(counted_sources) -> None:
    job_scout_service.run_scout(["Cloud Engineer", "SRE"], location="Austin, TX")

    assert sorted(args[0] for args, _ in counted_sources["adzuna"]) == ["Cloud Engineer", "SRE"]
    assert [args[1] for args, _ in counted_sources["adzuna"]] == ["Austin, TX", "Austin, TX"]
    assert sorted(args[0] for args, _ in counted_sources["remotive"]) == ["Cloud Engineer", "SRE"]
    assert sorted(args[0] for args, _ in counted_sources["jobicy"]) == ["Cloud Engineer", "SRE"]
    assert sorted(args[0] for args, _ in counted_sources["himalayas"]) == ["Cloud Engineer", "SRE"]


def test_one_failing_source_does_not_stop_the_others(counted_sources, monkeypatch) -> None:
    def _boom(*args, **kwargs):
        raise job_scout_service.JobScoutError("Greenhouse is unreachable")

    monkeypatch.setattr(job_scout_service, "scout_greenhouse", _boom)
    job_scout_service.run_scout(["Cloud Engineer"])

    assert len(counted_sources["remoteok"]) == 1
    assert len(counted_sources["lever"]) == 1
    assert len(counted_sources["adzuna"]) == 1


def test_one_role_failing_a_search_source_does_not_stop_the_rest(counted_sources, monkeypatch) -> None:
    """Per-role isolation on the search sources, matching the existing
    per-source isolation."""
    seen: list[str] = []

    def _fail_first(query, *args, **kwargs):
        seen.append(query)
        if query == "Cloud Engineer":
            raise job_scout_service.JobScoutError("rate limited")
        return []

    monkeypatch.setattr(job_scout_service, "scout_remotive", _fail_first)
    job_scout_service.run_scout(["Cloud Engineer", "SRE"])

    assert set(seen) == {"Cloud Engineer", "SRE"}


def test_jobicy_failure_does_not_stop_the_other_sources(counted_sources, monkeypatch) -> None:
    def _boom(*args, **kwargs):
        raise job_scout_service.JobScoutError("Jobicy is unreachable")

    monkeypatch.setattr(job_scout_service, "scout_jobicy", _boom)
    job_scout_service.run_scout(["Cloud Engineer"])

    assert len(counted_sources["himalayas"]) == 1
    assert len(counted_sources["remotive"]) == 1
    assert len(counted_sources["remoteok"]) == 1


def test_himalayas_failure_does_not_stop_the_other_sources(counted_sources, monkeypatch) -> None:
    def _boom(*args, **kwargs):
        raise job_scout_service.JobScoutError("Himalayas is unreachable")

    monkeypatch.setattr(job_scout_service, "scout_himalayas", _boom)
    job_scout_service.run_scout(["Cloud Engineer"])

    assert len(counted_sources["jobicy"]) == 1
    assert len(counted_sources["remotive"]) == 1
    assert len(counted_sources["greenhouse"]) == 1


# ---------------------------------------------------------------------------
# Title matching across several roles
# ---------------------------------------------------------------------------


def test_any_query_matcher_matches_on_any_word_of_any_role() -> None:
    queries = ["Cloud Engineer", "Data Analyst"]
    assert _title_matches_any_query("Senior Data Scientist", queries) is True  # "data"
    assert _title_matches_any_query("Cloud Architect", queries) is True  # "cloud"
    assert _title_matches_any_query("Pastry Chef", queries) is False


def test_any_query_matcher_matches_everything_for_an_empty_list() -> None:
    """Mirrors _title_matches_query's behavior for an empty query."""
    assert _title_matches_any_query("Anything At All", []) is True
    assert _title_matches_query("Anything At All", "") is True


def test_feed_sources_reject_a_bare_string_instead_of_matching_characters() -> None:
    """A string is iterable, so passing one where a list is expected would
    match single characters — every listing matching on "e" — and look like a
    working search returning noise."""
    for source in (
        job_scout_service.scout_remoteok,
        job_scout_service.scout_greenhouse,
        job_scout_service.scout_lever,
    ):
        with pytest.raises(TypeError):
            source("cloud engineer")

    with pytest.raises(TypeError):
        job_scout_service.run_scout("cloud engineer")


# ---------------------------------------------------------------------------
# Route: an explicit search still wins
# ---------------------------------------------------------------------------


@pytest.fixture
def captured_scout(monkeypatch: pytest.MonkeyPatch):
    """Capture what the route asked discovery to search for."""
    seen: dict = {}

    def _fake_scout_jobs(queries=None, location=None):
        seen["queries"] = queries
        seen["location"] = location
        return []

    monkeypatch.setattr("backend.api.routes.jobs.scout_jobs", _fake_scout_jobs)
    return seen


def _save_preferences(SessionLocal, user_id, **overrides) -> None:
    with SessionLocal() as db:
        _preference(db, user_id=user_id, **overrides)


def test_route_searches_saved_roles_when_no_query_given(isolated_client, captured_scout) -> None:
    client, SessionLocal = isolated_client
    _save_preferences(
        SessionLocal,
        client.test_user_id,
        target_roles=["Cloud Engineer", "SRE"],
        preferred_locations=["Austin, TX"],
    )

    response = client.post("/api/scout-jobs")
    assert response.status_code == 202
    assert captured_scout["queries"] == ["Cloud Engineer", "SRE"]
    assert captured_scout["location"] == "Austin, TX"
    assert "Cloud Engineer" not in response.json()["note"]
    assert "Auto-scored" in response.json()["note"]


def test_route_lets_an_explicit_query_override_preferences(isolated_client, captured_scout) -> None:
    """The regression that keeps manual search working: reading preferences
    fills in a blank, it never overrides a deliberate search."""
    client, SessionLocal = isolated_client
    _save_preferences(SessionLocal, client.test_user_id, target_roles=["Cloud Engineer"])

    client.post("/api/scout-jobs", params={"what": "data analyst"})
    assert captured_scout["queries"] == ["data analyst"]


def test_route_lets_an_explicit_location_override_preferences(isolated_client, captured_scout) -> None:
    client, SessionLocal = isolated_client
    _save_preferences(
        SessionLocal,
        client.test_user_id,
        target_roles=["Cloud Engineer"],
        preferred_locations=["Austin, TX"],
    )

    client.post("/api/scout-jobs", params={"where": "Seattle, WA"})
    assert captured_scout["queries"] == ["Cloud Engineer"]
    assert captured_scout["location"] == "Seattle, WA"


@pytest.mark.parametrize("blank", ["", "   "])
def test_route_treats_a_blank_query_as_absent(isolated_client, captured_scout, blank) -> None:
    client, SessionLocal = isolated_client
    _save_preferences(SessionLocal, client.test_user_id, target_roles=["Cloud Engineer"])

    client.post("/api/scout-jobs", params={"what": blank})
    assert captured_scout["queries"] == ["Cloud Engineer"]


def test_route_falls_back_for_a_user_with_no_preferences(isolated_client, captured_scout) -> None:
    client, _ = isolated_client
    response = client.post("/api/scout-jobs")
    assert response.status_code == 202
    assert captured_scout["queries"] == [DEFAULT_SCOUT_QUERY]


def test_route_requires_authentication(isolated_client) -> None:
    client, _ = isolated_client
    client.cookies.clear()
    assert client.post("/api/scout-jobs").status_code == 401


# ---------------------------------------------------------------------------
# Search terms end up in an outbound URL
# ---------------------------------------------------------------------------


def test_a_huge_saved_role_is_bounded(isolated_session) -> None:
    """A 5,000-character role produced a 5KB request URL, past what many
    proxies accept, for a search no job board could have matched."""
    ensure_user(isolated_session)
    _preference(isolated_session, target_roles=["x" * 5000])

    (query,) = derive_scout_criteria(isolated_session, TEST_USER_ID).queries
    assert len(query) == MAX_SEARCH_TERM_CHARS


def test_a_huge_saved_location_is_bounded(isolated_session) -> None:
    ensure_user(isolated_session)
    _preference(
        isolated_session, target_roles=["Cloud Engineer"], preferred_locations=["A" * 3000 + ", TX"]
    )

    location = derive_scout_criteria(isolated_session, TEST_USER_ID).location
    assert location is not None and len(location) == MAX_SEARCH_TERM_CHARS


@pytest.mark.parametrize(
    ("saved", "expected"),
    [
        ("Cloud\nEngineer", "Cloud Engineer"),
        ("\tCloud\tEngineer\t", "Cloud Engineer"),
        ("Cloud   Engineer", "Cloud Engineer"),
    ],
)
def test_whitespace_inside_a_role_is_normalized(isolated_session, saved, expected) -> None:
    """Newlines and tabs percent-encode safely but search for nonsense."""
    ensure_user(isolated_session)
    _preference(isolated_session, target_roles=[saved])

    assert derive_scout_criteria(isolated_session, TEST_USER_ID).queries == [expected]


def test_roles_differing_only_by_whitespace_dedupe(isolated_session) -> None:
    ensure_user(isolated_session)
    _preference(isolated_session, target_roles=["Cloud  Engineer", "Cloud Engineer"])

    assert derive_scout_criteria(isolated_session, TEST_USER_ID).queries == ["Cloud Engineer"]


def test_an_explicit_query_is_bounded_like_a_saved_one(isolated_client, captured_scout) -> None:
    """The explicit path reaches the same outbound query string, so it needs
    the same bound — otherwise ?what=<5000 chars> reintroduces the oversized
    URL the preferences path is protected against."""
    client, _ = isolated_client

    client.post("/api/scout-jobs", params={"what": "y" * 5000})
    (query,) = captured_scout["queries"]
    assert len(query) == MAX_SEARCH_TERM_CHARS


def test_an_explicit_query_has_its_whitespace_normalized(isolated_client, captured_scout) -> None:
    client, _ = isolated_client

    client.post("/api/scout-jobs", params={"what": "  Cloud\n\tEngineer  "})
    assert captured_scout["queries"] == ["Cloud Engineer"]


def test_a_whitespace_only_location_is_treated_as_absent(isolated_client, captured_scout) -> None:
    client, SessionLocal = isolated_client
    _save_preferences(
        SessionLocal,
        client.test_user_id,
        target_roles=["Cloud Engineer"],
        preferred_locations=["Austin, TX"],
    )

    client.post("/api/scout-jobs", params={"where": "   "})
    assert captured_scout["location"] == "Austin, TX"


def test_run_scout_refuses_an_empty_query_list() -> None:
    """An empty list makes the title filter match everything, so every feed
    source would be persisted unfiltered — hundreds of irrelevant jobs,
    silently. Unreachable through the route today; guarded so it stays that
    way if a future caller passes one."""
    with pytest.raises(ValueError):
        job_scout_service.run_scout([])
