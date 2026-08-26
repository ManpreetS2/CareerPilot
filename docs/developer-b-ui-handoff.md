# Developer B UI handoff — Jobs and Job Detail

This document is the target visual integration for Developer B. Developer A’s UI overhaul did **not** rewrite job discovery, verification, ATS/form-fill, or the Chrome extension.

Jobs now share the CareerPilot shell, tokens, compact-list + desktop preview layout, internships/full-time/both title filter, and previous/next job navigation. Discovery adapters, verification, and ATS/form-fill remain Developer B’s lane.

## Ownership

Developer B owns:

- job-source adapters and discovery (Greenhouse, Lever, Remotive, Adzuna, RemoteOK, manual URL)
- job verification implementation
- source badges and freshness
- ATS detection and form-fill backend behavior
- Chrome extension and unpacked-Chrome side-panel verification
- final Jobs list / Job Detail visual composition described below

Developer A owns:

- app shell, design tokens, shared primitives
- TanStack Query keys and AbortSignal request helper
- `/jobs/:jobId/prepare` (Prepare Application workspace)
- Interview Coach remains contextual under Job Detail (explicit Prepare Interview only)

## Current integration already on this branch

- Primary nav is Overview → Discover → Analyze → Prepare → Track, with Profile / Resume / Settings as supporting destinations.
- Job Detail primary CTA is **Prepare Application** → `/jobs/:jobId/prepare`.
- `/track` and `/applications` are the Application Tracker. `/applications/:jobId` still redirects to `/jobs/:jobId/prepare`.
- Opening Jobs or selecting a job must remain GET-only. No scoring, intelligence, materials, interview, or resume-version POST on select or page load.
- Shared badges (`SourceBadge`, `StatusBadge`) and tokenized `.btn-*` / `.card` classes remain available.

## JOBS DESKTOP — target

Adaptive split view.

**Left:** scrollable compact job-results list (rows, not a giant card wall).

**Right:** selected job preview/detail using the same Job Detail composition.

Selection must be represented in the URL (deep link `/jobs/:jobId`). Filters should survive navigation where appropriate.

## Job selection continuity (shared layout)

When Developer B implements the adaptive desktop Jobs split view, target a shared-layout interaction:

- selected compact job row on the left
- Job Detail header on the right

Company, role, and match metadata should feel spatially continuous (shared-layout / layoutId), not like a hard page cut.

Do **not** POST on select. Do **not** rewrite discovery/verification to achieve this motion.

Evidence for stored match factors should open in CareerPilot’s glass evidence drawer (claim → stored source path), without covering the whole canvas in heavy blur.


- Greenhouse
- Lever
- Remotive
- Adzuna
- RemoteOK
- manual URL ingest
- source badges
- freshness (`date_scraped` / scouted time)
- verification status

## TABLET / MOBILE — target

List → full-screen Job Detail.

No horizontal overflow. Long titles and company names must truncate or wrap inside the row, not the viewport.

## JOB DETAIL — target composition

This composition should work both inside the desktop split preview and as the full deep-linked Job Detail page.

**Header**

- company
- role
- location (missing location is allowed; do not invent)
- salary where real (omit when missing)
- source / freshness
- status
- match score when a stored score exists
- **Prepare Application** as the primary CTA

**Then progressive sections**

1. Overview
2. Match
3. Evidence

Evidence should open in a focused drawer where useful.

Interview Prep remains secondary/contextual. Opening Job Detail may GET stored interview prep. It must never POST `/prepare-interview` until the user clicks **Prepare interview**.

## Safety invariants (do not weaken)

- Page load is read-only.
- Assisted apply still requires approved materials.
- CareerPilot never auto-submits.
- Do not edit `browser-extension/**` from unrelated UI work.
- Do not delete backend tracker tables or routes because the web UI no longer promotes Application Tracker.

## Suggested query keys

Use the shared frontend keys in `frontend/src/lib/query-keys.ts`:

- `queryKeys.jobs`
- `queryKeys.job(jobId)`
- `queryKeys.jobIntelligence(jobId)`
- `queryKeys.score(jobId)`
- `queryKeys.interviewPrep(jobId)`

Pass `AbortSignal` into `api.getJob`, `api.getJobs`, `api.getJobIntelligence`, `api.getStoredScore`, and `api.getInterviewPrep` so a Job A response cannot overwrite Job B.
