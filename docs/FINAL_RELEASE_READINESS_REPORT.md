# CareerPilot — Final Release Readiness Report

**Date:** 2026-10-16
**Mainline SHA audited:** `ea13536ded11a7b41b48ce8029fa5104be2625f2`
**v1.0.0 tag (unchanged):** `b73a983ed3605d498aa90070c3b5f786a73bc525`
**Certified runtime SHA (unchanged):** `7b6c3ee100ca4fe6399ac29441bece8df71783c7` (A8/A9/Phase 6)

## 1. Executive summary

Post-merge main at `ea13536` includes backend remediation (#140) and Chrome extension reliability (#141). Automated backend, frontend, extension, Chromium-fixture, CI, and Gitleaks gates are green. No new critical runtime bugs were confirmed during this sprint’s fixture-level Chromium QA.

**Recommendation: CONDITIONAL GO** for a public portfolio showcase of current mainline, with the following explicit conditions:

1. Showcase docs PR #131 should land (rebased, mergeable) so GitHub README/LinkedIn copy match `ea13536`.
2. Do **not** claim a fresh live A8 ATS recertification — interactive Greenhouse/Lever Fill on employer pages was not fully re-run in a human Chrome session this sprint (fixture Chromium + GET-only live probe only).
3. Operators with a pre-#140 personal DB should dry-run the preference-skill audit (#142) before trusting historical Fit numbers.
4. Leave broad Dependabot groups (#138/#139) for a separate maintenance window.

## 2. Confirmed bugs discovered (this sprint)

| ID | Severity | Finding | Status |
| --- | --- | --- | --- |
| — | — | No new critical extension/runtime bugs confirmed beyond what #140/#141 already fixed | N/A |

Pre-existing issues already fixed on main before this report:

| Source | Issue | Fix |
| --- | --- | --- |
| #140 | Preference skills merged into `Candidate.skills`, inflating Fit | Stop merge; regression tests |
| #141 | Greenhouse react-select option IDs wrong | Strip `-input` / use `aria-controls` |
| #141 | Tab navigate mid-Fill could inject stale tab | `tab-guard.ts` document/URL/active checks |
| #141 | Resume attach failure aborted safe text fill | Partial fill + manual-upload warning |

## 3. Fixes / deliverables implemented this sprint

| Concern | PR | Contents |
| --- | --- | --- |
| Extension Chromium coverage | [QA branch / pending PR](https://github.com/ManpreetS2/CareerPilot/compare/main...cursor/release-readiness-qa-e27c) | Expanded `tests/test_extension_chromium_integration.py` (permission ungated start, attach failure vs safe text, Lever no-submit/EEO, live GET probe notes) |
| Historical Fit integrity | [#142](https://github.com/ManpreetS2/CareerPilot/pull/142) | `scripts/audit_preference_skill_contamination.py` dry-run / opt-in `--apply --confirm` |
| Showcase docs | [#131](https://github.com/ManpreetS2/CareerPilot/pull/131) | Rebased onto `ea13536`; LinkedIn/README provenance for #140/#141 |

No production `data/careerpilot.db` mutations. No `v1.0.0` tag moves. No paid LLM calls.

## 4. Chrome / Greenhouse / Lever testing evidence

### Automated (executed)

| Layer | Evidence |
| --- | --- |
| Extension unit/jsdom | `TZ=Asia/Kolkata npm test` → **123 passed** (includes react-select, tab-guard, attach/partial-fill races) |
| Chromium + unpacked extension | `pytest tests/test_extension_chromium_integration.py` → **10 passed** |
| Coverage | Service worker + sidepanel load; Greenhouse react-select graduation/enrollment/degree/sponsorship; native Greenhouse selects; Lever text fields; PDF attach success; attach failure/manual/unsupported still fills safe text; optional ATS permissions start ungated; privacy/EEO untouched; Submit never pressed |
| Live site | httpx GET `https://boards.greenhouse.io/stripe` → HTTP 200 (reachability only). **No fill, no submit, no EEO.** Notes: `/tmp/cursor/extension-live-qa-notes.txt` |

### Not claimed as live interactive QA

Full human Chrome session against a real employer apply form (install unpacked extension, login cookie, Fill, attach PDF/DOCX, tab switch mid-fill) was **not** completed in this cloud environment. A8 on `7b6c3ee…` remains the last certified live Fill.

### Operator checklist (if you re-validate live)

1. `cd browser-extension && npm ci && npm run build`
2. Load unpacked `browser-extension/` in Chrome → Reload after every rebuild
3. Run API on `127.0.0.1:8000`; set exact `EXTENSION_ORIGIN=chrome-extension://<id>`
4. Log into web app on the **same host** as the API cookie
5. Open a tracked Greenhouse + Lever apply URL you own/authorized
6. Preview → Fill safe fields → confirm EEO/terms untouched → confirm Submit never clicked
7. Fail attach intentionally (deny file permission / unsupported field) → confirm manual warning + text still filled
8. Switch tabs mid-download → confirm abort, no wrong-page fill
Capture screenshots for any failure; do not submit applications.

## 5. Historical data audit findings

- Root cause (pre-#140): preference save merged `skill_preferences` into `Candidate.skills`.
- Current code path: merge removed; regression in `tests/test_preference_skills_not_resume_evidence.py`.
- Recovery tool (#142): classifies intersection skills as `preference_only_suspect` (no other profile evidence) vs `ambiguous_overlap` (also in experience/projects/etc.).
- Ambiguous overlaps are **never** auto-deleted.
- `--apply --confirm` only removes high-confidence preference-only skills; Fit restales via candidate fingerprint.
- Production DB was **not** opened. Operators should copy with `scripts/make_temp_qa_db.py` (or an authorized copy path that is not silently assumed contaminated) before auditing.

## 6. Privacy and security verification

| Check | Result |
| --- | --- |
| `tests/test_cross_user_isolation.py` | Pass (run with chromium/privacy suite) |
| `tests/test_privacy_security.py` | Pass |
| Account deletion / legacy preferences coverage from #140 | Present on main |
| `python scripts/check_tracked_secrets.py` | Pass |
| Mapped paths | **131 valid / 0 missing** |
| Post-merge Security (Gitleaks) on `ea13536` | [success](https://github.com/ManpreetS2/CareerPilot/actions/runs/38867993396) |
| Post-merge CI on `ea13536` | [success](https://github.com/ManpreetS2/CareerPilot/actions/runs/38867993318) |

## 7. Test totals and CI links

| Suite | Result |
| --- | --- |
| Backend `pytest` | **1673 collected, exit 0** (isolated SQLite) |
| Frontend | typecheck + build + **294** tests pass |
| Extension | typecheck + build + **123** tests pass |
| Chromium extension integration | **10** pass |
| CI `ea13536` | https://github.com/ManpreetS2/CareerPilot/actions/runs/38867993318 |
| Security `ea13536` | https://github.com/ManpreetS2/CareerPilot/actions/runs/38867993396 |
| CI `#140` merge `fb07398` | https://github.com/ManpreetS2/CareerPilot/actions/runs/38867061395 |

## 8. GitHub PR links and merge status

| PR | Topic | Status |
| --- | --- | --- |
| [#140](https://github.com/ManpreetS2/CareerPilot/pull/140) | Backend bug remediation | **Merged** → `fb07398` |
| [#141](https://github.com/ManpreetS2/CareerPilot/pull/141) | Extension reliability | **Merged** → `ea13536` |
| [#131](https://github.com/ManpreetS2/CareerPilot/pull/131) | LinkedIn/showcase docs | **Open, mergeable**, rebased onto `ea13536` |
| [#142](https://github.com/ManpreetS2/CareerPilot/pull/142) | Preference-skill audit tool | **Open (draft)** |
| QA branch `cursor/release-readiness-qa-e27c` | Chromium coverage + this report | **Open for PR** |

### Dependabot triage (not merged)

| PR | Assessment | Action |
| --- | --- | --- |
| [#133](https://github.com/ManpreetS2/CareerPilot/pull/133) httpx floor ≥0.28.1 | Low risk; already installed 0.28.1; CI green | Optional narrow merge later |
| [#134](https://github.com/ManpreetS2/CareerPilot/pull/134) pydantic-settings floor | Low risk; installed 2.16.0 | Optional later |
| [#137](https://github.com/ManpreetS2/CareerPilot/pull/137) actions/setup-node 7.1.0 | Low risk CI tooling; CI green | Optional later |
| [#138](https://github.com/ManpreetS2/CareerPilot/pull/138) frontend 18-package group | Medium visual/breakage risk | **Do not merge** for showcase week |
| [#139](https://github.com/ManpreetS2/CareerPilot/pull/139) extension 5-package group | DevDependency noise | **Do not merge** until dedicated extension QA |

No high/critical production CVE was identified that requires emergency dependency landing before showcase.

## 9. Remaining limitations / blocked checks

- Interactive live Greenhouse/Lever Fill in a human Chrome profile: **unverified this sprint** (GET-only reachability ≠ Fill certification).
- Personal/historical `data/careerpilot.db` contamination: **unknown until operator dry-run** of #142.
- Showcase screenshots are synthetic / may lag newest UI polish.
- Not a hosted SaaS; no Chrome Web Store listing; Assisted Fill is Greenhouse/Lever only.
- Broad Dependabot groups deferred.
- Cloud agent cannot complete your personal login cookie / side-panel gesture flows without your browser.

## 10. GO / CONDITIONAL GO / NO-GO

### CONDITIONAL GO for showcasing latest mainline (`ea13536`)

Safe to show as a **local/self-hostable portfolio product** with accurate docs once #131 merges, provided public claims stay within:

- Never auto-applies; human Submit only
- Greenhouse/Lever assisted Fill only
- A8 live certification remains the historical SHA `7b6c3ee…`
- Current mainline hardening (#140/#141) is automated + fixture-Chromium verified, not a replacement A8 live recert

**Not NO-GO:** no confirmed critical open runtime bugs; required CI/Security green; privacy isolation tests green.

**Not unconditional GO:** live interactive ATS Fill and personal-DB preference-skill audit still need operator action if those claims are made absolute.
