# Screenshot inventory

Primary viewport: **1440×900**, light theme, `prefers-reduced-motion: reduce`, Playwright Chromium, no browser chrome, no unrelated tabs.

Source product: CareerPilot **v1.0.0** (`b73a983ed3605d498aa90070c3b5f786a73bc525`). Certified runtime for Fill/isolation remains `7b6c3ee100ca4fe6399ac29441bece8df71783c7`.

Data: isolated SQLite from `scripts/seed_showcase_demo.py`. Not `data/careerpilot.db`.

## Committed images

| File | Demonstrates | Alt-text intent |
| --- | --- | --- |
| [01-landing.png](./screenshots/01-landing.png) | Public landing: grounded job search, never auto-submitted, dotted globe | Landing page with CareerPilot headline, Get Started / Sign In, and dotted globe |
| [02-profile-readiness.png](./screenshots/02-profile-readiness.png) | Profile gate: identity, grounded evidence, target role all Ready | Profile page showing Discover unlocks only after identity, evidence, and target role |
| [03-discover.png](./screenshots/03-discover.png) | Discover list + preview: synthetic internships, Potential Match, no fake offers | Discover workspace with two synthetic internships and a Potential Match preview |
| [04-match-evidence.png](./screenshots/04-match-evidence.png) | Analyze → Evidence: satisfied Python/SQL, Docker not enough evidence | Job analysis Evidence tab citing Python and SQL, Docker marked not enough evidence |
| [05-prepare.png](./screenshots/05-prepare.png) | Approved grounded materials, eligibility confirmation, immutable resume version | Prepare page with approved materials, eligibility checkbox, and resume version 1 |
| [06-track.png](./screenshots/06-track.png) | Tracker list: saved vs ready_to_apply; follow-up export; `applied` not claimed | Track list showing one saved role and one approved ready-to-apply role |
| [06b-analytics.png](./screenshots/06b-analytics.png) | Honest funnel: saved/generated/approved, applied/interview/offer at 0 | Analytics funnel with materials approved and applied/offer still zero |
| [07-career-growth.png](./screenshots/07-career-growth.png) | Growth refuses to invent insights without stored Match Evidence | Career Growth empty state asking to analyze jobs rather than fabricating advice |
| [08-extension-fill.png](./screenshots/08-extension-fill.png) | Compatibility demo: assisted fields vs manual EEO; Submit visible, not clicked | Side-by-side synthetic application form and CareerPilot Fill preview that never submits |

`08-extension-fill.png` is a **fixture mock** (`fixtures/generic-ats-form.html`), not a live Greenhouse/Lever capture and not an employer endorsement. Live Fill was certified separately on Chrome 152 (release gate A8).

## Capture command

```bash
python scripts/capture_showcase_screenshots.py \
  --base-url http://127.0.0.1:5173 \
  --email demo.candidate@example.com \
  --password 'Showcase-Demo-Pass-1!' \
  --job-id showcase-harborline-intern
```

The script:

- Does not click Submit
- Does not type into EEO fields
- Opens Evidence on Job Detail
- Scrolls Prepare to the approval rail
- Uses Track **List** view so both seeded rows are visible (Kanban columns scroll horizontally by design)

## Image weight

Ordinary PNGs targeted under 700 KB. Recapture at 1440×900; do not commit 4K captures or GIFs.
