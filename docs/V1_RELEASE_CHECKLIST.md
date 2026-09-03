# CareerPilot v1 release checklist

Automation (pytest, frontend/extension tests, CI, Gitleaks) cannot prove these. Do them on a real machine before tagging v1.

## Canonical web workflow

- Fresh signup → onboarding/profile (minimum profile) → Overview → Discover → Analyze → Prepare → Track
- Incomplete profile cannot scout; completing the minimum profile unlocks Discover without a full reload
- Logout / login as a second user never flashes the first user's profile, scores, or tracker

## Extension (Chrome unpacked)

- Load `browser-extension/` as an unpacked extension against local API
- Real Greenhouse posting: supported path, fill preview, **never** clicks Submit
- Real Lever posting: same
- Approved owned resume attachment works where the browser/ATS allows it
- If programmatic attach is blocked, the panel says to upload manually (not "Unsupported")
- EEO / demographic questions stay untouched / manual

## Visual / a11y (frozen black / white / violet system)

- Dark mode and light mode
- Desktop 1440 and 1280, tablet 768, mobile 390
- 200% browser zoom, no horizontal overflow
- Keyboard navigation with a visible focus ring
- `prefers-reduced-motion: reduce`
- Landing, Login, Signup, Onboarding, Overview, Discover, Job Detail, Analyze/Match/Evidence, Prepare, Interview (job-contextual), Track, Growth, Profile, Resume, Settings, Privacy

## Privacy

- `/privacy` is reachable signed out
- Delete account removes that user's private records and revokes their sessions
- Shared job catalog rows remain
- Login errors stay generic (no "this email exists" on failed login)

Passing unit tests is not a substitute for the checks above.
