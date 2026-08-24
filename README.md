# CareerPilot AI

AI-assisted job search and application copilot.

CareerPilot helps a candidate move from a resume to ranked, verified jobs and human-approved application materials. These are logical modules inside **one application**, not separately deployed microservices or autonomous agents.

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
→ Assisted Application
→ Application Tracker
→ Interview Preparation
```

## Architecture

| Layer | Stack |
| --- | --- |
| Backend API | FastAPI + Uvicorn |
| Frontend | React + TypeScript + Vite + Tailwind CSS |
| Database | SQLite via SQLAlchemy (`data/careerpilot.db`, gitignored) |
| Schemas | Shared Pydantic models |
| LLM | Thin `LLMClient` for Gemini, Anthropic, and OpenAI |
| Browser extension | Unpacked Chrome extension for Greenhouse/Lever autofill |

```
CareerPilot_Ai/
├── backend/              # FastAPI app, DB, schemas, services
├── frontend/             # React + Vite UI
├── browser-extension/    # Local Chrome extension (never submits)
├── tests/                # pytest (isolated in-memory SQLite)
├── scripts/              # Privacy-safe matrix runners and audits
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
- Grounded candidate profile, job scout/verification/intelligence, fit scoring, materials, approval, assisted apply, tracker, and interview prep
- Application materials are generated from stored evidence, not a placeholder

Opening Jobs, Job Detail, Applications, or Application Detail never scores a job, extracts requirements, or generates materials by itself. Calculate Fit and Generate Materials stay explicit. Approval still requires the grounded/current-owner gate and eligibility confirmation. Assisted Apply and the extension never submit forms.

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
- Mock-interview feedback
- Reminders
- Automatic job application submission


## Privacy and safety

- Automated tests use isolated in-memory SQLite. They must never create or mutate `data/careerpilot.db`.
- Logs use IDs, counts, and exception types, not passwords, tokens, resumes, prompts, generated materials, or raw exception text that may contain those values.
- Validation errors never echo submitted `input` values.
- No candidate skill, employer, metric, or education claim may be invented without stored evidence.
- Assisted apply and the browser extension **never click submit**. The human reviews and submits.
- Page load for Jobs, Job Detail, Applications, Application Detail, Fit Score, and Interview Prep is read-only. Scoring and generation run only on an explicit user action.
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

Add `GEMINI_API_KEY` (and optional Anthropic/OpenAI keys) to `.env` for live resume parse / Job Intelligence extraction. Never commit `.env`.

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

`VITE_API_BASE_URL` defaults to `http://localhost:8000`.

### Browser extension

The extension is not published. Load it unpacked:

1. Start the backend (`uvicorn backend.main:app --reload`) and approve at least one Greenhouse or Lever application.
2. Open `chrome://extensions`, enable Developer mode, and **Load unpacked** on `browser-extension/`.
3. Open the real posting (or Lever `/apply` page) and click **Fill this page**.
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

- UI: http://localhost:5173

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
npm run typecheck
npm run build
```

CI (`.github/workflows/ci.yml`) runs pytest, frontend typecheck and production build, `git diff --check`, and the tracked-secret audit on Python 3.11 and Node.js 20. Playwright Chromium is installed for Form Fill fixture tests.

Optional live LLM smoke test (not part of CI):

```bash
python -m backend.utils.prompt_harness --provider gemini --prompt "Reply with one sentence confirming CareerPilot can reach the LLM."
```

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
| `GET`/`PATCH` | `/api/applications/{job_id}/tracking` | Explicit tracker updates |
| `GET` | `/api/dashboard/summary` | Real stored metrics |
| `GET` | `/api/jobs/{job_id}/interview-prep` | Read-only stored prep |
| `POST` | `/api/jobs/{job_id}/prepare-interview` | Deterministic baseline (explicit) |
