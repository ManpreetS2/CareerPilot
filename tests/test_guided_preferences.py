"""Guided preference fields persist custom values losslessly."""

from __future__ import annotations

from tests.mvp_helpers import insert_candidate


def test_preferences_store_custom_taxonomy_values(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        insert_candidate(db, user_id=client.test_user_id)

    response = client.post(
        "/api/preferences",
        json={
            "target_roles": ["Quant Researcher"],
            "preferred_locations": ["Pune, India"],
            "constraints": ["role_type:internships"],
            "field_of_study": "Computational Neuroscience",
            "degree_pursuing": "Integrated Master's",
            "industry_preferences": ["Climate Tech"],
            "opportunity_preference": "internships",
            "experience_levels": ["New Grad"],
            "work_mode_preferences": ["hybrid"],
            "skill_preferences": ["Polars"],
            "academic_year": "junior",
            "expected_graduation": "2027-05",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["target_roles"] == ["Quant Researcher"]
    assert body["preferred_locations"] == ["Pune, India"]
    assert body["field_of_study"] == "Computational Neuroscience"
    assert body["degree_pursuing"] == "Integrated Master's"
    assert body["industry_preferences"] == ["Climate Tech"]
    assert body["skill_preferences"] == ["Polars"]

    profile = client.get("/api/profile").json()
    assert profile["preferences"]["target_roles"] == ["Quant Researcher"]
    assert profile["preferences"]["field_of_study"] == "Computational Neuroscience"
    assert profile["preferences"]["industry_preferences"] == ["Climate Tech"]
    assert "Polars" in profile["candidate"]["skills"]
    assert profile["readiness"]["ready"] is True
