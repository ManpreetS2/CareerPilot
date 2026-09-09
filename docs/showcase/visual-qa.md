# Visual QA — Phase 9 showcase capture

Screens inspected while capturing the v1.0.0 showcase package. Light theme desktop PNGs are committed; dark, 390, 768, and 1280 were probed and not all committed.

Format: SCREEN / ISSUE / SEVERITY / EVIDENCE / FIXED or DEFERRED / REASON.

---

SCREEN: Track Kanban at 1440×900
ISSUE: Ready-to-apply column sits off-canvas; board uses internal horizontal scroll.
SEVERITY: P2
EVIDENCE: First Kanban capture showed only Saved; intern `ready_to_apply` was in a later column. CSS `.kanban-board { overflow-x: auto }` and `ApplicationsPage.test.tsx` already require in-page horizontal scroll.
FIXED / DEFERRED: DEFERRED (product). Showcase capture uses List view (`06-track.png`).
REASON: Existing layout contract, not a regression to “fix” by changing tracker behavior.

---

SCREEN: Prepare at 1440×900
ISSUE: Approval rail, eligibility checkbox, and resume versions sit below the fold under the match-summary card.
SEVERITY: P2
EVIDENCE: Unscrolled Prepare capture showed Fit summary only; approval is the human-gate story.
FIXED / DEFERRED: FIXED for screenshots — capture script scrolls `[data-testid=approval-rail]`. Product layout unchanged.
REASON: Scrolling is expected; changing Prepare persistence or approval flow would be a runtime change.

---

SCREEN: Job Detail default tab
ISSUE: Overview tab is the default; Evidence (the showcase story) is one click away.
SEVERITY: P3
EVIDENCE: First `04-match-evidence.png` showed posting text, not factor rows.
FIXED / DEFERRED: FIXED for screenshots — capture clicks the Evidence tab. Product default tab unchanged.
REASON: Default Overview is reasonable for posting context; do not change analysis routing for marketing.

---

SCREEN: Career Growth
ISSUE: Empty state when jobs exist but Match Evidence has not been aggregated.
SEVERITY: P3 (honest empty, not a defect)
EVIDENCE: `07-career-growth.png` — “no current Match Evidence to aggregate.”
FIXED / DEFERRED: DEFERRED
REASON: Inventing growth insights would violate grounding. Caption the screenshot as refusal-to-invent.

---

SCREEN: Discover job meta line
ISSUE: Harborline intern shows `Remote · Remote · Internship` when location and work mode are both Remote.
SEVERITY: P3
EVIDENCE: `03-discover.png` and 390 probe. `JobCard` joins `location`, `workLabel(job)`, employment.
FIXED / DEFERRED: DEFERRED
REASON: Literal join of two real fields. Deduping could hide work mode on other jobs. Seed could use a non-duplicative location later; no runtime change in this PR.

---

SCREEN: Discover job cards (accessibility)
ISSUE: The select-job control’s accessible name concatenates title, company, location, and badges (Playwright listed the whole card as a button name).
SEVERITY: P3
EVIDENCE: 390 probe `getByRole('button')` names.
FIXED / DEFERRED: DEFERRED
REASON: Pre-existing JobCard pattern. Changing it is an a11y code fix, not docs. Separate from showcase assets.

---

SCREEN: Landing / Login / Signup animation
ISSUE: None blocking. Dotted globe and assembling lattice sit in `pointer-events: none` frames (`.hero-globe-frame`, `AuthFrame`). Reduced-motion capture used `emulate_media(reduced_motion=reduce)`. Dark login globe remains visible, not a black hole.
SEVERITY: P3 (watch)
EVIDENCE: `frontend/src/index.css` `.hero-globe-frame { pointer-events: none }`; dark login QA screenshot (not committed). CTA hit-test on `/` after an authenticated session is not applicable (landing is public; authenticated capture continued from cookie).
FIXED / DEFERRED: DEFERRED
REASON: No presentation defect requiring a behavior change. Native 200% browser zoom remains a human spot-check (CSS zoom probe showed no horizontal overflow).

---

SCREEN: 390 Discover
ISSUE: Long Cedar title wraps; second card company is below the fold, not overflowing the viewport.
SEVERITY: P3
EVIDENCE: overflow probe `scrollWidth - innerWidth = 0` at 390/768/1280/1440 for `/`, `/login`, `/signup`, `/jobs`, `/track`, `/profile`, `/analytics`.
FIXED / DEFERRED: DEFERRED
REASON: Fold vs overflow. Wrapping already uses `wrap-anywhere`.

---

SCREEN: Analytics funnel
ISSUE: Applied / interviewing / offer remain 0.
SEVERITY: none
EVIDENCE: `06b-analytics.png`
FIXED / DEFERRED: n/a
REASON: Seed must not fabricate offers. Keep zeros.

---

SCREEN: Extension Fill screenshot
ISSUE: Not a live Greenhouse/Lever page; fixture mock to avoid employer-logo endorsement.
SEVERITY: n/a
EVIDENCE: `08-extension-fill.png` + `fixtures/generic-ats-form.html`
FIXED / DEFERRED: FIXED (intentional)
REASON: Compatibility demonstration. Live A8 remains the Fill certification. Submit is visible and was not clicked. EEO field left blank.

---

SCREEN: Dark / light
ISSUE: Dark login/signup remain readable; committed README shots stay light for consistency.
SEVERITY: P3
EVIDENCE: Dark login probe.
FIXED / DEFERRED: DEFERRED for committed set
REASON: One theme in the public screenshot strip. Dark is supported.

No P0 or P1 visual defects. No separate visual-fix PR: remaining items are either by-design, screenshot-script issues already addressed, or P3 presentation notes that would change product UI without a behavior-safe grouping.
