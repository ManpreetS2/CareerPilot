# 06 — Metrics

Only defensible, repository-backed metrics. No invented business KPIs.

## Clear separation

| Category | Allowed? | Examples |
| --- | --- | --- |
| Engineering / release metrics | Yes | Test counts at tag time, mapped paths, certified ATS paths, discovery sources, defect bar |
| Business / product outcome metrics | **No** (not in repo) | Users, hiring success, recruiter adoption, conversion, time saved, application success, interview rate |

If an interviewer asks for adoption metrics: say they were **out of scope** for a local/self-hostable v1 and were not instrumented as product analytics beyond owner-scoped event funnel plumbing.

---

## Release-gate metrics (tag time — cite these for v1)

Verified against showcase/release documentation aligned to annotated tag `v1.0.0` (`b73a983…`):

| Metric | Value | Notes |
| --- | --- | --- |
| Frontend automated tests | **226** | Release-gate npm frontend count at tag time |
| Extension automated tests | **109** | Release-gate extension count at tag time |
| Mapped paths | **124 valid / 0 missing** | Repo-map validity at tag time |
| Live certified ATS Fill paths | **2** (Greenhouse + Lever) | A8 on certified runtime |
| Job discovery sources | **7** + manual URLs | Adzuna, RemoteOK, Greenhouse, Lever, Remotive, Jobicy, Himalayas |
| Phase 6 defect bar | **No open P0/P1** | Adversarial audit on certified runtime |
| Chrome used for A8 | **152** | Documented in release checklist |

Sources: [`docs/showcase/portfolio-copy.md`](../showcase/portfolio-copy.md), [`docs/showcase/technical-walkthrough.md`](../showcase/technical-walkthrough.md), [`docs/V1_RELEASE_CHECKLIST.md`](../V1_RELEASE_CHECKLIST.md).

These counts are **not** a grand total of pytest + all npm suites combined. Backend pytest is a separate CI gate; do not invent a single “N total tests” rollup unless recomputed and labeled.

---

## Provenance metrics (release management)

| Artifact | Short SHA | Role |
| --- | --- | --- |
| Certified runtime | `7b6c3ee…` | A8 / A9 / Phase 6 |
| Phase 7 docs/version | `3196e18…` | 1.0.0 metadata only |
| Tag `v1.0.0` | `b73a983…` | Immutable release pointer |
| Case-study base `main` | `a9cdfd0…` | Post-tag docs/showcase present; not a recertification |

**Metric claim to protect:** `Certified runtime SHA ≠ release-tag SHA`.

---

## Current-main observation (do not conflate with tag-time gates)

Re-checked while writing this case study on `main` @ `a9cdfd0…`:

| Check | Result |
| --- | --- |
| Mapped paths script | **131 valid / 141 conceptual / 0 missing** |

Use this only to show the map still has **0 missing** paths after post-tag docs growth. **Do not replace** the v1 release-gate “124 valid” figure when talking about what was certified at tag time.

---

## Coverage of high-risk behavior (qualitative)

Defensible statements:

- Automated gates cover Fit contracts, ownership, grounding helpers, extension unit behavior, audits, secrets
- Live gates cover Greenhouse + Lever Fill, attachment honesty, no-submit, EEO/terms manual, isolation, deletion
- Two ATS paths certified ≠ every ATS supported

---

## Explicitly not claimed

- Monthly active users / waitlist size
- % increase in interview rate or offer rate
- Average minutes saved per application
- Recruiter NPS or hiring-manager adoption
- Production uptime / SLA
- “AI accuracy %” for Fit (Fit is deterministic evidence scoring, not an LLM accuracy KPI)
