"""Process-local rate limits and in-flight guards.

This is intentionally in-memory. CareerPilot's current deployment model is a
single local API process. Limits do not coordinate across processes or hosts.
Do not treat this as distributed production infrastructure.

Keys are hashed before storage. The store is bounded (LRU eviction) so an
attacker cannot grow memory forever by spraying unique strings.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict, defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from fastapi import HTTPException, Request, status

_MAX_KEYS = 4096
_HASH_PREFIX = "v1:"


class RateLimited(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__("rate limited")
        self.retry_after = max(1, int(retry_after))


class AlreadyInFlight(Exception):
    pass


@dataclass(frozen=True)
class Limit:
    max_events: int
    window_seconds: float
    max_inflight: int = 0


LOGIN_IP = Limit(max_events=20, window_seconds=15 * 60)
LOGIN_IDENTITY = Limit(max_events=8, window_seconds=15 * 60)
SCOUT = Limit(max_events=8, window_seconds=10 * 60, max_inflight=1)
PARSE_RESUME = Limit(max_events=10, window_seconds=10 * 60, max_inflight=1)
LLM = Limit(max_events=12, window_seconds=10 * 60, max_inflight=1)
INGEST = Limit(max_events=20, window_seconds=10 * 60, max_inflight=1)
SCORE = Limit(max_events=60, window_seconds=10 * 60, max_inflight=1)
INTERVIEW_PREP = Limit(max_events=20, window_seconds=10 * 60, max_inflight=1)
# Separate from SCOUT: saved searches rerun on their own background cadence,
# not a live user click. Sharing SCOUT's bucket would let a user's own
# enabled saved searches 429 their own next manual "Find Jobs" click.
SCHEDULED_SCOUT = Limit(max_events=6, window_seconds=6 * 60 * 60, max_inflight=1)

_CATEGORY_LIMITS: dict[str, Limit] = {
    "login_ip": LOGIN_IP,
    "login_identity": LOGIN_IDENTITY,
    "scout": SCOUT,
    "parse_resume": PARSE_RESUME,
    "llm": LLM,
    "ingest": INGEST,
    "score": SCORE,
    "interview_prep": INTERVIEW_PREP,
    "scheduled_scout": SCHEDULED_SCOUT,
}


def hash_key(raw: str) -> str:
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"{_HASH_PREFIX}{digest}"


def client_ip(request: Request) -> str:
    """Direct peer address only. X-Forwarded-For is not trusted without a known proxy."""
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


class RuntimeGuards:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._windows: OrderedDict[str, deque[float]] = OrderedDict()
        self._inflight: dict[str, int] = defaultdict(int)

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()
            self._inflight.clear()

    def _touch(self, key: str) -> deque[float]:
        window = self._windows.get(key)
        if window is None:
            while len(self._windows) >= _MAX_KEYS:
                self._windows.popitem(last=False)
            window = deque()
            self._windows[key] = window
        else:
            self._windows.move_to_end(key)
        return window

    def check_and_record(self, *, category: str, identity: str, now: float | None = None) -> None:
        limit = _CATEGORY_LIMITS[category]
        key = f"{category}:{hash_key(identity)}"
        stamp = time.monotonic() if now is None else now
        with self._lock:
            window = self._touch(key)
            cutoff = stamp - limit.window_seconds
            while window and window[0] <= cutoff:
                window.popleft()
            if len(window) >= limit.max_events:
                retry_after = int(limit.window_seconds - (stamp - window[0])) + 1
                raise RateLimited(retry_after)
            window.append(stamp)

    def clear(self, *, category: str, identity: str) -> None:
        key = f"{category}:{hash_key(identity)}"
        with self._lock:
            self._windows.pop(key, None)

    def acquire_inflight(self, *, category: str, identity: str) -> str:
        limit = _CATEGORY_LIMITS[category]
        key = f"{category}:{hash_key(identity)}"
        if limit.max_inflight <= 0:
            return key
        with self._lock:
            if self._inflight[key] >= limit.max_inflight:
                raise AlreadyInFlight()
            self._inflight[key] += 1
        return key

    def release_inflight(self, key: str) -> None:
        with self._lock:
            current = self._inflight.get(key, 0)
            if current <= 1:
                self._inflight.pop(key, None)
            else:
                self._inflight[key] = current - 1


runtime_guards = RuntimeGuards()


def reset_runtime_guards() -> None:
    runtime_guards.reset()


def _http_for_guard(exc: Exception) -> HTTPException:
    if isinstance(exc, RateLimited):
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Try again later.",
            headers={"Retry-After": str(exc.retry_after)},
        )
    if isinstance(exc, AlreadyInFlight):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This action is already running. Wait for it to finish.",
        )
    raise exc


@contextmanager
def guard_expensive(user_id: int, category: str) -> Iterator[None]:
    """Acquire in-flight first so a blocked concurrent call does not consume quota."""
    identity = str(user_id)
    token = None
    try:
        token = runtime_guards.acquire_inflight(category=category, identity=identity)
        runtime_guards.check_and_record(category=category, identity=identity)
    except (RateLimited, AlreadyInFlight) as exc:
        if token is not None:
            runtime_guards.release_inflight(token)
        raise _http_for_guard(exc) from exc
    try:
        yield
    finally:
        runtime_guards.release_inflight(token)


def record_failed_login(request: Request, email: str) -> None:
    ip = client_ip(request)
    identity = f"{ip}|{email.strip().lower()}"
    runtime_guards.check_and_record(category="login_ip", identity=ip)
    runtime_guards.check_and_record(category="login_identity", identity=identity)


def peek_login_allowed(request: Request, email: str) -> None:
    """Raise RateLimited if the next failed/success attempt would already be blocked."""
    ip = client_ip(request)
    identity = f"{ip}|{email.strip().lower()}"
    # check_and_record consumes a slot. Use a non-mutating peek:
    for category, raw in (("login_ip", ip), ("login_identity", identity)):
        limit = _CATEGORY_LIMITS[category]
        key = f"{category}:{hash_key(raw)}"
        stamp = time.monotonic()
        with runtime_guards._lock:
            window = runtime_guards._windows.get(key)
            if window is None:
                continue
            cutoff = stamp - limit.window_seconds
            live = [item for item in window if item > cutoff]
            if len(live) >= limit.max_events:
                retry_after = int(limit.window_seconds - (stamp - live[0])) + 1
                raise RateLimited(retry_after)


def clear_failed_login(request: Request, email: str) -> None:
    ip = client_ip(request)
    identity = f"{ip}|{email.strip().lower()}"
    runtime_guards.clear(category="login_ip", identity=ip)
    runtime_guards.clear(category="login_identity", identity=identity)
