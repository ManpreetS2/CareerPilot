# Python dependency reproducibility

CareerPilot's JavaScript apps commit lockfiles (`frontend/package-lock.json`, `browser-extension/package-lock.json`). Python CI does not. This note records the gap and the intended fix. It is not a lockfile.

## Current state

There is no `pyproject.toml`, `constraints-ci.txt`, `requirements-dev.txt`, `uv.lock`, or pip-tools input in this repository.

`requirements.txt` lists **direct** dependencies with version **ranges**. CI runs:

```bash
pip install -r requirements.txt
```

Each run resolves a compatible set from PyPI at that moment. Frontend and extension `npm ci` installs are bit-for-bit with their lockfiles; Python is not.

Blind `pip freeze > requirements.txt` is rejected: a developer venv can contain leftover tools, OS-specific wheels, and packages that are not CareerPilot dependencies. Freezing that mix would pin noise and hide the direct/transitive split.

## Direct vs transitive

Direct (from `requirements.txt`): FastAPI, Uvicorn, SQLAlchemy, Argon2, email-validator, Pydantic, pydantic-settings, python-dotenv, python-multipart, httpx, requests, pdfplumber, pytesseract, python-docx, reportlab, Playwright, google-genai, anthropic, openai, pytest, PyYAML.

Transitive examples that actually execute in CI: **Starlette** (via FastAPI), Playwright's `pyee`/browser download, LLM SDK internals, pdfminer.six, httpcore. Those versions are not named in `requirements.txt`.

## Highest-stability packages

| Area | Why it matters |
| --- | --- |
| Playwright | `playwright>=1.49.0` selects a matching Chromium build. A minor bump can change browser binary, launch flags, and browser-gate behavior. |
| FastAPI / Starlette | HTTP semantics, deprecation aliases, TestClient. |
| LLM SDKs (`google-genai`, `anthropic`, `openai`) | Unbounded minors can change request shapes; product code still must not invent evidence. |
| pdfplumber / python-docx | Resume extraction grounding. |

## Last known green CI resolve

From GitHub Actions `verify` on `main` SHA `b73a983ed3605d498aa90070c3b5f786a73bc525` (run `34376617071`, 2026-09-09):

- fastapi 0.141.1, starlette 1.6.0, playwright 1.62.0
- Playwright Chromium: Chrome for Testing 151.0.7922.34 (`chromium-1234`)
- openai 3.11.0, anthropic 1.4.0, google-genai 2.22.0
- pdfplumber 0.11.10, python-docx 1.2.0, sqlalchemy 2.0.52, pytest 9.1.1

That list is **observational**, not a constraints file. Do not paste it into `requirements.txt`.

## Starlette 422 alias

Installed Starlette 1.6.0 deprecates `HTTP_422_UNPROCESSABLE_ENTITY` in favor of `HTTP_422_UNPROCESSABLE_CONTENT` (both remain numeric 422).

`HTTP_422_UNPROCESSABLE_CONTENT` exists only from Starlette 0.48. Declared `fastapi>=0.115.0,<1.0.0` can still resolve FastAPI 0.115.x, whose Starlette upper bound is below 0.48. Replacing the alias with `CONTENT` would break that range.

Do **not** switch to `HTTP_422_UNPROCESSABLE_CONTENT` until the FastAPI lower bound cannot install a Starlette that lacks it. FastAPI itself uses literal `422` for cross-version compatibility. A later constraints pin can make either a literal `422` cleanup or the new constant safe. Tests already assert HTTP 422 on the affected ingest/auth/approval paths.

## Recommended approach (later PR)

Preferred: keep readable ranges in `requirements.txt` and add a **CI constraints file** generated from a **clean** Python 3.11 environment (GitHub `ubuntu-24.04` or an empty venv), not a developer laptop.

Conceptual CI install:

```bash
pip install -r requirements.txt -c constraints-ci.txt
```

Generation options: `pip-tools` (`pip-compile`) or `uv pip compile`. Review the compiled file so it contains only packages needed by `requirements.txt`. Commit it. Re-run the full `verify` gate, including Playwright browser steps, whenever Playwright's pin changes.

Do not enable Dependabot auto-merge for that file. Humans review Playwright and LLM SDK bumps.

## Test plan for a future constraints PR

1. Generate constraints in a clean 3.11 environment.
2. `pip install -r requirements.txt -c constraints-ci.txt`
3. Full backend/frontend/extension/`verify` matrix, including the three browser scripts.
4. Confirm no use of `data/careerpilot.db`.
5. Keep this document until the constraints file exists and CI uses it.
