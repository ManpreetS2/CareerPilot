# CareerPilot showcase package

Assets for a recruiter’s first minute on GitHub and an engineer’s follow-up inspection.

These files describe the **shipped v1.0.0 product**. They do not change runtime behavior.

## What is here

| File | Purpose |
| --- | --- |
| [demo-script.md](./demo-script.md) | 2–4 minute click-path and spoken beats. Complements [`docs/demo-runbook.md`](../demo-runbook.md). |
| [recruiter-walkthrough.md](./recruiter-walkthrough.md) | 30–60 second spoken story. |
| [technical-walkthrough.md](./technical-walkthrough.md) | 2–3 minute engineering walkthrough. |
| [portfolio-copy.md](./portfolio-copy.md) | Portfolio, resume, LinkedIn, and interview language. |
| [architecture.md](./architecture.md) | Compact architecture diagram (one local app, not microservices). |
| [screenshot-inventory.md](./screenshot-inventory.md) | What each image shows and how it was captured. |
| [visual-qa.md](./visual-qa.md) | Visual/accessibility notes from screenshot capture. |
| [post-v1-maintenance-triage.md](./post-v1-maintenance-triage.md) | Informational post-v1 items. Not part of this showcase’s runtime. |
| [screenshots/](./screenshots/) | Desktop PNG captures (1440×900). |
| [fixtures/generic-ats-form.html](./fixtures/generic-ats-form.html) | Synthetic ATS form used for the Fill-boundary image. |

## Released product state these assets demonstrate

| Item | Value |
| --- | --- |
| Repository | [ManpreetS2/CareerPilot](https://github.com/ManpreetS2/CareerPilot) |
| Tag | `v1.0.0` |
| Tagged commit | `b73a983ed3605d498aa90070c3b5f786a73bc525` |
| Certified runtime (A8 / A9 / Phase 6) | `7b6c3ee100ca4fe6399ac29441bece8df71783c7` |
| Release | https://github.com/ManpreetS2/CareerPilot/releases/tag/v1.0.0 |

The showcase branch may add documentation, screenshots, and an isolated demo seeder. It does not move the `v1.0.0` tag.

## How screenshots were generated

1. Seed an **isolated** SQLite file with `scripts/seed_showcase_demo.py` (refuses `data/careerpilot.db`).
2. Run backend and frontend against that database only.
3. Capture 1440×900 PNGs with `scripts/capture_showcase_screenshots.py` (Playwright, reduced motion, no Submit, no EEO fill).
4. The Fill image uses `fixtures/generic-ats-form.html` — a **compatibility demonstration**, not a live employer page and not an endorsement.

See [screenshot-inventory.md](./screenshot-inventory.md) for the exact commands.

## Synthetic data

All committed screenshots use:

- Email `demo.candidate@example.com`
- Name Jordan Avery
- Fictional companies Harborline Analytics and Cedar & Pine Robotics
- Posting text marked `DEMO / SYNTHETIC`

No real resume, phone number, API key, session cookie, private hostname, or production database path is included.

## Privacy rules for recapture

Do **not**:

- Point the seeder or capture script at `data/careerpilot.db`
- Use a real resume, real email, or live employer ATS page as a committed screenshot
- Show Tailscale hostnames, `.env` values, extension IDs, or unrelated browser chrome
- Click Submit, fill EEO/demographic fields, or acknowledge terms automatically
- Commit screen recordings into git

## Recapture later

```bash
python scripts/seed_showcase_demo.py --database "$TEMP/careerpilot-showcase/showcase.sqlite"
# Point DATABASE_URL at that file. Never data/careerpilot.db.
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
# other terminal
cd frontend && npm run dev
python scripts/capture_showcase_screenshots.py \
  --base-url http://127.0.0.1:5173 \
  --email demo.candidate@example.com \
  --password 'Showcase-Demo-Pass-1!' \
  --job-id showcase-harborline-intern
```

Use the same hostname for UI and API (`127.0.0.1` with `127.0.0.1`).
