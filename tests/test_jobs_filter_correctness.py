"""Jobs date, location, and role/experience filter correctness."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.db.models import JobRecord, JobRequirementProfileRecord
from backend.services.opportunity_type import infer_employment_type, infer_opportunity_type


def _ids(response) -> list[str]:
    return [item["job"]["id"] for item in response.json()["items"]]


def _job(
    db,
    *,
    public_id: str,
    title: str,
    location: str | None = None,
    description: str = "Build products.",
    date_posted: str | None = None,
    date_scraped: datetime | None = None,
) -> JobRecord:
    record = JobRecord(
        public_id=public_id,
        title=title,
        company="Acme",
        location=location,
        url=f"https://example.com/jobs/{public_id}",
        description=description,
        source="manual",
        status="discovered",
        date_posted=date_posted,
        date_scraped=date_scraped,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def test_date_posted_filter_and_newest_sort_use_employer_posting_time(isolated_client) -> None:
    client, SessionLocal = isolated_client
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        _job(
            db,
            public_id="old-posted-new-scrape",
            title="Software Engineer",
            location="Austin, TX",
            description="Full-time role.",
            date_posted=(now - timedelta(days=45)).date().isoformat(),
            date_scraped=now,
        )
        _job(
            db,
            public_id="posted-yesterday",
            title="Software Engineer II",
            location="Austin, TX",
            description="Full-time role.",
            date_posted=(now - timedelta(hours=12)).date().isoformat(),
            date_scraped=now - timedelta(days=1),
        )
        _job(
            db,
            public_id="scrape-fallback",
            title="Software Engineer III",
            location="Austin, TX",
            description="Full-time role.",
            date_posted=None,
            date_scraped=now,
        )
        _job(
            db,
            public_id="iso-datetime",
            title="Software Engineer IV",
            location="Austin, TX",
            description="Full-time role.",
            date_posted=(now - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            date_scraped=now - timedelta(days=10),
        )
        _job(
            db,
            public_id="invalid-posted",
            title="Software Engineer V",
            location="Austin, TX",
            description="Full-time role.",
            date_posted="not-a-date",
            date_scraped=now,
        )
        _job(
            db,
            public_id="epoch-garbage",
            title="Software Engineer VI",
            location="Austin, TX",
            description="Full-time role.",
            date_posted="1970-01-01",
            date_scraped=now,
        )

    past_24h = client.get("/api/jobs/query", params={"date_posted": "past_24h"})
    assert past_24h.status_code == 200
    ids = set(_ids(past_24h))
    assert "old-posted-new-scrape" not in ids
    assert "posted-yesterday" in ids
    assert "iso-datetime" in ids
    # Missing or untrustworthy posting dates may fall back to scrape time.
    assert "scrape-fallback" in ids
    assert "invalid-posted" in ids
    assert "epoch-garbage" in ids

    newest = client.get("/api/jobs/query", params={"sort": "newest"})
    assert newest.status_code == 200
    ranked = _ids(newest)
    assert ranked.index("posted-yesterday") < ranked.index("old-posted-new-scrape")
    assert ranked.index("iso-datetime") < ranked.index("old-posted-new-scrape")

    epoch_job = next(item["job"] for item in newest.json()["items"] if item["job"]["id"] == "epoch-garbage")
    assert epoch_job.get("date_posted") != "1970-01-01"
    assert epoch_job.get("date_posted") is None

    invalid = client.get("/api/jobs/query", params={"q": "Software Engineer V"})
    assert invalid.status_code == 200


def test_location_filter_uses_canonical_location_not_description(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        _job(
            db,
            public_id="ny-mentions-sf",
            title="Account Executive",
            location="New York, NY",
            description="Our San Francisco team and SF headquarters also hire.",
        )
        _job(
            db,
            public_id="sf-role",
            title="Software Engineer",
            location="San Francisco, CA",
            description="Backend platform.",
        )
        _job(
            db,
            public_id="oakland",
            title="Software Engineer",
            location="Oakland, CA",
            description="Onsite Oakland office.",
        )
        _job(
            db,
            public_id="san-jose",
            title="Software Engineer",
            location="San Jose, CA",
            description="South Bay office.",
        )
        _job(
            db,
            public_id="remote-us-mentions-sf",
            title="Software Engineer",
            location="Remote - United States",
            description="Remote US only. Our San Francisco headquarters is not the work site.",
        )
        _job(
            db,
            public_id="hybrid-palo-alto",
            title="Software Engineer",
            location="Palo Alto, CA",
            description="Hybrid in Palo Alto.",
        )
        remote_profile = _job(
            db,
            public_id="remote-profile-ca",
            title="Software Engineer",
            location="Remote",
            description="Mentions California office in passing.",
        )
        db.add(
            JobRequirementProfileRecord(
                job_id=remote_profile.id,
                source_fingerprint="loc-1",
                extraction_version=1,
                profile_json={
                    "work_mode": "remote",
                    "remote_scope": "US",
                    "locations": [{"label": "United States", "evidence_text": "Remote US"}],
                    "source_fingerprint": "loc-1",
                },
            )
        )
        db.commit()

    bay = client.get("/api/jobs/query", params={"location": "San Francisco Bay Area"})
    assert bay.status_code == 200
    ids = set(_ids(bay))
    assert "ny-mentions-sf" not in ids
    assert "remote-us-mentions-sf" not in ids
    assert "remote-profile-ca" not in ids
    assert "sf-role" in ids
    assert "oakland" in ids
    assert "san-jose" in ids
    assert "hybrid-palo-alto" in ids


def test_role_and_experience_filters_use_canonical_fields(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        _job(
            db,
            public_id="recruiter",
            title="Technical Recruiter",
            location="Austin, TX",
            description="Recruit software engineers for the engineering org.",
        )
        _job(
            db,
            public_id="marketing-intern",
            title="Marketing Intern",
            location="Austin, TX",
            description="Work with the software engineering team on campaigns.",
        )
        _job(
            db,
            public_id="senior-mentions-interns",
            title="Senior Software Engineer",
            location="Austin, TX",
            description="Mentor interns. Full-time. Remote.",
        )
        _job(
            db,
            public_id="swe-intern",
            title="Software Engineering Intern",
            location="Austin, TX",
            description="Summer internship on the platform team.",
        )
        _job(
            db,
            public_id="junior-swe",
            title="Software Engineer I",
            location="Austin, TX",
            description="Junior software engineer. Full-time.",
        )
        _job(
            db,
            public_id="new-grad",
            title="New Grad Software Engineer",
            location="Austin, TX",
            description="New grad program. Full-time rotation.",
        )

    swe = client.get("/api/jobs/query", params={"q": "Software Engineering"})
    assert swe.status_code == 200
    swe_ids = set(_ids(swe))
    assert "recruiter" not in swe_ids
    assert "marketing-intern" not in swe_ids
    assert "swe-intern" in swe_ids
    assert "junior-swe" in swe_ids
    assert "new-grad" in swe_ids
    assert "senior-mentions-interns" in swe_ids

    intern = client.get("/api/jobs/query", params={"experience_level": "intern"})
    intern_ids = set(_ids(intern))
    assert "senior-mentions-interns" not in intern_ids
    assert "swe-intern" in intern_ids
    assert "marketing-intern" in intern_ids

    junior = client.get("/api/jobs/query", params={"experience_level": "junior"})
    junior_ids = set(_ids(junior))
    assert "junior-swe" in junior_ids
    assert "swe-intern" not in junior_ids

    new_grad = client.get("/api/jobs/query", params={"experience_level": "new_grad"})
    assert "new-grad" in set(_ids(new_grad))
    assert "senior-mentions-interns" not in set(_ids(new_grad))

    assert infer_employment_type("Senior Software Engineer", "Mentor interns.") != "internship"
    assert infer_opportunity_type("Senior Software Engineer", "Mentor interns.") != "internship"
    assert infer_employment_type("Software Engineering Intern", "Summer internship.") == "internship"
    assert infer_employment_type("New Grad Software Engineer", "New grad program.") == "new_grad"
    assert infer_opportunity_type("Staff Platform Engineer", "Full-time. Remote.") == "role"
