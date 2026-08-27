# Jobs Workspace V2 audit

Stacked on PR #29 (`feat/full-job-requirements-foundation` @ `23cb46037e262b3c424db6fea85c6e7d08a2ca24`).
This is a product/UX/search branch. It must not rewrite Fit V2, requirement extraction, materials, form-fill, or the extension runtime.

---

## Existing behavior

| Surface | What it does today |
| --- | --- |
| `JobsPage` | Local React state. Loads **all** jobs via `GET /api/jobs`. Find Jobs calls `POST /api/scout-jobs` with **no query**. Title/company/location input filters the in-memory list. Natural-language bar is a non-working skeleton (`parser_ready=false`). |
| Tabs | Discover / Matches / Saved exist. Discover = filtered full catalog. Matches = jobs that have a stored score. Saved = honest empty placeholder. |
| Split view | Desktop list + right preview. Mobile list only; detail is a separate route. |
| Previous / Next | Job Detail ranks **all stored jobs** by ranking_score, not the current Jobs filters/tab. |
| Scout result | `setJobs(result.jobs)` replaces the visible list with whatever scout returned (usually the full persisted catalog after merge). |
| TanStack Query | Jobs page does **not** use it. Dashboard, Profile, Prepare, Resume do. |
| URL state | Selected job id is in `sessionStorage` only. Tab/search/filters are not in the URL. |
| `GET /api/jobs` | Unfiltered list of every stored job. No pagination. |
| Scout `what`/`where` | Backend already accepts them. Frontend never sends them. |
| Opportunity type | Frontend `title.includes("intern")` via `job-role-type.ts`. |
| Saved jobs | None. Application tracker has a `saved` status but it is not this product surface. |

## Working behavior to preserve

- Find Jobs progress (PR #28) and existing-jobs-stay-visible during scout
- Fit V2 ranking_score / Potential vs Verified (PR #29)
- Canonical persist/merge of scouted jobs (manual + previous searches stay in SQLite)
- Job Intelligence / requirement extract / score / prepare routes
- Source badges, verification statuses, Job Detail original posting
- Auth + per-user scores/materials isolation
- GET `/api/jobs` returning `list[Job]` for Dashboard and other callers

## Missing behavior

- Real natural-language → validated intent → backend filters
- Editable chips that represent the request
- Structured filter panel (work mode, eligibility, verified state, date posted)
- Canonical opportunity type on the server
- Server-side filter + pagination
- Matches as a first-class scored ranking (verified first)
- Persisted Saved jobs
- Previous/Next bound to current Jobs context
- URL-serialized workspace state
- Stale-response protection on Jobs (AbortSignal exists on `api.request` but Jobs page unused)
- Job Detail section/tabs Overview / Match / Evidence
- Inline verification loading on Potential jobs
- Dashboard Strongest Matches still treats `overall_score >= 70` as authoritative, including preliminary scores

## Unsafe / dead code

- NaturalSearchBar help text admits it does not search; easy to mistake for a working control
- In-memory `query` box looks like discovery search
- Saved tab is a placeholder — must not fake bookmarks
- `matchesRoleTypeFilter` title heuristics should not remain the product source of truth

## API gaps

- No `JobSearchIntent` request/response used by Jobs
- No paginated query endpoint
- No saved-job table/endpoints
- Scout frontend ignores `what`/`where`
- Job schema has no `opportunity_type` / `work_mode` for listing

## UI gaps

- Cards show status + source but not work mode, employment type, save, eligibility warning consistently
- Preview still dumps ScoreAssembly + truncated description
- Job Detail is a long scroll, not Overview/Match/Evidence
- No filter drawer
- Glass/workspace polish is incomplete vs the product spec

## Performance gaps

- Entire catalog (≈194) plus all scores loaded into React on every Jobs visit
- Filter/sort is O(n) in the browser including description-adjacent fields
- Job Detail re-fetches all jobs to compute neighbors
- No pagination

## Conservative decisions for this branch

1. Keep `GET /api/jobs` as an unfiltered `list[Job]` compatibility path.
2. Add `GET /api/jobs/query` for the workspace (filters + page, default 40, max 50).
3. Filter in Python over SQLite rows (~200) rather than a query-builder/ORM-from-LLM path.
4. New `saved_jobs` table only — no Alembic, no ALTER pile.
5. Deterministic NL parser first; Gemini flash-lite optional with a short timeout; never wait on Ollama for search.
6. Opportunity type is computed server-side: internship includes `internship` / `co_op` / `new_grad`; role is explicit non-intern employment; otherwise `unknown`. Ambiguous listings stay `unknown` and appear in Both.
