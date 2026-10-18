# CareerPilot — technical portfolio summary

Reusable entry for a personal developer portfolio or résumé packet.

## Project title

**CareerPilot**

## One-sentence summary

Local/self-hostable job-search workspace (FastAPI, React/TypeScript, SQLite, unpacked Chromium extension) that turns a résumé into a grounded profile, ranks jobs with deterministic explainable Fit, and keeps application materials human-approved — never auto-submitted.

## Technical highlights

1. **Grounded evidence + deterministic Fit** — qualification and preference alignment are scored from stored résumé/posting text without an LLM; missing evidence stays a gap, not an invented yes.
2. **Stale-data protection** — candidate, preference, and requirements fingerprints invalidate Fit, Match Evidence, and reviewed materials when inputs change.
3. **Human approval boundary** — generated materials remain drafts until eligibility is confirmed; tracker `applied` is human-recorded; the app never submits ATS forms.
4. **Safe Greenhouse/Lever Fill** — Manifest V3 side panel uses ATS posting identity, truthful resume-attachment verification, tab/document navigation guards, and leaves EEO/demographics/terms manual.
5. **User isolation** — scores, packages, tracker rows, analytics events, saved searches, and resume-version files are owner-scoped; automated tests never mutate `data/careerpilot.db`.

## Tech stack

| Layer | Stack |
| --- | --- |
| Backend | Python, FastAPI, SQLAlchemy, SQLite |
| Frontend | React, TypeScript, Vite |
| Extension | Chromium Manifest V3 (side panel) |
| Providers (optional) | Ollama, Gemini, Anthropic, OpenAI — extract/intelligence/materials/interview feedback only |
| Tooling | Playwright, Vitest, pytest, FFmpeg (showcase capture) |

## Links

- **GitHub:** https://github.com/ManpreetS2/CareerPilot
- **Release:** https://github.com/ManpreetS2/CareerPilot/releases/tag/v1.0.0
- **Demo video:** [`docs/showcase/video/careerpilot-demo.mp4`](./video/careerpilot-demo.mp4) (also mirrored under release/artifacts when published)
- **Architecture:** [`architecture/careerpilot-architecture.svg`](./architecture/careerpilot-architecture.svg)
- **Screenshots:** [`screenshots/`](./screenshots/) (`01-overview.webp` … `08-extension.webp`)

Source is **source-visible**, not open source. There is no hosted demo and no Chrome Web Store listing. LICENSE requires prior written permission to run or deploy.

## Résumé bullets (pick three)

- Built an end-to-end local job-search workspace (FastAPI, React/Vite, SQLite) that gates discovery on a grounded candidate profile and keeps Fit scores, materials, tracker rows, and analytics private per account.
- Implemented deterministic Fit scoring with fingerprint-based invalidation so Match Evidence and application packages cannot silently reuse a stale résumé or posting after profile changes.
- Shipped a Manifest V3 Chrome side panel for Greenhouse/Lever assisted Fill with ATS-ID identity, truthful resume-attachment checks, navigation guards, and hard boundaries that never submit or fill EEO/consent fields.

## Provenance note

Tagged release **v1.0.0** is `b73a983ed3605d498aa90070c3b5f786a73bc525`. A8/A9/Phase 6 certified runtime is `7b6c3ee100ca4fe6399ac29441bece8df71783c7`. Showcase screenshots and the demo video are later-mainline synthetic captures; they do not move the tag or inherit that certification.
