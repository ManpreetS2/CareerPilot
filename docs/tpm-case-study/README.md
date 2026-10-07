# CareerPilot — TPM Case Study

Interview-ready technical program management case study for CareerPilot v1.

This package turns the **real engineering and release history** into a coherent program narrative. It does not add product features. It does not rewrite release truth. It does not treat open post-v1 PRs as shipped.

## Start here

| Doc | Purpose |
| --- | --- |
| [01-program-brief.md](./01-program-brief.md) | Problem, user, goal, scope, success criteria |
| [02-roadmap-and-milestones.md](./02-roadmap-and-milestones.md) | Retrospective roadmap of what actually shipped |
| [03-dependency-map.md](./03-dependency-map.md) | Critical path and cross-cutting dependencies |
| [04-risk-register.md](./04-risk-register.md) | Risks, mitigations, detection evidence |
| [05-qa-launch-plan.md](./05-qa-launch-plan.md) | Automated vs live gates, release decision, rollback |
| [06-metrics.md](./06-metrics.md) | Defensible engineering/release metrics only |
| [07-retrospective.md](./07-retrospective.md) | What worked, what changed, tradeoffs, next |
| [08-executive-deck-outline.md](./08-executive-deck-outline.md) | Five-slide executive outline |
| [09-interview-stories.md](./09-interview-stories.md) | STAR / TPM interview stories |
| [deck/](./deck/) | Editable executive presentation (pptx) + notes |

## Release truth (verified)

Do not collapse these into one artifact:

| Artifact | SHA | Meaning |
| --- | --- | --- |
| Certified runtime / acceptance | `7b6c3ee100ca4fe6399ac29441bece8df71783c7` | A8 Chrome Greenhouse + Lever, A9 isolation/deletion, Phase 6 adversarial audit |
| Phase 7 docs / version metadata | `3196e18a8f1fb73795da26e5727311bca0c2cd6a` | Package/manifest/FastAPI set to 1.0.0; does not inherit A8/A9 |
| Annotated tag `v1.0.0` | `b73a983ed3605d498aa90070c3b5f786a73bc525` | Immutable release tag |
| Case-study base `main` (at write time) | `a9cdfd06ff49c4ec8e51b3b8060630b7dbe07e35` | Includes post-tag showcase/docs; not a recertification |

**Why provenance matters:** live ATS behavior was proven on a known runtime. Later documentation, version metadata, and showcase work do not magically inherit that certification. Post-v1 mainline improvements are backlog until separately accepted.

Canonical source: [`docs/V1_RELEASE_CHECKLIST.md`](../V1_RELEASE_CHECKLIST.md).

## Product in one sentence

CareerPilot is a **local / self-hostable** job-application workflow: grounded profile → discovery → explainable Fit → grounded materials → human approval → assisted Greenhouse/Lever Fill → tracking — **never auto-submits**.

## Ownership model (small team)

Not a large formal org. Historical workstream split used for coordination:

- **Developer A** — application shell / UI system, Prepare workflow, Interview Coach placement
- **Developer B** — discovery adapters, verification, ATS / form-fill, Chrome extension
- **Shared / platform** — auth/session, data ownership, Fit/scoring contracts, evidence grounding, privacy/security, release gates, integration contracts

See [`docs/developer-b-ui-handoff.md`](../developer-b-ui-handoff.md) and milestone notes in this package.

## Open PRs reviewed (post-v1 — not shipped)

Inspected while writing this package. **Do not merge as part of the case study. Do not claim as v1 functionality.**

| PR | Problem addressed | Runtime vs docs | Risk if merged | Relation to v1 | Case-study role |
| --- | --- | --- | --- | --- | --- |
| [#125](https://github.com/ManpreetS2/CareerPilot/pull/125) | Distinct job URL dedup, saved-search location alerts, HTTP verification | Runtime | Medium — discovery/verification behavior change; needs isolated-DB tests | Post-tag correctness | Maintenance / backlog |
| [#126](https://github.com/ManpreetS2/CareerPilot/pull/126) | Revalidation starvation, saved-search fairness, negative Analytics durations | Runtime | Medium — scheduling/analytics fairness | Post-tag correctness | Maintenance / backlog |
| [#127](https://github.com/ManpreetS2/CareerPilot/pull/127) | Stale evidence reads, interview prep freshness, legacy preferences, extension URL matching | Runtime | Medium–High if Fill/URL matching moves — may trigger A8 re-check | Residual freshness lesson | Maintenance + lesson learned |
| [#131](https://github.com/ManpreetS2/CareerPilot/pull/131) | README / showcase copy for LinkedIn launch | Docs-only | Low | Presentation only | Docs backlog |
| [#132](https://github.com/ManpreetS2/CareerPilot/pull/132) | Extension-compatible Dependabot group | Tooling/deps | Low–Medium build drift | Dependency hygiene | Maintenance |
| [#133](https://github.com/ManpreetS2/CareerPilot/pull/133) | httpx floor bump | Runtime dep | Low–Medium if HTTP client behavior shifts | Dependency hygiene | Maintenance |
| [#134](https://github.com/ManpreetS2/CareerPilot/pull/134) | pydantic-settings floor bump | Runtime dep | Low–Medium config parsing | Dependency hygiene | Maintenance |
| [#135](https://github.com/ManpreetS2/CareerPilot/pull/135) | Frontend-compatible Dependabot group | Frontend deps | Medium visual/tooling drift | Dependency hygiene | Maintenance |

## What this case study deliberately excludes

- Invented users, conversion, hiring success, time-saved, or interview-rate metrics
- Claiming open PRs (#125–#127, #131, Dependabot #132–#135) as shipped
- Claiming production hosted SaaS, auto-submit, universal ATS, or EEO autofill
- Runtime refactors performed “for the case study”

## Related source docs

- [`README.md`](../../README.md)
- [`docs/V1_RELEASE_CHECKLIST.md`](../V1_RELEASE_CHECKLIST.md)
- [`docs/agile-plan-gap-audit.md`](../agile-plan-gap-audit.md)
- [`docs/showcase/architecture.md`](../showcase/architecture.md)
- [`docs/showcase/technical-walkthrough.md`](../showcase/technical-walkthrough.md)
- [`docs/showcase/recruiter-walkthrough.md`](../showcase/recruiter-walkthrough.md)
- [`docs/showcase/portfolio-copy.md`](../showcase/portfolio-copy.md)
- [`docs/showcase/post-v1-maintenance-triage.md`](../showcase/post-v1-maintenance-triage.md)
- [`docs/showcase/visual-qa.md`](../showcase/visual-qa.md)
