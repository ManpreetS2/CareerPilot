# CareerPilot v1 release checklist

Certification through A9 and the Phase 6 adversarial audit is complete on
`7b6c3ee100ca4fe6399ac29441bece8df71783c7`. Remaining public release work is
**tag `v1.0.0` and create the GitHub Release** (Phase 8). Do not tag from this
docs snapshot until Phase 8.

Automation (pytest, frontend/extension tests, CI, Gitleaks) cannot replace
live ATS or privacy QA. Re-run those only if fill, attachment, session, or
deletion behavior changes.

## Certification status

| Gate | Result | Notes |
| --- | --- | --- |
| A1 | PASS | |
| A2 | PASS | |
| A3 | PASS | |
| A4 | PASS | |
| A5 | PASS | |
| A6 | PASS | |
| A7 | PASS | |
| A8 | PASS | Chrome 152, live Greenhouse + Lever. No Submit. EEO/terms/privacy remain manual. Resume attachment is verified on the page, not by filename match. |
| A9 | PASS | Session isolation, IDOR fail-closed, account deletion, generic login errors. Isolated/temp SQLite only. |
| Phase 6 adversarial audit | PASS | Cross-feature try-to-break on the SHA above. No open P0/P1. |

## Remaining release action

1. Confirm this checklist and `README.md` still match shipped source.
2. Confirm CI and Full-history Gitleaks are green on the SHA to tag.
3. Tag `v1.0.0`.
4. Create the GitHub Release.

Do not tag with an open P0/P1. Do not claim a hosted SaaS. Do not claim every ATS is supported.

## Release invariants

- CareerPilot never submits an application. The human presses Submit on the ATS.
- Extension Fill never calls `submit()`, `requestSubmit()`, or Enter-to-submit.
- EEO / demographic fields stay manual. Terms/privacy/consent stay manual.
- Materials stay grounded, or are visibly marked as an explicit `grounding_override`.
- Approval requires explicit human eligibility confirmation and does not mark tracker `applied`.
- Resume attachment is truthful: a matching filename alone is not proof.
- Greenhouse/Lever identity uses ATS posting identity, never fuzzy title/company matching.
- User-scoped rows (including analytics events, saved searches, and resume-version files) never leak across users.
- Account deletion removes owner-scoped private data and sessions; shared `JobRecord` remains.
- Destructive QA and automated tests use isolated/temp/copied SQLite only — never `data/careerpilot.db`.
- Ordinary page loads stay read-only unless explicitly documented (Find Jobs may persist deterministic scores after an explicit click).
- Required CI: `.github/workflows/ci.yml` and Full-history Gitleaks (`.github/workflows/security.yml`).

## Canonical web workflow (certified)

- Fresh signup → onboarding/profile (minimum profile) → Overview → Discover → Analyze → Prepare → Track
- Incomplete profile cannot scout; completing the minimum profile unlocks Discover without a full reload
- Logout / login as a second user never flashes the first user's profile, scores, tracker, analytics, or saved searches
- Discover saved-search unseen counts are owner-only and require profile readiness to create
- Track follow-up `.ics` / Google Calendar export is owner-only (file/URL only; no calendar OAuth, no email)
- Analytics (`/analytics`) is a read-only funnel of the signed-in user's events; it must not scout, score, or call providers

## Extension (Chrome unpacked, certified A8)

- Load `browser-extension/` as an unpacked extension against local API (`127.0.0.1` preferred)
- Real Greenhouse posting: supported path, fill preview, **never** clicks Submit
- Real Lever posting: same
- Approved owned resume attachment works where the browser/ATS allows it
- If programmatic attach is blocked, the panel says to upload manually (not "Unsupported")
- EEO / demographic questions stay untouched / manual

## Visual / a11y (frozen black / white / violet system)

Certified during release QA at 1440 / 1280 / 768 / 390, dark/light, public 200% zoom, and keyboard skip-to-content. Re-check after UI changes:

- Landing, Login, Signup, Onboarding, Overview, Discover, Job Detail, Analyze/Match/Evidence, Prepare, Interview (job-contextual), Track, Growth, Analytics, Profile, Resume, Settings, Privacy
- Keyboard navigation with a visible focus ring
- `prefers-reduced-motion: reduce`

## Privacy

- `/privacy` is reachable signed out
- Delete account removes that user's private records and revokes their sessions, including saved searches, saved-search matches, analytics events, and resume-version files
- Shared job catalog rows remain
- Login errors stay generic (no "this email exists" on failed login)

Passing unit tests is not a substitute for the live ATS and isolation checks above when those surfaces change.
