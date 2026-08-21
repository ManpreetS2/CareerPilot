# Local resumes (manual testing only)

Place **consenting** resume PDFs here for local Candidate Profile Agent checks.

## Rules

- Only resumes you have explicit permission to use may be placed in this folder.
- PDF files in this directory are gitignored and **must never be committed**.
- Personal details must not appear in reports, commits, screenshots shared publicly, or other tracked files.
- Generated synthetic PDFs under `local_resumes/generated/` are also ignored. Do not stage them.

## Real vs synthetic testing

Synthetic layouts are fictional QA fixtures. They **do not** count toward the three-consenting-real-resume matrix.

| Matrix | Meaning |
| --- | --- |
| Real resumes | Consenting human resumes with distinct layouts |
| Synthetic layouts | Generated fictional PDFs for automated/API QA |

Never report synthetic pass counts as additional real resumes.

## Generate the synthetic matrix

```bash
python scripts/generate_synthetic_resume_matrix.py
```

Writes ignored PDFs to `local_resumes/generated/` and refreshes JSON manifests under `tests/fixtures/synthetic_resumes/`.

## Run the matrix runner

Deterministic (mocked structured output, temporary in-process DB):

```bash
python scripts/test_candidate_profile_matrix.py --synthetic
```

Live API against a temporary SQLite database (does not use `data/careerpilot.db`):

```bash
python scripts/test_candidate_profile_matrix.py --synthetic --live
```

The runner prints only opaque layout identifiers, HTTP status, extraction method, stored ID format, category counts, rejection/failure counts, and pass/fail. It does not print names, emails, phones, companies, project names, resume text, or raw model output.

Unsupported returned claims fail the matrix. Missing optional grounded claims are recall, not an automatic fail.

Exit code is nonzero if any layout fails. Example summary: `synthetic_layouts=3 passed=3 failed=0`.

## Manual real-resume command

```bash
python scripts/test_candidate_profile.py local_resumes/resume.pdf
```

The script prints only safe IDs and category counts.

## Three-layout real-resume checkpoint

Before treating Day 2 as fully verified with real documents, run the real-resume script against:

1. Developer A resume
2. Developer B resume
3. One consenting resume with a different layout

Do not add real PDFs to the repository.
