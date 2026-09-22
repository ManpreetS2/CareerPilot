# Screenshot inventory

Primary viewport: **1440×900**, light theme, `prefers-reduced-motion: reduce`, Playwright Chromium, no browser chrome, no unrelated tabs.

**Tagged release:** v1.0.0 at `b73a983ed3605d498aa90070c3b5f786a73bc525`. **Certified runtime** for Fill/isolation remains `7b6c3ee100ca4fe6399ac29441bece8df71783c7` and applies only to that revision.

**Showcase capture revision:** Discover, cited Python Evidence, separate Docker-gap Evidence, Track, and Analytics were recaptured from the PR #114 branch against a **brand-new isolated synthetic SQLite database** after the PR #113 fixes. Other screenshots retain their previous mainline capture revision. The 96%/62% percentages are calculated from the synthetic résumé by production Fit V2, not hand-entered or hire probabilities. This showcase does not recertify the tagged v1.0.0 runtime or move the release tag.

Data: isolated SQLite from `scripts/seed_showcase_demo.py`. Not `data/careerpilot.db`. Fit scores are production Fit V2 results for the synthetic Jordan Avery résumé. Provider calls are disabled by default; explicitly set `CAREERPILOT_SHOWCASE_LIVE=1` for configured live extraction/generation. Prepare copy is **illustrative seeded materials** unless the seeder reported live generation.

## Committed images

| File | Demonstrates | Alt-text intent |
| --- | --- | --- |
| [01-landing.png](./screenshots/01-landing.png) | Public landing: PublicStage glass card, no globe or lattice, never auto-submitted | Landing page with CareerPilot headline, Get Started / Sign In, and a PublicStage summary card |
| [02-profile-readiness.png](./screenshots/02-profile-readiness.png) | Profile gate: identity, grounded evidence, target role all Ready | Profile page showing Discover unlocks only after identity, evidence, and target role |
| [03-discover.png](./screenshots/03-discover.png) | Discover list + preview: Harborline stronger Fit vs Cedar partial Fit; `Remote · Internship` vs `Portland, OR · Hybrid · Internship`; no fake offers | Discover workspace with two synthetic internships and distinct Fit scores |
| [04-match-evidence.png](./screenshots/04-match-evidence.png) | Open Python Evidence drawer: employer claim and exact stored synthetic résumé excerpt are visible; background is intentionally blurred by the dialog | Python requirement supported by a cited fictional candidate project |
| [04b-match-gap.png](./screenshots/04b-match-gap.png) | Closed drawer: required Python/SQL/FastAPI supported; preferred Docker has not enough evidence; posting has no recorded live check | Python, SQL and FastAPI satisfy required skills, while preferred Docker has no supporting candidate evidence |
| [05-prepare.png](./screenshots/05-prepare.png) | Cover letter, recruiter message, eligibility/approval controls, Harborline intern; seeded unless live generation was verified | Prepare page with Harborline materials and human approval controls |
| [06-track.png](./screenshots/06-track.png) | Tracker list: saved vs ready_to_apply; follow-up export; `applied` not claimed | Track list showing one saved role and one approved ready-to-apply role |
| [06b-analytics.png](./screenshots/06b-analytics.png) | Honest funnel: saved/generated/approved, applied/interview/offer at 0 | Analytics funnel with materials approved and applied/offer still zero |
| [07-career-growth.png](./screenshots/07-career-growth.png) | Three focus areas from two analyzed synthetic jobs, including Docker and AWS gaps; no candidate skills invented | Career Growth identifying Docker and AWS evidence gaps across two saved synthetic roles |
| [08-assisted-fill-boundary-mock.png](./screenshots/08-assisted-fill-boundary-mock.png) | Illustrative compatibility mock of assisted Fill vs manual EEO; Submit visible, not clicked | Illustrative mock of assisted Fill on a synthetic form — not the extension runtime |

This file is an **illustrative compatibility mock** generated from `fixtures/generic-ats-form.html`. It is **not** a screenshot of the shipped Chrome extension runtime and **not** a live Greenhouse/Lever capture. It is not an employer endorsement. Live Fill was certified separately on Chrome 152 (release gate A8) against real Greenhouse and Lever pages.

## Capture command

```bash
python scripts/capture_showcase_screenshots.py \
  --base-url http://127.0.0.1:5173
```

The script:

- Accepts only loopback `http://127.0.0.1`, `http://localhost`, or `http://[::1]`
- Logs in only as the synthetic showcase account from `scripts/seed_showcase_demo.py`
- Verifies that account, Jordan Avery, Harborline Analytics, Cedar & Pine Robotics, and `showcase-harborline-intern` before authenticated screenshots
- Does not take `--email` / `--password` for an arbitrary account
- Does not click Submit
- Does not type into EEO fields
- Opens Discover and selects the Harborline intern so the card and preview both show `Remote · Internship` and the stronger Fit
- Cedar card is expected to show `Portland, OR · Hybrid · Internship` and the partial Fit
- Captures the Python evidence drawer separately from the unblurred Docker gap, since opening a modal blurs underlying rows
- Scrolls Prepare to the Cover letter heading (`block: start`) so the letter, recruiter message, source-traceability label, and approval rail can share the 900px frame
- Uses Track **List** view so both seeded rows are visible (Kanban columns scroll horizontally by design)
- Writes `08-assisted-fill-boundary-mock.png` from the local HTML fixture, labeled as a mock

## Image weight

Ordinary PNGs targeted under 700 KB. Recapture at 1440×900; do not commit 4K captures or GIFs.
