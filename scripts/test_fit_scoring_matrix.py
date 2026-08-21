#!/usr/bin/env python3
"""Deterministic, privacy-safe Fit & Gap API/persistence matrix.

The runner creates only temporary SQLite databases, blocks network sockets,
and prints identifiers/counts/results rather than candidate or job content.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.api.routes.scoring import router as scoring_router
from backend.db.database import Base, get_db
from backend.db.models import (
    Candidate,
    JobIntelligenceRecord,
    JobRecord,
    MatchScoreRecord,
    TargetPreference,
)

FIXTURE_DIR = ROOT / "tests" / "fixtures" / "fit_scoring"
PRODUCTION_DATABASE = (ROOT / "data" / "careerpilot.db").resolve()
COMPONENT_RESPONSE_FIELDS = {
    "skill": "skill_score",
    "experience": "experience_score",
    "education": "education_score",
    "location": "location_score",
    "preference": "preference_score",
}


@dataclass(frozen=True)
class MatrixResult:
    scenario_id: str
    status: int
    score: float | None
    recommendation: str | None
    row_count: int
    passed: bool
    failures: tuple[str, ...]


def assert_safe_database_path(database_path: Path) -> Path:
    resolved = database_path.expanduser().resolve()
    if resolved == PRODUCTION_DATABASE:
        raise ValueError("Refusing to run the fit scoring matrix against the production database.")
    if resolved.suffix not in {".db", ".sqlite", ".sqlite3"}:
        raise ValueError("Matrix database must be a dedicated SQLite file.")
    return resolved


def load_manifests() -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"{path.name}: manifest must be a JSON object")
        manifests.append(payload)
    scenario_ids = [str(item.get("scenario_id") or "") for item in manifests]
    if not scenario_ids or any(not item for item in scenario_ids):
        raise ValueError("Every matrix manifest must have a stable scenario_id.")
    if len(scenario_ids) != len(set(scenario_ids)):
        raise ValueError("Matrix scenario_id values must be unique.")
    return manifests


def _seed(session: Session, manifest: dict[str, Any]) -> tuple[JobRecord | None, Candidate | None]:
    candidate_data = manifest.get("candidate")
    candidate = Candidate(**candidate_data) if isinstance(candidate_data, dict) else None
    if candidate is not None:
        session.add(candidate)
        session.flush()

    job_data = manifest.get("job")
    job = JobRecord(**job_data) if isinstance(job_data, dict) else None
    if job is not None:
        session.add(job)
        session.flush()

    preference_data = manifest.get("preferences")
    if isinstance(preference_data, dict):
        session.add(
            TargetPreference(
                candidate_id=candidate.id if candidate is not None else None,
                **preference_data,
            )
        )

    intelligence_data = manifest.get("intelligence")
    if isinstance(intelligence_data, dict):
        if job is None:
            raise ValueError("intelligence requires a job")
        session.add(JobIntelligenceRecord(job_id=job.id, **intelligence_data))

    session.commit()
    return job, candidate


def _intelligence_snapshot(session: Session, job: JobRecord | None) -> dict[str, Any] | None:
    if job is None:
        return None
    record = (
        session.query(JobIntelligenceRecord)
        .filter(JobIntelligenceRecord.job_id == job.id)
        .first()
    )
    if record is None:
        return None
    return {
        "required_skills": list(record.required_skills or []),
        "preferred_skills": list(record.preferred_skills or []),
        "years_experience": record.years_experience,
        "education_requirements": list(record.education_requirements or []),
        "tech_stack": list(record.tech_stack or []),
        "seniority": record.seniority,
        "responsibilities": list(record.responsibilities or []),
        "likely_interview_focus": list(record.likely_interview_focus or []),
    }


def _persisted_matches_response(
    row: MatchScoreRecord,
    payload: dict[str, Any],
    public_job_id: str,
) -> bool:
    return {
        "job_id": public_job_id,
        "overall_score": row.overall_score,
        "skill_score": row.skill_score,
        "experience_score": row.experience_score,
        "education_score": row.education_score,
        "location_score": row.location_score,
        "preference_score": row.preference_score,
        "matched_skills": list(row.matched_skills or []),
        "partial_matches": list(row.partial_matches or []),
        "missing_skills": list(row.missing_skills or []),
        "recommendation": row.recommendation,
        "rationale": row.rationale,
    } == payload


@contextmanager
def _network_blocked() -> Generator[None, None, None]:
    with patch.object(
        socket.socket,
        "connect",
        side_effect=AssertionError("network/provider calls are forbidden in the scoring matrix"),
    ):
        yield


def run_scenario(manifest: dict[str, Any], database_path: Path) -> MatrixResult:
    database_path = assert_safe_database_path(database_path)
    database_path.unlink(missing_ok=True)
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)
    failures: list[str] = []
    scenario_id = str(manifest["scenario_id"])
    expected = manifest["expected"]
    response_payload: dict[str, Any] = {}
    response_status = 0

    try:
        with SessionLocal() as session:
            job, _candidate = _seed(session, manifest)
            intelligence_before = _intelligence_snapshot(session, job)

        fail_commit = bool(manifest.get("commit_failure"))

        def _override_get_db() -> Generator[Session, None, None]:
            db = SessionLocal()
            try:
                if fail_commit:
                    with patch.object(
                        db,
                        "commit",
                        side_effect=RuntimeError("synthetic database failure"),
                    ):
                        yield db
                else:
                    yield db
            finally:
                db.close()

        app = FastAPI()
        app.include_router(scoring_router)
        app.dependency_overrides[get_db] = _override_get_db
        endpoint_job_id = str(
            manifest.get("request_job_id")
            or (manifest.get("job") or {}).get("public_id")
            or "missing-job"
        )
        repeats = int(manifest.get("request_count", 1))
        first_success_payload: dict[str, Any] | None = None

        with TestClient(app) as client:
            for request_index in range(repeats):
                if request_index == 1 and manifest.get("equivalent_intelligence"):
                    with SessionLocal() as session:
                        record = session.query(JobIntelligenceRecord).one()
                        for key, value in manifest["equivalent_intelligence"].items():
                            setattr(record, key, value)
                        session.commit()
                with _network_blocked():
                    response = client.post(f"/api/jobs/{endpoint_job_id}/score")
                response_status = response.status_code
                response_payload = response.json()
                if response_status == 200:
                    if first_success_payload is None:
                        first_success_payload = response_payload
                    elif manifest.get("equivalent_intelligence"):
                        comparable_fields = [
                            "overall_score",
                            "skill_score",
                            "experience_score",
                            "education_score",
                            "location_score",
                            "preference_score",
                            "recommendation",
                        ]
                        if any(
                            response_payload[field] != first_success_payload[field]
                            for field in comparable_fields
                        ):
                            failures.append("equivalent_order_changed_score")

        if response_status != int(expected["http_status"]):
            failures.append("http_status")

        if response_status == 200:
            expected_components = expected["component_scores"]
            for component, response_field in COMPONENT_RESPONSE_FIELDS.items():
                if response_payload.get(response_field) != expected_components[component]:
                    failures.append(f"component_{component}")
            if response_payload.get("overall_score") != expected["overall_score"]:
                failures.append("overall_score")
            if response_payload.get("recommendation") != expected["recommendation"]:
                failures.append("recommendation")
            for response_field, expected_key in (
                ("matched_skills", "matched"),
                ("partial_matches", "partial"),
                ("missing_skills", "missing"),
            ):
                if response_payload.get(response_field) != expected[expected_key]:
                    failures.append(expected_key)
            available = sorted(
                component
                for component, score in expected_components.items()
                if score is not None
            )
            null_components = sorted(
                component
                for component, score in expected_components.items()
                if score is None
            )
            if available != sorted(expected["available_components"]):
                failures.append("available_components_manifest")
            if null_components != sorted(expected["null_components"]):
                failures.append("null_components_manifest")

        with SessionLocal() as session:
            rows = session.query(MatchScoreRecord).all()
            row_count = len(rows)
            if row_count != int(expected["row_count"]):
                failures.append("row_count")
            if row_count != len({(row.job_id, row.candidate_id) for row in rows}):
                failures.append("duplicate_score_rows")
            if response_status == 200 and row_count == 1:
                public_job_id = str((manifest.get("job") or {}).get("public_id"))
                if not _persisted_matches_response(rows[0], response_payload, public_job_id):
                    failures.append("persistence_response_mismatch")
            intelligence_after = _intelligence_snapshot(session, job)
            expected_intelligence_after = intelligence_before
            if intelligence_before is not None and manifest.get("equivalent_intelligence"):
                expected_intelligence_after = {
                    **intelligence_before,
                    **manifest["equivalent_intelligence"],
                }
            if intelligence_after != expected_intelligence_after:
                failures.append("job_intelligence_mutated")

        expected_persistence = expected["persistence"]
        if expected_persistence == "none" and row_count != 0:
            failures.append("unexpected_persistence")
        if expected_persistence in {"insert", "upsert"} and row_count != 1:
            failures.append("missing_persistence")

        return MatrixResult(
            scenario_id=scenario_id,
            status=response_status,
            score=response_payload.get("overall_score") if response_status == 200 else None,
            recommendation=(
                response_payload.get("recommendation") if response_status == 200 else None
            ),
            row_count=row_count,
            passed=not failures,
            failures=tuple(sorted(set(failures))),
        )
    finally:
        engine.dispose()
        database_path.unlink(missing_ok=True)


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_for_url(url: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:  # noqa: BLE001 - readiness retry
            time.sleep(0.2)
    raise RuntimeError("Local test service did not become ready.")


def _stop_process(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _seed_browser_database(database_path: Path, backend_port: int) -> sessionmaker:
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)
    with SessionLocal() as session:
        candidate = Candidate(
            name="Synthetic Browser Candidate",
            skills=["Python"],
            projects=[],
            experience=[],
            education=[],
            certifications=[],
            strengths=[],
            evidence_links=[],
        )
        session.add(candidate)
        session.flush()
        session.add(
            TargetPreference(
                candidate_id=candidate.id,
                target_roles=[],
                preferred_locations=[],
                remote_preference=None,
                salary_min=None,
                work_authorization=None,
                sponsorship_required=None,
                constraints=[],
            )
        )
        success_job = JobRecord(
            public_id="browser-fit-success",
            title="Synthetic Backend Engineer",
            company="Fictional Browser Works",
            location=None,
            salary=None,
            url=f"http://127.0.0.1:{backend_port}/health",
            description="Requirements:\nPython",
            source="matrix",
            status="verified",
            verification_notes="Synthetic posting passed verification.",
            verified_at=datetime.now(timezone.utc),
        )
        no_requirements_job = JobRecord(
            public_id="browser-fit-no-requirements",
            title="Synthetic Team Contributor",
            company="Fictional Browser Works",
            location=None,
            salary=None,
            url=f"http://127.0.0.1:{backend_port}/health",
            description="Join a collaborative fictional team.",
            source="matrix",
            status="verified",
            verification_notes="Synthetic posting passed verification.",
            verified_at=datetime.now(timezone.utc),
        )
        session.add_all([success_job, no_requirements_job])
        session.flush()
        session.add(
            JobIntelligenceRecord(
                job_id=success_job.id,
                required_skills=["Python"],
                preferred_skills=[],
                years_experience=None,
                education_requirements=[],
                tech_stack=[],
                seniority=None,
                responsibilities=[],
                likely_interview_focus=[],
            )
        )
        session.commit()
    setattr(SessionLocal, "_matrix_engine", engine)
    return SessionLocal


def run_browser_e2e() -> dict[str, int]:
    """Run Chromium against real Uvicorn/Vite processes and temporary SQLite."""
    try:
        from playwright.sync_api import expect, sync_playwright
    except ImportError as exc:  # pragma: no cover - exact tooling blocker
        raise RuntimeError("Python Playwright is unavailable.") from exc

    with tempfile.TemporaryDirectory(prefix="careerpilot-fit-browser-") as temp_dir:
        database_path = assert_safe_database_path(Path(temp_dir) / "browser.sqlite")
        backend_port = _free_port()
        frontend_port = _free_port()
        SessionLocal = _seed_browser_database(database_path, backend_port)
        backend_env = os.environ.copy()
        backend_env["DATABASE_URL"] = f"sqlite:///{database_path}"
        frontend_env = os.environ.copy()
        frontend_env["VITE_API_BASE_URL"] = f"http://127.0.0.1:{backend_port}"
        backend = subprocess.Popen(
            [
                str(ROOT / ".venv" / "bin" / "python"),
                "-m",
                "uvicorn",
                "backend.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(backend_port),
            ],
            cwd=ROOT,
            env=backend_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        frontend = subprocess.Popen(
            [
                "npm",
                "run",
                "dev",
                "--",
                "--host",
                "127.0.0.1",
                "--port",
                str(frontend_port),
            ],
            cwd=ROOT / "frontend",
            env=frontend_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        score_requests: list[str] = []
        try:
            _wait_for_url(f"http://127.0.0.1:{backend_port}/health")
            _wait_for_url(f"http://127.0.0.1:{frontend_port}/")
            with sync_playwright() as playwright:
                executable = (
                    Path("/usr/bin/google-chrome")
                    if Path("/usr/bin/google-chrome").exists()
                    else None
                )
                browser = playwright.chromium.launch(
                    headless=True,
                    executable_path=str(executable) if executable else None,
                    args=["--disable-web-security"],
                )
                page = browser.new_page()
                page.on(
                    "request",
                    lambda request: (
                        score_requests.append(request.url)
                        if request.method == "POST" and request.url.endswith("/score")
                        else None
                    ),
                )
                base_url = f"http://127.0.0.1:{frontend_port}"
                success_url = f"{base_url}/jobs/browser-fit-success"

                page.goto(success_url)
                expect(page.get_by_role("heading", name="Synthetic Backend Engineer")).to_be_visible()
                expect(page.get_by_role("heading", name="Verification")).to_be_visible()
                expect(page.get_by_text("Synthetic posting passed verification.")).to_be_visible()
                expect(page.get_by_role("heading", name="Job overview")).to_be_visible()
                expect(page.get_by_text("Analysis available after processing")).to_be_visible()
                if score_requests:
                    raise AssertionError("Loading a job triggered scoring.")

                def _delay_score(route: Any) -> None:
                    time.sleep(0.3)
                    route.continue_()

                page.route("**/api/jobs/*/score", _delay_score)
                calculate = page.get_by_role("button", name="Calculate fit")
                calculate.evaluate(
                    """(button) => {
                      window.__fitButtonWasDisabled = button.disabled;
                      new MutationObserver(() => {
                        if (button.disabled) window.__fitButtonWasDisabled = true;
                      }).observe(button, { attributes: true, attributeFilter: ["disabled"] });
                    }"""
                )
                calculate.evaluate("(button) => { button.click(); button.click(); }")
                expect(page.get_by_text("Overall:")).to_be_visible()
                if not page.evaluate("window.__fitButtonWasDisabled"):
                    raise AssertionError("Calculate fit was not disabled while scoring.")
                expect(page.get_by_text("100%", exact=True)).to_be_visible()
                expect(page.get_by_text("Skills:")).to_contain_text("100")
                expect(page.get_by_text("Experience: unavailable", exact=False)).to_be_visible()
                if len(score_requests) != 1:
                    raise AssertionError("Pending double-click created concurrent score requests.")
                with SessionLocal() as session:
                    if session.query(MatchScoreRecord).count() != 1:
                        raise AssertionError("First calculation did not persist exactly one row.")

                page.get_by_role("button", name="Calculate fit").click()
                expect(page.get_by_text("Overall:")).to_be_visible()
                if len(score_requests) != 2:
                    raise AssertionError("Completed recalculation did not issue exactly one request.")
                with SessionLocal() as session:
                    if session.query(MatchScoreRecord).count() != 1:
                        raise AssertionError("Recalculation created a duplicate row.")

                page.reload()
                expect(page.get_by_role("button", name="Calculate fit")).to_be_visible()
                if len(score_requests) != 2:
                    raise AssertionError("Refresh triggered scoring.")

                page.route(
                    "**/api/jobs/browser-fit-success/verify",
                    lambda route: route.fulfill(
                        status=500,
                        content_type="application/json",
                        body='{"detail":"Unable to verify job."}',
                    ),
                )
                page.get_by_role("button", name="Re-verify").click()
                expect(page.get_by_role("alert")).to_contain_text("Unable to verify job.")
                expect(page.get_by_role("heading", name="Fit score")).to_be_visible()
                expect(page.get_by_role("heading", name="Job overview")).to_be_visible()
                page.unroute("**/api/jobs/browser-fit-success/verify")

                page.unroute("**/api/jobs/*/score", _delay_score)
                page.route(
                    "**/api/jobs/*/score",
                    lambda route: route.fulfill(
                        status=500,
                        content_type="application/json",
                        body='{"detail":"Unable to calculate fit score."}',
                    ),
                )
                page.get_by_role("button", name="Calculate fit").click()
                expect(page.get_by_role("alert")).to_contain_text("Unable to calculate fit score.")
                expect(page.get_by_text("Overall:")).to_have_count(0)
                page.unroute("**/api/jobs/*/score")
                page.route(
                    "**/api/jobs/*/score",
                    lambda route: route.fulfill(
                        status=404,
                        content_type="application/json",
                        body='{"detail":"Job not found."}',
                    ),
                )
                page.get_by_role("button", name="Calculate fit").click()
                expect(page.get_by_role("alert")).to_contain_text("Job not found.")
                expect(page.get_by_text("Overall:")).to_have_count(0)
                page.unroute("**/api/jobs/*/score")

                with SessionLocal() as session:
                    session.query(MatchScoreRecord).delete()
                    session.query(TargetPreference).delete()
                    session.query(Candidate).delete()
                    session.commit()
                page.goto(success_url)
                page.get_by_role("button", name="Calculate fit").click()
                expect(page.get_by_role("alert")).to_contain_text("Build a candidate profile")
                expect(page.get_by_role("link", name="Build Profile")).to_have_attribute(
                    "href", "/profile"
                )

                with SessionLocal() as session:
                    session.add(
                        Candidate(
                            name="Synthetic Browser Candidate Two",
                            skills=["Python"],
                            projects=[],
                            experience=[],
                            education=[],
                            certifications=[],
                            strengths=[],
                            evidence_links=[],
                        )
                    )
                    session.commit()
                page.goto(f"{base_url}/jobs/browser-fit-no-requirements")
                expect(page.get_by_text("Overall:")).to_have_count(0)
                page.get_by_role("button", name="Calculate fit").click()
                expect(page.get_by_role("alert")).to_contain_text(
                    "Job requirements are not available"
                )
                expect(page.get_by_role("link", name="Build Profile")).to_have_count(0)

                score_count_before_verify = len(score_requests)
                page.goto(success_url)
                verify_button = page.get_by_role("button", name="Re-verify")
                expect(verify_button).to_be_visible()
                verify_button.click()
                expect(page.get_by_text("Current status: flagged", exact=False)).to_be_visible()
                expect(page.get_by_text("Description is missing or too short", exact=False)).to_be_visible()
                if len(score_requests) != score_count_before_verify:
                    raise AssertionError("Verification triggered fit scoring.")
                browser.close()

            with SessionLocal() as session:
                final_rows = session.query(MatchScoreRecord).count()
            return {
                "score_requests": len(score_requests),
                "final_rows": final_rows,
                "browser_checks": 15,
            }
        finally:
            _stop_process(frontend)
            _stop_process(backend)
            engine = getattr(SessionLocal, "_matrix_engine")
            engine.dispose()
            database_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Privacy-safe Fit & Gap scoring matrix")
    parser.add_argument(
        "--browser-e2e",
        action="store_true",
        help="Also run Chromium against temporary Uvicorn/Vite services.",
    )
    args = parser.parse_args(argv)
    manifests = load_manifests()
    passed = 0
    failed = 0
    previous_disable = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        with tempfile.TemporaryDirectory(prefix="careerpilot-fit-matrix-") as temp_dir:
            for index, manifest in enumerate(manifests):
                result = run_scenario(
                    manifest,
                    Path(temp_dir) / f"scenario-{index:03d}.sqlite",
                )
                outcome = "pass" if result.passed else "fail"
                if result.passed:
                    passed += 1
                else:
                    failed += 1
                score = "na" if result.score is None else f"{result.score:.1f}"
                recommendation = result.recommendation or "na"
                print(
                    f"scenario={result.scenario_id} http={result.status} score={score} "
                    f"recommendation={recommendation} rows={result.row_count} result={outcome}"
                )
        print(f"scenarios={len(manifests)} passed={passed} failed={failed}")
        if failed:
            return 1
        if args.browser_e2e:
            browser_result = run_browser_e2e()
            print(
                f"browser_checks={browser_result['browser_checks']} "
                f"score_requests={browser_result['score_requests']} "
                f"rows={browser_result['final_rows']} result=pass"
            )
        return 0
    finally:
        logging.disable(previous_disable)


if __name__ == "__main__":
    raise SystemExit(main())
