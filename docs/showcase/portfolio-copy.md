# Portfolio, LinkedIn, and interview copy

Facts below are tied to the public v1.0.0 release. Do not add user counts, placement rates, or “used by recruiters.”

**Release:** https://github.com/ManpreetS2/CareerPilot/releases/tag/v1.0.0
**Tagged commit:** `b73a983ed3605d498aa90070c3b5f786a73bc525`
**Certified runtime (A8/A9/Phase 6):** `7b6c3ee100ca4fe6399ac29441bece8df71783c7`

## A. Portfolio description

CareerPilot is a local/self-hostable job-search workspace: FastAPI, React, SQLite, and an unpacked Chrome extension. It turns a resume into a grounded candidate profile, discovers jobs from several public sources plus manual URLs, and explains Fit with stored evidence instead of unsupported claims. Application materials stay drafts until the human confirms eligibility. A Chrome side panel can assist Greenhouse and Lever forms; it never submits, never fills EEO/demographic fields, and never ticks terms. Private records are user-scoped. Fit scoring is deterministic; language-model providers are used only for extraction, job intelligence, materials, and interview feedback, with honest failure when none are reachable.

## B. Resume bullets (pick 2–4)

- Built a local job-search workspace (FastAPI, React/Vite, SQLite) that gates discovery on a grounded profile and keeps scores, materials, tracker rows, and analytics private per account.
- Implemented deterministic Fit plus fingerprint-based invalidation so Match Evidence and materials cannot silently reuse a stale resume or posting.
- Designed a human approval gate: generated bullets stay drafts until eligibility is confirmed; tracker `applied` is recorded by the user, never by an auto-submit.
- Shipped an unpacked Chrome extension for Greenhouse/Lever Fill with ATS-ID identity, truthful resume-attachment verification, and regression guards that never submit or fill EEO/consent fields.
- Certified live Fill on Chrome 152 (Greenhouse + Lever) and isolation/deletion behavior on isolated SQLite, then tagged v1.0.0 with CI and full-history secret scanning.

## C. LinkedIn project-launch post

I tagged CareerPilot v1.0.0 — a local job-search workspace I built end to end.

It is not an auto-apply bot. It reads a real resume, ranks jobs with explainable Fit, drafts application text from stored evidence, and stops before Submit. Greenhouse and Lever can be assisted from a Chrome side panel; demographic questions and terms stay manual.

The hard parts were the unglamorous ones: user isolation, stale-data invalidation, truthful resume attachment, and refusing to invent skills or interview results.

Source and release notes: https://github.com/ManpreetS2/CareerPilot/releases/tag/v1.0.0

Local/self-hostable. No hosted demo, no Chrome Web Store listing, no claim that it applies for you.

## D. Interview talking points

1. **Grounding vs generation.** The interesting problem is not “LLM writes a cover letter.” It is citing stored resume and posting text, marking gaps as unknown, and blocking silent reuse after the profile changes.
2. **Deterministic Fit.** Scoring does not require a provider. That is why Find Jobs can persist scores without spending model calls, and why CI can test Fit without live keys.
3. **Human boundary.** Approval, EEO, terms, and Submit are human. Tracker `applied` is not proof that CareerPilot submitted anything.
4. **Identity.** Greenhouse/Lever matching uses ATS posting identity, not “similar title at similar company.”
5. **Privacy.** Private rows are owner-scoped, including analytics and saved searches. Deletion revokes sessions. Tests never touch `data/careerpilot.db`.
6. **Release engineering.** Runtime was certified on `7b6c3ee…` (A8/A9/Phase 6). The annotated tag is `b73a983…`. Those SHAs are different on purpose: last-mile docs after certification.

## E. Hardest engineering problems

- Grounded materials and Match Evidence that fail closed when evidence is missing, instead of completing the sentence.
- Fingerprint invalidation across Fit, evidence, and reviewed packages.
- User isolation for every private table, including analytics events and saved-search unseen counts.
- Account deletion vs a shared job catalog.
- Greenhouse/Lever URL/ATS identity without fuzzy title matching, plus SSRF controls on outbound URLs.
- Extension Fill that must not submit, must not fill EEO/consent, and must verify attachment from the live Resume/CV control after this attempt.
- Provider fallback that is ordered and honest, while Fit stays deterministic.
- Live ATS certification (A8) that unit tests cannot replace after fill/attachment changes.
- Adversarial Phase 6 QA and release provenance that does not relabel later docs commits as the certified runtime.

## Numbers you may use

v1.0.0 **release-gate** automated counts (not a summed “all tests in the repo”):

- Frontend: 226 tests
- Extension: 109 tests
- Mapped paths: 124 valid / 0 missing

Do not publish a combined pytest+frontend+extension total unless you re-count every suite on the SHA you are citing and say exactly what was counted.

## Never say

- Helped X users get hired / increased response rate / used by recruiters
- Production-ready SaaS / live hosted demo / Chrome Web Store
- CareerPilot automatically applies
- Fill works on every ATS
- Email alerts or Google Calendar OAuth
