# CareerPilot AI agent instructions

CareerPilot is one local/self-hostable app: FastAPI backend, React/Vite frontend, SQLite persistence, and an unpacked Chromium extension.

## Start here

1. Read `docs/AI_REPO_MAP.md` before broad repository exploration.
2. Use its **Task → files** index to identify the smallest likely implementation/test surface.
3. Inspect those mapped files first.
4. Expand search only when the map is insufficient, a referenced path moved, a failing test/stack trace points elsewhere, or source code contradicts the map.
5. Source code is authoritative. If the map is stale, finish the source task safely and update the map in the same structural PR.

Do not recursively scan the whole repository by default. Do not reread unrelated subsystems just to regain context.

## v1 working mode

Treat v1 feature development as frozen unless the user explicitly reopens scope. Prefer narrow release-gate fixes, regressions, and human-QA blockers over new features or broad refactors.

## Safety invariants

- Profile-first: discovery/scouting/ranking stays gated by canonical profile readiness.
- Ordinary page loads stay read-only unless explicitly documented otherwise.
- Find Jobs may persist deterministic scores, but must not spend LLM/provider calls before the profile gate.
- Missing candidate/employer evidence is not success and must not become an invented claim.
- Candidate/preference/requirement fingerprints invalidate stale Fit/Evidence/materials where designed.
- Materials remain grounded or visibly marked as an explicit grounding override.
- Approval requires explicit human eligibility confirmation.
- CareerPilot never submits applications.
- Tracker `applied` is human-recorded state only.
- Extension EEO/demographic fields stay manual.
- Terms/privacy/consent acknowledgements stay manual.
- Resume attachment state must be truthful.
- Greenhouse/Lever identity uses ATS posting identity, never fuzzy title/company matching.
- User-scoped records must never leak across users.

## Change discipline

- Keep release fixes small and test the affected subsystem first.
- Do not weaken grounding, profile gates, EEO rules, no-submit rules, approval gates, SSRF controls, session isolation, stale-data checks, or tests just to make a failure disappear.
- Automated tests must not create or mutate `data/careerpilot.db`; use isolated/temp/copied databases.
- Never commit `.env`, API keys, session tokens, resumes, generated private materials, or QA DB files.
- Run `python scripts/check_tracked_secrets.py` and `git diff --check` before a PR.
- Do not commit directly to `main`; use a branch and PR.
