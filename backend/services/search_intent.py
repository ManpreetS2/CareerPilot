"""Natural-language search contract. Does not generate SQL or URLs."""

from __future__ import annotations

from backend.schemas.job_requirements import SearchIntent
from backend.services.job_search_parser import parse_job_search_intent


def parse_search_intent(raw: str | None) -> SearchIntent:
    """Compatibility wrapper around JobSearchIntent for older callers."""
    parsed = parse_job_search_intent(raw)
    return SearchIntent(
        raw_query=parsed.raw_query,
        roles=list(parsed.roles),
        locations=list(parsed.locations),
        employment_types=list(parsed.employment_types),  # type: ignore[arg-type]
        experience_levels=list(parsed.experience_levels),  # type: ignore[arg-type]
        work_modes=list(parsed.work_modes),  # type: ignore[arg-type]
        industries=list(parsed.industries),
        skills=list(parsed.skills),
        salary_min=parsed.salary_min,
        parser_ready=True,
    )
