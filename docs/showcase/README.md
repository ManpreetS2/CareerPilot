# CareerPilot showcase package

Assets for a recruiter’s first minute on GitHub and an engineer’s follow-up inspection.

These files support a **portfolio showcase of the current mainline product**. They do not change production generation, do not move tags, and do not recertify runtime.

## What is here

| File | Purpose |
| --- | --- |
| [video/careerpilot-demo.mp4](./video/careerpilot-demo.mp4) | ~85s, 1920×1080, 30 fps silent-friendly demo from real browser footage |
| [screenshots/](./screenshots/) | Eight WebP portfolio assets (`01-overview.webp` … `08-extension.webp`) plus PNG sources |
| [architecture/careerpilot-architecture.svg](./architecture/careerpilot-architecture.svg) | Presentation architecture diagram ([`.mmd` source](./architecture/careerpilot-architecture.mmd)) |
| [portfolio-summary.md](./portfolio-summary.md) | One-pager + résumé bullets for personal portfolios |
| [demo-script.md](./demo-script.md) | Spoken walkthrough complementary to the rendered video |
| [recruiter-walkthrough.md](./recruiter-walkthrough.md) | 30–60 second spoken story |
| [technical-walkthrough.md](./technical-walkthrough.md) | 2–3 minute engineering walkthrough |
| [portfolio-copy.md](./portfolio-copy.md) | Portfolio, resume, LinkedIn, and interview language |
| [architecture.md](./architecture.md) | Compact architecture notes (one local app, not microservices) |
| [screenshot-inventory.md](./screenshot-inventory.md) | What each image shows and how it was captured |
| [visual-qa.md](./visual-qa.md) | Visual/accessibility notes from screenshot capture |
| [fixtures/generic-ats-form.html](./fixtures/generic-ats-form.html) | Illustrative ATS form + side-panel mock for the Fill-boundary image |

## Released product vs this showcase revision

| Item | Value |
| --- | --- |
| Repository | [ManpreetS2/CareerPilot](https://github.com/ManpreetS2/CareerPilot) |
| Tagged release | `v1.0.0` at `b73a983ed3605d498aa90070c3b5f786a73bc525` |
| Certified runtime (A8 / A9 / Phase 6) | `7b6c3ee100ca4fe6399ac29441bece8df71783c7` — that revision only |
| Product baseline for this showcase pass | `9318c27` (`origin/main` when portfolio production started) |
| Release | https://github.com/ManpreetS2/CareerPilot/releases/tag/v1.0.0 |

The tagged **v1.0.0** GitHub Release and its A8/A9/Phase 6 certification stay historical. Screenshots and the demo video are a **newer showcase revision** of later mainline UI. They do not move the `v1.0.0` tag and they do not inherit certification from `7b6c3ee`.

Public source is **source-visible**, not open source. Setup instructions in the root README are for authorized operators. LICENSE still requires prior written permission to run or deploy.

## Portfolio screenshot set (WebP)

| File | View |
| --- | --- |
| [01-overview.webp](./screenshots/01-overview.webp) | Dashboard / Overview |
| [02-discover.webp](./screenshots/02-discover.webp) | Discover Jobs |
| [03-job-detail.webp](./screenshots/03-job-detail.webp) | Job Detail |
| [04-match-evidence.webp](./screenshots/04-match-evidence.webp) | Fit Score + Match Evidence |
| [05-prepare.webp](./screenshots/05-prepare.webp) | Application Preparation |
| [06-tracker.webp](./screenshots/06-tracker.webp) | Application Tracker |
| [07-analytics.webp](./screenshots/07-analytics.webp) | Analytics |
| [08-extension.webp](./screenshots/08-extension.webp) | Illustrative Fill boundary (not live ATS) |

PNG originals remain alongside for archival capture. See [screenshot-inventory.md](./screenshot-inventory.md).

## Demo video

[`video/careerpilot-demo.mp4`](./video/careerpilot-demo.mp4) — Playwright-captured real UI + FFmpeg edit (title cards, captions, soft fades). Sequence: profile → discover → evidence → prepare → track → analytics → illustrative Fill boundary → stack/GitHub close. Does **not** claim applications were submitted or that the Fill scene is a live employer page.

Recreate:

```bash
python scripts/seed_showcase_demo.py --database "$TEMP/careerpilot-showcase/showcase.sqlite"
# Point DATABASE_URL at that file. Never data/careerpilot.db.
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
cd frontend && npm run dev -- --host 127.0.0.1 --port 5173
python scripts/produce_showcase_demo.py --base-url http://127.0.0.1:5173
```

## How screenshots were generated

1. Seed a **brand-new** isolated SQLite file with `scripts/seed_showcase_demo.py` (refuses `data/careerpilot.db`, production-looking names, and any path that already exists). Provider calls are disabled by default; `CAREERPILOT_SHOWCASE_LIVE=1` explicitly opts in when providers are configured. Automated tests never call live providers.
2. Run backend and frontend against that database only (authorized local use).
3. Capture 1440×900 PNGs with `scripts/capture_showcase_screenshots.py` (loopback-only, synthetic showcase identity, Playwright, reduced motion, no Submit, no EEO fill), then export WebP portfolio names.
4. The Fill image uses `fixtures/generic-ats-form.html` — an **illustrative compatibility mock**, not the shipped extension runtime, not a live employer page, and not an endorsement. Live Greenhouse/Lever Fill was certified on Chrome 152 (A8) at `7b6c3ee`.

Fit scores are calculated at seed time by the production scoring engine from a parsed synthetic résumé. They are not hardcoded. Prepare materials are **illustrative seeded materials** unless the seeder printed `materials_source=live_generation`. Do not call seeded text live-generated.

## Synthetic data

All committed screenshots and the demo video use:

- Email `demo.candidate@example.com`
- Name Jordan Avery
- Fictional companies Harborline Analytics and Cedar & Pine Robotics
- Posting text marked `DEMO / SYNTHETIC`

No real resume, phone number, API key, session cookie, private hostname, or production database path is included.

## Privacy rules for recapture

Do **not**:

- Point the seeder at `data/careerpilot.db` or at any file that already exists
- Point the capture script at a non-loopback URL or a real account
- Use a real resume, real email, or live employer ATS page as a committed screenshot
- Show Tailscale hostnames, `.env` values, extension IDs, or unrelated browser chrome
- Click Submit, fill EEO/demographic fields, or acknowledge terms automatically
- Commit screen recordings that contain real personal data
