# Security policy

CareerPilot is source-visible for portfolio, evaluation, demonstration, and collaboration. It is not an invitation to test against other people's accounts or production data.

## Reporting a vulnerability

Prefer GitHub private vulnerability reporting / a private security advisory when that feature is available on this repository (Security → Advisories → Report a vulnerability).

Do **not** open a public issue, pull request, or discussion that contains:

- passwords
- session cookies
- API keys or tokens
- resumes
- candidate personal information
- private application materials or tracker data
- live exploit payloads that include sensitive data

Describe the issue with a reproduction that uses synthetic or local data only. Include the affected route, component, or dependency, the impact, and (if known) a suggested fix. Do not attach real credentials, cookies, resumes, or production database files.

If private reporting is unavailable, contact the repository maintainer without including secrets or personal data in the message body. Rotate any credential you believe was exposed before writing.

## High-priority issues

Reports in these areas are treated as high priority:

- authentication or session bypass
- cross-user data leakage
- insecure direct object references (IDOR)
- secret exposure
- CSRF or CORS failures
- unsafe browser-extension behavior
- unintended application submission
- injection
- server-side request forgery (SSRF)
- sensitive logging
- resume or candidate-data exposure
- unsafe file handling
- dependency or supply-chain compromise

## Testing expectations

- Use synthetic or local data only.
- Do not attack another user's account, session, or data.
- Do not target production systems or production databases.
- Do not attempt to submit real job applications through CareerPilot or the extension.
- Automated tests in this repository use isolated in-memory SQLite and must not create or mutate `data/careerpilot.db`.
