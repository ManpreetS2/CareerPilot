# 07 — Retrospective

Grounded in repository history. Failures and course corrections are included on purpose — they are the TPM story.

## What went well

- **Explicit human submission boundary** — never auto-submits; human presses Submit on the ATS; extension guards are acceptance-tested live
- **Deterministic Fit** — scoring does not depend on an LLM; provider outages do not invent Fit
- **User isolation** — A9 treated privacy as a release criterion, not a polish pass
- **Evidence freshness** — fingerprints invalidate stale Fit/evidence/materials where designed
- **Real ATS testing** — Greenhouse + Lever on Chrome 152; attachment honesty beyond filename match
- **Release provenance** — certified runtime ≠ docs/version SHA ≠ immutable tag; showcase does not recertify Fill
- **Privacy as launch gate** — isolation, IDOR fail-closed, deletion, generic login errors required for ship
- **Scope honesty** — two deep ATS integrations beat shallow universal claims; local-first beat fake SaaS positioning

## What failed / slipped / changed

### Incomplete posting → misleading Fit

**Original plan / early state:** Job Intelligence and Fit surfaces could present scores without fully representing employer requirements when posting content was thin.

**What changed:** Requirement profiles, content status, deterministic mining, eligibility, **Verified vs Potential Fit**, UI that qualifies unverified percentages, Top-N verification without sending every listing to Gemini.

**Why it matters for TPM:** A mid-program product risk discovery forced a contract redesign across Shared + B + A — classic dependency and scope-control work.

Evidence: [`docs/agile-plan-gap-audit.md`](../agile-plan-gap-audit.md).

### Pipeline orchestrator stayed narrower than envisioned

Early language implied a broader agent/orchestrator. Final v1 kept a tighter path: scout → evidence/Fit → materials → approval → Fill, with JI scoped to materials/interview rather than “AI runs the whole career OS.”

### Migration strategy remained technical debt

No Alembic at v1. Persistence remains `create_all` + additive column/index helpers. Documented as debt rather than silently “fixed” in release notes.

### Showcase / visual QA found product-vs-presentation issues

Screenshot and copy QA surfaced clarity and boundary-presentation gaps (e.g. how assisted-fill limits are shown). Non-critical presentation issues were deferred rather than destabilizing certified runtime — see quality-vs-schedule story in [`09-interview-stories.md`](./09-interview-stories.md) and [`docs/showcase/visual-qa.md`](../showcase/visual-qa.md).

### Post-v1 correctness still open

Open PRs #125–#127 address real correctness/fairness/freshness edges discovered after tag. They are **maintenance backlog**, not proof that v1 “wasn’t real.” Tag truth and certified runtime remain.

## Tradeoffs

| Choice | Alternative considered | Why v1 chose this |
| --- | --- | --- |
| SQLite / local-first | Hosted multi-tenant SaaS | Ship interview-ready product with ownership clarity; avoid cloud scope |
| Two certifiable ATS integrations | Many shallow ATS adapters | Acceptance evidence over brochure breadth |
| Deterministic Fit | AI-scored Fit everywhere | Explainability, offline/provider resilience, less hallucination risk |
| No auto-submit | Maximum automation | Trust and legal/safety boundary |
| Immutable tag + separate certification SHA | Moving tag when docs change | Honest release management |
| Post-v1 maintenance PRs stay open | Merge everything into “v1” narrative | Do not rewrite release truth |

## What I would do next (bounded)

Not a wishlist dump — reasonable follow-ons only:

1. **Triage and land targeted post-v1 correctness** (#125–#127 class) with automated gates; re-run A8/A9 only if Fill/session/deletion surfaces move
2. **Migration maturity** — introduce Alembic (or equivalent) before schema churn grows painful
3. **Dependency hygiene** — review Dependabot groups (#132–#135) without React Router 7 drive-bys
4. **Keep showcase/docs honest** as main evolves — never imply open PRs are certified

Explicitly **not** “next”: auto-submit, universal ATS, hosted SaaS MVP, EEO autofill, or inventing adoption metrics.
