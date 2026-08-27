# CareerPilot

Grounded job search. Human-approved applications.

CareerPilot helps a candidate move from a resume to ranked, verified jobs and human-approved application materials. These are logical modules inside **one application**, not separately deployed microservices or autonomous agents. CareerPilot never automatically submits an application.

## Product destinations

Primary web navigation is workflow-first:

- Overview (`/dashboard`)
- Discover (`/jobs`)
- Analyze (`/jobs/:jobId`, or `/analyze` when no job is selected)
- Prepare (`/jobs/:jobId/prepare`, or `/prepare` when no job is selected)
- Track (`/track`; `/applications` is the same tracker)

Supporting destinations: Profile, Resume, Settings.

Analyze and Prepare stay contextual under a selected job. Interview Coach remains on Job Detail. Application Tracker is a first-class Track destination with Kanban and list/timeline views.

Public routes: `/`, `/login`, `/signup`. New signup continues through `/onboarding`.

## MVP workflow

```
Resume
→ Candidate Profile
→ Job Discovery
→ Job Verification
→ Job Intelligence
→ Fit Score
→ Ranked Jobs
→ Tailored Application Materials
→ Human Approval
→ Immutable Resume Version
→ Assisted Application
→ Interview Preparation
```

## Architecture

| Layer | Stack |
| --- | --- |
| Backend API | FastAPI + Uvicorn |
| Frontend | React + TypeScript + Vite + Tailwind CSS + customized shadcn/Radix primitives |
| Data fetching | TanStack Query |
| Database | SQLite via SQLAlchemy (`data/careerpilot.db`, gitignored) |
| Schemas | Shared Pydantic models |
| LLM | Thin `LLMClient` for Ollama, Gemini, Anthropic, and OpenAI. Candidate profile, Job Intelligence, application materials, and mock-interview answer feedback try providers in `LLM_PROVIDER_ORDER` (one provider at a time). Fit scoring stays deterministic. `DEFAULT_LLM_PROVIDER` is only the prompt harness default when `--provider` is omitted. |
| Browser extension | Unpacked Chrome extension with a side panel and approved Greenhouse/Lever autofill. It never submits. |

```
CareerPilot/
├── backend/              # FastAPI app, DB, schemas, services
├── frontend/             # React + Vite UI
├── browser-extension/    # Local Chrome extension (never submits)
├── tests/                # pytest (isolated in-memory SQLite)
├── scripts/              # Privacy-safe matrix runners and audits
├── docs/                 # Product and developer-handoff notes
├── data/                 # SQLite file (gitignored)
├── logs/                 # runtime logs (gitignored)
├── .env.example
├── requirements.txt
└── README.md
```

## Current status

CareerPilot is an authenticated local product. Signup, login, logout, and `GET /api/auth/me` exist. Private records (candidate, preferences, scores, materials, tracker rows, interview prep, form-fill attempts) are scoped to the signed-in user. Jobs and job intelligence remain shared public data.

**Completed in this repo**

- Signup / login / logout / `/api/auth/me` with an HttpOnly session cookie (`careerpilot_session`)
- CSRF origin checks for cookie-authenticated state changes
- CORS from exact `ALLOWED_ORIGINS` plus an optional exact `EXTENSION_ORIGIN`
- `COOKIE_SECURE` required when `APP_ENV=production`
- Extension session header accepted only on the exact autofill route from the configured extension origin
- `GET /api/profile` — read-only current candidate and latest preferences
- Grounded candidate profile, job scout/verification/intelligence, fit scoring, materials, approval, assisted apply, tracker APIs, interview prep, and immutable resume versions
- Application materials are generated from stored evidence, not a placeholder
- Mock-interview answer feedback is ephemeral (not stored) and follows `LLM_PROVIDER_ORDER`
- Tracker rows can store a user-set follow-up date; CareerPilot does not send automated notifications or reminders. Track is a primary web destination (`/track`).

Opening Dashboard, Jobs, Job Detail, Prepare Application, Profile, Resume, or Settings never scores a job, extracts requirements, generates materials, approves, or creates a resume version by itself. Find Jobs persists a deterministic fit score (`score_job`) for each scoreable listing and does not call an LLM. Calculate Fit, Generate Materials, Prepare Interview, Approve, and Save Resume Version stay explicit. Approval still requires the grounded/current-owner gate and eligibility confirmation. Assisted Apply and the extension never submit forms.

Job discovery currently supports Greenhouse, Lever, Remotive, Adzuna, RemoteOK, Jobicy, Himalayas, and manual posting URLs. The Jobs workspace now uses a compact list plus desktop preview, internships/full-time/both title filter, and previous/next job navigation. Developer B still owns discovery, verification, ATS/form-fill, and the Chrome extension; see `docs/developer-b-ui-handoff.md`.

PDF and DOCX export are **not** implemented. Do not expect download buttons.

The Chrome extension provides a side panel and approved autofill for Greenhouse/Lever. Extension resume-file upload is not implemented. Unpacked real-Chrome visual verification remains Developer B’s lane and is not claimed complete here.

**Legacy local data**

Rows created before auth (`user_id` NULL) are **not** auto-assigned. To attach them to one existing account, run the dry-run CLI first:

```bash
python scripts/claim_legacy_ownership.py --user-id <id>
python scripts/claim_legacy_ownership.py --user-id <id> --apply --confirm
```

Writing the production file `data/careerpilot.db` also requires `--confirm-production-database`. The command never runs during startup, imports, tests, or CI.

**Still out of scope**

- Deployment / production hosting
- Password reset
- Email verification
- Login rate limiting
- Live-provider verification in CI
- Automatic job application submission
- PDF / DOCX resume export
- Extension resume-file upload


## Privacy and safety

- Automated tests use isolated in-memory SQLite. They must never create or mutate `data/careerpilot.db`.
- Logs use IDs, counts, and exception types, not passwords, tokens, resumes, prompts, generated materials, or raw exception text that may contain those values.
- Validation errors never echo submitted `input` values.
- No candidate skill, employer, metric, or education claim may be invented without stored evidence.
- Assisted apply and the browser extension **never click submit**. The human reviews and submits.
- Page load for Jobs, Job Detail, Prepare Application, Fit Score, Resume, and Interview Prep is read-only. Calculate Fit and generation run only on an explicit user action. Find Jobs also persists a deterministic fit score for scoreable listings (no LLM).
- Private records are user-scoped. Shared job titles may be visible to every signed-in user; scores, recommendations, packages, tracker state, approval, and interview evidence are not.

## Setup

Requires **Python 3.11+** and **Node.js 20+**.

### Backend

```bash
python3.11 -m venv .venv
```

macOS / Linux:

```bash
source .venv/bin/activate
```

Windows:

```bash
.venv\Scripts\activate
```

```bash
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env
```

Add `GEMINI_API_KEY` (and optional Anthropic/OpenAI keys) to `.env` for Gemini fallback. Never commit `.env`.

Ollama is optional but recommended on the host PC:

```
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:14b
LLM_PROVIDER_ORDER=ollama,gemini
```

Teammate devices do **not** install Ollama or pull `qwen3:14b`. They run CareerPilot locally and send inference to the host through Tailscale Serve, using a placeholder like this only in their own gitignored `.env`:

```
OLLAMA_BASE_URL=https://<host-device>.<tailnet>.ts.net
OLLAMA_MODEL=qwen3:14b
LLM_PROVIDER_ORDER=ollama,gemini
```

Rules:

- Only the host installs Ollama and pulls `qwen3:14b`.
- Keep Ollama bound to `127.0.0.1:11434`. Never set `OLLAMA_HOST=0.0.0.0`.
- Use Tailscale Serve to proxy that loopback port inside the tailnet. Never use Tailscale Funnel. Never port-forward or firewall-open port 11434.
- The host must stay powered on, awake, running Ollama, and connected to Tailscale.
- Each developer keeps a separate gitignored `.env` and a separate Gemini key. Never send an API key through Git or chat.
- If the host is unavailable, Gemini is attempted next. Without a configured Gemini key, fallback cannot succeed.
- CareerPilot never pulls models automatically.

Auth settings in `.env`:

- `ALLOWED_ORIGINS` — comma-separated exact `http://` or `https://` frontend origins. No `*`, path, query, or fragment. Credentialed CORS never uses a wildcard.
- `COOKIE_SECURE=false` for local http. `APP_ENV=production` refuses to start unless `COOKIE_SECURE=true`.
- `EXTENSION_ORIGIN` — blank, or one exact `chrome-extension://<extension-id>` origin. The session header is accepted only on the autofill route from that origin.

Database tables are created on API startup, or manually:

```bash
python -m backend.db.init_db
```

### Frontend

```bash
cd frontend
cp .env.example .env.local
npm install
```

`VITE_API_BASE_URL` defaults to `http://<this-page-hostname>:8000` for local
aliases (`localhost` and `127.0.0.1`). Opening the UI at either hostname talks
to the matching API host so the `SameSite=Lax` session cookie stays first-party.
A copied local alias is rewritten the same way. An explicit non-local URL is
left unchanged. Do not set `VITE_API_BASE_URL=http://localhost:8000` in
`.env.local` if you also open the app at `http://127.0.0.1:5173`.

### Browser extension

The extension is not published. Load it unpacked:

1. Start the backend (`uvicorn backend.main:app --reload`) and approve at least one Greenhouse or Lever application.
2. Open `chrome://extensions`, enable Developer mode, and **Load unpacked** on `browser-extension/`.
3. Open the extension side panel on a real posting (or Lever `/apply` page) and fill from approved materials.
4. Review flagged fields yourself. The extension never submits.

See `browser-extension/README.md` for selector and CSP details.

## Run

Terminal 1 — backend:

```bash
source .venv/bin/activate
uvicorn backend.main:app --reload
```

- API: http://localhost:8000
- Docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

Terminal 2 — frontend:

```bash
cd frontend
npm run dev
```

- UI: http://localhost:5173 or http://127.0.0.1:5173
  (the frontend rewrites a local API origin to whichever hostname you used)

## Tests

Backend (isolated SQLite, fake/blocked providers, no `data/careerpilot.db`):

```bash
python -m pytest -q
python scripts/test_fit_scoring_matrix.py
python scripts/test_candidate_profile_matrix.py --synthetic
python -m pytest tests/test_job_intelligence.py tests/test_job_intelligence_pipeline.py -q
python scripts/check_tracked_secrets.py
```

Frontend:

```bash
cd frontend
npm run test:run
npm run typecheck
npm run build
```

CI (`.github/workflows/ci.yml`) runs pytest, the MVP browser workflow, frontend unit tests, frontend typecheck and production build, the browser-extension build, `git diff --check`, and the tracked-secret audit on Python 3.11 and Node.js 20. Playwright Chromium is installed for Form Fill fixture tests.

Optional live LLM smoke test (not part of CI):

```bash
python -m backend.utils.prompt_harness --provider ollama --prompt "Reply with one sentence confirming CareerPilot can reach the LLM."
python scripts/smoke_ollama.py
```

`scripts/smoke_ollama.py` checks `/api/tags` and one tiny schema-constrained reply. It does not run in CI, does not pull models, does not write application data, and does not print the endpoint, prompts, or secrets.

Optional host live check against a temporary database (also not CI):

```bash
python scripts/live_ollama_gemini_check.py
```

## Ollama troubleshooting

- Host not serving: confirm Ollama is running and `http://127.0.0.1:11434/api/tags` works on the host only.
- Teammate cannot reach the host: install the official Tailscale client, join the same invited tailnet, and put the private Serve URL only in that device's gitignored `.env`.
- Same-machine Serve URL may return 403; that is a Tailscale identity check, not public exposure. The teammate should verify `/api/tags` from their own device.
- Gemini fallback used: the host was offline, timed out, or returned unusable structured output. Check that a Gemini key exists on that machine.
- Never expose Ollama on the public internet.

## Two-developer Git workflow

Do **not** commit directly to `main`. Work on feature branches and merge through pull requests.

Developer B ownership remains: Job Scout, Job Verification, Form Fill, browser-extension, ATS fixtures, and existing approval / assisted-apply behavior. Do not rewrite those implementations while completing Application Materials.

## Useful API routes

| Method | Path | Notes |
| --- | --- | --- |
| `POST` | `/api/auth/signup` | Create account and set session cookie |
| `POST` | `/api/auth/login` | Log in |
| `POST` | `/api/auth/logout` | Revoke session |
| `GET` | `/api/auth/me` | Current user |
| `GET` | `/api/profile` | Current candidate and latest preferences (read-only) |
| `POST` | `/api/parse-resume` | Grounded candidate profile |
| `POST` | `/api/preferences` | Reusable application answers |
| `POST` | `/api/scout-jobs` | Live job discovery |
| `POST` | `/api/jobs/ingest-url` | Manual posting URL |
| `POST` | `/api/jobs/verify` | Verification sweep |
| `GET`/`POST` | `/api/jobs/{job_id}/intelligence` | Stored / extract Job Intelligence |
| `GET` | `/api/jobs/{job_id}/score` | Stored fit score (read-only; 404 if missing) |
| `GET` | `/api/jobs/scores` | Stored scores for the Jobs page (read-only) |
| `POST` | `/api/jobs/{job_id}/score` | Fit & Gap (explicit) |
| `GET` | `/api/jobs/{job_id}/materials` | Stored grounded materials (read-only; 404 if missing) |
| `POST` | `/api/jobs/{job_id}/generate-materials` | Grounded materials (explicit) |
| `POST` | `/api/jobs/{job_id}/approve` | Approval Agent |
| `POST` | `/api/jobs/{job_id}/fill-application` | Assisted apply preview (never submits) |
| `GET` | `/api/extension/autofill` | Browser extension field values |
| `GET` | `/api/applications` | Tracker list (read-only) |
| `GET`/`PATCH` | `/api/applications/{job_id}/tracking` | Explicit tracker updates, including optional follow-up date |
| `GET` | `/api/dashboard/summary` | Real stored metrics |
| `GET` | `/api/resume-versions` | Owner-scoped immutable resume version summaries |
| `GET` | `/api/resume-versions/{version_id}` | Historical resume version detail (no hashes or raw snapshot) |
| `GET`/`POST` | `/api/jobs/{job_id}/resume-versions` | Per-job list / explicit save |
| `GET` | `/api/jobs/{job_id}/interview-prep` | Read-only stored prep |
| `POST` | `/api/jobs/{job_id}/prepare-interview` | Deterministic baseline (explicit) |
| `POST` | `/api/jobs/{job_id}/interview-prep/feedback` | Ephemeral mock-interview answer feedback (`LLM_PROVIDER_ORDER`) |
