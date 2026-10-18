# Screenshot inventory

Primary viewport: **1440×900**, light theme, `prefers-reduced-motion: reduce`, Playwright Chromium, no browser chrome, no unrelated tabs.

**Tagged release:** v1.0.0 at `b73a983ed3605d498aa90070c3b5f786a73bc525`. **Certified runtime** for Fill/isolation remains `7b6c3ee100ca4fe6399ac29441bece8df71783c7` and applies only to that revision.

**Showcase capture revision:** Portfolio production pass against mainline `9318c27` with a **brand-new isolated synthetic SQLite database**. Fit percentages are calculated from the synthetic résumé by production Fit V2, not hand-entered or hire probabilities. This showcase does not recertify the tagged v1.0.0 runtime or move the release tag.

Data: isolated SQLite from `scripts/seed_showcase_demo.py`. Not `data/careerpilot.db`. Provider calls are disabled by default; explicitly set `CAREERPILOT_SHOWCASE_LIVE=1` for configured live extraction/generation. Prepare copy is **illustrative seeded materials** unless the seeder reported live generation.

## Portfolio WebP set (primary)

| File | Demonstrates | Alt-text intent |
| --- | --- | --- |
| [01-overview.webp](./screenshots/01-overview.webp) | Dashboard Overview: next action, top matches, profile readiness | Overview dashboard with Harborline/Cedar Fit scores and Ready profile gates |
| [02-discover.webp](./screenshots/02-discover.webp) | Discover list + preview: Harborline stronger Fit vs Cedar partial Fit | Discover workspace with two synthetic internships and distinct Fit scores |
| [03-job-detail.webp](./screenshots/03-job-detail.webp) | Job Detail for Harborline intern | Job detail page for the synthetic Harborline internship |
| [04-match-evidence.webp](./screenshots/04-match-evidence.webp) | Open Python Evidence drawer with cited résumé excerpt | Python requirement supported by a cited fictional candidate project |
| [05-prepare.webp](./screenshots/05-prepare.webp) | Cover letter, recruiter message, eligibility/approval controls | Prepare page with Harborline materials and human approval controls |
| [06-tracker.webp](./screenshots/06-tracker.webp) | Tracker list: saved vs ready_to_apply; `applied` not claimed | Track list showing synthetic application states |
| [07-analytics.webp](./screenshots/07-analytics.webp) | Honest funnel: saved/generated/approved; applied/interview/offer at 0 | Analytics funnel with materials approved and applied/offer still zero |
| [08-extension.webp](./screenshots/08-extension.webp) | Illustrative compatibility mock of assisted Fill vs manual EEO | Illustrative mock of assisted Fill — not the extension runtime |

Matching PNG twins (`01-overview.png` … `08-extension.png`) are kept for archival/print use.

## Additional capture PNGs (legacy / detail)

| File | Demonstrates |
| --- | --- |
| [01-landing.png](./screenshots/01-landing.png) | Public landing |
| [02-profile-readiness.png](./screenshots/02-profile-readiness.png) | Profile gate detail |
| [04b-match-gap.png](./screenshots/04b-match-gap.png) | Preferred Docker gap (drawer closed) |
| [07-career-growth.png](./screenshots/07-career-growth.png) | Career Growth focus areas |
| [08-assisted-fill-boundary-mock.png](./screenshots/08-assisted-fill-boundary-mock.png) | Same mock source as `08-extension.webp` |

`08-extension.webp` / `08-assisted-fill-boundary-mock.png` are generated from `fixtures/generic-ats-form.html`. They are **not** screenshots of the shipped Chrome extension runtime and **not** live Greenhouse/Lever captures. Live Fill was certified separately on Chrome 152 (release gate A8) against real Greenhouse and Lever pages.

## Capture command

```bash
python scripts/capture_showcase_screenshots.py \
  --base-url http://127.0.0.1:5173
```

The script:

- Accepts only loopback `http://127.0.0.1`, `http://localhost`, or `http://[::1]`
- Logs in only as the synthetic showcase account from `scripts/seed_showcase_demo.py`
- Verifies that account, Jordan Avery, Harborline Analytics, Cedar & Pine Robotics, and `showcase-harborline-intern` before authenticated screenshots
- Captures Overview (`/dashboard`), Discover, Job Detail, Evidence, Prepare, Track, Analytics, Growth, and the Fill mock
- Exports the eight portfolio WebP names listed above
- Does not click Submit or type into EEO fields

## Image weight

WebP portfolio assets targeted under ~100 KB each. PNG sources under ~700 KB. Recapture at 1440×900; do not commit 4K captures or GIFs.
