# Extension side-panel v2 audit

Stacked on PR #30 (`feat/jobs-workspace-v2`). This branch must not rewrite Fit V2, materials generation, or the injected `fillFormInPage` fill engine except for the EEO/no-submit safety rules.

## What already works

| Piece | Behavior |
| --- | --- |
| Manifest V3 | Native `chrome.sidePanel`, `sidePanel` permission, toolbar click opens the panel. No injected website sidebar. |
| Background | `setPanelBehavior({ openPanelOnActionClick: true })`. `TAB_CHANGED` on activate/URL change. Needs `tabs` because a service worker has no `activeTab` gesture. |
| Auth | Session cookie read via `chrome.cookies` and sent as `X-CareerPilot-Session`. Only `/api/extension/*` accepts that header. Cookie-only web routes stay cookie-only. |
| CORS | Exact `EXTENSION_ORIGIN` (`chrome-extension://` + 32-char id). Empty disables extension CORS. Wildcards are rejected at startup. |
| Panel data | `GET /api/extension/panel-data?url=` is read-only. Matches Greenhouse/Lever URL shapes (embed, boards vs job-boards, `/apply`, tracking params). `tracked=false` is 200, not 404. |
| Autofill | `GET /api/extension/autofill` requires an approved package. Injected `fillFormInPage` never calls `.submit()`. Optional origin permission is requested from the fill click. |
| ATS | Greenhouse and Lever only. Other HTTP(S) pages can still be *tracked* jobs (Remotive, etc.) but assisted apply is hidden. |
| Stale responses | `requestToken` drops a slower panel-data response after a tab switch. Fill refuses if the active tab URL drifted. |
| Tests | `sidepanel.test.ts`, `render.test.ts`, `panel-states.test.ts`. Backend coverage in `tests/test_form_fill_service.py`. |

## Gaps this branch is allowed to close

- Hard-coded `http://localhost:8000` / `5173` (no 127.0.0.1 cookie lookup, no build-time web/API URLs).
- Untracked Greenhouse/Lever pages only say “add it from Jobs” — no ingest-from-panel using the existing safe ingest + persist/dedupe path.
- Panel does not show Saved, eligibility copy, must-have summary, Verify Match, or field-level Ready / Needs review / Manual.
- EEO fields can still be auto-selected from loose label matching when preference values exist.
- Visual system is a light/dark card fork, not the graphite / indigo-violet glass language of the web Jobs workspace.
- Host permissions list only `localhost:8000`, not `127.0.0.1:8000`.

## Do not rewrite

- `fillFormInPage` selector/label/react-select logic (except skip EEO auto-fill).
- Approval/materials backend.
- File upload / DataTransfer / resume attachment.
- Auto-submit. Never.

## Permissions (keep narrow)

Standing: `activeTab`, `scripting`, `cookies`, `sidePanel`, `tabs`, loopback API hosts.
Optional: `https://*.greenhouse.io/*`, `https://*.lever.co/*` requested per origin at fill time.
