"""Preview-only integration smoke. Never touches data/careerpilot.db."""

from __future__ import annotations

import os
import sys

PREVIEW_FRAGMENT = "careerpilot-demo-preview.db"
FORBIDDEN = "data/careerpilot.db"


def main() -> int:
    url = os.environ.get("DATABASE_URL", "")
    if FORBIDDEN in url.replace("\\", "/"):
        print("Refusing to run against data/careerpilot.db")
        return 2
    if PREVIEW_FRAGMENT not in url.replace("\\", "/"):
        print(
            "Set DATABASE_URL to sqlite:///./data/careerpilot-demo-preview.db before this smoke."
        )
        print("Conceptual flow: sign in, candidate, scout, verify, requirements,")
        print("eligibility, Verified Fit, materials, approval, form-fill preview,")
        print("interview prep. No submit.")
        return 1
    print("Preview database selected. Run the demo-runbook checklist against this DB.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
