"""Browser-workflow ASGI app. Production startup must not import this module."""

from __future__ import annotations

import json

from backend.main import app

def _browser_fake_materials(_prompt: str, _system_prompt: str | None = None) -> str:
    """Deterministic grounded JSON for the privacy-safe browser workflow only."""
    return json.dumps(
        {
            "tailored_bullets": [
                "Python is listed in the stored candidate skill evidence."
            ],
            "cover_letter_draft": "Thank you for considering my application.",
            "recruiter_message": "I would welcome the chance to discuss this role.",
            "source_traceability_notes": ["Python <- candidate skills"],
        }
    )


app.state.application_materials_generator = _browser_fake_materials
