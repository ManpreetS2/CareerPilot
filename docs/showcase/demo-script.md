# Showcase demo script (2–4 minutes)

Use this for a live walkthrough. Keep [`docs/demo-runbook.md`](../demo-runbook.md) as the operator start (how to boot the app). This script is what to click and say.

**Length:** 2–4 minutes. Do not detour into Settings.

**Data:** isolated showcase SQLite from `scripts/seed_showcase_demo.py`, or a throwaway signup. Never `data/careerpilot.db`. Never a real resume on a recorded demo unless the candidate owns that machine and the recording will not be committed.

**Hostname:** `http://127.0.0.1:5173` talking to `http://127.0.0.1:8000`. Do not mix `localhost` and `127.0.0.1`.

## What not to expose

- Real email, resume, phone, API keys, Tailscale URLs, `.env`, extension ID
- Other users’ data
- Submit being clicked
- EEO/demographic answers
- Fake placement, interview, or offer claims

## Fallback if a provider is down

Fit still works. Skip Generate Materials / Job Intelligence / interview feedback. Say: “Those steps need a configured model. Fit does not.” The seeded demo already has stored grounded materials, so you can still show Prepare → approved package without calling a provider.

## Fallback if ATS attachment is blocked

Say the side panel will tell you to attach the file yourself. A matching filename is not proof. Do not pretend Cover Letter counts as Resume/CV.

## Path

### 1. Landing (10s)

**Click:** open `/`.

**Say:** CareerPilot is local. It ranks jobs from a real profile and keeps applications human-approved. It never auto-submits.

### 2. Sign in (10s)

**Click:** Sign In. Use the synthetic demo account from the seeder, or a throwaway signup.

**Say:** Everything after this is that user’s private records. Jobs in the catalog can be shared; scores and tracker rows are not.

### 3. Profile readiness (15s)

**Click:** Profile.

**Say:** Discover stays gated until identity, at least one grounded evidence source, and a target role exist. This is not a marketing checklist — the API refuses scout without it.

### 4. Discover (20s)

**Click:** Discover.

**Say:** Find Jobs is explicit. Opening the page does not spend a model call. Ranked cards are Potential or Verified Fit, not “you will get this job.”

If you are on a cold database, click Find Jobs and wait for the API to return. Do not leave it running as theater.

### 5. Open one job (5s)

**Click:** Software Engineer Intern (or the strongest stored match).

### 6. Analyze Match / Evidence (25s)

**Click:** Evidence (and Match if you need requirements).

**Say:** This is the interesting part. Python and SQL are cited from the profile. Docker is “not enough evidence,” not a invented yes. If the resume changes, this row goes stale instead of lying.

### 7. Prepare grounded materials (25s)

**Click:** Prepare Application.

**Say:** Bullets and the letter have to point at stored evidence. If a provider is missing, generation fails honestly. Seeded demos can show an already-stored package.

### 8. Approval (15s)

**Show:** eligibility checkbox and Approved state.

**Say:** Approval is a human gate. It does not submit the application and it does not mark Applied for you.

### 9. Resume version (10s)

**Show:** Version 1 PDF/DOCX.

**Say:** Immutable snapshot of the tailored bullets. Download is not a send.

### 10. Assisted Fill (20s)

**Show:** unpacked extension on a Greenhouse or Lever page you already ingested. If you cannot use a live ATS on this recording, you may show `docs/showcase/fixtures/generic-ats-form.html` / `08-assisted-fill-boundary-mock.png` and say out loud that it is an **illustrative mock**, not the extension runtime. Live Fill was certified on Chrome 152 (A8).

**Say:** Greenhouse and Lever only. Mapped fields can fill. EEO and terms stay empty for you.

### 11. Stop before Submit (10s)

**Do not click Submit.**

**Say:** The human reviews the form and presses Submit. CareerPilot does not.

If attachment was blocked, point at the panel’s manual-upload message and stop.

### 12. Track (15s)

**Click:** Track. Prefer List if Kanban columns run off-screen.

**Say:** Ready to apply means materials are approved. Applied is a status you record after **you** submitted. CareerPilot did not apply.

### 13. Close on Analytics or Growth (15s)

**Click:** Analytics (preferred close) or Career Growth.

**Say, Analytics:** Funnel is this account’s events. Applied, interview, and offer stay zero until you record them. No fake success metrics.

**Say, Growth:** If there is no stored Match Evidence to aggregate, the page says so. It will not invent a skills-gap story.

Stop. Do not open Settings unless asked about deletion.
