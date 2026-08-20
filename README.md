# CareerPilot AI

AI-assisted job search and application copilot.

CareerPilot helps a candidate move from a resume to ranked, verified jobs and human-approved application materials. This repository is a **9-day Agile MVP**. **Day 1 is scaffolding only.**

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
| Frontend | Streamlit |
| Database | SQLite via SQLAlchemy (`data/careerpilot.db`) |
| Schemas | Shared Pydantic models |
| LLM | Thin `LLMClient` for Gemini, Anthropic, and OpenAI |

```
CareerPilot_Ai/
├── backend/          # FastAPI app, DB, schemas, services
├── frontend/         # Streamlit UI + API client
├── tests/            # pytest
├── data/             # SQLite file (gitignored)
├── logs/             # runtime + prompt-harness logs (gitignored)
├── .env.example
├── requirements.txt
└── README.md
```

## Day 1 status

**In scope**

- Git-ready layout
- FastAPI with mock agent routes
- Streamlit pages (Upload, Jobs, Application)
- SQLite tables
- Shared Pydantic schemas
- LLM provider wrapper + prompt harness
- Basic pytest coverage

**Out of scope (do not start on Day 1)**

- Real resume parsing / OCR
- Job scraping
- Fit scoring
- Application generation
- Playwright assisted apply
- Auth, Docker, deployment, multi-agent frameworks

`pdfplumber`, `pytesseract`, and `playwright` are installed as dependencies only.

## Setup

Requires **Python 3.11+**. From the repository root:

```bash
python3.11 -m venv .venv
```

If `python3.11` is not on your PATH, use any 3.11+ interpreter (`python3.12`, `python3.13`, or `python` if it is new enough):

```bash
python3 -m venv .venv
```

macOS / Linux:

```bash
source .venv/bin/activate
```

Windows:

```bash
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a local env file (never commit `.env`):

```bash
cp .env.example .env
```

Add at least one LLM key if you want to run a live model call:

- `GEMINI_API_KEY` (recommended for the Day 1 smoke test)
- or `ANTHROPIC_API_KEY`
- or `OPENAI_API_KEY`

The API and Streamlit UI **run without keys**. Keys are required only for `LLMClient` / the prompt harness.

## Database initialization

Tables are created automatically when the API starts. You can also initialize them manually:

```bash
python -m backend.db.init_db
```

Database file: `data/careerpilot.db`

## Run the backend

```bash
uvicorn backend.main:app --reload
```

- API: http://localhost:8000
- Docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

## Run the frontend

In a second terminal (venv activated):

```bash
streamlit run frontend/app.py
```

UI: http://localhost:8501

The frontend reads `BACKEND_URL` from `.env` (default `http://localhost:8000`).

## Tests

```bash
pytest
```

## LLM smoke test (optional)

One successful live call, with latency logged under `logs/`:

```bash
python -m backend.utils.prompt_harness --provider gemini --prompt "Reply with one sentence confirming CareerPilot can reach the LLM."
```

Equivalent:

```bash
python -m backend.services.llm_client
```

No API keys are written to logs.

## Two-developer Git workflow

Do **not** commit directly to `main`. Work on feature branches and merge through pull requests.

```
main
├── dev-a/backend-ai
└── dev-b/frontend-infra
```

Smaller branches are better when a slice of work is independent, for example:

- `feature/day1-backend`
- `feature/day1-frontend`
- `feature/llm-client`

Suggested split for Day 2+:

| Developer A (`dev-a/backend-ai`) | Developer B (`dev-b/frontend-infra`) |
| --- | --- |
| Schemas, DB, LLM, agent services | Streamlit pages, API client, local DX |
| Scoring / materials endpoints | UI for jobs, approval, tracker |

Pull from `main` often. Keep PRs small.

## Placeholder API routes

All of these return **mock data** on Day 1:

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
