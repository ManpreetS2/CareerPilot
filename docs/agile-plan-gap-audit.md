# Agile plan gap audit

Stacked on PR #28 (`feat/job-discovery-progress` @ `12961b225524c397ec5b43063fb4e068f1a3d22f`).
This audit is a map of what already exists. It does not reimplement Fit Score V2.

**Migration note:** There is no Alembic. Persistence uses `Base.metadata.create_all` plus `_add_missing_columns()` in `backend/db/init_db.py`. New tables are safe. Large ALTER piles against `data/careerpilot.db` are not. This stacked work stores the requirement profile as a new table plus a small number of `jobs` columns, and records Alembic as remaining debt.

**Owner map** (from `docs/developer-b-ui-handoff.md`): Developer B owns discovery adapters, verification, ATS/form-fill, and the Chrome extension. Developer A owns shell, tokens, Prepare workspace, and Interview Coach placement.

## Implementation status on this stacked branch

`feat/full-job-requirements-foundation` adds `JobRequirementProfile`, content status, deterministic mining with AND/OR groups, eligibility, Verified vs Potential Fit, Top-N full-posting verification without sending all listings to Gemini, and Jobs/Job Detail UI that hides unverified percentages. Job Intelligence remains for materials/interview. Alembic is still not introduced.

---

---

## Original Days 1–9

### Day 1 — Auth, sessions, user isolation

| Field | Detail |
| --- | --- |
| Plan feature | Real login, HttpOnly session, CSRF, per-user private records |
| Current implementation | Signup/login/logout/`/me`, SHA-256 session tokens, origin CSRF, cookie-only web auth, extension header only on autofill |
| Current file(s) | `backend/api/routes/auth.py`, `backend/core/csrf.py`, `backend/services/auth_service.py`, `backend/db/models.py` (`User`, `UserSession`), `tests/test_auth.py`, `tests/test_auth_hardening.py`, `tests/test_cross_user_isolation.py` |
| Status | **complete** |
| Remaining work | None for this stacked PR |
| Dependency | — |
| Owner | Platform |

### Day 2 — Candidate profile / resume parsing / grounding

| Field | Detail |
| --- | --- |
| Plan feature | Extract a grounded candidate profile from a resume |
| Current implementation | PDF text + Gemini-first / Ollama fallback structured extract, grounding, persist. Progress UI exists. |
| Current file(s) | `backend/services/candidate_profile_agent.py`, `backend/api/routes/candidate.py`, `frontend/src/components/ResumeParsingProgress.tsx`, `tests/test_candidate_profile.py` |
| Status | **complete** (interactive path). Academic year / final-year / recent-grad fields are only loosely present (`currently_enrolled_in_program`, `expected_graduation`, `degree_pursuing`). |
| Remaining work | Structured academic-year + graduation-date comparison for eligibility (this PR) |
| Dependency | Day 1 |
| Owner | Platform |

### Day 3 — Job ingestion and discovery

| Field | Detail |
| --- | --- |
| Plan feature | Search live sources, normalize, persist, verify |
| Current implementation | Adzuna, RemoteOK, Greenhouse (`content=true`), Lever, Remotive, Jobicy, Himalayas, manual URL ingest. Per-source isolation. Bounded HTTP worker pool. SSRF via `fetch_url_safely`. |
| Current file(s) | `backend/services/job_scout_service.py`, `backend/services/job_service.py`, `backend/services/job_verification_service.py`, `backend/services/url_safety.py`, `backend/api/routes/jobs.py` |
| Status | **partial** |
| Remaining work | `job_content_status` (full/partial/unknown). Jobicy/Himalayas may store excerpts. Adzuna is often a snippet. No canonical content fingerprint. Greenhouse/Lever already have complete ATS postings when the API returns `content`. |
| Dependency | Day 1 |
| Owner | Developer B (adapters) |

### Day 4 — Job intelligence + Fit scoring

| Field | Detail |
| --- | --- |
| Plan feature | Structured requirements, then explainable fit |
| Current implementation | Job Intelligence extracts skills/years/education/seniority/responsibilities and grounds them. Fit V2 is deterministic: qualification / preference / eligibility / confidence / ranking. Find Jobs uses `score_jobs_batch` (no LLM). Calculate Fit uses `score_job_with_intelligence`. |
| Current file(s) | `backend/services/job_intelligence_service.py`, `backend/services/fit_v2.py`, `backend/services/analysis_service.py`, `backend/services/scoring_orchestrator.py`, `backend/db/models.py` (`JobIntelligenceRecord`, `MatchScoreRecord`) |
| Status | **partial** |
| Remaining work | Intelligence does **not** model AND/OR groups, final-year/recent-grad, sponsorship/CPT/OPT, work mode/geography, travel, or requirement evidence objects. Preliminary Fit can still show an authoritative-looking percentage from an incomplete posting. That is the P0 bug. |
| Dependency | Days 2–3, PR #28 Fit V2 (keep) |
| Owner | Platform |

### Day 5 — Application materials + approval

| Field | Detail |
| --- | --- |
| Plan feature | Grounded materials, approve/edit/reject, eligibility confirmation, no-submit |
| Current implementation | Working end-to-end: generate from stored evidence, grounding flags, override, approval states, `eligibility_confirmed`. Never submits. |
| Current file(s) | `backend/services/application_service.py`, `backend/services/application_materials_agent.py`, `backend/api/routes/applications.py`, `frontend/src/pages/PrepareApplicationPage.tsx`, `tests/test_application_service.py`, `tests/test_application_materials_agent.py` |
| Status | **complete** as a materials/approval product. **Not connected** to Verified Fit / `JobRequirementProfile` / likely-ineligible blockers. |
| Remaining work | Adapter: surface eligibility conflict before generate; do not silently write materials for `likely_ineligible` without explicit review |
| Dependency | Days 2, 4 |
| Owner | Developer A (Prepare workspace) |

### Day 6 — Orchestrator + assisted apply / form fill

| Field | Detail |
| --- | --- |
| Plan feature | Typed pipeline stages; Greenhouse/Lever assisted fill; no submit |
| Current implementation | `scoring_orchestrator.py` only coordinates intelligence-then-score. No job-level pipeline status (`discovered` → `approved`). Form fill is real Playwright for Greenhouse/Lever, no-submit, stores attempts. Extension fill runtime exists. |
| Current file(s) | `backend/services/scoring_orchestrator.py`, `backend/services/form_fill_service.py`, `browser-extension/src/fillForm.ts`, `tests/test_form_fill_service.py` |
| Status | Orchestrator: **skeleton** (score-only). Form fill: **complete** for supported ATS. Pipeline stages: **missing**. |
| Remaining work | Typed pipeline contract + persistence; eligibility-unresolved ⇒ review-required before autofill. Do not rewrite Developer B ATS runtime. |
| Dependency | Days 4–5 |
| Owner | Form fill: Developer B. Pipeline types: this stacked PR. |

### Day 7 — Observability + integration harness

| Field | Detail |
| --- | --- |
| Plan feature | Privacy-safe stage logs; smoke flow against preview DB |
| Current implementation | Structured logs for scout/score/parse with IDs, durations, counts. `scripts/test_mvp_foundation_browser.py` covers a broad MVP path. No requirement-extraction / verified-fit smoke. |
| Current file(s) | `backend/api/routes/jobs.py` (`_log_job_scout`), `scripts/test_mvp_foundation_browser.py`, `logs/` (gitignored) |
| Status | **partial** |
| Remaining work | Normalized error categories for requirement extraction. Preview-DB smoke: scout → verify → extract profile → eligibility → verified fit → materials (no submit). |
| Dependency | Days 4–6 |
| Owner | Platform |

### Day 8 — Interview coach

| Field | Detail |
| --- | --- |
| Plan feature | Questions/talking points from stored requirements + candidate evidence |
| Current implementation | Deterministic baseline from Job Intelligence + match scores. LLM improver is injectable, not the production path. Lives on Job Detail. |
| Current file(s) | `backend/services/interview_service.py`, `frontend/src/pages/JobDetailPage.tsx`, `tests/test_interview_service.py` |
| Status | **complete** against Job Intelligence. **Not connected** to `JobRequirementProfile`. |
| Remaining work | Prefer verified profile responsibilities/skills/gaps when present |
| Dependency | Day 4 |
| Owner | Developer A (placement); platform (service) |

### Day 9 — Demo / release gate

| Field | Detail |
| --- | --- |
| Plan feature | Repeatable demo runbook + rollback |
| Current implementation | README workflow + MVP browser script. No `docs/demo-runbook.md`. |
| Current file(s) | `README.md`, `scripts/test_mvp_foundation_browser.py` |
| Status | **missing** (runbook) |
| Remaining work | Preview-DB demo checklist: Potential vs Verified, one qualified role, one hard-blocked role, no submit, rollback |
| Dependency | Days 1–8 |
| Owner | Platform |

---

## Committed post-MVP Days 10–14

### Day 10 — Real job discovery

| Field | Detail |
| --- | --- |
| Plan feature | Canonical provider model, source ID/URL, workplace type, timestamps, content hash, freshness, error isolation |
| Current implementation | Seven live sources, source badges, `date_posted` / `date_scraped`, ATS field, per-source failure isolation (PR #25/#28). |
| Current file(s) | `backend/services/job_scout_service.py`, `frontend/src/components/SourceBadge.tsx` |
| Status | **partial** |
| Remaining work | `content_status`, `content_hash` / `source_fingerprint`, `source_job_id`, workplace type, remote geography. Do not redo PR #25/#28. |
| Dependency | PR #25, PR #28 |
| Owner | Developer B |

### Day 11 — React product structure

| Field | Detail |
| --- | --- |
| Plan feature | Jobs IA (Discover / Matches / Saved inside Jobs), Verified vs Potential, Job Detail composition |
| Current implementation | Discover is the Jobs page. Split list + preview exists. Job Detail is a separate route. MatchBadge still shows `89% Strong Match` for preliminary V2 scores. No Saved persistence. No natural-language search. |
| Current file(s) | `frontend/src/pages/JobsPage.tsx`, `frontend/src/pages/JobDetailPage.tsx`, `frontend/src/components/JobCard.tsx`, `frontend/src/components/MatchBadge.tsx`, `frontend/src/components/signature/ScoreAssembly.tsx` |
| Status | **partial** |
| Remaining work | Inside-Jobs tabs; Potential vs Verified; requirement/eligibility/work-location panels; NL search **skeleton only** if parser is not safe |
| Dependency | Day 4 verified-fit contract |
| Owner | Developer A (tokens); this PR (Jobs IA for verified/potential) |

### Day 12 — Chrome right-side panel

| Field | Detail |
| --- | --- |
| Plan feature | Side panel states for recognized job, match, eligibility, autofill, signed-out, error |
| Current implementation | Side panel + Greenhouse/Lever fill. Panel data endpoint exists. |
| Current file(s) | `browser-extension/src/sidepanel.ts`, `browser-extension/src/fillForm.ts`, `backend/api/routes/applications.py` (`get_extension_panel_data`) |
| Status | **partial** |
| Remaining work | Visual/state skeleton for Potential/Verified/requirements-loading. Do not rewrite tab detection, permissions, ATS runtime, or no-submit. |
| Dependency | Days 6, 11 |
| Owner | Developer B |

### Day 13 — Resume file / version contracts

| Field | Detail |
| --- | --- |
| Plan feature | Approved ResumeVersion, export, ownership-checked download, extension attachment |
| Current implementation | Immutable per-job resume versions with content hash. No PDF/DOCX export, no filesystem access. |
| Current file(s) | `backend/services/resume_version_service.py`, `backend/db/models.py` (`ResumeVersionRecord`), `tests/test_resume_version_service.py` |
| Status | **partial** |
| Remaining work | Export availability contract; extension attachment selection. No unsafe FS. |
| Dependency | Day 5 |
| Owner | Platform |

### Day 14 — Extension hardening

| Field | Detail |
| --- | --- |
| Plan feature | State-matrix tests for signed-out, unsupported site, stale job, review-required, no-submit |
| Current implementation | Manifest + sidepanel tests. Not the full state matrix. |
| Current file(s) | `browser-extension/tests/sidepanel.test.ts`, `tests/test_extension_manifest.py` |
| Status | **skeleton** |
| Remaining work | Status/state coverage listed in the plan. Keep permissions minimal. |
| Dependency | Days 12–13 |
| Owner | Developer B |

---

## Cross-cutting findings (P0)

1. **Fit V2 is kept.** Ranking quality is much better. The remaining product bug is scoring from incomplete employer requirements.
2. **Job Intelligence is a skills/responsibilities extractor**, not a full employer requirement profile. Evolving it in place would overload one table. This stacked PR adds `JobRequirementProfile` as a sibling, and keeps Job Intelligence for interview/legacy compatibility.
3. **Find Jobs must stay LLM-free for the 190-job corpus.** Deep analysis is Top N + on-open.
4. **UI currently presents preliminary `overall_score` as the match.** That must become Potential Match until a current grounded profile exists.
5. **No Alembic.** New table + few columns. Do not migrate `data/careerpilot.db` in this task.
