"""Per-provider fetch cache/cooldown, shared across every caller of a scout
source's raw fetch — a live "Find Jobs" click, a Saved Search tick, or a
second Saved Search due in the same tick.

Deliberately in-memory, matching backend/core/rate_limit.py's own
convention ("intentionally in-memory... single local API process"):
provider cooldown is the same category of ephemeral, restart-safe-to-lose
state, not something that needs to survive a process restart.

This caches raw provider responses, not per-query filtered results — the
raw fetch is what's actually redundant across saved searches with
different query terms hitting the same Greenhouse board/Lever company/
RemoteOK feed. Filtering by query must always happen fresh on top of a
cached (or freshly fetched) raw response; caching the already-filtered
output would let a second saved search silently receive the first
search's filtered — i.e. wrong — results within the cache window.
"""

from __future__ import annotations

import threading
import time
from typing import Callable

# Real per-provider constraints, not arbitrary: Remotive is rate-limited by
# its own terms and should not be polled aggressively by an unattended
# background loop; Himalayas' catalog refreshes daily, so anything more
# frequent just repeats identical work; Adzuna usage must stay inside an
# account quota; the remaining feed sources tolerate a short cooldown that
# mainly exists to collapse near-simultaneous saved-search ticks.
PROVIDER_MIN_INTERVAL_SECONDS: dict[str, float] = {
    "remoteok": 5 * 60,
    "greenhouse": 5 * 60,
    "lever": 5 * 60,
    "jobicy": 10 * 60,
    "adzuna": 10 * 60,
    "remotive": 60 * 60,
    "himalayas": 24 * 60 * 60,
}


class ProviderFetchCache:
    """Keyed by (source, cache_key): cache_key is None for a source whose
    raw fetch doesn't vary by query (RemoteOK's single feed, one
    Greenhouse board, one Lever company), or the outgoing query/tag for a
    source that searches server-side."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[tuple[str, str | None], tuple[float, list[dict]]] = {}

    def get_or_fetch(
        self, source: str, cache_key: str | None, fetch_fn: Callable[[], list[dict]]
    ) -> list[dict]:
        key = (source, cache_key)
        interval = PROVIDER_MIN_INTERVAL_SECONDS.get(source, 0)
        now = time.monotonic()
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None and (now - cached[0]) < interval:
                return cached[1]
        # Network call outside the lock — a slow fetch must not block every
        # other thread's cache lookup for an unrelated key.
        listings = fetch_fn()
        with self._lock:
            self._entries[key] = (now, listings)
        return listings

    def reset(self) -> None:
        with self._lock:
            self._entries.clear()


provider_fetch_cache = ProviderFetchCache()


def reset_provider_throttle() -> None:
    """Test-isolation hook — wired into tests/conftest.py's autouse fixture
    the same way backend.core.rate_limit's runtime guards already are.
    Process-local in-memory state leaks across tests otherwise: a cache
    entry left by one test can silently skip another test's mocked source
    call."""
    provider_fetch_cache.reset()
