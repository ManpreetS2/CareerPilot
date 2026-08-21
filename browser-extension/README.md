# CareerPilot Assisted Apply (browser extension)

Fills your approved CareerPilot application directly into the real
Greenhouse or Lever form you're looking at — the same kind of autofill
Jobright, Simplify, and similar tools do. It never clicks submit.

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

## How it works

1. You click the extension icon while viewing a real Greenhouse or Lever
   application page.
2. The popup asks CareerPilot's backend (`localhost:8000`) for the field
   values from your approved application, matched by the page's URL.
3. It injects a fill function into that same tab (`chrome.scripting.executeScript`),
   which sets each matched field's value directly — the same
   native-setter-plus-event-dispatch technique needed for React-controlled
   inputs to actually register the change, not just cosmetically show it.
4. Anything it can't confidently map (resume upload, custom questions, a
   missing candidate field) is listed in the popup instead of guessed.
5. Nothing is ever submitted. You review the filled form and send it
   yourself.

## Loading it locally

This isn't published to the Chrome Web Store — load it as an unpacked
extension:

1. Make sure the CareerPilot backend is running (`uvicorn backend.main:app --reload`)
   and you have at least one **approved** application for a Greenhouse or
   Lever job.
2. Open `chrome://extensions` in Chrome.
3. Turn on **Developer mode** (top-right toggle).
4. Click **Load unpacked** and select this `browser-extension/` folder.
5. Navigate to the real job posting (the same URL you approved in
   CareerPilot). For Lever, either the posting page or its `/apply` page
   works — the extension resolves either back to the same job.
6. Click the extension's icon in the toolbar, then **Fill this page**.

## Scope

- Greenhouse and Lever only, matching the backend's `detect_ats_platform`.
- Matches the current tab's URL against your CareerPilot jobs — if there's
  no approved application for that exact posting, it'll say so rather than
  fill anything.
- `host_permissions` is scoped to `http://localhost:8000/*` only; it
  doesn't request access to job board domains up front — page access is
  granted per-click via `activeTab`, not a standing permission.
