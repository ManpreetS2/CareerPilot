# Post-v1 maintenance triage

Informational only. Opened during Phase 9 so these items are not rediscovered in a separate prompt. **Do not merge as part of the showcase package.**

Showcase work must not merge Dependabot #88–#91, must not perform a React Router 7 migration, and must not invent GitHub Actions commit SHAs.

---

ITEM: Dependabot #88 — extension-compatible group (`@types/chrome`, autoprefixer, postcss)
CURRENT RISK: Low. Dev/tooling dependencies in `browser-extension/`.
USER-FACING: No, unless a build/toolchain break appears after the bump.
BREAKING RISK: Low.
RECOMMENDED ACTION: Review the PR diff, run `npm ci && npm test && npm run typecheck && npm run build` in `browser-extension/`, merge only if the lockfile change is boring.
RECOMMENDED PR GROUP: extension-dev-deps
DO NOW / LATER: LATER
WHY: Post-v1. Not a high/critical production finding. Keep Fill/attachment certification SHA unchanged unless fill code moves.

---

ITEM: Dependabot #89 — python-docx floor `>=1.2.0,<2.0.0`
CURRENT RISK: Low. Resume export dependency floor.
USER-FACING: Only if export PDF/DOCX changes.
BREAKING RISK: Low inside `<2.0.0`; still needs export tests.
RECOMMENDED ACTION: Dedicated pip PR. Run resume export tests and `python -m pytest -q`.
RECOMMENDED PR GROUP: python-export-floors (can pair with #90 if both stay non-breaking)
DO NOW / LATER: LATER
WHY: Floor bump, not an emergency. Do not fold into docs/screenshots.

---

ITEM: Dependabot #90 — pdfplumber floor `>=0.11.10`
CURRENT RISK: Low. Resume parse/extraction dependency floor.
USER-FACING: Only if parse behavior changes.
BREAKING RISK: Low for a patch floor; still needs candidate-profile/resume tests.
RECOMMENDED ACTION: Dedicated pip PR. Run resume/profile tests on isolated SQLite.
RECOMMENDED PR GROUP: python-export-floors (optional with #89)
DO NOW / LATER: LATER
WHY: Same as #89. Do not merge merely because it is newer than #88.

---

ITEM: Dependabot #91 — frontend-compatible group (includes lucide, motion, and other frontend updates)
CURRENT RISK: Medium operational noise. Broad grouped bump can change UI without a product bug.
USER-FACING: Possible visual/animation drift.
BREAKING RISK: Medium for a grouped bump; still not React Router 7.
RECOMMENDED ACTION: Do **not** merge because it is the newest Dependabot PR. Review each package, run frontend `npm run test:run`, typecheck, build, and a visual pass on landing/auth.
RECOMMENDED PR GROUP: frontend-deps (alone)
DO NOW / LATER: LATER
WHY: Showcase screenshots should not fight an animation library bump in the same week.

---

ITEM: Moderate react-router finding (react-router-dom ^6.29.0) requiring a 7.x migration
CURRENT RISK: Moderate advisory on 6.x. CI production audit uses `--audit-level=high` and was green at v1.0.0.
USER-FACING: None until migrated.
BREAKING RISK: **High.** React Router 7 is a breaking migration (data routers, future flags, type changes).
RECOMMENDED ACTION: Schedule a dedicated migration PR with frontend tests and a route-by-route pass. Do not “just bump” inside #91.
RECOMMENDED PR GROUP: breaking-react-router-7
DO NOW / LATER: LATER
WHY: Explicitly out of Phase 9. Do not migrate in a showcase or grouped Dependabot PR.

---

ITEM: Extension dev vitest / `@vitest/mocker` moderate
CURRENT RISK: Low. `browser-extension` vitest `^3.2.7` is a **devDependency**. Not shipped in the unpacked extension runtime.
USER-FACING: No.
BREAKING RISK: Low–medium if vitest major-bumps test APIs.
RECOMMENDED ACTION: Track with extension-dev-deps. Run `npm test`. Do not treat as a Fill certification trigger.
RECOMMENDED PR GROUP: extension-dev-deps
DO NOW / LATER: LATER
WHY: Dev-only advisory. Unrelated to A8.

---

ITEM: CI GitHub Actions exact-SHA pinning (`actions/checkout@v4`, `setup-python@v5`, `setup-node@v4` in `.github/workflows/ci.yml`)
CURRENT RISK: Supply-chain hygiene. Security workflow already pins `actions/checkout` to `3d3c42e5aac5ba805825da76410c181273ba90b1` (# v7.0.1). CI still uses floating tags.
USER-FACING: No.
BREAKING RISK: Low if SHAs are copied from the **official** action release that matches the intended tag. High if SHAs are guessed.
RECOMMENDED ACTION: Pin only after resolving each tag to the upstream commit published by `actions/checkout`, `actions/setup-python`, and `actions/setup-node`. Record tag + SHA in the PR.
RECOMMENDED PR GROUP: ci-action-pinning
DO NOW / LATER: LATER
WHY: Do not invent SHAs in Phase 9. Floating tags are a known follow-up, not a v1.0.0 blocker.

---

ITEM: Historical Day 1 / Developer A/B source comments
CURRENT RISK: None functional. Comments and docs (`backend/services/__init__.py`, `backend/db/models.py`, `docs/developer-b-ui-handoff.md`, `docs/agile-plan-gap-audit.md`) describe an older split.
USER-FACING: No.
BREAKING RISK: None if comments are edited; noise if a cleanup PR touches runtime files without need.
RECOMMENDED ACTION: Optional comment/doc cleanup PR. Do not rewrite services “to match the comments.”
RECOMMENDED PR GROUP: docs-comment-hygiene
DO NOW / LATER: LATER
WHY: Historical context. Cleaning comments is not a product fix.

---

ITEM: Starlette `HTTP_422_UNPROCESSABLE_ENTITY` deprecation warnings
CURRENT RISK: Low. Call sites in `backend/api/routes/*.py`, `application_service.py`, `auth_service.py`, and tests still use the alias.
USER-FACING: No. Request validation still returns 422.
BREAKING RISK: Low if replaced with the current Starlette/FastAPI constant (`HTTP_422_UNPROCESSABLE_CONTENT` in newer Starlette). Must keep status code 422.
RECOMMENDED ACTION: Mechanical alias update + existing 422 tests. No API contract change.
RECOMMENDED PR GROUP: starlette-422-alias
DO NOW / LATER: LATER
WHY: Deprecation noise in pytest, not a security issue. Do not mix with showcase docs.
