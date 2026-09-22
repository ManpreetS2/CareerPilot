"""ProviderFetchCache: the per-provider fetch cooldown shared across every
caller of a scout source's raw fetch (a live "Find Jobs" click, a Saved
Search tick, or several Saved Searches due in the same tick)."""

from __future__ import annotations

from backend.services.provider_throttle import PROVIDER_MIN_INTERVAL_SECONDS, ProviderFetchCache


def test_cache_hit_within_the_interval_skips_the_underlying_fetch(monkeypatch) -> None:
    cache = ProviderFetchCache()
    clock = {"now": 1000.0}
    monkeypatch.setattr("backend.services.provider_throttle.time.monotonic", lambda: clock["now"])
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return [{"id": calls["n"]}]

    first = cache.get_or_fetch("remoteok", None, fetch)
    clock["now"] += PROVIDER_MIN_INTERVAL_SECONDS["remoteok"] / 2
    second = cache.get_or_fetch("remoteok", None, fetch)

    assert calls["n"] == 1
    assert first == second == [{"id": 1}]


def test_cache_miss_after_the_interval_elapses_refetches(monkeypatch) -> None:
    cache = ProviderFetchCache()
    clock = {"now": 1000.0}
    monkeypatch.setattr("backend.services.provider_throttle.time.monotonic", lambda: clock["now"])
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return [{"id": calls["n"]}]

    cache.get_or_fetch("remoteok", None, fetch)
    clock["now"] += PROVIDER_MIN_INTERVAL_SECONDS["remoteok"] + 1
    second = cache.get_or_fetch("remoteok", None, fetch)

    assert calls["n"] == 2
    assert second == [{"id": 2}]


def test_a_failed_fetch_is_never_cached(monkeypatch) -> None:
    cache = ProviderFetchCache()
    monkeypatch.setattr("backend.services.provider_throttle.time.monotonic", lambda: 1000.0)
    calls = {"n": 0}

    def failing_fetch():
        calls["n"] += 1
        raise RuntimeError("provider unreachable")

    for _ in range(3):
        try:
            cache.get_or_fetch("remoteok", None, failing_fetch)
        except RuntimeError:
            pass

    assert calls["n"] == 3  # never suppressed by a cached failure


def test_different_cache_keys_are_independent(monkeypatch) -> None:
    cache = ProviderFetchCache()
    monkeypatch.setattr("backend.services.provider_throttle.time.monotonic", lambda: 1000.0)
    calls: dict[str, int] = {}

    def fetch_for(key):
        def _fetch():
            calls[key] = calls.get(key, 0) + 1
            return [{"board": key}]

        return _fetch

    a = cache.get_or_fetch("greenhouse", "board-a", fetch_for("board-a"))
    b = cache.get_or_fetch("greenhouse", "board-b", fetch_for("board-b"))
    a_again = cache.get_or_fetch("greenhouse", "board-a", fetch_for("board-a"))

    assert a == [{"board": "board-a"}]
    assert b == [{"board": "board-b"}]
    assert a_again == a
    assert calls == {"board-a": 1, "board-b": 1}


def test_different_sources_never_collide_on_the_same_cache_key(monkeypatch) -> None:
    cache = ProviderFetchCache()
    monkeypatch.setattr("backend.services.provider_throttle.time.monotonic", lambda: 1000.0)

    greenhouse_result = cache.get_or_fetch("greenhouse", "acme", lambda: [{"source": "greenhouse"}])
    lever_result = cache.get_or_fetch("lever", "acme", lambda: [{"source": "lever"}])

    assert greenhouse_result == [{"source": "greenhouse"}]
    assert lever_result == [{"source": "lever"}]


def test_reset_clears_every_entry(monkeypatch) -> None:
    cache = ProviderFetchCache()
    monkeypatch.setattr("backend.services.provider_throttle.time.monotonic", lambda: 1000.0)
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return []

    cache.get_or_fetch("remoteok", None, fetch)
    cache.reset()
    cache.get_or_fetch("remoteok", None, fetch)

    assert calls["n"] == 2


def test_an_unconfigured_source_has_no_cooldown(monkeypatch) -> None:
    """A source with no entry in PROVIDER_MIN_INTERVAL_SECONDS defaults to
    a zero-second interval — always a fresh fetch, never a stale one from
    an unrecognized key silently sticking around forever."""
    cache = ProviderFetchCache()
    monkeypatch.setattr("backend.services.provider_throttle.time.monotonic", lambda: 1000.0)
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return []

    cache.get_or_fetch("some_future_source", None, fetch)
    cache.get_or_fetch("some_future_source", None, fetch)

    assert calls["n"] == 2
