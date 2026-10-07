# Speaker notes — CareerPilot TPM executive deck

Total walkthrough: **~3–5 minutes** (~35–45 seconds per slide).

Tone: internship candidate explaining real program work — decisions, dependencies, risks, gates, tradeoffs. No buzzword soup, no fake users/ROI, no “I leveraged AI.”

Full hashes (say only if asked):

- Certified runtime: `7b6c3ee100ca4fe6399ac29441bece8df71783c7`
- Tag `v1.0.0`: `b73a983ed3605d498aa90070c3b5f786a73bc525`
- Phase 7 docs/version: `3196e18a8f1fb73795da26e5727311bca0c2cd6a`

---

## Slide 1 — The program (~40s)

Career tools often look smart while Fit scores and autofill run ahead of evidence — or worse, submit for you. CareerPilot’s v1 program was to ship a grounded workflow from resume/profile through discovery, explainable Fit, materials, human approval, and assisted Fill — while the human keeps eligibility, EEO/terms, and Submit.

We are explicit: **never auto-submits**, local/self-hostable, not a production SaaS claim. The workflow on the slide is the whole product spine.

If asked “why not auto-apply?”: that was a deliberate quality and trust boundary, not a missing feature.

---

## Slide 2 — Architecture + critical path (~40s)

One app: React/Vite and a Chrome extension talking to FastAPI over SQLite — not separately deployed microservices. Shared job catalog versus user-scoped private records is the privacy boundary.

Critical path is evidence-driven: identity → candidate evidence → posting requirements → deterministic Fit → materials → approval → Fill. Two decisions matter in interviews: Fit does not depend on an LLM, and fingerprints invalidate stale packages. ATS identity is posting-ID based so we don’t fill the wrong job.

---

## Slide 3 — Program plan + risks (~45s)

Six milestones from identity through release and post-v1 maintenance. Ownership was a **small team** split — Developer A on shell/Prepare, Developer B on discovery/ATS/extension, Shared on auth/Fit/privacy/gates — meeting at contracts.

Top risks were product-real: incomplete postings making Fit look too sure (we redesigned Verified/Potential), stale evidence, cross-user leakage, and extension overreach. Mitigations became release invariants, not backlog stickers.

---

## Slide 4 — Launch evidence (~45s)

This is the strongest slide. Automated gates at tag time: 226 frontend tests, 109 extension tests, 124 mapped paths valid / 0 missing, CI, audits, full-history secret scan. Live gates: Greenhouse and Lever Fill on Chrome 152, A9 isolation/deletion, Phase 6 with no open P0/P1.

The provenance line is the release-management punchline: **certified runtime SHA ≠ release-tag SHA**. Later docs and version metadata did not inherit A8/A9. Showcase and open maintenance PRs do not silently recertify Fill.

---

## Slide 5 — Results + next (~40s)

What shipped is a certifiable slice: grounded evidence, deterministic Fit, human approval, two ATS Fill paths, per-user privacy, immutable `v1.0.0`. What we deliberately did not ship: auto-submit, universal ATS, hosted SaaS, EEO/consent automation.

Lessons: live acceptance when CI can’t prove browser behavior; provenance matters; exclusion can be quality. Next work is targeted post-v1 correctness and migration maturity — not random feature expansion. Open PRs are backlog, not rewritten history.
