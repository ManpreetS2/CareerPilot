"""Bounded parallel Job Intelligence extraction: quality, slots, cache, safety."""

from __future__ import annotations

import json
import threading
import time
from unittest.mock import Mock

import pytest

from backend.core.config import configured_gemini_keys, settings, validate_llm_settings
from backend.db.models import JobIntelligenceRecord, JobRecord
from backend.schemas.schemas import JobIntelligence
from backend.services.extraction_pool import (
    peak_workers_used,
    reset_extraction_runtime,
)
from backend.services.extraction_task import INTELLIGENCE_EXTRACTION_VERSION
from backend.services.job_intelligence_service import (
    extract_job_intelligence,
    extract_job_intelligence_batch,
)
from backend.services.llm_client import LLMAuthError, LLMRateLimitError, provider_is_configured
from backend.services.provider_slots import slot_pool
from tests.test_job_intelligence import _job, _payload


def _sleeping_generator(delay_s: float, payload: dict | None = None, counter: dict | None = None):
    body = json.dumps(payload or _payload())
    lock = threading.Lock()
    state = counter if counter is not None else {"n": 0, "active": 0, "peak": 0}

    def generate(prompt: str, system: str | None) -> str:
        del prompt, system
        with lock:
            state["n"] += 1
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
        try:
            if delay_s:
                time.sleep(delay_s)
            return body
        finally:
            with lock:
                state["active"] -= 1

    generate.state = state  # type: ignore[attr-defined]
    return generate


def _jobs(session, count: int, *, prefix: str = "px") -> list[JobRecord]:
    return [
        _job(session, public_id=f"{prefix}-{index}", title=f"Platform Engineer {index}")
        for index in range(1, count + 1)
    ]


def _as_intelligence(item) -> JobIntelligence:
    assert isinstance(item, JobIntelligence), item
    return item


def test_configured_gemini_keys_primary_extras_dedupe_and_blanks(monkeypatch) -> None:
    monkeypatch.setattr(settings, "gemini_api_key", "primary-key")
    monkeypatch.setattr(settings, "gemini_api_keys", " extra-one, primary-key, ,extra-two, extra-one ")
    assert configured_gemini_keys() == ["primary-key", "extra-one", "extra-two"]
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "gemini_api_keys", "")
    assert configured_gemini_keys() == []
    assert provider_is_configured("gemini") is False
    monkeypatch.setattr(settings, "gemini_api_keys", "only-extra")
    assert configured_gemini_keys() == ["only-extra"]
    assert provider_is_configured("gemini") is True


def test_extraction_worker_bounds_reject_invalid_values(monkeypatch) -> None:
    monkeypatch.setattr(settings, "job_extraction_max_workers", 0)
    with pytest.raises(RuntimeError, match="JOB_EXTRACTION_MAX_WORKERS"):
        validate_llm_settings(settings)
    monkeypatch.setattr(settings, "job_extraction_max_workers", 3)
    monkeypatch.setattr(settings, "job_extraction_ollama_max_workers", 99)
    with pytest.raises(RuntimeError, match="JOB_EXTRACTION_OLLAMA_MAX_WORKERS"):
        validate_llm_settings(settings)


def test_serial_and_parallel_intelligence_are_equivalent(isolated_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "job_extraction_max_workers", 3)
    postings = [
        (
            "or-required",
            "Backend Engineer",
            "Required: Python or Java. Preferred: React.js. Node.js / NodeJS. "
            "Bachelor's enrollment required. Graduation window: May 2027. "
            "Must be authorized to work in the United States. No sponsorship. "
            "Secret clearance required. GPA 3.5. Driver's license required. "
            "Hybrid 3 days in Seattle. Salary $120,000. Preferred skills are a plus. "
            + ("Filler. " * 80)
            + "Eligibility at the end: must be eligible to work without sponsorship.",
        ),
        (
            "end-eligibility",
            "Data Engineer",
            "We use Python. Preferred: React.js. "
            + ("More description. " * 60)
            + "Must be authorized to work in the United States.",
        ),
    ]
    jobs = []
    for public_id, title, description in postings:
        jobs.append(_job(isolated_session, public_id=public_id, title=title, description=description))

    def generate(prompt: str, system: str | None) -> str:
        del system
        if "Backend Engineer" in prompt:
            return json.dumps(
                _payload(
                    required_skills=["Python", "Java"],
                    preferred_skills=["React.js"],
                    tech_stack=["Node.js"],
                    education_requirements=["Bachelor's enrollment required"],
                    years_experience=None,
                    seniority=None,
                    responsibilities=[],
                    likely_interview_focus=[],
                )
            )
        return json.dumps(
            _payload(
                required_skills=["Python"],
                preferred_skills=["React.js"],
                tech_stack=[],
                education_requirements=[],
                years_experience=None,
                seniority=None,
                responsibilities=[],
                likely_interview_focus=[],
            )
        )

    serial = [
        extract_job_intelligence(isolated_session, job.public_id, generate_fn=generate).model_dump()
        for job in jobs
    ]
    for row in isolated_session.query(JobIntelligenceRecord).all():
        isolated_session.delete(row)
    isolated_session.commit()

    parallel = [
        _as_intelligence(item).model_dump()
        for item in extract_job_intelligence_batch(
            isolated_session,
            [job.public_id for job in jobs],
            generate_fn=generate,
            force=True,
        )
    ]
    assert serial == parallel


def test_fake_provider_benchmark_shows_concurrency(isolated_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "job_extraction_max_workers", 1)
    one = _jobs(isolated_session, 1, prefix="bench1")
    delay = 0.12
    started = time.perf_counter()
    extract_job_intelligence_batch(
        isolated_session,
        [one[0].public_id],
        generate_fn=_sleeping_generator(delay),
        force=True,
    )
    one_s = time.perf_counter() - started
    assert peak_workers_used() == 1
    assert one_s >= delay * 0.8
    isolated_session.query(JobIntelligenceRecord).delete()
    isolated_session.commit()

    jobs = _jobs(isolated_session, 6, prefix="bench")
    ids = [job.public_id for job in jobs]
    delay = 0.12
    serial_gen = _sleeping_generator(delay)
    started = time.perf_counter()
    extract_job_intelligence_batch(isolated_session, ids, generate_fn=serial_gen, force=True)
    serial_s = time.perf_counter() - started
    serial_peak = peak_workers_used()
    isolated_session.query(JobIntelligenceRecord).delete()
    isolated_session.commit()

    timings = {"1": serial_s}
    peaks = {"1": serial_peak}
    for workers in (2, 3, 6):
        monkeypatch.setattr(settings, "job_extraction_max_workers", workers)
        reset_extraction_runtime()
        gen = _sleeping_generator(delay)
        started = time.perf_counter()
        extract_job_intelligence_batch(isolated_session, ids, generate_fn=gen, force=True)
        timings[str(workers)] = time.perf_counter() - started
        peaks[str(workers)] = peak_workers_used()
        isolated_session.query(JobIntelligenceRecord).delete()
        isolated_session.commit()

    assert peaks["1"] == 1
    assert peaks["2"] == 2
    assert peaks["3"] == 3
    assert peaks["6"] == 6
    assert timings["1"] >= delay * 5
    assert timings["2"] < timings["1"] * 0.85
    assert timings["3"] < timings["1"] * 0.7
    assert timings["6"] < timings["1"] * 0.55


def test_cached_jobs_make_zero_provider_calls(isolated_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "job_extraction_max_workers", 3)
    jobs = _jobs(isolated_session, 4, prefix="cache")
    ids = [job.public_id for job in jobs]
    generator = _sleeping_generator(0.01)
    extract_job_intelligence_batch(isolated_session, ids[:2], generate_fn=generator, force=True)
    first_calls = generator.state["n"]
    mixed = _sleeping_generator(0.01)
    extract_job_intelligence_batch(isolated_session, ids, generate_fn=mixed, force=False)
    assert mixed.state["n"] == 2
    cached = _sleeping_generator(0.01)
    extract_job_intelligence_batch(isolated_session, ids, generate_fn=cached, force=False)
    assert cached.state["n"] == 0
    assert first_calls == 2


def test_fingerprint_change_and_version_bump_miss_cache(isolated_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "job_extraction_max_workers", 2)
    job = _job(isolated_session, public_id="fp-1")
    generator = _sleeping_generator(0.0)
    extract_job_intelligence_batch(
        isolated_session, [job.public_id], generate_fn=generator, force=False
    )
    assert generator.state["n"] == 1
    job.description = job.description + "\nUpdated eligibility: GPA 3.8 required."
    isolated_session.commit()
    second = _sleeping_generator(0.0)
    extract_job_intelligence_batch(
        isolated_session, [job.public_id], generate_fn=second, force=False
    )
    assert second.state["n"] == 1
    third = _sleeping_generator(0.0)
    monkeypatch.setattr(
        "backend.services.job_intelligence_service.INTELLIGENCE_EXTRACTION_VERSION",
        INTELLIGENCE_EXTRACTION_VERSION + 1,
    )
    extract_job_intelligence_batch(
        isolated_session, [job.public_id], generate_fn=third, force=False
    )
    assert third.state["n"] == 1


def test_inflight_dedupe_does_not_duplicate_provider_calls(tmp_path, monkeypatch) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.db.database import Base

    monkeypatch.setattr(settings, "job_extraction_max_workers", 2)
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'inflight.sqlite').as_posix()}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    with SessionLocal() as seed:
        job = _job(seed, public_id="inflight-1")
        public_id = job.public_id
    started = threading.Event()
    release = threading.Event()
    calls = {"n": 0}
    lock = threading.Lock()

    def generate(prompt: str, system: str | None) -> str:
        del prompt, system
        with lock:
            calls["n"] += 1
        started.set()
        assert release.wait(timeout=2)
        return json.dumps(_payload())

    errors: list[BaseException] = []

    def run() -> None:
        try:
            with SessionLocal() as db:
                extract_job_intelligence_batch(
                    db,
                    [public_id],
                    generate_fn=generate,
                    force=True,
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    first = threading.Thread(target=run)
    first.start()
    assert started.wait(timeout=2)
    second = threading.Thread(target=run)
    second.start()
    time.sleep(0.05)
    release.set()
    first.join(timeout=5)
    second.join(timeout=5)
    assert errors == []
    assert calls["n"] == 1
    engine.dispose()


def test_one_failure_does_not_poison_batch(isolated_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "job_extraction_max_workers", 3)
    jobs = _jobs(isolated_session, 6, prefix="iso")
    lock = threading.Lock()
    calls = {"n": 0}

    def generate(prompt: str, system: str | None) -> str:
        with lock:
            calls["n"] += 1
            n = calls["n"]
        if "Platform Engineer 3" in prompt:
            raise RuntimeError("injected provider failure")
        return json.dumps(_payload())

    results = extract_job_intelligence_batch(
        isolated_session,
        [job.public_id for job in jobs],
        generate_fn=generate,
        force=True,
    )
    successes = [item for item in results if isinstance(item, JobIntelligence)]
    failures = [item for item in results if not isinstance(item, JobIntelligence)]
    assert len(successes) == 5
    assert len(failures) == 1
    assert isolated_session.query(JobIntelligenceRecord).count() == 5
    assert [item.job_id for item in successes] == [
        job.public_id for job, item in zip(jobs, results) if isinstance(item, JobIntelligence)
    ]


def test_request_session_is_not_used_on_worker_threads(isolated_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "job_extraction_max_workers", 3)
    jobs = _jobs(isolated_session, 3, prefix="sess")
    main_id = threading.get_ident()
    foreign: list[int] = []
    original_query = isolated_session.query

    def wrapped(*args, **kwargs):
        ident = threading.get_ident()
        if ident != main_id:
            foreign.append(ident)
        return original_query(*args, **kwargs)

    isolated_session.query = wrapped  # type: ignore[method-assign]
    extract_job_intelligence_batch(
        isolated_session,
        [job.public_id for job in jobs],
        generate_fn=_sleeping_generator(0.05),
        force=True,
    )
    assert foreign == []


def test_slot_ids_are_secret_safe_and_released_after_error(monkeypatch) -> None:
    monkeypatch.setattr(settings, "gemini_api_key", "super-secret-key-value")
    monkeypatch.setattr(settings, "gemini_api_keys", "another-super-secret-key")
    reset_extraction_runtime()
    ids = [slot.slot_id for slot in slot_pool.slots() if slot.provider == "gemini"]
    assert ids == ["gemini-slot-1", "gemini-slot-2"]
    assert "secret" not in "".join(ids).lower()
    slot = slot_pool.acquire("gemini")
    assert slot is not None
    slot_pool.mark_disabled(slot)
    other = slot_pool.acquire("gemini")
    assert other is not None
    assert other.slot_id == "gemini-slot-2"
    slot_pool.release(other)
    assert slot_pool.acquire("gemini") is not None


def test_two_gemini_slots_run_two_jobs_concurrently(isolated_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "gemini_api_key", "slot-key-one")
    monkeypatch.setattr(settings, "gemini_api_keys", "slot-key-two")
    monkeypatch.setattr(settings, "job_extraction_max_workers", 2)
    monkeypatch.setattr(settings, "llm_provider_order", "gemini")
    reset_extraction_runtime()
    jobs = _jobs(isolated_session, 2, prefix="slots")
    active = 0
    peak = 0
    lock = threading.Lock()
    used_keys: set[str] = set()

    def fake_generate(self, prompt, system_prompt=None, json_schema=None):
        del prompt, system_prompt, json_schema
        nonlocal active, peak
        key = self._api_key() or ""
        with lock:
            used_keys.add(key)
            active += 1
            peak = max(peak, active)
        try:
            time.sleep(0.15)
            return json.dumps(_payload())
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr("backend.services.llm_client.LLMClient.generate", fake_generate)
    extract_job_intelligence_batch(
        isolated_session,
        [job.public_id for job in jobs],
        force=True,
    )
    assert peak == 2
    assert used_keys == {"slot-key-one", "slot-key-two"}
    assert isolated_session.query(JobIntelligenceRecord).count() == 2


def test_max_workers_caps_three_keys(isolated_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "gemini_api_key", "k1")
    monkeypatch.setattr(settings, "gemini_api_keys", "k2,k3")
    monkeypatch.setattr(settings, "job_extraction_max_workers", 2)
    monkeypatch.setattr(settings, "llm_provider_order", "gemini")
    reset_extraction_runtime()
    jobs = _jobs(isolated_session, 6, prefix="cap")
    active = 0
    peak = 0
    lock = threading.Lock()

    def fake_generate(self, prompt, system_prompt=None, json_schema=None):
        del self, prompt, system_prompt, json_schema
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            time.sleep(0.08)
            return json.dumps(_payload())
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr("backend.services.llm_client.LLMClient.generate", fake_generate)
    extract_job_intelligence_batch(
        isolated_session,
        [job.public_id for job in jobs],
        force=True,
    )
    assert peak == 2
    assert isolated_session.query(JobIntelligenceRecord).count() == 6


def test_rate_limited_gemini_slot_does_not_poison_other_slot(isolated_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "gemini_api_key", "rate-limited-key")
    monkeypatch.setattr(settings, "gemini_api_keys", "healthy-key")
    monkeypatch.setattr(settings, "job_extraction_max_workers", 2)
    monkeypatch.setattr(settings, "job_extraction_slot_cooldown_seconds", 30)
    monkeypatch.setattr(settings, "llm_provider_order", "gemini")
    reset_extraction_runtime()
    jobs = _jobs(isolated_session, 2, prefix="rl")

    def fake_generate(self, prompt, system_prompt=None, json_schema=None):
        del prompt, system_prompt, json_schema
        if self._api_key() == "rate-limited-key":
            raise LLMRateLimitError("Gemini provider request failed.")
        return json.dumps(_payload())

    monkeypatch.setattr("backend.services.llm_client.LLMClient.generate", fake_generate)
    results = extract_job_intelligence_batch(
        isolated_session,
        [job.public_id for job in jobs],
        force=True,
    )
    assert all(isinstance(item, JobIntelligence) for item in results)


def test_all_gemini_slots_rate_limited_fall_back_to_ollama(isolated_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "gemini_api_key", "g1")
    monkeypatch.setattr(settings, "gemini_api_keys", "g2")
    monkeypatch.setattr(settings, "llm_provider_order", "gemini,ollama")
    monkeypatch.setattr(settings, "job_extraction_max_workers", 2)
    monkeypatch.setattr(settings, "job_extraction_slot_cooldown_seconds", 30)
    reset_extraction_runtime()
    job = _job(isolated_session, public_id="fallback-ollama")
    providers: list[str] = []

    def fake_generate(self, prompt, system_prompt=None, json_schema=None):
        del prompt, system_prompt, json_schema
        providers.append(self.provider)
        if self.provider == "gemini":
            raise LLMRateLimitError("Gemini provider request failed.")
        return json.dumps(_payload())

    monkeypatch.setattr("backend.services.llm_client.LLMClient.generate", fake_generate)
    result = extract_job_intelligence_batch(
        isolated_session, [job.public_id], force=True
    )[0]
    assert isinstance(result, JobIntelligence)
    assert "ollama" in providers
    assert providers[0] == "gemini"


def test_invalid_gemini_key_is_disabled_for_the_run(isolated_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "gemini_api_key", "invalid-key")
    monkeypatch.setattr(settings, "gemini_api_keys", "valid-key")
    monkeypatch.setattr(settings, "llm_provider_order", "gemini")
    monkeypatch.setattr(settings, "job_extraction_max_workers", 2)
    reset_extraction_runtime()
    jobs = _jobs(isolated_session, 2, prefix="auth")
    counts = {"invalid-key": 0, "valid-key": 0}

    def fake_generate(self, prompt, system_prompt=None, json_schema=None):
        del prompt, system_prompt, json_schema
        key = self._api_key() or ""
        counts[key] = counts.get(key, 0) + 1
        if key == "invalid-key":
            raise LLMAuthError("Gemini provider request failed.")
        return json.dumps(_payload())

    monkeypatch.setattr("backend.services.llm_client.LLMClient.generate", fake_generate)
    results = extract_job_intelligence_batch(
        isolated_session,
        [job.public_id for job in jobs],
        force=True,
    )
    assert all(isinstance(item, JobIntelligence) for item in results)
    assert counts["invalid-key"] == 1
    assert counts["valid-key"] >= 1


def test_zero_gemini_keys_use_configured_fallback(isolated_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "gemini_api_keys", "")
    monkeypatch.setattr(settings, "llm_provider_order", "gemini,ollama")
    monkeypatch.setattr(settings, "job_extraction_max_workers", 1)
    reset_extraction_runtime()
    job = _job(isolated_session, public_id="zero-keys")
    providers: list[str] = []

    def fake_generate(self, prompt, system_prompt=None, json_schema=None):
        del prompt, system_prompt, json_schema
        providers.append(self.provider)
        if self.provider == "gemini":
            raise AssertionError("gemini must not be called without keys")
        return json.dumps(_payload())

    monkeypatch.setattr("backend.services.llm_client.LLMClient.generate", fake_generate)
    result = extract_job_intelligence_batch(
        isolated_session, [job.public_id], force=True
    )[0]
    assert isinstance(result, JobIntelligence)
    assert providers == ["ollama"]


def test_stale_fingerprint_is_not_persisted(isolated_session, monkeypatch) -> None:
    from sqlalchemy.orm import sessionmaker

    monkeypatch.setattr(settings, "job_extraction_max_workers", 1)
    job = _job(isolated_session, public_id="stale-fp")
    SessionLocal = sessionmaker(bind=isolated_session.get_bind(), autocommit=False, autoflush=False)

    def generate(prompt: str, system: str | None) -> str:
        del prompt, system
        with SessionLocal() as other:
            row = other.query(JobRecord).filter_by(public_id="stale-fp").one()
            row.description = row.description + "\nChanged during extraction. GPA 3.9 required."
            other.commit()
        return json.dumps(_payload())

    result = extract_job_intelligence_batch(
        isolated_session, [job.public_id], generate_fn=generate, force=True
    )[0]
    assert result is None
    isolated_session.expire_all()
    assert isolated_session.query(JobIntelligenceRecord).count() == 0


def test_incomplete_profile_starts_zero_extraction_workers(isolated_client, monkeypatch) -> None:
    client, _ = isolated_client
    worker = Mock(side_effect=AssertionError("workers must not start"))
    monkeypatch.setattr(
        "backend.services.extraction_pool.run_extraction_batch",
        worker,
    )
    response = client.post("/api/scout-jobs")
    assert response.status_code == 409
    assert worker.call_count == 0
    assert peak_workers_used() == 0


def test_find_jobs_auto_score_does_not_call_parallel_extraction(isolated_session, monkeypatch) -> None:
    from backend.services.verified_fit_service import verify_top_ranked_jobs

    batch = Mock(side_effect=AssertionError("Find Jobs must stay deterministic"))
    monkeypatch.setattr(
        "backend.services.job_intelligence_service.extract_job_intelligence_batch",
        batch,
    )
    verify_top_ranked_jobs(isolated_session, 1, [], [])
    assert batch.call_count == 0


def test_concurrent_batches_do_not_cross_contaminate(tmp_path, monkeypatch) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.db.database import Base

    monkeypatch.setattr(settings, "job_extraction_max_workers", 2)
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'parallel.sqlite').as_posix()}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    with SessionLocal() as seed:
        jobs_a = _jobs(seed, 2, prefix="user-a")
        jobs_b = _jobs(seed, 2, prefix="user-b")
        ids_a = [job.public_id for job in jobs_a]
        ids_b = [job.public_id for job in jobs_b]

    def gen_a(prompt: str, system: str | None) -> str:
        del system
        assert "user-b" not in prompt
        time.sleep(0.05)
        return json.dumps(_payload(required_skills=["Python"], preferred_skills=[]))

    def gen_b(prompt: str, system: str | None) -> str:
        del system
        assert "user-a" not in prompt
        time.sleep(0.05)
        return json.dumps(
            _payload(required_skills=["Python"], preferred_skills=["PostgreSQL"])
        )

    errors: list[BaseException] = []

    def run(ids, generate_fn) -> None:
        try:
            with SessionLocal() as db:
                extract_job_intelligence_batch(
                    db, ids, generate_fn=generate_fn, force=True
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    t1 = threading.Thread(target=run, args=(ids_a, gen_a))
    t2 = threading.Thread(target=run, args=(ids_b, gen_b))
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)
    assert errors == []
    with SessionLocal() as db:
        stored = {
            row.job.public_id: list(row.preferred_skills or [])
            for row in db.query(JobIntelligenceRecord).all()
        }
    assert stored[ids_a[0]] == []
    assert stored[ids_b[0]] == ["PostgreSQL"]
    engine.dispose()


def test_logs_do_not_include_keys_prompts_or_postings(
    isolated_session, monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    secret = "GEMINI_LIVE_SECRET_VALUE_DO_NOT_LOG"
    monkeypatch.setattr(settings, "gemini_api_key", secret)
    monkeypatch.setattr(settings, "job_extraction_max_workers", 1)
    job = _job(isolated_session, public_id="log-safe")
    with caplog.at_level("INFO"):
        extract_job_intelligence_batch(
            isolated_session,
            [job.public_id],
            generate_fn=_sleeping_generator(0.0),
            force=True,
        )
    blob = caplog.text
    assert secret not in blob
    assert job.description not in blob
    assert "Extract factual job requirements" not in blob
    assert "batch_size=" in blob
