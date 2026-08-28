# CareerPilot Assisted Apply (browser extension)

A side panel that stays open beside the job page: it shows whether the
current page is a job CareerPilot has seen, its fit score and evidence, and
your application-materials status — and fills your approved application
directly into the real Greenhouse or Lever form you're looking at. It never
clicks submit.

## Why this exists instead of something simpler

An earlier version ran the fill server-side in a throwaway headless
browser and returned a summary — accurate, but useless for actually
finishing the application, since a server-side browser session has no
connection to your own Chrome tab. A bookmarklet was the next idea, but
Greenhouse's own Content-Security-Policy header blocks a page from making
network requests to anything outside its allowlist (confirmed directly
against a real posting — `localhost` isn't on it, and this is enforced
regardless of what injects the request). A browser extension's background
context isn't bound by the visited page's CSP, which is the only way to
both reach the CareerPilot backend and touch the real page.

The panel itself started as a single popup button. A popup fully unmounts
every time it closes, so it couldn't show anything ambient (fit score,
materials status) without the user reopening it and re-triggering a fetch
every time — a persistent side panel that follows the active tab replaces
that with something that's actually useful to leave open while browsing.

## How it works

1. Click the extension's toolbar icon to open the side panel — it stays
   open beside the page as you browse and switch tabs.
2. The panel asks CareerPilot's backend (`localhost:8000`) whether the
   active tab's URL matches a job it's seen, and if so, its fit score and
   materials status. Switching tabs re-checks automatically.
3. On a real Greenhouse or Lever application page with an **approved**
   application, click **Fill this page** to inject the fill (`chrome.scripting.executeScript`),
   which sets each matched field's value directly — the same
   native-setter-plus-event-dispatch technique needed for React-controlled
   inputs to actually register the change, not just cosmetically show it.
4. Anything it can't confidently map (resume upload, custom questions, a
   missing candidate field) is listed in the panel instead of guessed.
5. Nothing is ever submitted. You review the filled form and send it
   yourself.

## Building it

```bash
cd browser-extension
npm install
npm run build
```

This compiles `sidepanel.html`/`background.ts` into `dist/`, which the
manifest points at (`side_panel.default_path`, `background.service_worker`).
Re-run `npm run build` after any source change — nothing auto-reloads the
loaded extension for you.

`npm test` runs the panel's unit tests (Vitest, jsdom). CI runs them under
`TZ=Asia/Kolkata` rather than the runner's UTC, because the backend sends
naive UTC timestamps and a UTC-only run would hide local-time parsing bugs.

## Loading it locally

This isn't published to the Chrome Web Store — load it as an unpacked
extension:

1. Build it first (see above).
2. Make sure the CareerPilot backend is running (`uvicorn backend.main:app --reload`).
3. Open `chrome://extensions` in Chrome.
4. Turn on **Developer mode** (top-right toggle).
5. Click **Load unpacked** and select this `browser-extension/` folder.
6. Click the extension's icon in the toolbar to open the side panel.
7. Navigate to a job posting. If CareerPilot has seen it, the panel shows
   its status; on a Greenhouse/Lever page with an approved application, use
   **Fill this page**. For Lever, either the posting page or its `/apply`
   page works — the panel resolves either back to the same job.

## Scope

- Job recognition/fit-score/materials status: any tracked job, any source.
- Assisted apply: Greenhouse and Lever only, matching the backend's
  `detect_ats_platform`, and only once there's an **approved** application
  for that exact posting.
- `host_permissions` is scoped to `http://localhost:8000/*` and
  `http://127.0.0.1:8000/*` only — the
  extension has no standing access to any job board. Page access for the
  fill is requested at the moment you click **Fill this page**, scoped to
  that one posting's origin, via `optional_host_permissions` (limited to
  `greenhouse.io` and `lever.co`). `activeTab` alone is not enough here:
  it covers only the tab that was active when you opened the panel, and a
  panel that follows you across tabs would otherwise fail to fill on every
  tab you moved to afterwards.
- The broader `tabs` permission gives the panel tab URLs only, never page
  content. It is what lets the panel follow you as you switch tabs.
- **The active tab's URL is sent to your CareerPilot backend** each time it
  changes, so the panel can ask whether it's a tracked job. Only `http`/
  `https` pages are ever sent — `chrome://` pages, the New Tab page,
  `file://` URLs and other extensions' pages are filtered out in the panel
  before any request is made. That backend is your own local instance.
