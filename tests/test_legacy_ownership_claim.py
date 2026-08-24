"""Explicit legacy owner-claim CLI. Never touches data/careerpilot.db."""

from __future__ import annotations

import threading
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from backend.db.database import Base
from backend.db.models import (
    ApplicationPackageRecord,
    Candidate,
    FormFillAttemptRecord,
    JobRecord,
    TargetPreference,
    User,
)
from scripts.claim_legacy_ownership import apply_claim, inspect_claim, is_production_database, main

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = ROOT / "data" / "careerpilot.db"


def _engine(tmp_path: Path):
    path = tmp_path / "legacy.sqlite"
    engine = create_engine(f"sqlite:///{path}", future=True)
    Base.metadata.create_all(bind=engine)
    return engine, path


def _user(session, email: str) -> User:
    user = User(email=email, hashed_password="x")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_claim_succeeds_for_single_null_owner_set(tmp_path) -> None:
    engine, _path = _engine(tmp_path)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        user = _user(session, "owner@example.com")
        user_id = user.id
        session.add(Candidate(user_id=None, name="Legacy Candidate", skills=["Python"]))
        session.add(TargetPreference(user_id=None, target_roles=["Intern"]))
        session.commit()
        plan = apply_claim(session, user_id)
    assert not plan.errors
    with SessionLocal() as session:
        candidate = session.query(Candidate).one()
        prefs = session.query(TargetPreference).one()
        assert candidate.user_id == user_id
        assert prefs.user_id == user_id
        second = apply_claim(session, user_id)
    assert second.claimable_total == 0
    assert second.already_owned_total >= 1


def test_claim_refuses_ambiguous_null_candidates(tmp_path) -> None:
    engine, _path = _engine(tmp_path)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        user = _user(session, "owner@example.com")
        session.add(Candidate(user_id=None, name="Legacy A", skills=["Python"]))
        session.add(Candidate(user_id=None, name="Legacy B", skills=["SQL"]))
        session.commit()
        plan = apply_claim(session, user.id)
    assert plan.errors
    with SessionLocal() as session:
        assert all(row.user_id is None for row in session.query(Candidate).all())


def test_claim_is_idempotent_and_cross_user_safe(tmp_path) -> None:
    engine, _path = _engine(tmp_path)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        owner = _user(session, "owner@example.com")
        other = _user(session, "other@example.com")
        owner_id = owner.id
        other_id = other.id
        session.add(Candidate(user_id=None, name="Legacy Candidate", skills=["Python"]))
        session.add(Candidate(user_id=other_id, name="Other Candidate", skills=["Go"]))
        session.add(
            JobRecord(
                public_id="job-1",
                title="Engineer",
                company="Acme",
                url="https://example.com/job",
                description="Python",
                source="manual",
            )
        )
        session.commit()
        first = apply_claim(session, owner_id)
        second = apply_claim(session, owner_id)
    assert not first.errors
    assert not second.errors
    assert second.claimable_total == 0
    with SessionLocal() as session:
        owned = session.query(Candidate).filter(Candidate.user_id == owner_id).one()
        other_row = session.query(Candidate).filter(Candidate.user_id == other_id).one()
        assert owned.name == "Legacy Candidate"
        assert other_row.name == "Other Candidate"


def test_claim_cli_dry_run_does_not_write(tmp_path) -> None:
    engine, path = _engine(tmp_path)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        user = _user(session, "owner@example.com")
        session.add(Candidate(user_id=None, name="Legacy Candidate", skills=["Python"]))
        session.commit()
        user_id = user.id
    code = main(
        [
            "--user-id",
            str(user_id),
            "--database-url",
            f"sqlite:///{path}",
        ]
    )
    assert code == 0
    with SessionLocal() as session:
        assert session.query(Candidate).one().user_id is None


def test_claim_refuses_production_database_without_extra_flag(tmp_path, monkeypatch) -> None:
    assert is_production_database(f"sqlite:///{PRODUCTION.resolve()}") is True
    engine, path = _engine(tmp_path)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        user = _user(session, "owner@example.com")
        user_id = user.id
    monkeypatch.setattr("scripts.claim_legacy_ownership.is_production_database", lambda _url: True)
    code = main(
        [
            "--user-id",
            str(user_id),
            "--database-url",
            f"sqlite:///{path}",
            "--apply",
            "--confirm",
        ]
    )
    assert code == 2


def test_startup_modules_do_not_import_claim_script() -> None:
    for relative in ("backend/main.py", "backend/db/init_db.py"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "claim_legacy_ownership" not in text


def _job(session, public_id: str = "legacy-job") -> JobRecord:
    job = JobRecord(
        public_id=public_id,
        title="Engineer",
        company="Acme",
        url=f"https://example.com/{public_id}",
        description="Python",
        source="manual",
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def test_null_preference_for_other_users_candidate_cannot_be_claimed(tmp_path) -> None:
    engine, _path = _engine(tmp_path)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        user_a = _user(session, "a@example.com")
        user_b = _user(session, "b@example.com")
        owned = Candidate(user_id=user_b.id, name="B Candidate", skills=["Go"])
        session.add(owned)
        session.commit()
        session.refresh(owned)
        session.add(
            TargetPreference(
                user_id=None,
                candidate_id=owned.id,
                target_roles=["Intern"],
            )
        )
        session.commit()
        plan = apply_claim(session, user_a.id)
        assert plan.errors
        prefs = session.query(TargetPreference).all()
        assert all(row.user_id is None for row in prefs)
        assert session.query(Candidate).one().user_id == user_b.id


def test_null_package_for_other_users_candidate_cannot_be_claimed(tmp_path) -> None:
    engine, _path = _engine(tmp_path)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        user_a = _user(session, "a@example.com")
        user_b = _user(session, "b@example.com")
        owned = Candidate(user_id=user_b.id, name="B Candidate", skills=["Go"])
        session.add(owned)
        session.commit()
        session.refresh(owned)
        job = _job(session)
        session.add(
            ApplicationPackageRecord(
                user_id=None,
                candidate_id=owned.id,
                job_id=job.id,
                tailored_bullets=[],
                source_traceability_notes=[],
            )
        )
        session.commit()
        plan = apply_claim(session, user_a.id)
        assert plan.errors
        packages = session.query(ApplicationPackageRecord).all()
        assert all(row.user_id is None for row in packages)
        assert session.query(Candidate).one().user_id == user_b.id


def test_null_form_fill_for_other_users_package_cannot_be_claimed(tmp_path) -> None:
    engine, _path = _engine(tmp_path)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        user_a = _user(session, "a@example.com")
        user_b = _user(session, "b@example.com")
        job = _job(session)
        session.add(
            ApplicationPackageRecord(
                user_id=user_b.id,
                job_id=job.id,
                tailored_bullets=[],
                source_traceability_notes=[],
            )
        )
        session.add(
            FormFillAttemptRecord(
                user_id=None,
                job_id=job.id,
                ats_platform="greenhouse",
                status="filled",
                filled_fields=[],
                flagged_fields=[],
            )
        )
        session.commit()
        plan = apply_claim(session, user_a.id)
        assert plan.errors
        attempts = session.query(FormFillAttemptRecord).all()
        assert all(row.user_id is None for row in attempts)
        assert session.query(ApplicationPackageRecord).one().user_id == user_b.id


def test_one_invalid_linked_row_rolls_back_the_entire_claim(tmp_path) -> None:
    engine, _path = _engine(tmp_path)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        user_a = _user(session, "a@example.com")
        user_b = _user(session, "b@example.com")
        b_candidate = Candidate(user_id=user_b.id, name="B Candidate", skills=["Go"])
        session.add(b_candidate)
        session.commit()
        session.refresh(b_candidate)
        session.add(Candidate(user_id=None, name="Legacy Candidate", skills=["Python"]))
        session.add(TargetPreference(user_id=None, target_roles=["Valid"]))
        session.add(
            TargetPreference(
                user_id=None,
                candidate_id=b_candidate.id,
                target_roles=["Invalid"],
            )
        )
        session.commit()
        plan = apply_claim(session, user_a.id)
        assert plan.errors
        assert all(row.user_id is None for row in session.query(Candidate).filter(Candidate.name == "Legacy Candidate"))
        assert all(row.user_id is None for row in session.query(TargetPreference).all())
        assert session.query(Candidate).filter(Candidate.name == "B Candidate").one().user_id == user_b.id


def test_consistent_ownerless_graph_can_be_claimed(tmp_path) -> None:
    engine, _path = _engine(tmp_path)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        user = _user(session, "owner@example.com")
        user_id = user.id
        candidate = Candidate(user_id=None, name="Legacy Candidate", skills=["Python"])
        session.add(candidate)
        session.commit()
        session.refresh(candidate)
        job = _job(session)
        session.add(
            TargetPreference(
                user_id=None,
                candidate_id=candidate.id,
                target_roles=["Intern"],
            )
        )
        session.add(
            ApplicationPackageRecord(
                user_id=None,
                candidate_id=candidate.id,
                job_id=job.id,
                tailored_bullets=["legacy-bullet"],
                source_traceability_notes=[],
            )
        )
        session.add(
            FormFillAttemptRecord(
                user_id=None,
                job_id=job.id,
                ats_platform="greenhouse",
                status="filled",
                filled_fields=[],
                flagged_fields=[],
            )
        )
        session.commit()
        plan = apply_claim(session, user_id)
        assert not plan.errors
        assert session.query(Candidate).one().user_id == user_id
        assert session.query(TargetPreference).one().user_id == user_id
        assert session.query(ApplicationPackageRecord).one().user_id == user_id
        assert session.query(FormFillAttemptRecord).one().user_id == user_id


def test_successful_claim_is_idempotent_on_repeat(tmp_path) -> None:
    engine, _path = _engine(tmp_path)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        user = _user(session, "owner@example.com")
        user_id = user.id
        session.add(Candidate(user_id=None, name="Legacy Candidate", skills=["Python"]))
        session.add(TargetPreference(user_id=None, target_roles=["Intern"]))
        session.commit()
        first = apply_claim(session, user_id)
        second = apply_claim(session, user_id)
        assert not first.errors
        assert not second.errors
        assert second.claimable_total == 0
        assert session.query(Candidate).one().user_id == user_id
        assert session.query(TargetPreference).one().user_id == user_id


def test_already_owned_rows_are_never_rewritten(tmp_path) -> None:
    engine, _path = _engine(tmp_path)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        owner = _user(session, "owner@example.com")
        other = _user(session, "other@example.com")
        owner_id = owner.id
        other_id = other.id
        owned_pref = TargetPreference(
            user_id=owner_id,
            target_roles=["Keep"],
            legal_name="Do Not Rewrite",
        )
        foreign = Candidate(
            user_id=other_id,
            name="Keep Other Name",
            skills=["Go"],
            email="other@example.com",
        )
        session.add_all([owned_pref, foreign])
        session.commit()
        session.refresh(owned_pref)
        session.refresh(foreign)
        owned_created = owned_pref.created_at
        owned_id = owned_pref.id
        foreign_created = foreign.created_at
        session.add(Candidate(user_id=None, name="Legacy Candidate", skills=["SQL"]))
        session.add(TargetPreference(user_id=None, target_roles=["Claim me"]))
        session.commit()
        plan = apply_claim(session, owner_id)
        assert not plan.errors
        kept_pref = session.get(TargetPreference, owned_id)
        kept_other = session.query(Candidate).filter(Candidate.email == "other@example.com").one()
        claimed = session.query(Candidate).filter(Candidate.name == "Legacy Candidate").one()
        assert kept_pref.user_id == owner_id
        assert kept_pref.legal_name == "Do Not Rewrite"
        assert kept_pref.target_roles == ["Keep"]
        assert kept_pref.created_at == owned_created
        assert kept_other.user_id == other_id
        assert kept_other.name == "Keep Other Name"
        assert kept_other.created_at == foreign_created
        assert claimed.user_id == owner_id


def _try_steal_nulls(path: Path, table: str, user_id: int) -> int:
    """Attempt an independent write. timeout=0 avoids same-thread deadlock."""

    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False, "timeout": 0},
        future=True,
    )
    try:
        with engine.connect() as conn:
            conn.execute(text("PRAGMA busy_timeout=0"))
            result = conn.execute(
                text(f"UPDATE {table} SET user_id = :uid WHERE user_id IS NULL"),
                {"uid": user_id},
            )
            conn.commit()
            return int(result.rowcount or 0)
    except Exception:
        return 0
    finally:
        engine.dispose()


def _patch_inspect_then_steal(monkeypatch, path: Path, table: str, thief_user_id: int) -> None:
    import scripts.claim_legacy_ownership as claim_mod

    real_inspect = claim_mod.inspect_claim

    def wrapped(session: Session, user_id: int):
        plan = real_inspect(session, user_id)
        _try_steal_nulls(path, table, thief_user_id)
        return plan

    monkeypatch.setattr(claim_mod, "inspect_claim", wrapped)


def _assert_linked_owners_match(session, *, parent, child, parent_fk: str) -> None:
    parent_row = session.query(parent).one()
    child_row = session.query(child).one()
    parent_id = parent_row.id
    assert getattr(child_row, parent_fk) in {None, parent_id}
    if getattr(child_row, parent_fk) == parent_id:
        if child_row.user_id is not None and parent_row.user_id is not None:
            assert child_row.user_id == parent_row.user_id
        assert not (child_row.user_id is not None and parent_row.user_id is None)


def test_claim_refuses_candidate_preference_race(tmp_path, monkeypatch) -> None:
    engine, path = _engine(tmp_path)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        user_a = _user(session, "a@example.com")
        user_b = _user(session, "b@example.com")
        user_a_id = user_a.id
        user_b_id = user_b.id
        candidate = Candidate(user_id=None, name="Legacy Candidate", skills=["Python"])
        session.add(candidate)
        session.commit()
        session.refresh(candidate)
        session.add(
            TargetPreference(
                user_id=None,
                candidate_id=candidate.id,
                target_roles=["Intern"],
            )
        )
        session.commit()
        _patch_inspect_then_steal(monkeypatch, path, "candidates", user_b_id)
        plan = apply_claim(session, user_a_id)
    with SessionLocal() as session:
        candidate = session.query(Candidate).one()
        pref = session.query(TargetPreference).one()
        assert not (candidate.user_id == user_b_id and pref.user_id == user_a_id)
        if candidate.user_id == user_b_id:
            assert plan.errors
            assert pref.user_id is None
        else:
            assert candidate.user_id == user_a_id
            assert pref.user_id == user_a_id
        _assert_linked_owners_match(
            session, parent=Candidate, child=TargetPreference, parent_fk="candidate_id"
        )


def test_claim_refuses_candidate_package_race(tmp_path, monkeypatch) -> None:
    engine, path = _engine(tmp_path)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        user_a = _user(session, "a@example.com")
        user_b = _user(session, "b@example.com")
        user_a_id = user_a.id
        user_b_id = user_b.id
        candidate = Candidate(user_id=None, name="Legacy Candidate", skills=["Python"])
        session.add(candidate)
        session.commit()
        session.refresh(candidate)
        job = _job(session)
        session.add(
            ApplicationPackageRecord(
                user_id=None,
                candidate_id=candidate.id,
                job_id=job.id,
                tailored_bullets=[],
                source_traceability_notes=[],
            )
        )
        session.commit()
        _patch_inspect_then_steal(monkeypatch, path, "candidates", user_b_id)
        plan = apply_claim(session, user_a_id)
    with SessionLocal() as session:
        candidate = session.query(Candidate).one()
        package = session.query(ApplicationPackageRecord).one()
        assert not (candidate.user_id == user_b_id and package.user_id == user_a_id)
        if candidate.user_id == user_b_id:
            assert plan.errors
            assert package.user_id is None
        else:
            assert candidate.user_id == user_a_id
            assert package.user_id == user_a_id
        _assert_linked_owners_match(
            session,
            parent=Candidate,
            child=ApplicationPackageRecord,
            parent_fk="candidate_id",
        )


def test_claim_refuses_package_form_fill_race(tmp_path, monkeypatch) -> None:
    engine, path = _engine(tmp_path)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        user_a = _user(session, "a@example.com")
        user_b = _user(session, "b@example.com")
        user_a_id = user_a.id
        user_b_id = user_b.id
        job = _job(session)
        session.add(
            ApplicationPackageRecord(
                user_id=None,
                job_id=job.id,
                tailored_bullets=[],
                source_traceability_notes=[],
            )
        )
        session.add(
            FormFillAttemptRecord(
                user_id=None,
                job_id=job.id,
                ats_platform="greenhouse",
                status="filled",
                filled_fields=[],
                flagged_fields=[],
            )
        )
        session.commit()
        _patch_inspect_then_steal(monkeypatch, path, "application_packages", user_b_id)
        plan = apply_claim(session, user_a_id)
    with SessionLocal() as session:
        package = session.query(ApplicationPackageRecord).one()
        attempt = session.query(FormFillAttemptRecord).one()
        assert not (package.user_id == user_b_id and attempt.user_id == user_a_id)
        if package.user_id == user_b_id:
            assert plan.errors
            assert attempt.user_id is None
        else:
            assert package.user_id == user_a_id
            assert attempt.user_id == user_a_id
        if attempt.user_id is not None and package.user_id is not None:
            assert attempt.user_id == package.user_id
        assert not (attempt.user_id is not None and package.user_id is None)


def test_concurrent_claims_leave_a_consistent_graph(tmp_path) -> None:
    _created, path = _engine(tmp_path)
    _created.dispose()
    SessionLocal = sessionmaker(
        bind=create_engine(
            f"sqlite:///{path}",
            connect_args={"check_same_thread": False, "timeout": 10},
            future=True,
        ),
        autoflush=False,
        autocommit=False,
    )
    with SessionLocal() as session:
        user_a = _user(session, "a@example.com")
        user_b = _user(session, "b@example.com")
        user_a_id = user_a.id
        user_b_id = user_b.id
        candidate = Candidate(user_id=None, name="Legacy Candidate", skills=["Python"])
        session.add(candidate)
        session.commit()
        session.refresh(candidate)
        session.add(
            TargetPreference(
                user_id=None,
                candidate_id=candidate.id,
                target_roles=["Intern"],
            )
        )
        session.commit()

    barrier = threading.Barrier(2)
    plans: list = []
    errors: list[BaseException] = []

    def _claim(user_id: int) -> None:
        try:
            barrier.wait()
            with SessionLocal() as session:
                plans.append(apply_claim(session, user_id))
        except BaseException as exc:
            errors.append(exc)

    first = threading.Thread(target=_claim, args=(user_a_id,))
    second = threading.Thread(target=_claim, args=(user_b_id,))
    first.start()
    second.start()
    first.join()
    second.join()
    assert not errors
    with SessionLocal() as session:
        candidate = session.query(Candidate).one()
        pref = session.query(TargetPreference).one()
        assert candidate.user_id in {user_a_id, user_b_id}
        assert pref.user_id == candidate.user_id
        _assert_linked_owners_match(
            session, parent=Candidate, child=TargetPreference, parent_fk="candidate_id"
        )


def test_injected_update_exception_rolls_back_every_mutation(tmp_path, monkeypatch) -> None:
    engine, _path = _engine(tmp_path)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        user = _user(session, "owner@example.com")
        user_id = user.id
        session.add(Candidate(user_id=None, name="Legacy Candidate", skills=["Python"]))
        session.add(TargetPreference(user_id=None, target_roles=["Intern"]))
        session.commit()

        real_execute = Session.execute
        seen = {"updates": 0}

        def wrapped(self, statement, *args, **kwargs):
            statement_text = str(statement).upper()
            if "UPDATE" in statement_text and "USER_ID" in statement_text:
                seen["updates"] += 1
                if seen["updates"] >= 1:
                    raise RuntimeError("injected update failure")
            return real_execute(self, statement, *args, **kwargs)

        monkeypatch.setattr(Session, "execute", wrapped)
        try:
            plan = apply_claim(session, user_id)
            raised = None
        except Exception as exc:
            raised = exc
            session.rollback()
            plan = None
        assert raised is not None or (plan is not None and plan.errors)
    with SessionLocal() as session:
        assert all(row.user_id is None for row in session.query(Candidate).all())
        assert all(row.user_id is None for row in session.query(TargetPreference).all())


def test_write_lock_failure_claims_no_rows(tmp_path, monkeypatch) -> None:
    engine, _path = _engine(tmp_path)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        user = _user(session, "owner@example.com")
        user_id = user.id
        session.add(Candidate(user_id=None, name="Legacy Candidate", skills=["Python"]))
        session.add(TargetPreference(user_id=None, target_roles=["Intern"]))
        session.commit()

        def _fail_lock(_session) -> None:
            raise RuntimeError("could not obtain a write lock for the ownership claim")

        monkeypatch.setattr("scripts.claim_legacy_ownership._begin_immediate", _fail_lock, raising=False)
        plan = apply_claim(session, user_id)
        assert plan.errors
        assert all("user_id=" not in error for error in plan.errors)
    with SessionLocal() as session:
        assert all(row.user_id is None for row in session.query(Candidate).all())
        assert all(row.user_id is None for row in session.query(TargetPreference).all())


def test_race_safe_successful_claim_is_idempotent(tmp_path) -> None:
    engine, _path = _engine(tmp_path)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        user = _user(session, "owner@example.com")
        user_id = user.id
        candidate = Candidate(user_id=None, name="Legacy Candidate", skills=["Python"])
        session.add(candidate)
        session.commit()
        session.refresh(candidate)
        session.add(
            TargetPreference(
                user_id=None,
                candidate_id=candidate.id,
                target_roles=["Intern"],
            )
        )
        session.commit()
        first = apply_claim(session, user_id)
        second = apply_claim(session, user_id)
        assert not first.errors
        assert not second.errors
        assert second.claimable_total == 0
        assert session.query(Candidate).one().user_id == user_id
        assert session.query(TargetPreference).one().user_id == user_id
