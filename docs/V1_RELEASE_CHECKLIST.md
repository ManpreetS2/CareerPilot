# CareerPilot v1 release checklist

## Certification provenance

- **Certified runtime/product SHA:** `7b6c3ee100ca4fe6399ac29441bece8df71783c7` — A8 (Chrome 152 Greenhouse + Lever), A9 isolation/deletion, and Phase 6 adversarial audit. Fill, attachment, no-submit, EEO/manual fields, auth/session, and account deletion were certified on this SHA.
- **Phase 7 docs/version-metadata SHA:** `3196e18a8f1fb73795da26e5727311bca0c2cd6a` — PR #87. Sets explicit package/manifest/FastAPI versions to 1.0.0. Does not change ATS identity, fill/attachment, auth, grounding, or isolation behavior.
- Last-mile pre-tag edits are documentation/release-truth only. Tag the `main` merge commit after this checklist is on `main` and CI/Gitleaks are green on **that** SHA. Do not attribute A8/A9 to untested runtime.

Remaining public release work is **tag `v1.0.0` and create the GitHub Release** (Phase 8).

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
| A8 | PASS | Chrome 152, live Greenhouse + Lever. No Submit. EEO/terms/privacy remain manual. Resume attachment is verified from the live Resume/CV input or Resume/CV-group widget after the current attachment attempt. A matching filename alone is not proof. An unrelated or Cover Letter same-named filename is not proof. |
| A9 | PASS | Session isolation, IDOR fail-closed, account deletion, generic login errors. Isolated/temp SQLite only. |
| Phase 6 adversarial audit | PASS | Cross-feature try-to-break on the certified runtime SHA. No open P0/P1. |
| Phase 7 release-truth | PASS | Docs/version metadata on `3196e18a…`. |

## Remaining release action

1. Confirm this checklist and `README.md` still match shipped source.
2. Confirm CI and Full-history Gitleaks are green on the SHA to tag.
3. Tag `v1.0.0` on that exact `main` SHA.
4. Create the GitHub Release.

Do not tag with an open P0/P1. Do not claim a hosted SaaS. Do not claim every ATS is supported.

Dependabot dependency-floor/group updates opened after the release candidate are **post-v1** unless they fix a current high/critical issue on the shipped tree.

## Release invariants

- CareerPilot never submits an application. The human presses Submit on the ATS.
- Extension Fill never calls `submit()`, `requestSubmit()`, or Enter-to-submit.
- EEO / demographic fields stay manual. Terms/privacy/consent stay manual.
- Materials stay grounded, or are visibly marked as an explicit `grounding_override`.
- Approval requires explicit human eligibility confirmation and does not mark tracker `applied`.
- Resume attachment is truthful: verification uses the live Resume/CV input/widget after this attempt. A matching filename alone is not proof. Cover Letter or unrelated same-named text is not proof.
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
