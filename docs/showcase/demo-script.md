# Showcase demo script

Use this for a live walkthrough or a short screen recording. Keep [`docs/demo-runbook.md`](../demo-runbook.md) as the operator start (how to boot the app, authorized use only). This script is what to click and say.

**Data:** isolated showcase SQLite from `scripts/seed_showcase_demo.py`, or a throwaway signup. Never `data/careerpilot.db`. Never a real resume on a recorded demo unless the candidate owns that machine and the recording will not be committed.

**Hostname:** `http://127.0.0.1:5173` talking to `http://127.0.0.1:8000`. Do not mix `localhost` and `127.0.0.1`.

**Provenance:** Fit scores on the seeded demo are calculated by the production Fit V2 engine from the parsed synthetic résumé and two fictional postings. They are **not** hardcoded. Prepare may show **illustrative seeded materials** if live generation was not available; do not call those AI-generated. Production generation is unchanged.

## What not to expose

- Real email, resume, phone, API keys, Tailscale URLs, `.env`, extension ID
- Other users’ data
- Submit being clicked
- EEO/demographic answers
- Fake placement, interview, or offer claims
- A hosted demo, Chrome Web Store listing, or live extension recording that was not actually captured

## 45–60 second recording sequence

Record this path only. Do **not** include extension footage unless you actually recorded the unpacked extension on a real Greenhouse/Lever page in this take. The committed `08-assisted-fill-boundary-mock.png` is an illustrative mock, not the extension runtime.

| Time | Click | Say |
| --- | --- | --- |
| 0:00–0:08 | Profile | Jordan Avery is a synthetic intern. The résumé went through parse and grounding: Python, SQL, FastAPI, pytest, Git — no Docker or cloud. Discover stays gated until that profile exists. |
| 0:08–0:16 | Discover | Two fictional internships, both scored by Fit V2. Harborline is about 96%; Cedar is about 62%. These percentages measure qualification and preference alignment against stored evidence, not a chance of getting hired or passing an ATS. |
| 0:16–0:32 | Harborline intern → Evidence | Strength: Python is cited from Campus Planner on the stored résumé. Gap: Docker is preferred here and is not on the résumé — missing stays missing. Work authorization was not listed, so it stays a watchout, not a yes. |
| 0:32–0:48 | Prepare | Review the letter, confirm eligibility, approve. Approval does not submit. If this demo used seeded materials, say so; do not call them live-generated. |
| 0:48–0:60 | Track | Ready to apply means materials are approved. Applied is a status you record after **you** submitted. CareerPilot never auto-submits. |

Stop. Do not open Settings. Do not click Submit.

### Fallback if a provider is down

Fit still works. Skip Generate Materials / Job Intelligence / interview feedback. Say: “Those steps need a configured model. Fit does not.” The committed showcase capture used a live résumé parse and illustrative seeded materials after materials generation returned 503. A fresh seed run defaults to faithful synthetic extraction and illustrative seeded materials; live provider calls require `CAREERPILOT_SHOWCASE_LIVE=1`. Do not imply a new default run made live calls. Do not call that Prepare text live-generated.

### Fallback if you cannot show a live ATS

Do not splice in the HTML mock as if it were the extension. If you mention Fill at all, say out loud that `08-assisted-fill-boundary-mock.png` is an **illustrative compatibility mock**, not the shipped Chrome extension, and that live Greenhouse/Lever Fill was certified separately on Chrome 152 (A8) at runtime `7b6c3ee`.

## Optional 2–4 minute spoken walkthrough

Use this only when you have more than a minute. Same safety rules.

### 1. Landing (10s)

**Click:** open `/`.

**Say:** CareerPilot is local/self-hostable. It ranks jobs from a real profile and keeps applications human-approved. It never auto-submits. Records live in the deployment you run; configured AI providers can receive resume or job text.

### 2. Sign in (10s)

**Click:** Sign In. Use the synthetic demo account from the seeder, or a throwaway signup.

**Say:** Everything after this is that user’s private records. Jobs in the catalog can be shared; scores and tracker rows are not.

### 3. Profile readiness (15s)

**Click:** Profile.

**Say:** Discover stays gated until identity, at least one grounded evidence source, and a target role exist. This is not a marketing checklist — the API refuses scout without it.

### 4. Discover (20s)

**Click:** Discover.

**Say:** Find Jobs is explicit. Opening the page does not spend a model call. Harborline is the stronger Fit; Cedar is partial because required Docker and AWS are not on the résumé. The percentage is Fit V2 qualification/preference alignment, not a hire or ATS probability.

If you are on a cold database, click Find Jobs and wait for the API to return. Do not leave it running as theater.

### 5. Open one job (5s)

**Click:** Software Engineer Intern (or the strongest stored match).

### 6. Analyze Match / Evidence (25s)

**Click:** Evidence (and Match if you need requirements).

**Say:** This is the interesting part. Python is cited from Campus Planner on the stored résumé. Docker is preferred and still missing — not an invented yes. Cedar would miss required Docker and AWS. Work authorization was not listed, so eligibility is not treated as proven. If the resume changes, this row goes stale instead of lying.

### 7. Prepare grounded materials (25s)

**Click:** Prepare Application.

**Say:** Bullets and the letter have to point at stored evidence. Seeded demos show an already-stored illustrative package, not live generation. If a provider is missing on a real account, generation fails honestly.

### 8. Approval (15s)

**Show:** eligibility checkbox and Approved state.

**Say:** Approval is a human gate. It does not submit the application and it does not mark Applied for you.

### 9. Resume version (10s)

**Show:** Version 1 PDF/DOCX.

**Say:** Immutable snapshot of the tailored bullets. Download is not a send.

### 10. Assisted Fill (only if recorded)

**Show:** unpacked extension on a Greenhouse or Lever page you already ingested, **if this recording actually captured it**. Otherwise skip. Do not present `docs/showcase/fixtures/generic-ats-form.html` as the extension.

**Say:** Greenhouse and Lever only. Mapped fields can fill. EEO and terms stay empty for you.

### 11. Stop before Submit (10s)

**Do not click Submit.**

**Say:** The human reviews the form and presses Submit. CareerPilot does not.

### 12. Track (15s)

**Click:** Track. Prefer List if Kanban columns run off-screen.

**Say:** Ready to apply means materials are approved. Applied is a status you record after **you** submitted. CareerPilot did not apply.

### 13. Close on Analytics or Growth (15s)

**Click:** Analytics (preferred close) or Career Growth.

**Say, Analytics:** Funnel is this account’s events. Applied, interview, and offer stay zero until you record them. No fake success metrics.

**Say, Growth:** If there is no stored Match Evidence to aggregate, the page says so. It will not invent a skills-gap story.

Stop. Do not open Settings unless asked about deletion.
