"""Bounded, secret-safe provider slots for extraction workers.

Credentials stay in memory. Logs may use slot_id values such as gemini-slot-1.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from backend.core.config import configured_gemini_keys, settings


@dataclass
class ProviderSlot:
    slot_id: str
    provider: str
    _credential: str | None = field(repr=False, default=None)
    cooldown_until: float = 0.0
    disabled: bool = False
    in_use: bool = False

    @property
    def credential(self) -> str | None:
        return self._credential

    def is_healthy(self, now: float | None = None) -> bool:
        stamp = time.monotonic() if now is None else now
        return not self.disabled and stamp >= self.cooldown_until


class SlotPool:
    def __init__(self) -> None:
        self._lock = threading.Condition()
        self._slots: list[ProviderSlot] = []
        self.cooldown_count = 0

    def reset(self) -> None:
        with self._lock:
            self._slots = _build_slots()
            self.cooldown_count = 0
            self._lock.notify_all()

    def rebuild_if_needed(self) -> None:
        expected = _slot_signature()
        with self._lock:
            current = tuple((slot.slot_id, slot.provider) for slot in self._slots)
            if current != expected or not self._slots:
                self._slots = _build_slots()
                self.cooldown_count = 0
                self._lock.notify_all()

    def slots(self) -> list[ProviderSlot]:
        with self._lock:
            return list(self._slots)

    def provider_capacity(self, provider: str) -> int:
        now = time.monotonic()
        with self._lock:
            return sum(
                1
                for slot in self._slots
                if slot.provider == provider and not slot.disabled and slot.is_healthy(now)
            )

    def acquire(self, provider: str, *, timeout: float | None = None) -> ProviderSlot | None:
        wait_for = float(
            settings.job_extraction_slot_acquire_timeout_seconds if timeout is None else timeout
        )
        deadline = time.monotonic() + max(0.0, wait_for)
        with self._lock:
            while True:
                now = time.monotonic()
                available = [
                    slot
                    for slot in self._slots
                    if slot.provider == provider and not slot.in_use and slot.is_healthy(now)
                ]
                if available:
                    slot = available[0]
                    slot.in_use = True
                    return slot
                provider_slots = [slot for slot in self._slots if slot.provider == provider]
                if not provider_slots:
                    return None
                busy = any(slot.in_use for slot in provider_slots)
                if not busy:
                    return None
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._lock.wait(timeout=min(remaining, 0.05))

    def release(self, slot: ProviderSlot) -> None:
        with self._lock:
            slot.in_use = False
            self._lock.notify_all()

    def mark_cooldown(self, slot: ProviderSlot, seconds: float | None = None) -> None:
        delay = float(
            settings.job_extraction_slot_cooldown_seconds if seconds is None else seconds
        )
        with self._lock:
            slot.cooldown_until = time.monotonic() + max(0.1, delay)
            slot.in_use = False
            self.cooldown_count += 1
            self._lock.notify_all()

    def mark_disabled(self, slot: ProviderSlot) -> None:
        with self._lock:
            slot.disabled = True
            slot.in_use = False
            self._lock.notify_all()


def _slot_signature() -> tuple[tuple[str, str], ...]:
    names: list[tuple[str, str]] = []
    for index, _key in enumerate(configured_gemini_keys(), start=1):
        names.append((f"gemini-slot-{index}", "gemini"))
    ollama_n = max(0, int(settings.job_extraction_ollama_max_workers))
    for index in range(1, ollama_n + 1):
        names.append((f"ollama-slot-{index}", "ollama"))
    return tuple(names)


def _build_slots() -> list[ProviderSlot]:
    slots: list[ProviderSlot] = []
    for index, key in enumerate(configured_gemini_keys(), start=1):
        slots.append(
            ProviderSlot(slot_id=f"gemini-slot-{index}", provider="gemini", _credential=key)
        )
    ollama_n = max(0, int(settings.job_extraction_ollama_max_workers))
    for index in range(1, ollama_n + 1):
        slots.append(ProviderSlot(slot_id=f"ollama-slot-{index}", provider="ollama"))
    return slots


slot_pool = SlotPool()
slot_pool.reset()


def reset_provider_slots() -> None:
    slot_pool.reset()
