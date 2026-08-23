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

**Completed and merged**

- Candidate Profile Agent (grounded resume parse, no invented experience)
- Job Scout (Adzuna/RemoteOK/manual URL + persistence)
- Job Verification (still-open and suspicious-posting checks)
- Job Intelligence extraction (grounded structured requirements)
- Fit & Gap scoring (deterministic, explainable, no LLM)
- Approval Agent (human-in-the-loop review, eligibility confirmation)
- Greenhouse/Lever assisted form fill (server-side preview, never submits)
- Browser extension autofill for the live tab (never submits)
- Candidate reusable application answers / preferences

**Foundation in this repo**

- Application Tracker with explicit status updates and real dashboard metrics
- Deterministic Interview Preparation baseline from stored Job Intelligence, Fit & Gap, and candidate evidence
- Grounded Application Materials generation, loaded from storage on page load and created only when you click Generate materials

Opening Jobs, Job Detail, Applications, or Application Detail never scores a job, extracts requirements, or generates materials by itself.

**Still out of scope**

- Auth / accounts / multi-user access
- Coordinated Form Fill / browser-extension authentication
- Deployment / production hosting
- Automatic job application submission
- Live LLM interview-question generation (injectable boundary only)

## Privacy and safety

- Automated tests use isolated in-memory SQLite. They must never create or mutate `data/careerpilot.db`.
- Logs use IDs and counts, not resume text, prompt contents, or raw provider output.
- No candidate skill, employer, metric, or education claim may be invented without stored evidence.
- Assisted apply and the browser extension **never click submit**. The human reviews and submits.
- Page load for Jobs, Job Detail, Applications, Application Detail, Fit Score, and Interview Prep is read-only. Scoring and generation run only on an explicit user action.
- This MVP is single-user and intended for local development. There is no authentication and no deployment yet.

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
