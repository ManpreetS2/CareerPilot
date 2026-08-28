"""Natural-language search contract. Does not generate SQL or URLs."""

from __future__ import annotations

from backend.schemas.job_requirements import SearchIntent


def parse_search_intent(raw: str | None) -> SearchIntent:
    """Skeleton parser. Returns an explicit unparsed intent until a safe parser exists."""
    text = (raw or "").strip()
    return SearchIntent(raw_query=text or None, parser_ready=False)
