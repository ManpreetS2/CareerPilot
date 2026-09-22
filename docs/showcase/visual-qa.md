# Visual QA — Phase 9 showcase capture

Screens inspected while capturing the current showcase package (newer than tagged v1.0.0). Light theme desktop PNGs are committed; dark, 390, 768, and 1280 were probed and not all committed.

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
EVIDENCE: Unscrolled Prepare capture showed Fit summary only; approval is the human-gate story. Weak seeded copy (“I am applying using stored Python…”) was replaced with role-specific illustrative seeded materials.
FIXED / DEFERRED: FIXED for screenshots — capture script scrolls the Cover letter heading so letter and recruiter copy are readable; approval controls stay on the same page. Product layout unchanged.
REASON: Scrolling is expected; changing Prepare persistence or approval flow would be a runtime change. Seeded materials are labeled in docs and source-traceability notes.

---

SCREEN: Job Detail default tab
ISSUE: Overview tab is the default; Evidence (the showcase story) is one click away.
SEVERITY: P3
EVIDENCE: First `04-match-evidence.png` showed posting text, not factor rows.
FIXED / DEFERRED: FIXED for screenshots — capture clicks the Evidence tab. Product default tab unchanged.
REASON: Default Overview is reasonable for posting context; do not change analysis routing for marketing.

---

SCREEN: Python citation and preferred Docker evidence gap
ISSUE: An open evidence drawer intentionally blurs background factor rows, so one static image cannot legibly display the résumé citation and Docker's missing evidence at once.
SEVERITY: none
EVIDENCE: `04-match-evidence.png` shows the exact stored synthetic project excerpt for Python; `04b-match-gap.png` shows the unblurred satisfied Python/SQL/FastAPI requirements and Docker marked Not enough evidence.
FIXED / DEFERRED: FIXED with two separate, fresh synthetic screenshots and explicit synthetic-demo labels on Discover and Track.
REASON: Both sides of the evidence claim remain readable without altering modal accessibility or inventing candidate Docker experience.

---

SCREEN: Career Growth
ISSUE: Prior QA notes incorrectly said there were no repeated skill gaps.
SEVERITY: P3 (incorrect showcase documentation, not a product defect)
EVIDENCE: `07-career-growth.png` shows 2 analyzed jobs, 3 focus areas, including Docker (required in one job and preferred in the other) and AWS (required in one job).
FIXED / DEFERRED: FIXED documentation to match the committed image.
REASON: A job requirement can identify an evidence gap without inventing candidate experience. The screenshot shows real gaps, not an empty-of-gaps state.

---

SCREEN: Analyze job header meta
ISSUE: Job Detail header previously joined location and work mode as `Remote · Remote · Internship`.
SEVERITY: was P3
EVIDENCE: The Job Detail metadata contract is regression-tested (`location`, work mode, employment type, salary); Harborline Analyze renders `Remote · Internship`. The refreshed 04/04b screenshots scroll to factor rows and do not show the job header.
FIXED / DEFERRED: FIXED on main (#104). The current screenshot pair demonstrates evidence, not header metadata.
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

SCREEN: Discover job cards (selection / link semantics)
ISSUE: The badge row used `stopPropagation`, so Potential Match, timestamps, and non-link source badges did not select the job. Aggregator source links were nested inside the card’s selection button.
SEVERITY: was P2
EVIDENCE: Current `JobCard` keeps title/company/meta in the select button; badges sit outside it. Article click selects unless the target is a source `<a>` or the save control. Chromium 390/1440: nested `a`/`button` inside `.job-card-select` is 0. Potential Match and Manual badges select Harborline/Cedar. Keyboard focus remains on `.job-card-select`.
FIXED / DEFERRED: FIXED in this pass.
REASON: Valid interactive nesting; source links stay independently clickable.

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

SCREEN: Discover Fit scores
ISSUE: Previous seed used identical intelligence on both jobs, so Harborline and Cedar could not demonstrate a real strong vs partial Fit.
SEVERITY: n/a (showcase data)
EVIDENCE: Recaptured `03-discover.png` — Harborline 96% Strong Match, Cedar 62% Possible Match from production Fit V2 on the parsed synthetic résumé. Docker is preferred on Harborline and required on Cedar.
FIXED / DEFERRED: FIXED in this showcase seed pass.
REASON: Scores are calculated, not hardcoded. Percentage is qualification/preference alignment, not a hire or ATS probability.

---

SCREEN: Dark / light
ISSUE: Dark login/signup remain readable; committed README shots stay light for consistency.
SEVERITY: P3
EVIDENCE: Dark login probe.
FIXED / DEFERRED: DEFERRED for committed set
REASON: One theme in the public screenshot strip. Dark is supported.

No P0 or P1 visual defects. Track Kanban overflow, Prepare below-fold approval, and default Overview tab stay by design. Discover and Analyze both show Harborline as `Remote · Internship`. Cedar Discover shows `Portland, OR · Hybrid · Internship`. Public landing/auth use PublicStage; the dotted globe remains on Dashboard only. Career Growth identifies Docker/AWS evidence gaps without fabricating candidate skills.
