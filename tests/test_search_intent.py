from backend.services.search_intent import parse_search_intent
from backend.services.job_search_parser import parse_job_search_intent, scout_terms_from_intent


EXAMPLE = (
    "Software engineering internships in the Bay Area at fintech companies, hybrid or onsite"
)


def test_search_intent_parses_the_bay_area_internship_example() -> None:
    intent = parse_job_search_intent(EXAMPLE)
    assert intent.parser_ready is True
    assert intent.roles == ["Software Engineering"]
    assert intent.opportunity_types == ["internship"]
    assert intent.employment_types == ["internship"]
    assert intent.locations == ["San Francisco Bay Area"]
    assert intent.work_modes == ["hybrid", "onsite"]
    assert intent.industries == ["fintech"]
    assert "SELECT" not in (intent.raw_query or "")
    assert "DROP" not in (intent.query or "")


def test_search_intent_wrapper_is_ready() -> None:
    intent = parse_search_intent(EXAMPLE)
    assert intent.parser_ready is True
    assert intent.roles == ["Software Engineering"]
    assert intent.locations == ["San Francisco Bay Area"]


def test_search_intent_does_not_compile_sql_or_urls() -> None:
    intent = parse_job_search_intent("internships'; SELECT * FROM jobs; -- https://evil.test")
    dumped = intent.model_dump_json()
    assert "SELECT" in dumped  # user text is preserved as text
    assert "sqlalchemy" not in dumped.lower()
    assert "orm" not in dumped.lower()
    queries, location = scout_terms_from_intent(intent)
    assert all(not item.lower().startswith("http") for item in queries)
    assert location is None or not location.lower().startswith("http")


def test_empty_search_is_ready_not_fake() -> None:
    intent = parse_job_search_intent("  ")
    assert intent.parser_source == "empty"
    assert intent.roles == []
