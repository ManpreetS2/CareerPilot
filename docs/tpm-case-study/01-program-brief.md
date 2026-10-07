# 01 — Program brief

One-page style brief for CareerPilot v1 as a technical program.

## Problem

Career tools become unsafe or misleading when:

- job posting content is incomplete, yet Fit scores look authoritative
- stale resume or posting evidence is silently reused
- generated application claims outrun stored evidence
- private candidate information crosses account boundaries
- form automation crosses from assistance into submission
- sensitive fields (EEO, demographics, terms/privacy consent) are autofilled

The program risk was not “missing features.” It was shipping a workflow that *looked* helpful while eroding trust on Fit, privacy, and application control.

## User

A job seeker who wants:

- job discovery
- explainable Fit
- grounded application materials
- application preparation
- workflow tracking
- repetitive-form assistance on supported ATS pages

…without giving up final approval, sensitive-question control, or Submit.

## Program goal

Ship an **interview-ready v1** covering the end-to-end workflow:

**profile → discovery → Fit / evidence → materials → human approval → assisted Greenhouse / Lever Fill → tracking / analytics**

with real acceptance evidence for high-risk behavior (live ATS Fill, isolation, deletion, adversarial audit).

CareerPilot remains a **local / self-hostable** app (FastAPI + React/Vite + SQLite + unpacked Chrome extension). It is not positioned as a production hosted SaaS.

## Scope (shipped v1)

Grounded in what actually certified and tagged:

| Area | Shipped |
| --- | --- |
| Identity | Auth / session ownership; second-user isolation |
| Profile | Resume-backed candidate profile; profile-first gating for discovery |
| Discovery | Seven job sources + manual URL ingestion |
| Fit / evidence | Deterministic Fit V2; Verified vs Potential; requirement profiles; fingerprints for staleness |
| Materials | Grounded materials or visible `grounding_override` |
| Approval | Explicit human eligibility confirmation; approval ≠ tracker `applied` |
| Assisted Fill | Chrome extension; Greenhouse + Lever; ATS-ID identity; no Submit; EEO/terms manual |
| Tracking | Owner-scoped tracker + read-only analytics funnel |
| Privacy | Account deletion of owner-scoped private data; shared job catalog retained |
| Release | Automated CI gates + live A8/A9 + Phase 6 adversarial; annotated `v1.0.0` |

Canonical workflow and invariants: [`docs/V1_RELEASE_CHECKLIST.md`](../V1_RELEASE_CHECKLIST.md).

## Out of scope (explicit exclusions)

Do not invent scope. v1 deliberately does **not** include:

- production hosted SaaS / multi-tenant cloud product
- auto-submit or auto-apply
- universal ATS support (only Greenhouse + Lever certified for Fill)
- EEO / demographic autofill
- automatic terms / privacy / consent acknowledgement
- billing / monetization
- unsupported alerts or account integrations (no calendar OAuth, no email send)
- claiming LinkedIn or other boards as Fill targets
- moving or re-minting the `v1.0.0` tag to absorb post-release docs

## Ownership / stakeholders (small-team model)

Not a giant formal organization. Coordination used a small-project ownership split:

| Workstream | Focus |
| --- | --- |
| **Developer A** | Application shell / UI system, Prepare workflow, Interview Coach placement |
| **Developer B** | Discovery adapters, verification, ATS / form-fill, Chrome extension |
| **Shared / platform** | Auth/session, data ownership, Fit/scoring contracts, evidence grounding, privacy/security, release gates, integration between workstreams |

Handoff evidence: [`docs/developer-b-ui-handoff.md`](../developer-b-ui-handoff.md). Integration risk lived at API/product contracts (Fit payloads, evidence freshness, approval eligibility, extension identity), not at “throw code over the wall.”

## Success criteria (real release gates)

Success meant **no open P0/P1 after adversarial audit** on a known runtime, plus automated gates green, plus live external proofs:

1. **A1–A7** — subsystem acceptance as documented in the release checklist
2. **A8** — Chrome live Greenhouse + Lever Fill; no Submit; EEO/terms manual; truthful resume attachment
3. **A9** — session isolation, IDOR fail-closed, account deletion, generic login errors (isolated SQLite only)
4. **Phase 6** — adversarial cross-feature audit; no open P0/P1
5. **Phase 7** — release-truth docs / version metadata (does not recertify runtime)
6. **Phase 8** — annotated immutable tag `v1.0.0`
7. **CI** — `.github/workflows/ci.yml` and Full-history Gitleaks `.github/workflows/security.yml`

Automation does not replace live ATS or privacy QA when Fill, attachment, session, or deletion behavior changes.

## Non-goals for this case-study package

- Adding features
- Merging open maintenance PRs
- Claiming post-tag showcase or open PR work as certified runtime
