#!/usr/bin/env python3
"""Opt-in live Ollama/Gemini checks against a temporary SQLite database.

Never writes data/careerpilot.db. Not run in CI.
Prints only pass/fail stage names — never endpoints, prompts, or secrets.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core.config import settings
from backend.db.database import Base
from backend.services.application_materials_agent import generate_grounded_application_materials
from backend.services.candidate_profile_agent import extract_candidate_profile_with_llm
from backend.services.job_intelligence_service import extract_job_intelligence
from backend.services.llm_client import LLMClient, LLMProviderError, get_llm_client
from tests.mvp_helpers import TEST_USER_ID, seed_materials_prerequisites
from tests.pdf_fixtures import SAMPLE_RESUME_TEXT
from tests.test_job_intelligence import _job


def _temp_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    return engine, session


def stage(name: str, ok: bool) -> None:
    print(f"live_check stage={name} result={'pass' if ok else 'fail'}")


def main() -> int:
    production = ROOT / "data" / "careerpilot.db"
    existed = production.exists()
    before = production.stat().st_mtime if existed else None
    gemini_calls = {"n": 0}

    def _gemini_blocked(self, *_args, **_kwargs):
        gemini_calls["n"] += 1
        raise AssertionError("Gemini must not be called on the Ollama success path")

    original_url = settings.ollama_base_url
    original_order = settings.llm_provider_order
    failed = False
    try:
        settings.llm_provider_order = "ollama"
        with patch.object(LLMClient, "_generate_gemini", _gemini_blocked):
            client = get_llm_client("ollama")
            schema = {
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
            }
            text = client.generate("Reply with ok true.", system_prompt="Return JSON.", json_schema=schema)
            parsed = json.loads(text)
            ok = parsed.get("ok") is True and gemini_calls["n"] == 0
            stage("ollama_success_skips_gemini", ok)
            failed = failed or not ok

            raw = extract_candidate_profile_with_llm(SAMPLE_RESUME_TEXT, provider="ollama")
            ok = isinstance(raw, dict) and bool(raw.get("name"))
            stage("structured_candidate_extraction", ok)
            failed = failed or not ok

            engine, session = _temp_session()
            try:
                job = _job(session)
                stored = extract_job_intelligence(session, job.public_id)
                ok = bool(stored.required_skills or stored.tech_stack or stored.responsibilities)
                stage("structured_job_intelligence", ok)
                failed = failed or not ok

                try:
                    materials_job, _candidate = seed_materials_prerequisites(session)
                    draft = generate_grounded_application_materials(
                        session, materials_job.public_id, TEST_USER_ID
                    )
                    ok = bool(draft.tailored_bullets and draft.cover_letter_draft)
                    stage("structured_application_materials", ok)
                    failed = failed or not ok
                except Exception as exc:
                    stage(
                        "structured_application_materials_" + type(exc).__name__,
                        False,
                    )
                    failed = True
            finally:
                session.close()
                engine.dispose()
    except Exception as exc:
        stage("ollama_structured_" + type(exc).__name__, False)
        failed = True
    finally:
        settings.ollama_base_url = original_url
        settings.llm_provider_order = original_order

    try:
        settings.llm_provider_order = "ollama,gemini"
        settings.ollama_base_url = "http://127.0.0.1:1"
        client = LLMClient(provider="ollama")
        try:
            client.generate("Reply with ok true.", system_prompt="Return JSON.")
            stage("unreachable_ollama_should_fail", False)
            failed = True
        except LLMProviderError:
            stage("unreachable_ollama_should_fail", True)
        except Exception as exc:
            stage("unreachable_ollama_should_fail_" + type(exc).__name__, False)
            failed = True
        if not (settings.gemini_api_key or "").strip():
            stage("gemini_fallback_unverified_no_key", True)
        else:
            gemini = LLMClient(provider="gemini")
            text = gemini.generate("Reply with the single word ok.")
            ok = bool(text and text.strip())
            stage("gemini_fallback_after_unreachable_ollama", ok)
            failed = failed or not ok
    except Exception as exc:
        stage("gemini_fallback_" + type(exc).__name__, False)
        failed = True
    finally:
        settings.ollama_base_url = original_url
        settings.llm_provider_order = original_order

    if existed and production.exists() and production.stat().st_mtime != before:
        stage("production_db_untouched", False)
        failed = True
    elif not existed and production.exists():
        stage("production_db_untouched", False)
        failed = True
    else:
        stage("production_db_untouched", True)

    print(f"live_check result={'fail' if failed else 'pass'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
