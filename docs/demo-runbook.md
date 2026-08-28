# CareerPilot demo runbook (preview database only)

Use `sqlite:///./data/careerpilot-demo-preview.db`. Never run this against `data/careerpilot.db`.

## Fresh preview

1. Confirm `.env` `DATABASE_URL` points at the preview file.
2. Start API without `--reload` on Windows: `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`
3. Start frontend: `npm run dev` in `frontend/`
4. Sign in as the preview account.
5. Resume upload → grounded candidate profile.
6. Find Jobs. Existing listings stay visible. Progress ends only when the API returns.
7. List rows show **Potential Match** until a job has `score_kind=verified`.
8. Open one software/data intern that CareerPilot verified. Confirm Verified Fit %, eligibility, and original posting text still visible.
9. Open or fixture a final-year/recent-grad posting the candidate does not satisfy. Confirm Likely ineligible and not Strong Match.
10. Prepare Application only after reviewing eligibility. CareerPilot never submits.
11. Interview prep stays on Job Detail.
12. Autofill is review-only / no-submit.

## Rollback

- Do not merge stacked PRs automatically.
- PR #28 (`feat/job-discovery-progress`) stays the Fit V2 base.
- This branch (`feat/full-job-requirements-foundation`) can be abandoned without reverting #28.
- Preview DB is disposable. Production `data/careerpilot.db` must not be migrated by this work.
