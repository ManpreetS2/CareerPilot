# CareerPilot AI

AI-assisted job search and application copilot.

CareerPilot helps a candidate move from a resume to ranked, verified jobs and human-approved application materials.

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

These are logical modules inside **one application**, not separately deployed microservices or autonomous agents.

## Architecture

| Layer | Stack |
| --- | --- |
| Backend API | FastAPI + Uvicorn |
| Frontend | React + TypeScript + Vite + Tailwind CSS |
| Database | SQLite via SQLAlchemy (`data/careerpilot.db`) |
| Schemas | Shared Pydantic models |
| LLM | Thin `LLMClient` for Gemini, Anthropic, and OpenAI |

```
CareerPilot_Ai/
├── backend/          # FastAPI app, DB, schemas, services
├── frontend/         # React + Vite UI
├── tests/            # pytest (backend)
├── data/             # SQLite file (gitignored)
├── logs/             # runtime + prompt-harness logs (gitignored)
├── .env.example
├── requirements.txt
└── README.md
```

## Current status

**Done**

- FastAPI scaffold with mock agent routes
- SQLite tables + shared Pydantic schemas
- LLM provider wrapper + Gemini smoke path
- React product UI (Dashboard, Profile, Jobs, Job Detail, Applications)
- Light/dark theme, responsive shell, typed API client

**Day 2 human work (not finished by scaffolding)**

- Developer A: Candidate Profile Agent (real resume parse + grounding)
- Developer B: Job Scout (Adzuna/RemoteOK/manual URL + persistence)

**Still out of scope**

- Fit & Gap scoring (Day 3+)
- Job Intelligence (Day 3+)
- Application tailoring (Day 4+)
- Playwright assisted apply
- Auth / deployment

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
cp .env.example .env
```

Add `GEMINI_API_KEY` (and optional Anthropic/OpenAI keys) to `.env`. Never commit `.env`.

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

Backend:

```bash
pytest
```

Frontend:

```bash
cd frontend
npm run typecheck
npm run build
```

## LLM smoke test (optional)

```bash
python -m backend.utils.prompt_harness --provider gemini --prompt "Reply with one sentence confirming CareerPilot can reach the LLM."
```

## Two-developer Git workflow

Do **not** commit directly to `main`. Work on feature branches and merge through pull requests.

```
main
├── feature/candidate-profile-agent   # Developer A
└── feature/job-scout                 # Developer B
```

### Day 2 task split

**Developer A — Candidate Profile Agent**

Starting files:

- `backend/services/candidate_profile_agent.py`
- `backend/services/candidate_service.py`
- `backend/api/routes/candidate.py`
- `backend/db/models.py`
- `backend/schemas/schemas.py`

TODOs:

1. Resume text extraction with `pdfplumber`
2. OCR fallback only when extracted text is nearly empty
3. CandidateProfile Gemini prompt
4. Strict structured JSON output
5. CandidateProfile Pydantic validation
6. Evidence / grounding validation
7. Save profile to SQLite
8. Wire real `POST /api/parse-resume`
9. Test with at least 3 resumes

Critical invariant: **never invent** candidate experience, skills, projects, education, or certifications.

**Developer B — Job Scout**

Starting files:

- `backend/services/job_scout_service.py`
- `backend/services/job_service.py`
- `backend/api/routes/jobs.py`
- `backend/db/models.py`
- `frontend/src/pages/JobsPage.tsx`

TODOs:

1. Configure Adzuna (or another stable free source)
2. Add RemoteOK if useful
3. Normalize into `Job` records
4. Manual job URL ingestion
5. Deduplicate jobs
6. Save jobs to SQLite
7. Wire real `POST /api/scout-jobs`
8. Confirm jobs render in the React Jobs page

## Placeholder API routes

Several endpoints still return mock data until Day 2+ services are wired:

| Method | Path |
| --- | --- |
| `GET` | `/` |
| `GET` | `/health` |
| `POST` | `/api/parse-resume` |
| `POST` | `/api/preferences` |
| `GET` | `/api/jobs` |
| `POST` | `/api/scout-jobs` |
| `GET` | `/api/jobs/{job_id}` |
| `POST` | `/api/jobs/{job_id}/score` |
| `POST` | `/api/jobs/{job_id}/generate-materials` |
| `POST` | `/api/jobs/{job_id}/approve` |
| `POST` | `/api/jobs/{job_id}/prepare-interview` |
