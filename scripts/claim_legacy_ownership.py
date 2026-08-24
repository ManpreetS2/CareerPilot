#!/usr/bin/env python3
"""One-time, explicit claim of pre-auth rows with NULL user_id.

Dry-run by default. Never imported by the API, startup, tests, or CI.
Does not run unless invoked as a CLI. Refuses the production database
unless --confirm-production-database is also passed.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_DB = (ROOT / "data" / "careerpilot.db").resolve()

CLAIMABLE = (
    ("candidates", "user_id", True),
    ("target_preferences", "user_id", False),
    ("application_packages", "user_id", True),
    ("form_fill_attempts", "user_id", False),
    ("application_tracker", "user_id", True),
    ("interview_prep", "user_id", True),
)


@dataclass
class TableClaim:
    table: str
    null_rows: int = 0
    already_owned: int = 0
    other_owned: int = 0
    claimable: int = 0


@dataclass
class ClaimPlan:
    user_id: int
    tables: list[TableClaim] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def claimable_total(self) -> int:
        return sum(item.claimable for item in self.tables)

    @property
    def already_owned_total(self) -> int:
        return sum(item.already_owned for item in self.tables)


def resolve_sqlite_path(database_url: str) -> Path | None:
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite") or not url.database or url.database == ":memory:":
        return None
    path = Path(url.database)
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    else:
        path = path.resolve()
    return path


def is_production_database(database_url: str) -> bool:
    path = resolve_sqlite_path(database_url)
    return path is not None and path == PRODUCTION_DB


def _table_has_user_id(engine: Engine, table: str) -> bool:
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return False
    return any(col["name"] == "user_id" for col in inspector.get_columns(table))


def _table_has_column(engine: Engine, table: str, column: str) -> bool:
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return False
    return any(col["name"] == column for col in inspector.get_columns(table))


def _ownership_graph_errors(session: Session, user_id: int) -> list[str]:
    """Refuse ownerless children whose private parents belong to someone else.

    A row is claimable only when every private parent is ownerless (and would
    be included in this same claim) or already owned by the target user.
    """

    errors: list[str] = []
    bind = session.get_bind()
    if _table_has_column(bind, "target_preferences", "candidate_id") and _table_has_user_id(
        bind, "candidates"
    ):
        bad = session.execute(
            text(
                """
                SELECT COUNT(*) FROM target_preferences AS child
                LEFT JOIN candidates AS parent ON parent.id = child.candidate_id
                WHERE child.user_id IS NULL
                  AND child.candidate_id IS NOT NULL
                  AND (
                        parent.id IS NULL
                        OR (parent.user_id IS NOT NULL AND parent.user_id != :uid)
                      )
                """
            ),
            {"uid": user_id},
        ).scalar_one()
        if bad:
            errors.append(
                "ownerless target_preferences reference a candidate owned by a different user"
            )

    if _table_has_column(bind, "application_packages", "candidate_id") and _table_has_user_id(
        bind, "candidates"
    ):
        bad = session.execute(
            text(
                """
                SELECT COUNT(*) FROM application_packages AS child
                LEFT JOIN candidates AS parent ON parent.id = child.candidate_id
                WHERE child.user_id IS NULL
                  AND child.candidate_id IS NOT NULL
                  AND (
                        parent.id IS NULL
                        OR (parent.user_id IS NOT NULL AND parent.user_id != :uid)
                      )
                """
            ),
            {"uid": user_id},
        ).scalar_one()
        if bad:
            errors.append(
                "ownerless application_packages reference a candidate owned by a different user"
            )

    if _table_has_user_id(bind, "form_fill_attempts") and _table_has_user_id(
        bind, "application_packages"
    ):
        bad = session.execute(
            text(
                """
                SELECT COUNT(*) FROM form_fill_attempts AS child
                JOIN application_packages AS parent ON parent.job_id = child.job_id
                WHERE child.user_id IS NULL
                  AND parent.user_id IS NOT NULL
                  AND parent.user_id != :uid
                """
            ),
            {"uid": user_id},
        ).scalar_one()
        if bad:
            errors.append(
                "ownerless form_fill_attempts reference a package owned by a different user"
            )
    return errors


def _unique_conflict(session: Session, table: str, user_id: int) -> str | None:
    if table == "candidates":
        owned = session.execute(
            text("SELECT COUNT(*) FROM candidates WHERE user_id = :uid"),
            {"uid": user_id},
        ).scalar_one()
        nulls = session.execute(
            text("SELECT COUNT(*) FROM candidates WHERE user_id IS NULL")
        ).scalar_one()
        if nulls > 1:
            return "multiple ownerless candidate rows; refuse to guess"
        if owned and nulls:
            return "target user already has a candidate; ownerless candidate is ambiguous"
    if table in {"application_packages", "application_tracker", "interview_prep"}:
        null_jobs = session.execute(
            text(f"SELECT job_id, COUNT(*) FROM {table} WHERE user_id IS NULL GROUP BY job_id HAVING COUNT(*) > 1")
        ).fetchall()
        if null_jobs:
            return f"{table} has multiple ownerless rows for the same job"
        conflicts = session.execute(
            text(
                f"""
                SELECT ownerless.job_id FROM {table} AS ownerless
                JOIN {table} AS owned
                  ON owned.job_id = ownerless.job_id
                 AND owned.user_id = :uid
                WHERE ownerless.user_id IS NULL
                """
            ),
            {"uid": user_id},
        ).fetchall()
        if conflicts:
            return f"{table} already has a row for this user on a job with an ownerless row"
    return None


def inspect_claim(session: Session, user_id: int) -> ClaimPlan:
    plan = ClaimPlan(user_id=user_id)
    user_exists = session.execute(
        text("SELECT COUNT(*) FROM users WHERE id = :uid"),
        {"uid": user_id},
    ).scalar_one()
    if not user_exists:
        plan.errors.append(f"user_id={user_id} does not exist")
        return plan

    bind = session.get_bind()
    for table, _column, _unique in CLAIMABLE:
        if not _table_has_user_id(bind, table):
            continue
        null_rows = session.execute(
            text(f"SELECT COUNT(*) FROM {table} WHERE user_id IS NULL")
        ).scalar_one()
        already_owned = session.execute(
            text(f"SELECT COUNT(*) FROM {table} WHERE user_id = :uid"),
            {"uid": user_id},
        ).scalar_one()
        other_owned = session.execute(
            text(f"SELECT COUNT(*) FROM {table} WHERE user_id IS NOT NULL AND user_id != :uid"),
            {"uid": user_id},
        ).scalar_one()
        item = TableClaim(
            table=table,
            null_rows=int(null_rows),
            already_owned=int(already_owned),
            other_owned=int(other_owned),
            claimable=int(null_rows),
        )
        conflict = _unique_conflict(session, table, user_id)
        if conflict:
            plan.errors.append(conflict)
            item.claimable = 0
        plan.tables.append(item)
    plan.errors.extend(_ownership_graph_errors(session, user_id))
    if plan.errors:
        for item in plan.tables:
            item.claimable = 0
    return plan


def apply_claim(session: Session, user_id: int) -> ClaimPlan:
    plan = inspect_claim(session, user_id)
    if plan.errors:
        return plan
    bind = session.get_bind()
    try:
        for item in plan.tables:
            if item.claimable == 0 or not _table_has_user_id(bind, item.table):
                continue
            session.execute(
                text(f"UPDATE {item.table} SET user_id = :uid WHERE user_id IS NULL"),
                {"uid": user_id},
            )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return inspect_claim(session, user_id)


def _print_plan(plan: ClaimPlan, *, applied: bool, counts_only: bool = False) -> None:
    if not counts_only:
        mode = "applied" if applied else "dry-run"
        print(f"legacy_owner_claim mode={mode} user_id={plan.user_id}")
        if plan.errors:
            print("status=refused")
            for error in plan.errors:
                print(f"error={error}")
            return
    elif plan.errors:
        print("status=refused")
    for item in plan.tables:
        print(
            f"table={item.table} null={item.null_rows} "
            f"claimable={item.claimable} already_owned={item.already_owned} "
            f"other_owned={item.other_owned}"
        )
    print(
        f"totals claimable={plan.claimable_total} already_owned={plan.already_owned_total}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--confirm-production-database", action="store_true")
    parser.add_argument("--counts-only", action="store_true")
    args = parser.parse_args(argv)

    database_url = args.database_url
    if not database_url:
        from backend.core.config import settings

        database_url = settings.database_url

    if is_production_database(database_url) and args.apply and not args.confirm_production_database:
        print("Refusing to write the production database without --confirm-production-database.")
        return 2

    engine = create_engine(database_url, future=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        if args.apply:
            if not args.confirm:
                print("Refusing to write without --confirm.")
                return 2
            plan = apply_claim(session, args.user_id)
            _print_plan(plan, applied=not plan.errors, counts_only=args.counts_only)
            return 1 if plan.errors else 0
        plan = inspect_claim(session, args.user_id)
        _print_plan(plan, applied=False, counts_only=args.counts_only)
        return 1 if plan.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
