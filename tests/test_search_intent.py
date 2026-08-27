from backend.services.search_intent import parse_search_intent


def test_search_intent_is_an_unparsed_skeleton() -> None:
    intent = parse_search_intent(
        "Software engineering internships in the Bay Area at fintech companies, hybrid or onsite, starting next summer."
    )
    assert intent.parser_ready is False
    assert intent.roles == []
    assert intent.locations == []
    assert "SELECT" not in (intent.raw_query or "")
