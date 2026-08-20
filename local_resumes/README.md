# Local resumes (manual testing only)

Place **consenting** resume PDFs here for local Candidate Profile Agent checks.

## Rules

- Only resumes you have explicit permission to use may be placed in this folder.
- PDF files in this directory are gitignored and **must never be committed**.
- Personal details must not appear in reports, commits, screenshots shared publicly, or other tracked files.

## Manual command

```bash
python scripts/test_candidate_profile.py local_resumes/resume.pdf
```

The script prints only safe IDs and category counts (extraction method, stored candidate ID, field counts, and grounding rejection category totals). It does not print names, emails, phones, companies, project names, resume text, or raw model output.

## Three-layout checkpoint

Before treating Day 2 as fully verified manually, run the script against:

1. Developer A resume
2. Developer B resume
3. One consenting resume with a different layout

Do not add real PDFs to the repository.
