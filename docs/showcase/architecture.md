# Architecture

CareerPilot is **one local/self-hostable application**. The boxes below are process layers, not separately deployed services and not a hosted SaaS.

```mermaid
flowchart TB
  browser["Browser"]
  ui["React / TypeScript / Vite frontend"]
  api["FastAPI backend"]
  db["SQLite via SQLAlchemy"]

  browser --> ui
  ui -->|"HTTP + session cookie"| api
  api --> db

  subgraph catalog["Shared job catalog"]
    jobs["JobRecord postings"]
  end

  subgraph private["User-scoped private records"]
    profile["Candidate, preferences, scores"]
    materials["Materials, approval, resume versions"]
    tracker["Tracker, analytics events, saved searches"]
  end

  db --> catalog
  db --> private

  subgraph sources["Job sources — discovery"]
    gh["Greenhouse"]
    lever["Lever"]
    remotive["Remotive"]
    adzuna["Adzuna"]
    remoteok["RemoteOK"]
    jobicy["Jobicy"]
    himalayas["Himalayas"]
    manual["Approved manual URL ingestion"]
  end

  sources --> api

  subgraph llm["AI provider abstraction — not Fit"]
    ollama["Ollama"]
    gemini["Gemini"]
    anthropic["Anthropic"]
    openai["OpenAI"]
  end

  api -.->|"candidate extract, job intelligence, materials, interview feedback"| llm

  ext["Chrome side panel"]
  ats["Greenhouse / Lever form assistance"]
  human["Human reviews and presses Submit"]

  ext -->|"local FastAPI + session header"| api
  api --> ext
  ext --> ats
  ats --> human
```

## Deterministic vs provider-backed

| Kind | What |
| --- | --- |
| **Deterministic** | Fit scoring. Find Jobs may persist those scores after an explicit click. No LLM required. |
| **Provider-backed** | Candidate extraction where applicable, job intelligence, application materials, mock-interview answer feedback. Tries `LLM_PROVIDER_ORDER` (Ollama, Gemini, Anthropic, OpenAI). Failures stay honest. |

## Isolation

- **Shared:** job catalog (`JobRecord`) and stored job intelligence for a posting.
- **Private:** candidate profile, preferences, scores, materials, approval, tracker, interview prep, form-fill attempts, analytics events, saved searches, resume-version files.

Account deletion removes owner-scoped private rows and sessions. It does not delete the shared catalog.

## What this diagram does not claim

- Microservices, Kubernetes, or production cloud hosting
- Auto-submit, email alerts, or Google Calendar OAuth
- Assisted Fill for ATS vendors other than Greenhouse and Lever
- Infinite scale
