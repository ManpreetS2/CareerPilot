# Technical walkthrough (2–3 minutes)

CareerPilot is one authenticated local app: a React/TypeScript/Vite UI talking to a FastAPI API over an HttpOnly session cookie, with SQLAlchemy on SQLite.

## Data split

The job catalog (`JobRecord`) is shared. Almost everything else is user-scoped: candidate, preferences, scores, materials, tracker, interview prep, form-fill attempts, analytics events, saved searches, resume-version files. Opening another account does not flash the first user’s private rows. Account deletion revokes sessions and owner-scoped data; it does not delete the shared catalog.

## Scoring and staleness

Fit is **deterministic**. Fingerprints on the candidate, preferences, and posting invalidate stored Fit, Match Evidence, and materials when those inputs change. Ordinary page loads are read-only. Find Jobs may persist a deterministic score after an explicit click; it does not spend a provider call to do that.

## Providers

A thin `LLMClient` can try Ollama, then Gemini, Anthropic, and OpenAI in `LLM_PROVIDER_ORDER`. That path is for candidate extraction where applicable, job intelligence, application materials, and ephemeral interview feedback. If no provider is reachable, those steps fail honestly. Fit still works.

## Materials and approval

Generated text is grounded in stored evidence, or it is marked as an explicit `grounding_override`. Approval requires the current-owner package **and** a human eligibility checkbox. Approval does not mark the tracker `applied`. Resume versions are immutable snapshots of tailored bullets; downloading PDF/DOCX is not a submission.

## Extension

The unpacked Chrome side panel talks to the local API. Greenhouse and Lever identity uses ATS posting IDs, not fuzzy title/company matching. Fill assists mapped fields only. EEO/demographic and terms/privacy stay manual. Resume attachment is verified from the live Resume/CV input or widget after **this** attempt; a matching filename, a Cover Letter field, or an unrelated same-named file is not proof. If the page blocks programmatic attach, the panel says to upload the file yourself.

CareerPilot never calls submit. The human reviews the ATS form and presses Submit.

## What v1 actually certified

- **A8:** Chrome 152, live Greenhouse and Lever Fill. No Submit. EEO/terms manual. Attachment verified from the live Resume/CV control.
- **A9:** session isolation, IDOR fail-closed, account deletion, generic login errors. Isolated SQLite only.
- **Phase 6:** adversarial QA on certified runtime SHA `7b6c3ee100ca4fe6399ac29441bece8df71783c7`.
- **v1.0.0:** annotated tag on `b73a983ed3605d498aa90070c3b5f786a73bc525` — https://github.com/ManpreetS2/CareerPilot/releases/tag/v1.0.0

Release-gate automated counts at tag time: frontend **226** tests, extension **109** tests, mapped paths **124** valid / 0 missing. That is not a grand total across pytest + npm.

## Do not claim

Infinite scale, production SaaS hosting, autonomous submission, or Fill for every ATS.
