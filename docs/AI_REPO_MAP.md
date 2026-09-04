# CareerPilot AI Repository Map
> Fast navigation for Cursor/AI agents. Read this before broad code search.
>
> **Source snapshot:** GitHub `main` at `f3e870c6d267c1c78f2b6827c380e59f7bd12b15` (PR #78 already present). Source code wins if this map and the repository disagree.
>
> **A8 note:** PR #79 contains pending Greenhouse/Lever A8 fixes. It is open and not merged, so those implementation details are not part of this main-snapshot map yet. Update this section after the PR lands.
## 1. Fast Task → Files Index
| Task / symptom | Start here | Primary tests |
| --- | --- | --- |
| App boot/config/DB | `backend/main.py`, `backend/core/config.py`, `backend/db/database.py`, `backend/db/init_db.py` | full backend suite |
| Auth/login/session | `backend/api/routes/auth.py`, `backend/services/auth_service.py`, `backend/api/dependencies.py` | `test_auth.py`, `test_auth_hardening.py`, `test_cross_user_isolation.py` |
| Account deletion/privacy | `backend/api/routes/account.py`, `backend/services/account_deletion.py` | account/privacy + cross-user tests |
| Resume parse/profile | `backend/api/routes/candidate.py`, `candidate_profile_agent.py`, `candidate_provenance.py` | `test_candidate_profile.py` + resume matrix |
| Profile readiness/Discover gate | `profile_readiness.py`, `backend/api/profile_gate.py`, `ProfilePage.tsx` | `test_profile_readiness.py` |
| Find Jobs/providers | `backend/api/routes/jobs.py`, `job_scout_service.py`, `job_service.py` | scout/source tests + MVP smoke |
| Greenhouse identity/ingest | `job_scout_service.py`, `form_fill_service.py` | `test_job_source_expansion.py`, `test_form_fill_service.py` |
| Lever identity/ingest | `job_scout_service.py`, `form_fill_service.py` | `test_job_source_expansion.py`, `test_form_fill_service.py` |
| SSRF/outbound URL safety | `url_safety.py`, callers in scout/form-fill | URL/source/form-fill tests |
| Job verification/content | `job_verification_service.py`, `job_content.py` | verification/content tests |
| Job Intelligence | `backend/api/routes/scoring.py`, `job_intelligence_service.py` | `test_job_intelligence.py`, `test_job_intelligence_pipeline.py` |
| Full requirements extraction | `job_requirement_extractor.py` | requirement/Verified Fit tests |
| Fit wrong/stale | `analysis_service.py`, `scoring_orchestrator.py`, `verified_fit_service.py` | fit/scoring tests + matrix |
| Match Evidence wrong/stale | `match_evidence_service.py`, scoring route | `test_match_evidence.py`, `test_match_evidence_invariants.py` |
| Materials/grounding | `application_materials_agent.py`, `application_service.py` | materials agent/service/merge-gate tests |
| Approval/stale reviewed package | `application_service.py`, applications route | application service + merge-gate tests |
| Resume versions/export | `resume_version_service.py`, `resume_export_service.py`, applications route | resume version/export tests |
| Assisted Apply backend | `form_fill_service.py`, applications route | `test_form_fill_service.py` |
| Extension recognition | `job-recognition.ts`, `sidepanel.ts`, backend `find_job_by_url` | sidepanel + form-fill tests |
| Extension fill | `fillForm.ts`, `field-status.ts` | `browser-extension/tests/fillForm.test.ts` |
| Extension resume attach | `attachFile.ts`, `sidepanel.ts`, extension API | sidepanel/attachment + extension export tests |
| EEO/manual-field safety | `field-status.ts`, `fillForm.ts`, backend form-fill | fillForm + form-fill tests |
| Interview prep | `backend/api/routes/interview.py`, `interview_service.py`, `InterviewPrepPanel.tsx` | `test_interview_service.py` |
| Tracker/follow-up | `backend/api/routes/tracker.py`, `application_tracker_service.py`, `ApplicationsPage.tsx` | tracker + ApplicationsPage tests |
| Dashboard counts | `application_tracker_service.py`, `DashboardPage.tsx` | dashboard/tracker tests |
| Career Growth | `career_growth_service.py`, `GrowthPage.tsx` | `test_career_growth.py`, GrowthPage tests |
| Conversion Analytics | `analytics_service.py`, `AnalyticsPage.tsx` | `test_analytics.py`, AnalyticsPage tests |
| Theme/reduced motion | `frontend/src/lib/theme.tsx`, `frontend/src/index.css`, `SettingsPage.tsx` | frontend + human visual QA |
| Frontend routes | `frontend/src/App.tsx`, `AppShell.tsx` | affected page tests |
| Frontend API/types | `frontend/src/lib/api.ts`, `frontend/src/lib/types.ts` | affected page/component tests + typecheck |
| CORS/CSRF/security headers | `backend/main.py`, `core/csrf.py`, `core/security_headers.py`, `core/config.py` | security + CORS browser checks |
| CI/release gate | `.github/workflows/ci.yml`, `.github/workflows/security.yml`, `docs/V1_RELEASE_CHECKLIST.md` | CI + Gitleaks + manual checklist |
## 2. Top-Level Architecture

```text
React/Vite browser app
    ↓ HTTP + session cookie
FastAPI routes
    ↓
Service layer
    ↓
SQLAlchemy models / SQLite
Chromium extension side panel
    ↓ local extension API + session header
FastAPI extension endpoints
    ↓ approved package / resume-version gates
Injected Greenhouse/Lever helpers
    ↓
Human reviews and manually presses Submit
```
- `backend/` — API, config/security, DB, schemas, services.
- `frontend/` — React/TypeScript/Vite UI.
- `browser-extension/` — Manifest V3 side panel + live ATS form fill.
- `tests/` — backend pytest with isolated SQLite/fixtures.
- `scripts/` — browser/matrix/security/manual smoke helpers.
- `docs/` — release/product/handoff notes.
- `.github/workflows/` — CI and full-history security scan.
## 3. App Boot, Config, Database
**Files**
- `backend/main.py` — FastAPI app, lifespan, CORS, CSRF/security middleware, router registration, sanitized exception handlers.
- `backend/core/config.py` — settings/runtime validation.
- `backend/db/database.py` — SQLAlchemy engine/session/base.
- `backend/db/init_db.py` — table creation and compatibility column setup; no Alembic.
- `backend/db/models.py` — persistent records/relationships.
**Debug**
- Startup refusal → `config.py` / `main.py`.
- Missing table/column → `init_db.py` then `models.py`.
- Never point automated tests at `data/careerpilot.db`.
## 4. Auth, Sessions, Isolation, Account Deletion
**Routes/services**
- `backend/api/routes/auth.py`
- `backend/api/routes/account.py`
- `backend/api/dependencies.py`
- `backend/services/auth_service.py`
- `backend/services/account_deletion.py`
- `backend/core/csrf.py`, `rate_limit.py`, `security.py`, `security_headers.py`
**Models**
- `User`, `UserSession`, plus user-owned rows in `models.py`.
**Frontend**
- `frontend/src/lib/auth.tsx`
- `LoginPage.tsx`, `SignupPage.tsx`, `SettingsPage.tsx`
- `frontend/src/components/ProtectedRoute.tsx`
**Invariants**
- Failed login stays generic.
- Delete account removes owner-scoped private rows and sessions; shared job catalog remains.
- One user's score/material/tracker/interview data never leaks to another.
**Tests**
- `tests/test_auth.py`
- `tests/test_auth_hardening.py`
- `tests/test_cross_user_isolation.py`
## 5. Candidate Profile / Resume Parsing
**Route** `backend/api/routes/candidate.py`
**Services**
- `backend/services/candidate_profile_agent.py` — parse/extract/ground profile.
- `backend/services/candidate_provenance.py` — candidate provenance/fingerprint helpers.
**Models** `Candidate`, `TargetPreference`
**Frontend**
- `ProfilePage.tsx`, `OnboardingPage.tsx`, `ResumePage.tsx`
- `frontend/src/components/ResumeParsingProgress.tsx`
**Invariants**
- Resume text is evidence, not permission to invent fields.
- Parser omissions remain omissions downstream.
- Candidate changes may stale Fit/Evidence/materials.
**Tests** `tests/test_candidate_profile.py`; `python scripts/test_candidate_profile_matrix.py --synthetic`
## 6. Profile Readiness Gate
**Canonical source**
- `backend/services/profile_readiness.py`
- HTTP adapter: `backend/api/profile_gate.py`
**Minimum readiness**
- usable identity/name;
- at least one grounded candidate evidence category;
- at least one target role;
- locations/work mode/opportunity type optional unless source changes.
**Frontend consumers** `ProfilePage.tsx`, `DashboardPage.tsx`
**Invariant** UI must follow server readiness rather than invent a stricter checklist.
**Tests** `tests/test_profile_readiness.py`
## 7. Job Discovery / Scout / Persistence
**Route** `backend/api/routes/jobs.py`
**Services**
- `job_scout_service.py` — Adzuna, RemoteOK, Greenhouse, Lever, Remotive, Jobicy, Himalayas, manual URLs, normalization/dedupe/persistence.
- `job_service.py` — record/schema/listing helpers.
- `job_verification_service.py` — verification/freshness.
- `job_content.py` — content status/fingerprint.
- `url_safety.py` — outbound/SSRF safety.
- `saved_job_service.py` — user bookmark state.
**Models** shared `JobRecord`; user-scoped `SavedJobRecord`.
**Frontend** `JobsPage.tsx`, `JobDetailPage.tsx`.
**Invariants**
- readiness before scouting/provider work;
- Find Jobs avoids LLM-per-listing behavior;
- one dead provider does not kill entire scout;
- shared JobRecord is not private application state.
## 8. Greenhouse Identity / Ingestion
**Files**
- `backend/services/job_scout_service.py`: `parse_greenhouse_posting_url`, `canonical_greenhouse_posting_url`, API fetch/ingest/dedupe.
- `backend/services/form_fill_service.py`: `find_job_by_url` for live tab lookup.
- `browser-extension/src/job-recognition.ts`.
**Identity** board token + numeric job ID. Tracking query params/host aliases must not create a second posting. Never fuzzy-match title/company.
**Tests** `tests/test_job_source_expansion.py`, `tests/test_form_fill_service.py`, extension recognition/sidepanel tests.
## 9. Lever Identity / Ingestion
**Files**
- `backend/services/job_scout_service.py`: `parse_lever_posting_url`, `canonical_lever_posting_url`, provider/manual ingest.
- `backend/services/form_fill_service.py`: posting vs `/apply` identity.
- `browser-extension/src/job-recognition.ts`.
**Identity** company slug + posting UUID. Posting and `/apply` are one job. Tracking queries must not fork identity. Outbound API calls remain host-allowlisted/SSRF-safe.
**A8 caveat** PR #79 is open and not merged; Lever manual-ingest internals on main may change after it lands.
## 10. Job Intelligence / Requirement Extraction
Two employer-evidence layers exist; do not casually collapse them.
**Job Intelligence**
- `backend/services/job_intelligence_service.py`
- `JobIntelligenceRecord`
- route surface in `backend/api/routes/scoring.py`
- used by materials/interview compatibility paths.
**Full requirement profile**
- `backend/services/job_requirement_extractor.py`
- `backend/schemas/job_requirements.py`
- `JobRequirementProfileRecord`
- richer requirements/groups/evidence for Verified Fit.
**Tests** `tests/test_job_intelligence.py`, `tests/test_job_intelligence_pipeline.py`, requirement/verified-fit tests.
**Invariant** employer requirements never become candidate experience.
## 11. Fit Scoring / Verified Fit
**Route** `backend/api/routes/scoring.py`
**Services**
- `backend/services/analysis_service.py` — deterministic score logic, stored-score reads, fingerprints/staleness.
- `backend/services/scoring_orchestrator.py` — explicit intelligence→score orchestration.
- `backend/services/verified_fit_service.py` — Verified Fit overlay from full requirements.
- `backend/services/fit_v2.py` — Fit V2 components where referenced.
- `backend/services/eligibility_engine.py` — eligibility/group logic.
**Model** `MatchScoreRecord`
**Frontend** `JobsPage.tsx`, `JobDetailPage.tsx`, match/evidence components.
**Invariants**
- Stored-score GET is read-only; Calculate Fit is explicit.
- Missing/stale score does not masquerade as current.
- Missing skill/requirement evidence is not satisfied.
- Potential/preliminary and Verified semantics remain distinct.
**Useful command** `python scripts/test_fit_scoring_matrix.py`
## 12. Match Evidence / Staleness
**Service** `backend/services/match_evidence_service.py`
**Route** `GET /api/jobs/{job_id}/match-evidence` in scoring routes.
**Model** `MatchEvidenceRecord` linked to `MatchScoreRecord`.
**Fingerprint dependencies**
- candidate: `candidate_provenance.py`
- requirement: `job_requirement_extractor.py`
- preference: `match_evidence_service.py`
**Invariants**
- Evidence GET never rescoring/provider-calls.
- candidate/preference/requirement changes surface stale evidence.
- aliases/groups cannot manufacture candidate matches.
**Tests** `tests/test_match_evidence.py`, `tests/test_match_evidence_invariants.py`
## 13. Application Materials / Grounding
**Route surface** `backend/api/routes/applications.py`
**Services**
- `backend/services/application_service.py` — package lifecycle/persistence/approval orchestration.
- `backend/services/application_materials_agent.py` — prompt, canonical evidence catalog, claim grounding, unsupported-claim handling.
- `backend/services/llm_client.py`, `llm_provider_sequence.py` — provider boundary.
**Model** `ApplicationPackageRecord`
**Frontend**
- `frontend/src/pages/PrepareApplicationPage.tsx`
- `frontend/src/components/PrepareApplicationWorkspace.tsx`
**Invariants**
- page load only reads stored package;
- Generate is explicit;
- grounding validator is final authority;
- `grounding_override` is explicit and visibly different from `grounded=true`;
- job requirements cannot become candidate accomplishments;
- no invented employers/titles/projects/metrics/years/skills.
**Tests**
- `tests/test_application_materials_agent.py`
- `tests/test_application_service.py`
- `tests/test_application_materials_merge_gates.py`
## 14. Approval / Reviewed Materials
**Files** `application_service.py`, applications route, `PrepareApplicationWorkspace.tsx`.
**Invariants**
- Approve requires explicit eligibility confirmation.
- Stale reviewed materials require explicit discard/regenerate behavior.
- Approval never submits or auto-marks tracker `applied`.
- `approved_materials_hash` protects the reviewed snapshot.
## 15. Resume Versions / Export
**Services**
- `backend/services/resume_version_service.py`
- `backend/services/resume_export_service.py`
- some export contracts/helpers also reference `backend/services/resume_export.py`.
**Routes** resume-version endpoints in `backend/api/routes/applications.py`.
**Model** `ResumeVersionRecord`
**Frontend** `ResumeVersionPanel.tsx`, `ResumePage.tsx`
**Extension** `browser-extension/src/api.ts` downloads owned version files.
**Invariants**
- immutable approved snapshot;
- no automatic version creation on load/approval;
- ownership checked before download;
- PDF/DOCX MIME/filename truthful.
**Tests** `test_resume_version_service.py`, `test_resume_export.py`, `test_extension_resume_export.py`
## 16. Assisted Apply Backend
**Service** `backend/services/form_fill_service.py`
**Routes** assisted-apply and `/api/extension/*` surfaces in `backend/api/routes/applications.py`.
**Responsibilities**
- resolve browser URL to stored ATS job;
- require approved/current application package;
- build safe reusable candidate fields;
- never infer unsupported fields;
- expose panel/autofill data.
**Model** `FormFillAttemptRecord` where server-side preview attempts are stored.
**Invariant** Assisted Apply ends before submit. Human submits.
**Tests** `tests/test_form_fill_service.py`
## 17. Browser Extension Side Panel
**Files**
- `browser-extension/manifest.json`
- `browser-extension/src/config.ts`
- `browser-extension/src/background.ts`
- `browser-extension/src/sidepanel.ts`
- built output under `browser-extension/dist/`.
**API/auth** `browser-extension/src/api.ts`
**Panel state/rendering** `panel-states.ts`, `render.ts`
**Invariants**
- no separate fake account state;
- unsupported/non-http tabs are not treated as jobs;
- tab switches cannot leak prior job/score/material/document state;
- permissions remain scoped to local API + supported ATS origins.
**Tests** `browser-extension/tests/sidepanel.test.ts`, `tests/test_extension_manifest.py`
## 18. Extension ATS Recognition
**File** `browser-extension/src/job-recognition.ts`
**Backend partner**
- `form_fill_service.py::find_job_by_url`
- canonical parsers in `job_scout_service.py`.
**Supported identity shapes** Greenhouse posting/embed forms supported by source; Lever UUID posting and `/apply`.
**Invariant** frontend recognition and backend canonical identity must agree.
## 19. Extension Safe Autofill
**Files** `browser-extension/src/fillForm.ts`, `field-status.ts`, orchestration in `sidepanel.ts`.
**Behavior**
- fills safe stored identity/contact/reusable fields;
- may reveal Greenhouse Cover Letter `Enter manually` text area;
- flags uncertain/unmapped required fields;
- returns filled/flagged summary.
**Never do**
- `.submit()`;
- `requestSubmit()`;
- simulated Enter-to-submit;
- click ATS Submit/Application Send;
- guess unsupported custom answers.
## 20. Resume Attachment in Extension
**Files** `attachFile.ts`, `sidepanel.ts`, `api.ts`
**Flow**

```text
owned ResumeVersion
→ extension download
→ recognize resume input
→ File/DataTransfer attach
→ input/change events
→ verify real page attachment/display
→ fill safe fields
→ re-verify
```
**Invariants**
- blocked programmatic attach → truthful manual-upload guidance;
- never report Attached without real page verification;
- never use previous tab/job's resume version;
- PR #77 changed Greenhouse attachment verification; preserve it during A8 rebases.
## 21. EEO / Manual-Only Safety
**Files** `browser-extension/src/field-status.ts`, `fillForm.ts`, backend `form_fill_service.py`.
**Always manual** gender, race/ethnicity, veteran status, disability status.
**Also deliberate human actions** terms/privacy/policy acknowledgement and uncertain custom questions.
**Invariant** a stored preference value does not make protected-class questions safe to autofill.
## 22. Interview Prep / Answer Feedback
**Route** `backend/api/routes/interview.py`
**Service** `backend/services/interview_service.py`
**Frontend** `frontend/src/components/InterviewPrepPanel.tsx`, hosted by `JobDetailPage.tsx`.
**Behavior**
- Prepare Interview baseline is deterministic from stored employer/candidate/Fit evidence.
- Stored prep persists.
- Practice-answer feedback is explicit, can call provider sequence, and is ephemeral.
**Invariants**
- missing skills remain gaps;
- page load generates nothing;
- feedback cannot manufacture experience.
**Tests** `tests/test_interview_service.py`
## 23. Application Tracker / Dashboard
**Route** `backend/api/routes/tracker.py`
**Service** `backend/services/application_tracker_service.py`
**Model** `ApplicationTrackerRecord`
**Frontend**
- `frontend/src/pages/ApplicationsPage.tsx` (`/track`, legacy `/applications`)
- `frontend/src/pages/DashboardPage.tsx`
**Invariants**
- GET/list reads create no tracker rows;
- state changes only by explicit PATCH;
- backend transition graph is authoritative;
- `applied` is user-recorded state, not a submission;
- follow-up date is storage only, not an email/calendar/push promise;
- dashboard must not double-count approval fallback + tracker row.
**Tests** tracker tests, `ApplicationsPage.test.tsx`, `DashboardPage.test.tsx`
## 24. Application Conversion Analytics
**Current main**
- `backend/api/routes/analytics.py`
- `backend/services/analytics_service.py`
- `backend/schemas/analytics.py`
- `ApplicationEventRecord` in `backend/db/models.py`
- `frontend/src/pages/AnalyticsPage.tsx`
- `/analytics` in `frontend/src/App.tsx`.
**Flow**

```text
existing save/materials/approval/tracker mutations
→ analytics_service.record_event
→ ApplicationEventRecord
→ GET /api/analytics/summary
→ funnel / conversion / median-time / breakdown UI
```
**Tests** `tests/test_analytics.py`, `frontend/src/pages/AnalyticsPage.test.tsx`
**Invariant** analytics summary is read-only and must not scout, score, or call providers.
## 25. Career Growth / Skills Gap
- Route: `backend/api/routes/career_growth.py`
- Service: `backend/services/career_growth_service.py`
- UI: `frontend/src/pages/GrowthPage.tsx`
- Tests: `tests/test_career_growth.py`, `GrowthPage.test.tsx`
- Invariants: ready profile required; read-only stored evidence; no scoring/provider on load; never changes Fit.
## 26. Frontend Routing / Product Surfaces
- Router: `frontend/src/App.tsx`
- Shell/auth: `AppShell.tsx`, `ProtectedRoute.tsx`, `frontend/src/lib/auth.tsx`
- Public: `/`, `/login`, `/signup`, `/privacy`
- Protected: `/onboarding`, `/dashboard`, `/profile`, `/jobs`, `/jobs/:jobId`, `/jobs/:jobId/prepare`, `/analyze`, `/prepare`, `/track`, `/growth`, `/analytics`, `/resume`, `/resume/:versionId`, `/settings`.
- `/applications` aliases Track; `/applications/:jobId` redirects to Prepare.
## 27. Theme / Responsive / Reduced Motion
- `frontend/src/lib/theme.tsx`
- `frontend/src/index.css`
- `frontend/src/pages/SettingsPage.tsx`
- Contract: Light/Dark/System; black/midnight + cool-light + violet; reduced motion = OS media query OR app preference.
- Human gate: 1440/1280/768/390, real browser 200% zoom, visible keyboard focus, reduced motion, dark/light readability.
- Checklist: `docs/V1_RELEASE_CHECKLIST.md`
## 28. Privacy / CORS / CSRF / SSRF / Logging
- `backend/core/config.py`, `csrf.py`, `security.py`, `security_headers.py`, `rate_limit.py`
- `backend/services/url_safety.py`
- sanitized exception handling: `backend/main.py`
- `.gitleaks.toml`, `.github/workflows/security.yml`
- Rules: no wildcard credentialed CORS; production secure-cookie enforcement; no raw private input in errors/logs; outbound ingest URLs stay allowlisted; log IDs/counts/categories, not resumes/prompts/materials/tokens.
## 29. Release / CI / Manual Gate
- CI: `.github/workflows/ci.yml`
- Security: `.github/workflows/security.yml`
- Manual: `docs/V1_RELEASE_CHECKLIST.md`, `docs/demo-runbook.md`
- Broad checks: `scripts/test_mvp_foundation_browser.py`, `scripts/test_fit_scoring_matrix.py`, `scripts/test_candidate_profile_matrix.py --synthetic`
- Automated tests do not replace live browser/ATS checks. Do not tag/publish with a known A8/A9 release blocker.
## 30. Core Data Flows
**Profile → Discover**

```text
resume → candidate route → candidate_profile_agent → Candidate/TargetPreference
→ profile_readiness → Find Jobs gate → job_scout_service → JobRecord → Discover
```
**Analyze / Verified Fit**

```text
JobRecord/posting → Intelligence + requirement extraction → candidate/preferences
→ eligibility/Fit → MatchScoreRecord → MatchEvidenceRecord → Job Detail
```
**Prepare**

```text
Candidate + preferences + current Fit + employer evidence
→ application_materials_agent → grounding → ApplicationPackageRecord
→ human eligibility confirmation → approval → optional ResumeVersion
```
**Interview**

```text
stored employer evidence + current Fit gaps + candidate evidence
→ deterministic InterviewPrepRecord → optional explicit ephemeral LLM feedback
```
**Track**

```text
stored jobs/packages/scores → GET applications → human PATCH status
→ ApplicationTrackerRecord → Dashboard aggregation
```
**Extension**

```text
active ATS tab → job-recognition.ts → panel-data → backend ATS identity lookup
→ approved/current package gate → autofill + owned resume download
→ attachFile.ts + fillFormInPage → manual EEO/custom fields → HUMAN Submit
```
**Analytics**

```text
existing state mutations → analytics_service.record_event
→ ApplicationEventRecord → read-only summary → AnalyticsPage
```
## 31. Critical v1 Invariants — Do Not Re-Derive Every Session
1. Profile-first discovery is backend-authoritative.
2. No gated provider/scouting spend before canonical readiness.
3. Ordinary page loads are read-only unless explicitly documented.
4. Find Jobs may write deterministic scores; it is not LLM-per-job.
5. Missing employer/candidate evidence is not success.
6. Employer requirements and candidate evidence are separate domains.
7. Fingerprints control stale Fit/Evidence/materials.
8. Grounding is a release safety boundary.
9. Override is explicit and never masquerades as grounded.
10. Approval requires human eligibility confirmation and does not submit.
11. Tracker `applied` does not submit.
12. Extension Fill does not submit.
13. EEO/protected-class and terms/privacy consent remain manual.
14. Unknown/custom fields are manual rather than guessed.
15. Resume attachment status reflects the real ATS page.
16. Extension documents follow the current job/tab.
17. ATS identity is posting-ID based, not title similarity.
18. User-owned data is isolated; shared JobRecord can be global.
19. Account deletion removes private owner data/sessions, not shared jobs.
20. Career Growth and Analytics reads do not modify Fit or call providers.
21. Automated tests never mutate `data/careerpilot.db`.
## 32. Test / Command Index
**Backend**

```bash
python -m pytest -q
python scripts/test_fit_scoring_matrix.py
python scripts/test_candidate_profile_matrix.py --synthetic
```
**Useful focused backend**

```bash
python -m pytest -q tests/test_profile_readiness.py
python -m pytest -q tests/test_job_source_expansion.py tests/test_form_fill_service.py
python -m pytest -q tests/test_job_intelligence.py tests/test_job_intelligence_pipeline.py
python -m pytest -q tests/test_match_evidence.py tests/test_match_evidence_invariants.py
python -m pytest -q tests/test_application_materials_agent.py tests/test_application_service.py tests/test_application_materials_merge_gates.py
python -m pytest -q tests/test_resume_version_service.py tests/test_resume_export.py tests/test_extension_resume_export.py
python -m pytest -q tests/test_interview_service.py tests/test_career_growth.py tests/test_analytics.py
```
**Frontend**

```bash
cd frontend && npm run test:run && npm run typecheck && npm run build
```
**Extension**

```bash
cd browser-extension && npm test && npm run typecheck && npm run build
```
**Security/whitespace**

```bash
python scripts/check_tracked_secrets.py
git diff --check
```
## 33. When to Expand Beyond the Map
Expand only when a mapped path moved, stack trace/test points elsewhere, ownership changed, a real bug crosses subsystem boundaries, the map is stale after a structural PR, or the user explicitly requests a repo-wide audit. Search by symbol/error/path first; do not immediately scan every file.
## 34. Map Maintenance
Update this map in the same structural PR when routes/product destinations, service ownership, major models, ATS identity, provider/grounding/staleness contracts, extension permission/fill/attachment architecture, or primary test/release commands change. Small implementation-only fixes do not require map churn if ownership and invariants stay the same.
## 35. Known Documentation Inconsistency at This Snapshot
`README.md` still says analytics is out of scope, but current `main` contains `/analytics`, `ApplicationEventRecord`, `analytics_service.py`, `AnalyticsPage.tsx`, and analytics tests from PR #78. Source code is authoritative. Align README separately if the owner wants the public description updated; do not hide this mismatch inside an unrelated release fix.
