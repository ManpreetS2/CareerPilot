#!/usr/bin/env python3
"""Generate ignored synthetic resume PDFs and write committed-safe manifests.

Usage:
  python scripts/generate_synthetic_resume_matrix.py
  python scripts/generate_synthetic_resume_matrix.py --out local_resumes/generated
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.synthetic_resume_matrix import (
    GENERATED_DIR,
    LAYOUTS,
    generate_all,
    write_layout_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate fictional synthetic resume PDFs")
    parser.add_argument("--out", type=Path, default=GENERATED_DIR)
    args = parser.parse_args()
    paths = generate_all(args.out)
    fixture_dir = ROOT / "tests" / "fixtures" / "synthetic_resumes"
    for layout in LAYOUTS:
        write_layout_manifest(layout, fixture_dir)
    print(f"layouts={len(paths)}")
    print(f"directory={args.out.name}")
    print("pdfs_tracked=no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
