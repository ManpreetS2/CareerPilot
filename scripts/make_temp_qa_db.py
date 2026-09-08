#!/usr/bin/env python3
"""Create an isolated SQLite file for A8/A9 human QA.

Never reads or writes data/careerpilot.db. Prints a DATABASE_URL for uvicorn.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_DATABASE = (ROOT / "data" / "careerpilot.db").resolve()


def _refuse_production(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == PRODUCTION_DATABASE:
        raise SystemExit("Refusing data/careerpilot.db. Use a copied or empty temp SQLite file.")
    if resolved.suffix not in {".db", ".sqlite", ".sqlite3"}:
        raise SystemExit("QA database must be a .db/.sqlite/.sqlite3 file.")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from",
        dest="source",
        type=Path,
        default=None,
        help="Optional existing SQLite file to copy. Must not be data/careerpilot.db.",
    )
    args = parser.parse_args()

    temp_dir = Path(tempfile.mkdtemp(prefix="careerpilot-qa-"))
    dest = _refuse_production(temp_dir / "qa.sqlite")

    if args.source is not None:
        source = _refuse_production(args.source)
        if not source.is_file():
            raise SystemExit(f"Source database not found: {source}")
        shutil.copy2(source, dest)
        print(f"Copied {source} -> {dest}", file=sys.stderr)
    else:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from sqlalchemy import create_engine

        from backend.db.database import Base
        from backend.db import models as _models  # noqa: F401

        engine = create_engine(f"sqlite:///{dest.as_posix()}")
        Base.metadata.create_all(engine)
        engine.dispose()
        print(f"Created empty schema at {dest}", file=sys.stderr)

    url = f"sqlite:///{dest.as_posix()}"
    print(f"DATABASE_URL={url}")
    print("uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000", file=sys.stderr)
    print("Open the UI at http://127.0.0.1:5173 only (do not mix localhost).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
