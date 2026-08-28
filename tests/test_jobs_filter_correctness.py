"""Jobs date, location, and role/experience filter correctness."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.db.models import JobRecord, JobRequirementProfileRecord
from backend.schemas.job_requirements import EXTRACTION_VERSION
from backend.services.job_content import source_fingerprint
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


def _add_profile(db, job: JobRecord, fingerprint: str, **fields) -> JobRequirementProfileRecord:
    payload = {
        "source_fingerprint": fingerprint,
        "extraction_version": EXTRACTION_VERSION,
        **fields,
    }
    row = JobRequirementProfileRecord(
        job_id=job.id,
        source_fingerprint=fingerprint,
        extraction_version=EXTRACTION_VERSION,
        profile_json=payload,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


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
    assert "posted-yesterday" in ids
    assert "iso-datetime" in ids
    assert "old-posted-new-scrape" not in ids
    assert "scrape-fallback" not in ids
    assert "invalid-posted" not in ids
    assert "epoch-garbage" not in ids

    newest = client.get("/api/jobs/query", params={"sort": "newest"})
    assert newest.status_code == 200
    ranked = _ids(newest)
    assert ranked.index("posted-yesterday") < ranked.index("old-posted-new-scrape")
    assert ranked.index("iso-datetime") < ranked.index("old-posted-new-scrape")
    assert ranked.index("iso-datetime") < ranked.index("scrape-fallback")
    assert ranked.index("iso-datetime") < ranked.index("invalid-posted")
    assert ranked.index("iso-datetime") < ranked.index("epoch-garbage")

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
        _job(
            db,
            public_id="coop",
            title="Software Engineering Co-op",
            location="Austin, TX",
            description="Fall co-op rotation.",
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
    assert "new-grad" not in intern_ids

    internships = client.get("/api/jobs/query", params={"opportunity": "internship"})
    internships_ids = set(_ids(internships))
    assert "swe-intern" in internships_ids
    assert "coop" in internships_ids
    assert "new-grad" not in internships_ids

    roles = client.get("/api/jobs/query", params={"opportunity": "role"})
    roles_ids = set(_ids(roles))
    assert "new-grad" in roles_ids
    assert "swe-intern" not in roles_ids
    assert "coop" not in roles_ids

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
    assert infer_opportunity_type("New Grad Software Engineer", "New grad program.") == "role"
    assert infer_opportunity_type("Staff Platform Engineer", "Full-time. Remote.") == "role"


def test_work_mode_and_employment_ignore_description_false_positives(isolated_client) -> None:
    from backend.services.opportunity_type import infer_work_mode

    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        _job(
            db,
            public_id="onsite-remote-teams",
            title="Software Engineer",
            location="Austin, TX",
            description="This is an onsite role. You will collaborate with remote teams.",
        )
        _job(
            db,
            public_id="onsite-remote-customers",
            title="Software Engineer",
            location="Austin, TX",
            description="Work onsite five days per week. The company also supports remote customer deployments.",
        )
        _job(
            db,
            public_id="hybrid-explicit",
            title="Software Engineer",
            location="Palo Alto, CA",
            description="Hybrid role, three days in the Palo Alto office.",
        )
        _job(
            db,
            public_id="full-time-contractors",
            title="Software Engineer",
            location="Austin, TX",
            description="This is a full-time role. You will work closely with contractors.",
        )
        _job(
            db,
            public_id="contract-explicit",
            title="Software Engineer",
            location="Austin, TX",
            description="6-month contract position on the platform team.",
        )
        _job(
            db,
            public_id="benefits-boilerplate",
            title="Software Engineer",
            location="Austin, TX",
            description="Full-time employee benefits are available. Coordinate with contract vendors. Support internship and fellowship programs.",
        )

    assert infer_work_mode(
        "Software Engineer",
        "This is an onsite role. You will collaborate with remote teams.",
        "Austin, TX",
    ) == "onsite"
    assert infer_work_mode(
        "Software Engineer",
        "Work onsite five days per week. The company also supports remote customer deployments.",
        "Austin, TX",
    ) == "onsite"
    assert infer_work_mode(
        "Software Engineer",
        "Hybrid role, three days in the Palo Alto office.",
        "Palo Alto, CA",
    ) == "hybrid"

    remote = client.get("/api/jobs/query", params={"work_mode": "remote"})
    remote_ids = set(_ids(remote))
    assert "onsite-remote-teams" not in remote_ids
    assert "onsite-remote-customers" not in remote_ids

    hybrid = client.get("/api/jobs/query", params={"work_mode": "hybrid"})
    assert "hybrid-explicit" in set(_ids(hybrid))

    onsite = client.get("/api/jobs/query", params={"work_mode": "onsite"})
    onsite_ids = set(_ids(onsite))
    assert "onsite-remote-teams" in onsite_ids
    assert "onsite-remote-customers" in onsite_ids

    contract = client.get("/api/jobs/query", params={"employment_type": "contract"})
    contract_ids = set(_ids(contract))
    assert "full-time-contractors" not in contract_ids
    assert "benefits-boilerplate" not in contract_ids
    assert "contract-explicit" in contract_ids

    full_time = client.get("/api/jobs/query", params={"employment_type": "full_time"})
    full_time_ids = set(_ids(full_time))
    assert "full-time-contractors" in full_time_ids
    assert "contract-explicit" not in full_time_ids

    assert infer_employment_type(
        "Software Engineer",
        "This is a full-time role. You will work closely with contractors.",
    ) == "full_time"
    assert infer_employment_type(
        "Software Engineer",
        "Full-time employee benefits are available. Coordinate with contract vendors.",
    ) == "unknown"


def test_experience_level_uses_occupational_title_patterns(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        _job(db, public_id="mid-market", title="Mid-Market Account Executive", location="Austin, TX")
        _job(db, public_id="lead-gen", title="Lead Generation Intern", location="Austin, TX")
        _job(db, public_id="staffing", title="Staffing Coordinator", location="Austin, TX")
        _job(db, public_id="senior-swe", title="Senior Software Engineer", location="Austin, TX")
        _job(db, public_id="staff-swe", title="Staff Software Engineer", location="Austin, TX")
        _job(db, public_id="lead-swe", title="Lead Software Engineer", location="Austin, TX")
        _job(db, public_id="principal", title="Principal Engineer", location="Austin, TX")

    assert "mid-market" not in set(_ids(client.get("/api/jobs/query", params={"experience_level": "mid"})))
    assert "lead-gen" not in set(_ids(client.get("/api/jobs/query", params={"experience_level": "lead"})))
    assert "staffing" not in set(_ids(client.get("/api/jobs/query", params={"experience_level": "staff"})))
    assert "senior-swe" in set(_ids(client.get("/api/jobs/query", params={"experience_level": "senior"})))
    assert "staff-swe" in set(_ids(client.get("/api/jobs/query", params={"experience_level": "staff"})))
    assert "lead-swe" in set(_ids(client.get("/api/jobs/query", params={"experience_level": "lead"})))
    assert "principal" in set(_ids(client.get("/api/jobs/query", params={"experience_level": "principal"})))


def test_malformed_and_future_posted_dates_do_not_500_or_rank_newest(isolated_client) -> None:
    client, SessionLocal = isolated_client
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        _job(
            db,
            public_id="unix-seconds",
            title="Software Engineer",
            date_posted=str(int((now - timedelta(days=1)).timestamp())),
        )
        _job(
            db,
            public_id="unix-millis",
            title="Software Engineer II",
            date_posted=str(int((now - timedelta(days=1)).timestamp() * 1000)),
        )
        _job(
            db,
            public_id="microseconds",
            title="Software Engineer III",
            date_posted="1717000000000000",
        )
        _job(
            db,
            public_id="overflow",
            title="Software Engineer IV",
            date_posted="9999999999999999",
        )
        _job(
            db,
            public_id="year-2286",
            title="Software Engineer V",
            date_posted="9999999999999",
        )
        _job(
            db,
            public_id="nan-like",
            title="Software Engineer VI",
            date_posted="NaN",
        )
        _job(
            db,
            public_id="inf-like",
            title="Software Engineer VII",
            date_posted="Infinity",
        )
        _job(
            db,
            public_id="recent-iso",
            title="Software Engineer VIII",
            date_posted=(now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    catalog = client.get("/api/jobs")
    query = client.get("/api/jobs/query")
    newest = client.get("/api/jobs/query", params={"sort": "newest"})
    assert catalog.status_code == 200
    assert query.status_code == 200
    assert newest.status_code == 200
    newest_ids = _ids(newest)
    by_id = {job["id"]: job for job in catalog.json()}
    assert by_id["unix-seconds"]["date_posted"] is not None
    assert by_id["unix-millis"]["date_posted"] is not None
    assert by_id["microseconds"]["date_posted"] is None
    assert by_id["overflow"]["date_posted"] is None
    assert by_id["year-2286"]["date_posted"] is None
    assert by_id["nan-like"]["date_posted"] is None
    assert newest_ids[0] == "recent-iso"
    assert newest_ids[0] not in {"year-2286", "overflow", "microseconds"}


def test_date_posted_filter_requires_valid_employer_posting_date(isolated_client) -> None:
    client, SessionLocal = isolated_client
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        _job(
            db,
            public_id="valid-recent",
            title="Software Engineer",
            date_posted=(now - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            date_scraped=now,
        )
        _job(
            db,
            public_id="old-scraped-today",
            title="Software Engineer II",
            date_posted=(now - timedelta(days=45)).date().isoformat(),
            date_scraped=now,
        )
        _job(
            db,
            public_id="missing-scraped-today",
            title="Software Engineer III",
            date_posted=None,
            date_scraped=now,
        )
        _job(
            db,
            public_id="invalid-scraped-today",
            title="Software Engineer IV",
            date_posted="not-a-date",
            date_scraped=now,
        )
        _job(
            db,
            public_id="epoch-scraped-today",
            title="Software Engineer V",
            date_posted="1970-01-01",
            date_scraped=now,
        )
        _job(
            db,
            public_id="future-scraped-today",
            title="Software Engineer VI",
            date_posted=(now + timedelta(days=400)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            date_scraped=now,
        )

    past_24h = client.get("/api/jobs/query", params={"date_posted": "past_24h"})
    assert past_24h.status_code == 200
    ids = set(_ids(past_24h))
    assert ids == {"valid-recent"}
    newest = client.get("/api/jobs/query", params={"sort": "newest"})
    assert newest.status_code == 200
    ranked = _ids(newest)
    assert ranked[0] == "valid-recent"
    for junk in (
        "missing-scraped-today",
        "invalid-scraped-today",
        "epoch-scraped-today",
        "future-scraped-today",
    ):
        assert ranked.index("valid-recent") < ranked.index(junk)
        assert ranked.index("old-scraped-today") < ranked.index(junk)


def test_stale_requirement_profile_does_not_drive_jobs_filters(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        job = _job(
            db,
            public_id="stale-profile-job",
            title="Remote Software Engineer",
            location="Remote - United States",
            description="This is a remote role. Full-time. Senior software engineer.",
        )
        fingerprint_a = source_fingerprint(job.title, job.description)
        _add_profile(
            db,
            job,
            fingerprint_a,
            work_mode="remote",
            employment_type="full_time",
            experience_level="senior",
            locations=[{"label": "United States", "evidence_text": "Remote US"}],
            remote_scope="US",
        )
        job.title = "On-site Software Engineer"
        job.location = "Austin, TX"
        job.description = "This is an onsite role. Full-time. Senior software engineer."
        db.commit()
        mutated_description = job.description

    assert fingerprint_a != source_fingerprint("On-site Software Engineer", mutated_description)
    remote = client.get("/api/jobs/query", params={"work_mode": "remote"})
    onsite = client.get("/api/jobs/query", params={"work_mode": "onsite"})
    assert "stale-profile-job" not in set(_ids(remote))
    assert "stale-profile-job" in set(_ids(onsite))

    with SessionLocal() as db:
        job = db.query(JobRecord).filter(JobRecord.public_id == "stale-profile-job").one()
        job.title = "Software Engineer"
        job.location = "Austin, TX"
        job.description = "Build products. Collaborate with contractors."
        db.commit()
        row = db.query(JobRequirementProfileRecord).filter(JobRequirementProfileRecord.job_id == job.id).one()
        row.profile_json = {
            **row.profile_json,
            "employment_type": "contract",
            "experience_level": "intern",
            "locations": [{"label": "San Francisco", "evidence_text": "stale SF"}],
            "work_mode": "remote",
        }
        db.commit()

    assert "stale-profile-job" not in set(
        _ids(client.get("/api/jobs/query", params={"employment_type": "contract"}))
    )
    assert "stale-profile-job" not in set(
        _ids(client.get("/api/jobs/query", params={"experience_level": "intern"}))
    )
    assert "stale-profile-job" not in set(
        _ids(client.get("/api/jobs/query", params={"location": "San Francisco"}))
    )

    with SessionLocal() as db:
        job = db.query(JobRecord).filter(JobRecord.public_id == "stale-profile-job").one()
        job.title = "On-site Software Engineer"
        job.location = "Austin, TX"
        job.description = "This is an onsite role. Full-time. Senior software engineer."
        db.commit()
        fingerprint_b = source_fingerprint(job.title, job.description)
        row = db.query(JobRequirementProfileRecord).filter(JobRequirementProfileRecord.job_id == job.id).one()
        row.source_fingerprint = fingerprint_b
        row.profile_json = {
            "source_fingerprint": fingerprint_b,
            "extraction_version": EXTRACTION_VERSION,
            "work_mode": "onsite",
            "employment_type": "full_time",
            "experience_level": "senior",
            "locations": [{"label": "Austin, TX", "evidence_text": "Austin office"}],
        }
        db.commit()

    assert "stale-profile-job" in set(_ids(client.get("/api/jobs/query", params={"work_mode": "onsite"})))
    assert "stale-profile-job" not in set(_ids(client.get("/api/jobs/query", params={"work_mode": "remote"})))


def test_jobs_endpoints_share_current_profile_metadata_and_drop_stale(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        job = _job(
            db,
            public_id="canonical-meta",
            title="Software Engineer",
            location="Palo Alto, CA",
            description="Collaborate with remote teams and contractors. Build products.",
        )
        fingerprint = source_fingerprint(job.title, job.description)
        _add_profile(
            db,
            job,
            fingerprint,
            work_mode="hybrid",
            employment_type="full_time",
            experience_level="senior",
        )

    def _meta_from_catalog():
        catalog = client.get("/api/jobs")
        assert catalog.status_code == 200
        return next(item for item in catalog.json() if item["id"] == "canonical-meta")

    def _meta_from_detail():
        detail = client.get("/api/jobs/canonical-meta")
        assert detail.status_code == 200
        return detail.json()

    def _meta_from_query():
        query = client.get("/api/jobs/query")
        assert query.status_code == 200
        return next(item["job"] for item in query.json()["items"] if item["job"]["id"] == "canonical-meta")

    catalog_job = _meta_from_catalog()
    detail_job = _meta_from_detail()
    query_job = _meta_from_query()
    for payload in (catalog_job, detail_job, query_job):
        assert payload["work_mode"] == "hybrid"
        assert payload["employment_type"] == "full_time"
        assert payload["opportunity_type"] == "role"

    assert "canonical-meta" in set(_ids(client.get("/api/jobs/query", params={"work_mode": "hybrid"})))
    assert "canonical-meta" in set(
        _ids(client.get("/api/jobs/query", params={"employment_type": "full_time"}))
    )
    assert "canonical-meta" in set(
        _ids(client.get("/api/jobs/query", params={"experience_level": "senior"}))
    )
    assert "canonical-meta" in set(_ids(client.get("/api/jobs/query", params={"opportunity": "role"})))
    assert "canonical-meta" not in set(
        _ids(client.get("/api/jobs/query", params={"opportunity": "internship"}))
    )

    with SessionLocal() as db:
        job = db.query(JobRecord).filter(JobRecord.public_id == "canonical-meta").one()
        job.description = "Updated posting. Collaborate with remote teams and contractors."
        db.commit()

    catalog_job = _meta_from_catalog()
    detail_job = _meta_from_detail()
    query_job = _meta_from_query()
    for payload in (catalog_job, detail_job, query_job):
        assert payload["work_mode"] != "hybrid"
        assert payload["employment_type"] != "full_time"
    assert "canonical-meta" not in set(_ids(client.get("/api/jobs/query", params={"work_mode": "hybrid"})))
    assert "canonical-meta" not in set(
        _ids(client.get("/api/jobs/query", params={"employment_type": "full_time"}))
    )
    assert "canonical-meta" not in set(
        _ids(client.get("/api/jobs/query", params={"experience_level": "senior"}))
    )
