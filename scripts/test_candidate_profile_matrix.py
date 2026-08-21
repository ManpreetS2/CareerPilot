#!/usr/bin/env python3
"""Privacy-safe Candidate Profile synthetic/real-layout matrix runner.

Uses a temporary SQLite database. Never prints names, emails, phones,
companies, project names, resume text, or model output.

Usage:
  python scripts/generate_synthetic_resume_matrix.py
  python scripts/test_candidate_profile_matrix.py --synthetic
  python scripts/test_candidate_profile_matrix.py --synthetic --live
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.synthetic_resume_matrix import (
    GENERATED_DIR,
    LAYOUT_BY_ID,
    CAND_ID_RE,
    forbidden_output_tokens,
    generate_all,
    layout_ids,
    manifest_for,
    validate_parse_response,
)


def _print_safe(*parts: object) -> None:
    line = " ".join(str(part) for part in parts)
    lowered = line.lower()
    for token in forbidden_output_tokens():
        if token and token.lower() in lowered:
            line = "output_redacted=privacy"
            break
    print(line)


def _candidate_count(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='candidates'"
        ).fetchone()
        if not row or row[0] == 0:
            return 0
        return int(conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0])
    finally:
        conn.close()


def _post_parse(base_url: str, pdf_path: Path) -> tuple[int, dict]:
    boundary = "----careerpilotmatrix"
    data = pdf_path.read_bytes()
    filename = pdf_path.name
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/parse-resume",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            return resp.status, payload
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            payload = {"detail": type(exc).__name__}
        return exc.code, payload


def _wait_health(base_url: str, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url.rstrip('/')}/health", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            time.sleep(0.25)
    return False


def _start_backend(db_path: Path, port: int):
    import subprocess

    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _run_inprocess(pdf_path: Path, layout_id: str, generate_fn) -> tuple[int, dict, Path]:
    """Deterministic path: TestClient + isolated DB + injected structured output."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from backend.db.database import Base, get_db
    from backend.main import app
    from fastapi.testclient import TestClient

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def _override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    from contextlib import asynccontextmanager
    from collections.abc import AsyncIterator
    from fastapi import FastAPI
    from unittest.mock import patch

    @asynccontextmanager
    async def _noop(_app: FastAPI) -> AsyncIterator[None]:
        yield

    previous = app.router.lifespan_context
    app.dependency_overrides[get_db] = _override_get_db
    app.router.lifespan_context = _noop
    tmp = Path(tempfile.mkdtemp()) / "matrix.db"
    try:
        with patch(
            "backend.services.candidate_profile_agent.extract_candidate_profile_with_llm",
            side_effect=lambda *args, **kwargs: generate_fn(*args, **kwargs),
        ):
            with TestClient(app) as client:
                response = client.post(
                    "/api/parse-resume",
                    files={"file": (pdf_path.name, pdf_path.read_bytes(), "application/pdf")},
                )
                payload = response.json()
                status = response.status_code
        # Persist evidence into a temp file DB copy of counts via isolated session.
        with SessionLocal() as db:
            from backend.db.models import Candidate

            count = db.query(Candidate).count()
            tmp.write_text(str(count), encoding="utf-8")
        return status, payload, tmp
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.router.lifespan_context = previous
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Privacy-safe resume layout matrix")
    parser.add_argument("pdfs", nargs="*", type=Path)
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--live", action="store_true", help="Call a live backend/provider")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if args.synthetic or not args.pdfs:
        generate_all(GENERATED_DIR)
        pdfs = [GENERATED_DIR / f"{layout_id}.pdf" for layout_id in layout_ids()]
        layout_map = {path.name: path.stem for path in pdfs}
    else:
        pdfs = args.pdfs
        layout_map = {path.name: path.stem for path in pdfs}

    passed = 0
    failed = 0
    proc = None
    db_file = None
    base_url = f"http://127.0.0.1:{args.port}"

    try:
        if args.live:
            db_file = Path(tempfile.mkstemp(suffix=".db")[1])
            proc = _start_backend(db_file, args.port)
            if not _wait_health(base_url):
                _print_safe("backend_start=failed")
                return 2

        for pdf_path in pdfs:
            layout_id = layout_map.get(pdf_path.name, pdf_path.stem)
            if layout_id not in LAYOUT_BY_ID:
                _print_safe(f"layout={layout_id} result=fail reason=unknown_layout")
                failed += 1
                continue
            if not pdf_path.exists():
                _print_safe(f"layout={layout_id} result=fail reason=missing_pdf")
                failed += 1
                continue

            before = _candidate_count(db_file) if db_file else 0
            if args.live:
                status, payload = _post_parse(base_url, pdf_path)
            else:
                from tests.synthetic_resume_matrix import expected_llm_payload

                status, payload, _meta = _run_inprocess(
                    pdf_path,
                    layout_id,
                    lambda *_a, **_k: expected_llm_payload(layout_id),
                )

            ok = status == 200
            failures: list[str] = []
            if ok:
                failures = validate_parse_response(payload, manifest_for(layout_id))
            else:
                failures = ["http_error"]
                after = _candidate_count(db_file) if db_file else before
                if after != before:
                    failures.append("failed_parse_created_row")

            note = str((payload or {}).get("note") or "")
            method = "pdfplumber" if "pdfplumber" in note else ("ocr" if "ocr" in note else "unknown")
            candidate = (payload or {}).get("candidate") or {}
            stored = candidate.get("id") if ok else None
            id_ok = bool(isinstance(stored, str) and CAND_ID_RE.match(stored))
            counts = {
                "skills": len(candidate.get("skills") or []),
                "projects": len(candidate.get("projects") or []),
                "experiences": len(candidate.get("experience") or []),
                "education": len(candidate.get("education") or []),
                "certifications": len(candidate.get("certifications") or []),
            }
            result = "pass" if ok and not failures else "fail"
            if result == "pass":
                passed += 1
            else:
                failed += 1
            _print_safe(
                f"layout={layout_id} http={status} result={result} "
                f"extraction_method={method} stored_id={'cand-###' if id_ok else 'missing'} "
                f"skills={counts['skills']} projects={counts['projects']} "
                f"experiences={counts['experiences']} education={counts['education']} "
                f"certifications={counts['certifications']} "
                f"failures={len(failures)} preferences_null={payload.get('preferences') is None}"
            )

        _print_safe(f"synthetic_layouts={len(pdfs)} passed={passed} failed={failed}")
        return 0 if failed == 0 else 1
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                proc.kill()
        if db_file is not None:
            db_file.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
