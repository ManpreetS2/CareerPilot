# 08 — Executive deck outline

Exactly **five** slides. Editable deck lives in [`deck/`](./deck/). This outline is the source checklist for slide content.

Audience: internship recruiter, engineering manager, TPM interviewer, Solutions / Customer Engineering interviewer. ~2 minutes skim / ~5 minutes walkthrough.

Footer on every slide: `CareerPilot — TPM Case Study`

---

## Slide 1 — Problem + Goal

**Title:** CareerPilot: Building a Grounded, Human-Controlled Job Application Workflow

**Takeaway:** Ship a grounded profile→Fill workflow without surrendering Submit, sensitive fields, or evidence honesty.

**Visible bullets (max 5):**

- Problem: scoring, generation, and automation outrun evidence
- Goal: grounded workflow with human control of eligibility, EEO/terms, and Submit
- Workflow: Resume/Profile → Discover → Fit → Materials → Approval → Assisted Fill → Track
- **Never auto-submits**
- Local / self-hostable v1 — not a production SaaS claim

**Recommended visual:** Horizontal workflow chevron; red “Never auto-submits” callout.

**Speaker notes (~40s):** Job tools often look smart while Fit and autofill run ahead of evidence. CareerPilot’s program was to prove a safer workflow end-to-end: grounded profile, explainable Fit, materials tied to evidence, human approval, then assisted fill on Greenhouse/Lever only — human still hits Submit. We deliberately did not build hosted SaaS or auto-apply.

**Do NOT overstate:** production SaaS; universal ATS; auto-apply success rates.

---

## Slide 2 — Architecture + Critical Path

**Title:** One App, Clear Ownership Boundaries

**Takeaway:** Monolithic local stack with a strict evidence→Fit→Fill dependency chain — not microservices theater.

**Visible bullets:**

- React/Vite → FastAPI → SQLite/SQLAlchemy
- Externals: job sources, AI providers, Chrome extension ↔ Greenhouse/Lever
- Shared job catalog vs user-scoped private records
- Critical path: identity → evidence → requirements → Fit → materials → approval → Fill
- Decisions: deterministic Fit (no LLM); fingerprints invalidate stale packages

**Recommended visual:** Layer diagram + dependency chain; catalog vs private split.

**Speaker notes (~40s):** One process, not a service mesh. Shared jobs stay shared; profiles, materials, tracker, analytics stay owner-scoped. Fit is deterministic so provider outage doesn’t invent scores. Fingerprints kill stale materials when resume or posting evidence changes. Extension only fills after approval with exact ATS IDs.

**Do NOT overstate:** separately deployed microservices; AI “decides” Fit; Fill for every ATS.

---

## Slide 3 — Roadmap + Risks

**Title:** Program Plan, Ownership, Top Risks

**Takeaway:** Small-team workstreams + mid-program Fit redesign + privacy as a ship gate.

**Visible bullets:**

- Milestones: Identity → Discovery/Fit → Materials/Approval → Fill → Privacy QA → Release/maintenance
- Ownership: Developer A (shell/Prepare), Developer B (discovery/ATS/extension), Shared (auth/Fit/privacy/gates)
- Top risks: incomplete posting→misleading Fit; stale evidence; cross-user privacy; extension overreach
- Mitigations: Verified/Potential + content status; fingerprints; A9 isolation; no-submit + EEO manual

**Recommended visual:** Compact timeline + 2×2 risk/mitigation chips.

**Speaker notes (~45s):** We weren’t a large org — three workstreams meeting at contracts. Biggest product risk mid-flight was incomplete postings making Fit look too sure; we redesigned requirements/evidence semantics. Privacy and extension overreach were treated as launch blockers, not backlog.

**Do NOT overstate:** team size; that open PRs are already shipped mitigations.

---

## Slide 4 — Launch + Evidence

**Title:** Launch Evidence and Release Provenance

**Takeaway:** Automated gates + live ATS/privacy acceptance; certified runtime ≠ tag.

**Visible bullets:**

- Automated: frontend 226, extension 109, mapped paths 124/0, CI, full-history secret scan (tag-time)
- Live: Greenhouse + Lever Fill (Chrome 152), A9 isolation/deletion, Phase 6 no open P0/P1
- `Certified runtime SHA ≠ release-tag SHA`
- Later docs/version commits did not inherit runtime certification
- Tag `v1.0.0` immutable

**Recommended visual:** Two columns Automated | Live; provenance strip with short hashes `7b6c3ee` vs `b73a983`.

**Speaker notes (~45s):** CI was necessary but not sufficient. We certified Fill and isolation on a known runtime, then tagged after docs/version metadata. Those are different SHAs on purpose — so we never pretend a README bump re-proves Greenhouse. Full hashes in notes: runtime `7b6c3ee100ca4fe6399ac29441bece8df71783c7`, tag `b73a983ed3605d498aa90070c3b5f786a73bc525`.

**Do NOT overstate:** current-main test counts as tag-time; that showcase recertified Fill; business KPIs.

---

## Slide 5 — Results + Tradeoffs + Next Step

**Title:** What Shipped, What Didn’t, What’s Next

**Takeaway:** Honest scope is a quality decision; next work is targeted correctness + migration maturity.

**Visible bullets:**

- Shipped: grounded evidence, deterministic Fit, human approval, GH/Lever Fill, per-user privacy, tagged v1.0.0
- Not shipped: auto-submit, universal ATS, hosted SaaS, EEO/consent automation
- Lessons: live acceptance when CI can’t prove browser behavior; provenance matters; exclusion can be quality
- Next: targeted post-v1 correctness + migration maturity — not random feature expansion

**Recommended visual:** Two columns Shipped | Deliberately not; closing next-step line.

**Speaker notes (~40s):** We shipped a certifiable slice and left dangerous automation out. Open maintenance PRs are backlog — they don’t rewrite the tag. Next is correctness and schema-migration maturity, not auto-apply.

**Do NOT overstate:** open PRs as done; roadmap as funded SaaS plan; fake ROI.
