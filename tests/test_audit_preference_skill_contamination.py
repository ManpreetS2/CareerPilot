"""Isolated-DB tests for preference→Candidate.skills contamination audit."""

from __future__ import annotations

import json
import subprocess

import pytest
import sys
from pathlib import Path

from backend.db.models import Candidate, TargetPreference
from backend.services.analysis_service import score_job
from scripts.audit_preference_skill_contamination import audit_database
from tests.mvp_helpers import insert_candidate, insert_job

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_preference_skill_contamination.py"


def test_dry_run_flags_preference_only_and_keeps_grounded_overlap(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        candidate = insert_candidate(db, user_id=client.test_user_id)
        # Simulate pre-#140 merge: preference skill landed on Candidate.skills.
        candidate.skills = ["Python", "Kubernetes", "Terraform"]
        candidate.experience = [{"company": "Acme", "bullets": ["Built APIs in Python"]}]
        db.add(
            TargetPreference(
                user_id=client.test_user_id,
                candidate_id=candidate.id,
                target_roles=["Software Engineer"],
                skill_preferences=["Kubernetes", "Python"],
            )
        )
        db.commit()

        report = audit_database(db, apply=False)

    suspect_names = {row.skill for row in report.preference_only_suspects}
    ambiguous_names = {row.skill for row in report.ambiguous_overlaps}
    assert "Kubernetes" in suspect_names
    assert "Terraform" not in suspect_names  # not a preference
    assert "Python" in ambiguous_names  # preference + experience evidence
    with SessionLocal() as db:
        stored = db.query(Candidate).filter(Candidate.user_id == client.test_user_id).one()
        assert set(stored.skills) == {"Python", "Kubernetes", "Terraform"}


def test_apply_removes_only_preference_only_and_deflates_fit(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        candidate = insert_candidate(db, user_id=client.test_user_id)
        candidate.skills = ["Python", "Kubernetes"]
        candidate.experience = [{"company": "Acme", "bullets": ["Shipped Python services"]}]
        db.add(
            TargetPreference(
                user_id=client.test_user_id,
                candidate_id=candidate.id,
                target_roles=["Software Engineer"],
                skill_preferences=["Kubernetes"],
            )
        )
        job = insert_job(db, public_id="contam-job")
        job.description = "Requirements: Kubernetes and Python."
        db.commit()

        before = score_job(db, "contam-job", client.test_user_id)
        assert "Kubernetes" in before.matched_skills

        # No heuristic cleanup without a human-verified allowlist.
        with pytest.raises(ValueError, match="approval"):
            audit_database(db, apply=True)

        report = audit_database(
            db,
            apply=True,
            approved_removals={(candidate.id, "Kubernetes")},
        )
        assert {row.skill for row in report.removed} == {"Kubernetes"}
        assert report.users_with_removals == [client.test_user_id]

        after = score_job(db, "contam-job", client.test_user_id)
        assert "Kubernetes" not in after.matched_skills
        assert "Kubernetes" in after.missing_skills
        assert "Python" in after.matched_skills

        stored = db.query(Candidate).filter(Candidate.user_id == client.test_user_id).one()
        assert stored.skills == ["Python"]


def test_cli_refuses_apply_without_confirm(tmp_path: Path) -> None:
    from sqlalchemy import create_engine

    from backend.db import models as _models  # noqa: F401
    from backend.db.database import Base

    db_path = tmp_path / "audit.sqlite"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    Base.metadata.create_all(engine)
    engine.dispose()

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--database", str(db_path), "--apply"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "--confirm" in (proc.stderr + proc.stdout)

    dry = subprocess.run(
        [sys.executable, str(SCRIPT), "--database", str(db_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(dry.stdout)
    assert payload["mode"] == "dry-run"
    assert payload["candidates_scanned"] == 0

def test_overlap_without_profile_text_is_only_a_suspect_until_reviewed(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        candidate = insert_candidate(db, user_id=client.test_user_id)
        # A real resume can list skills without repeating them in project bullets.
        candidate.skills = ["Kubernetes", "Python"]
        candidate.experience = [{"company": "Acme", "bullets": ["Built internal systems"]}]
        db.add(
            TargetPreference(
                user_id=client.test_user_id,
                candidate_id=candidate.id,
                target_roles=["Software Engineer"],
                skill_preferences=["Kubernetes"],
            )
        )
        db.commit()

        report = audit_database(db, apply=False)
        assert {row.skill for row in report.preference_only_suspects} == {"Kubernetes"}

        with pytest.raises(ValueError, match="approval"):
            audit_database(db, apply=True)

        with pytest.raises(ValueError, match="did not match eligible"):
            audit_database(db, apply=True, approved_removals={(candidate.id, "Python")})

        db.refresh(candidate)
        assert candidate.skills == ["Kubernetes", "Python"]


def test_cli_requires_reviewed_removals_file_even_with_confirm(tmp_path: Path) -> None:
    from sqlalchemy import create_engine

    from backend.db import models as _models  # noqa: F401
    from backend.db.database import Base

    db_path = tmp_path / "audit.sqlite"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    Base.metadata.create_all(engine)
    engine.dispose()

    missing_allowlist = subprocess.run(
        [sys.executable, str(SCRIPT), "--database", str(db_path), "--apply", "--confirm"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert missing_allowlist.returncode != 0
    assert "--approved-removals" in (missing_allowlist.stdout + missing_allowlist.stderr)

    approvals = tmp_path / "reviewed.json"
    approvals.write_text('[{"candidate_id": 999, "skill": "Kubernetes"}]', encoding="utf-8")
    invalid_targets = subprocess.run(
        [
            sys.executable, str(SCRIPT), "--database", str(db_path),
            "--apply", "--confirm", "--approved-removals", str(approvals),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert invalid_targets.returncode != 0
    assert "no changes committed" in (invalid_targets.stdout + invalid_targets.stderr)
