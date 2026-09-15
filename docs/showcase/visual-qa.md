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
ISSUE: Recapture on the current tree shows two analyzed jobs and “No repeated skill gaps,” not the older empty-evidence copy.
SEVERITY: P3 (honest empty-of-gaps, not a defect)
EVIDENCE: `07-career-growth.png` — zeros for invented focus areas; copy still refuses to fabricate skills.
FIXED / DEFERRED: n/a
REASON: Caption the screenshot as refusal-to-invent, not as “no jobs analyzed.”

---

SCREEN: Analyze job header meta
ISSUE: Job Detail header previously joined location and work mode as `Remote · Remote · Internship`.
SEVERITY: was P3
EVIDENCE: Recaptured `04-match-evidence.png` after the Job Detail metadata contract matched Discover (`location`, work mode, employment type, salary). Harborline Analyze now shows `Remote · Internship`.
FIXED / DEFERRED: FIXED on current main (#104). Recapture documents the shipped UI.
REASON: Showcase assets must match the final product. Adjacent equivalent labels collapse; salary stays last when present.

---

SCREEN: Discover job meta line
ISSUE: Harborline intern previously showed `Remote · Remote · Internship` when location and work mode were both Remote. Cedar seed previously stored `Hybrid — Portland, OR`, which duplicated Hybrid in the card line.
SEVERITY: was P3
EVIDENCE: Recaptured `03-discover.png`. Harborline card and preview show `Remote · Internship`. Cedar stores `Portland, OR` with `work_mode=hybrid` and renders `Portland, OR · Hybrid · Internship`.
FIXED / DEFERRED: FIXED on current main (#104) plus synthetic Cedar location cleanup in this showcase refresh.
REASON: Showcase assets must match the final product. Do not treat duplicate Remote as a current defect. Cedar location is a city, not a work-mode prefix.

---

SCREEN: Discover job cards (accessibility)
ISSUE: The select-job control’s accessible name used to concatenate title, company, location, and badges.
SEVERITY: was P3
EVIDENCE: Current `selectJobCardLabel(title, company)` → `Select Software Engineer Intern at Harborline Analytics`.
FIXED / DEFERRED: FIXED on current main (not this showcase PR).
REASON: Capture script can target that concise name. No product change in this docs/screenshot PR.

---

SCREEN: Landing / Login / Signup decoration
ISSUE: Public/auth no longer uses a dotted globe or assembling-block lattice.
SEVERITY: none
EVIDENCE: `LandingPage.tsx` / `AuthFrame.tsx` render `PublicStage`. No `.hero-globe-frame`. Dashboard retains the dotted globe via `DashboardAtmosphere`. Reduced-motion capture used `emulate_media(reduced_motion=reduce)`.
FIXED / DEFERRED: FIXED on current main (#103). Recapture `01-landing.png` to match PublicStage.
REASON: Showcase must not show the retired globe/lattice. Native 200% browser zoom remains a human spot-check.

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
EVIDENCE: `08-assisted-fill-boundary-mock.png` + `fixtures/generic-ats-form.html`. Filename and alt text say mock; not the shipped extension runtime.
FIXED / DEFERRED: FIXED (intentional)
REASON: Illustrative mock, not the shipped extension. Live A8 remains the Fill certification. Submit is visible and was not clicked. EEO field left blank.

---

SCREEN: Dark / light
ISSUE: Dark login/signup remain readable; committed README shots stay light for consistency.
SEVERITY: P3
EVIDENCE: Dark login probe.
FIXED / DEFERRED: DEFERRED for committed set
REASON: One theme in the public screenshot strip. Dark is supported.

No P0 or P1 visual defects. Track Kanban overflow, Prepare below-fold approval, and default Overview tab stay by design. Discover and Analyze both show Harborline as `Remote · Internship`. Cedar Discover shows `Portland, OR · Hybrid · Internship`. Public landing/auth use PublicStage; the dotted globe remains on Dashboard only. Career Growth recapture still refuses to invent skill gaps.
