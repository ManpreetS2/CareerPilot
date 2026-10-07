# 04 — Risk register

Serious risks for CareerPilot v1. Likelihood/impact use qualitative labels only — there is no numeric scoring system in-repo.

Status meanings:

- **Mitigated (certified)** — controls proven on certified runtime and still treated as invariants
- **Accepted debt** — known limitation, documented, not pretended away
- **Watch / post-v1** — open maintenance or residual drift risk after tag

---

### R1 — Incomplete posting presented as authoritative Fit

| | |
| --- | --- |
| **Description** | Partial job content yields a confident Fit % that overstates knowledge of employer requirements |
| **Likelihood** | High without controls; Medium with content status + Verified/Potential |
| **Impact** | High — trust and decision quality |
| **Mitigation** | Requirement profiles; content status; Verified vs Potential; hide/qualify unverified percentages; Top-N full-posting verification |
| **Owner / workstream** | Shared (Fit/evidence) + Developer B (verification) + Developer A (UI honesty) |
| **Detection / acceptance** | Fit/evidence UI tests; agile gap audit redesign; release checklist Fit invariants |
| **Status** | Mitigated (certified) — redesign was a mid-program course correction |

### R2 — Stale resume/posting evidence reused

| | |
| --- | --- |
| **Description** | Candidate or posting changes while Fit/materials packages silently remain |
| **Likelihood** | Medium |
| **Impact** | High — wrong materials / wrong claims |
| **Mitigation** | Fingerprints invalidate stale Fit/evidence/materials where designed |
| **Owner / workstream** | Shared/platform |
| **Detection / acceptance** | Stale-path tests; Prepare/materials gates |
| **Status** | Mitigated (certified); residual correctness tracked in open post-v1 PRs (e.g. #127) as **maintenance**, not v1 rewrite |

### R3 — Cross-user privacy leakage

| | |
| --- | --- |
| **Description** | Profile, scores, tracker, analytics, saved searches, or resume files leak across accounts |
| **Likelihood** | Medium without strict ownership; Low with A9 controls |
| **Impact** | Critical |
| **Mitigation** | Session ownership on all private routes; IDOR fail-closed; generic login errors; deletion of owner-scoped data |
| **Owner / workstream** | Shared/platform |
| **Detection / acceptance** | **A9** live isolation/deletion; analytics/saved-search isolation tests |
| **Status** | Mitigated (certified) |

### R4 — Extension accidentally submitting

| | |
| --- | --- |
| **Description** | Fill automation calls submit, requestSubmit, or Enter-to-submit |
| **Likelihood** | Medium without hard rules |
| **Impact** | Critical — product boundary failure |
| **Mitigation** | Explicit no-submit rules; human presses Submit on ATS; A8 live proof |
| **Owner / workstream** | Developer B (extension) |
| **Detection / acceptance** | Extension tests + **A8** live Greenhouse/Lever |
| **Status** | Mitigated (certified) |

### R5 — Extension filling EEO / terms

| | |
| --- | --- |
| **Description** | Demographic or consent fields autofilled |
| **Likelihood** | Medium without field classification |
| **Impact** | Critical — legal/trust |
| **Mitigation** | EEO/demographic and terms/privacy remain manual; A8 checks untouched fields |
| **Owner / workstream** | Developer B |
| **Detection / acceptance** | **A8** |
| **Status** | Mitigated (certified) |

### R6 — False resume-attachment success

| | |
| --- | --- |
| **Description** | UI claims resume attached because filenames match, Cover Letter shares a name, or stale widget state |
| **Likelihood** | Medium |
| **Impact** | High — user believes package is complete |
| **Mitigation** | Verify from live Resume/CV input or Resume/CV-group widget after current attempt; filename alone is not proof |
| **Owner / workstream** | Developer B |
| **Detection / acceptance** | **A8** attachment verification notes |
| **Status** | Mitigated (certified) |

### R7 — Job identity collision / wrong posting

| | |
| --- | --- |
| **Description** | Fuzzy title/company matching fills the wrong Greenhouse/Lever posting |
| **Likelihood** | Medium without ATS IDs |
| **Impact** | High |
| **Mitigation** | ATS posting identity only; URL parse helpers for Greenhouse/Lever |
| **Owner / workstream** | Developer B |
| **Detection / acceptance** | Identity unit tests; A8 on real postings |
| **Status** | Mitigated (certified); URL dedup/identity edge cases appear in post-v1 #125 as maintenance |

### R8 — AI / provider outage

| | |
| --- | --- |
| **Description** | Gemini/provider unavailable during extract, materials, or interview |
| **Likelihood** | Medium |
| **Impact** | Medium for generation; Low for Fit if deterministic |
| **Mitigation** | Deterministic Fit does not depend on LLM; degrade generation visibly; do not invent evidence |
| **Owner / workstream** | Shared |
| **Detection / acceptance** | Provider-failure paths in tests; product copy that Fit ≠ AI score |
| **Status** | Mitigated (by architecture) |

### R9 — Tests mutating real local DB

| | |
| --- | --- |
| **Description** | Automated or destructive QA writes to `data/careerpilot.db` |
| **Likelihood** | Medium without discipline |
| **Impact** | High — destroys developer/demo data; false confidence |
| **Mitigation** | Isolated/temp/copied SQLite only; AGENTS.md / checklist invariant |
| **Owner / workstream** | Shared + all contributors |
| **Detection / acceptance** | Test fixtures; release checklist; agent instructions |
| **Status** | Mitigated (process + fixtures) |

### R10 — Scope creep

| | |
| --- | --- |
| **Description** | Auto-submit, universal ATS, hosted SaaS, billing, or EEO autofill enter v1 |
| **Likelihood** | High without explicit exclusions |
| **Impact** | High — schedule and safety |
| **Mitigation** | Written out-of-scope list; two-ATS Fill strategy; local-first positioning; tag freeze |
| **Owner / workstream** | Program / Shared |
| **Detection / acceptance** | Release checklist exclusions; showcase copy review |
| **Status** | Mitigated (scope control) |

### R11 — Schema migration debt / no Alembic

| | |
| --- | --- |
| **Description** | `create_all` + `_add_missing_columns` insufficient for complex ALTER history on long-lived DBs |
| **Likelihood** | Certain as debt; Medium as near-term break for small additive changes |
| **Impact** | Medium–High over time |
| **Mitigation** | Document debt; prefer additive tables/columns; do not pretend Alembic exists |
| **Owner / workstream** | Shared/platform |
| **Detection / acceptance** | [`docs/agile-plan-gap-audit.md`](../agile-plan-gap-audit.md); `backend/db/init_db.py` |
| **Status** | Accepted debt |

### R12 — Live ATS behavior drifting after code changes

| | |
| --- | --- |
| **Description** | Post-certification commits change Fill/attachment/session/deletion without re-running A8/A9 |
| **Likelihood** | Medium on active main |
| **Impact** | High — false confidence if tag/runtime conflated |
| **Mitigation** | Immutable certification SHA vs tag vs later main; re-run live gates when those surfaces change; do not move `v1.0.0` |
| **Owner / workstream** | Shared/release |
| **Detection / acceptance** | Provenance section in release checklist; post-v1 triage |
| **Status** | Watch / post-v1 — open correctness PRs must not be described as re-certified merely by merging |

---

## Open PR relationship (not shipped)

| PR | Risk angle | Case-study role |
| --- | --- | --- |
| #125 | URL identity / saved-search / verification correctness | Maintenance backlog |
| #126 | Revalidation fairness / analytics duration | Maintenance backlog |
| #127 | Stale intel / interview freshness / preferences / extension URL | Maintenance + lesson on residual freshness |
| #131 | LinkedIn showcase copy | Docs-only backlog |
| #132–#135 | Dependabot floors/groups | Dependency hygiene backlog |

Do not merge these as part of the case-study program. Do not claim them as v1 functionality.
