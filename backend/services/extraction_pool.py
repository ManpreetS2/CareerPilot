"""Bounded extraction worker pool.

Workers perform provider/network work on immutable snapshots. The request
thread persists results in the original job order.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field

from backend.core.config import settings
from backend.schemas.schemas import JobIntelligence
from backend.services.extraction_task import ExtractionTask
from backend.services.llm_client import (
    LLMAuthError,
    LLMConfigurationError,
    LLMEmptyResponseError,
    LLMProviderError,
    LLMRateLimitError,
)
from backend.services.provider_slots import reset_provider_slots, slot_pool

logger = logging.getLogger(__name__)

GenerateFn = Callable[[str, str | None], str]
WorkerFn = Callable[[ExtractionTask, GenerateFn | None], "WorkerResult"]

_INFLIGHT: dict[str, Future] = {}
_INFLIGHT_LOCK = threading.Lock()
_PEAK_LOCK = threading.Lock()
_active_workers = 0
_peak_workers = 0


@dataclass
class WorkerResult:
    intelligence: JobIntelligence | None = None
    error: Exception | None = None
    provider: str | None = None
    slot_id: str | None = None
    attempts: int = 0
    fallbacks: int = 0
    provider_duration_ms: int = 0
    thread_id: int = 0


@dataclass
class BatchMetrics:
    batch_size: int = 0
    cache_hits: int = 0
    queued: int = 0
    completed: int = 0
    failed: int = 0
    workers_used: int = 0
    cooldown_count: int = 0
    total_duration_ms: int = 0
    provider_duration_ms: int = 0
    fallback_count: int = 0


@dataclass
class BatchOutcome:
    results: dict[str, WorkerResult] = field(default_factory=dict)
    metrics: BatchMetrics = field(default_factory=BatchMetrics)


def reset_extraction_runtime() -> None:
    global _active_workers, _peak_workers
    with _INFLIGHT_LOCK:
        _INFLIGHT.clear()
    with _PEAK_LOCK:
        _active_workers = 0
        _peak_workers = 0
    reset_provider_slots()


def _reset_peak() -> None:
    global _active_workers, _peak_workers
    with _PEAK_LOCK:
        _active_workers = 0
        _peak_workers = 0


def peak_workers_used() -> int:
    with _PEAK_LOCK:
        return _peak_workers


def _mark_active(delta: int) -> None:
    global _active_workers, _peak_workers
    with _PEAK_LOCK:
        _active_workers = max(0, _active_workers + delta)
        if _active_workers > _peak_workers:
            _peak_workers = _active_workers


def _log_batch(metrics: BatchMetrics) -> None:
    logger.info(
        "extraction_batch batch_size=%s cache_hits=%s queued=%s completed=%s "
        "failed=%s workers_used=%s fallback_count=%s cooldown_count=%s "
        "total_duration_ms=%s provider_duration_ms=%s",
        metrics.batch_size,
        metrics.cache_hits,
        metrics.queued,
        metrics.completed,
        metrics.failed,
        metrics.workers_used,
        metrics.fallback_count,
        metrics.cooldown_count,
        metrics.total_duration_ms,
        metrics.provider_duration_ms,
    )


def _capacity(task_count: int, generate_fn: GenerateFn | None) -> int:
    configured = max(1, int(settings.job_extraction_max_workers))
    if generate_fn is not None:
        return max(1, min(configured, task_count))
    slot_pool.rebuild_if_needed()
    gemini = slot_pool.provider_capacity("gemini")
    ollama = slot_pool.provider_capacity("ollama")
    available = max(gemini, ollama, 1)
    return max(1, min(configured, task_count, available))


def run_extraction_batch(
    tasks: list[ExtractionTask],
    worker: WorkerFn,
    *,
    generate_fn: GenerateFn | None = None,
) -> BatchOutcome:
    """Run independent extraction tasks on a bounded pool. No DB access."""
    started = time.perf_counter()
    metrics = BatchMetrics(batch_size=len(tasks), queued=len(tasks))
    if not tasks:
        return BatchOutcome(metrics=metrics)

    slot_pool.rebuild_if_needed()
    workers = _capacity(len(tasks), generate_fn)
    metrics.workers_used = workers
    _reset_peak()
    outcome = BatchOutcome(metrics=metrics)
    inflight_held: list[tuple[str, Future]] = []

    def _wrapped(task: ExtractionTask) -> WorkerResult:
        _mark_active(1)
        try:
            result = worker(task, generate_fn)
            result.thread_id = threading.get_ident()
            return result
        finally:
            _mark_active(-1)

    try:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="extract") as pool:
            future_for_task: dict[str, Future] = {}
            for task in tasks:
                key = task.cache_key
                with _INFLIGHT_LOCK:
                    existing = _INFLIGHT.get(key)
                    if existing is not None:
                        future_for_task[task.job_public_id] = existing
                        continue
                    future = pool.submit(_wrapped, task)
                    _INFLIGHT[key] = future
                    inflight_held.append((key, future))
                    future_for_task[task.job_public_id] = future
            wait(list(future_for_task.values()))
            for task in tasks:
                future = future_for_task[task.job_public_id]
                try:
                    result = future.result()
                except Exception as exc:  # noqa: BLE001 — isolate one worker crash
                    result = WorkerResult(error=exc, thread_id=threading.get_ident())
                outcome.results[task.job_public_id] = result
                if result.error is None:
                    metrics.completed += 1
                else:
                    metrics.failed += 1
                metrics.provider_duration_ms += result.provider_duration_ms
                metrics.fallback_count += result.fallbacks
            metrics.cooldown_count = slot_pool.cooldown_count
    finally:
        with _INFLIGHT_LOCK:
            for key, future in inflight_held:
                if _INFLIGHT.get(key) is future:
                    del _INFLIGHT[key]
        metrics.total_duration_ms = int((time.perf_counter() - started) * 1000)
        metrics.workers_used = max(metrics.workers_used, peak_workers_used())
        _log_batch(metrics)
    return outcome


def generate_with_provider_slot(
    provider: str,
    prompt: str,
    system_prompt: str | None,
    json_schema: dict | None,
    *,
    on_attempt: Callable[[str | None], None] | None = None,
) -> tuple[str, str | None]:
    """One provider call through a healthy slot. Never races two slots for one job."""
    from backend.services.llm_client import LLMClient
    from backend.services.llm_provider_sequence import invoke_provider_generate

    budget = max(1, int(settings.job_extraction_retry_budget))
    fallbacks = 0
    last_error: Exception | None = None
    for _attempt in range(budget):
        slot = slot_pool.acquire(provider)
        if slot is None:
            break
        if on_attempt is not None:
            on_attempt(slot.slot_id)
        try:
            client = LLMClient(provider=provider, api_key=slot.credential)
            text = invoke_provider_generate(client, prompt, system_prompt, json_schema)
            slot_pool.release(slot)
            logger.info(
                "extraction_slot provider=%s slot_id=%s attempt=%s",
                provider,
                slot.slot_id,
                _attempt + 1,
            )
            return text, slot.slot_id
        except LLMRateLimitError as exc:
            last_error = exc
            slot_pool.mark_cooldown(slot)
            fallbacks += 1
            logger.info(
                "extraction_slot cooldown provider=%s slot_id=%s",
                provider,
                slot.slot_id,
            )
            continue
        except LLMAuthError as exc:
            last_error = exc
            slot_pool.mark_disabled(slot)
            logger.info(
                "extraction_slot disabled provider=%s slot_id=%s",
                provider,
                slot.slot_id,
            )
            continue
        except (LLMProviderError, LLMEmptyResponseError, LLMConfigurationError, ValueError):
            slot_pool.release(slot)
            raise
        except Exception:
            slot_pool.release(slot)
            raise
    if last_error is not None:
        raise last_error
    raise LLMConfigurationError(f"{provider} has no healthy extraction slots.")


# Imported by tests that assert cleanup.
__all__ = [
    "BatchMetrics",
    "BatchOutcome",
    "WorkerResult",
    "generate_with_provider_slot",
    "peak_workers_used",
    "reset_extraction_runtime",
    "run_extraction_batch",
]
