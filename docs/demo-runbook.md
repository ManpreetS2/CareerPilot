# CareerPilot demo runbook

Local/self-hostable demo. Prefer an isolated SQLite URL. Never run destructive
QA against `data/careerpilot.db`.

Canonical product path: **Profile → Discover → Analyze → Prepare → Track**.

For a 2–4 minute spoken walkthrough, recruiter copy, and screenshot recapture, see [`docs/showcase/README.md`](./showcase/README.md). This runbook stays the operator boot.

## Start

1. Copy `.env.example` to `.env`. For a disposable demo, point `DATABASE_URL` at a temp/copy file (see `scripts/make_temp_qa_db.py`). Leave `COOKIE_SECURE=false` for local http.
2. Backend (match the UI hostname; prefer `127.0.0.1`):

   ```bash
   python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
   ```

3. Frontend:

   ```bash
   cd frontend
   npm run dev
   ```

4. Open `http://127.0.0.1:5173`. Do not mix `localhost` and `127.0.0.1`.

Provider-backed materials, Job Intelligence, resume parse, and interview
feedback need a configured model (`LLM_PROVIDER_ORDER`, typically Ollama
and/or `GEMINI_API_KEY`). Fit scoring stays deterministic. Without a reachable
provider, those generate/extract steps fail honestly.

## Canonical demo path

1. Sign up.
2. Complete Profile: identity, at least one grounded evidence category, and at least one target role. Incomplete profiles cannot Find Jobs.
3. Discover → Find Jobs. Existing listings stay visible while scout runs. Progress ends when the API returns.
4. Analyze a listing (Match / Evidence). Calculate Fit and extract intelligence are explicit; opening Job Detail does not score or generate.
5. Prepare materials only after reviewing eligibility. Approve with eligibility confirmation. Optional: save an immutable resume version (PDF/DOCX).
6. Track status. Follow-up dates can export as `.ics` or a Google Calendar URL. CareerPilot does not send email and does not OAuth a calendar account.

Supporting destinations: Interview Coach on Job Detail, Career Growth, Analytics, Resume library, Settings (delete account).

## Browser extension

1. `cd browser-extension && npm ci && npm run build`
2. Chrome → `chrome://extensions` → Developer mode → **Load unpacked** → `browser-extension/` (the folder with `manifest.json`).
3. Set `EXTENSION_ORIGIN=chrome-extension://<id>` in `.env` and restart the API.
4. Open a Greenhouse posting or Lever posting/`/apply` page for a job CareerPilot has ingested, with an **approved** package.
5. Use Fill this page. Review the form. **You** press Submit on the ATS. CareerPilot never submits.
6. Do not auto-fill EEO/demographic fields or terms/privacy consent. Custom/unknown fields stay manual.
7. Resume attach is attempted when a Resume/CV input exists. A matching filename on the page is not enough. If attach is blocked, upload the file yourself.

Assisted Fill supports **Greenhouse and Lever only**. Other sources can still appear as tracked jobs.

## Safety

- CareerPilot never submits applications.
- Tracker `applied` is human-recorded state, not a submission.
- Preview/demo databases are disposable. Do not migrate or overwrite `data/careerpilot.db` for a demo.
