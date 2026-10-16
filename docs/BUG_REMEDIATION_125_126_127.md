# Bug remediation report — PRs #125 / #126 / #127 + preference-skills

Integration branch: `fix/bug-remediation-125-126-127`
Base `main`: `d1f0da0d9423ec28253d6b372fbf7f9b2b13791f`

## Summary

Merged existing tested fixes from #125, #126, and #127 into one branch, fixed the #126 CI failure caused by `SCHEDULED_SCOUT` quota interacting with fairness, and closed a confirmed preference→skills evidence leak discovered in the independent audit.

## Before / after

| ID | Bug | Before | After | Evidence |
| --- | --- | --- | --- | --- |
| 125a | Distinct job URLs collapsed when title+employer matched | Unrelated postings could merge | URL/identity preserved in normalization/dedupe | `tests/test_job_scout_service.py`, `tests/test_persist_jobs.py` |
| 125b | Saved-search location ignored returned job location | Provider query location alone could alert | Match requires job location filter | `tests/test_saved_search_service.py` |
| 125c | Non-success HTTP treated as verified availability | Error responses could mark jobs live | Only success paths verify | `tests/test_job_verification_service.py` |
| 126a | Revalidation queue starvation | Later unseen jobs never checked | Fair revalidation progress | `tests/test_job_source_expansion.py` |
| 126b | Failed saved searches starved later searches | First five failures blocked the queue | Round-robin cursor advances on attempts | `test_failed_first_five_do_not_starve_later_searches_across_ticks` |
| 126c | Negative Analytics stage durations | Clock skew → negative durations | Durations clamped/non-negative | `tests/test_analytics.py` |
| 126d | Quota × fairness CI failure | Tick1 burned 5/6 `SCHEDULED_SCOUT` slots; tick2 only scouted one later search → assertion `['q5'] == ['q5','q6']` | Explicit policy: fairness ≠ quota; fairness test clears quota between ticks; new quota-policy test | `tests/test_saved_search_service.py` |
| 127a | Stale Job Intelligence after posting change | Old intel reused | Content change invalidates | `tests/test_job_intelligence.py` |
| 127b–d | Stale interview prep / feedback | Prep survived evidence/requirement drift | Fingerprint invalidation + reject stale feedback | `tests/test_interview_service.py` |
| 127e–f | Legacy preferences + deletion | Pre-resume prefs inaccessible; legacy rows surviving delete | Restore access; delete candidate-linked prefs | `tests/test_privacy_security.py` |
| 127g | Extension generic job URL matching | Supported pages missed | Generic URL recognition corrected | `tests/test_form_fill_service.py` |
| NEW | `skill_preferences` merged into `Candidate.skills` | Preference-only “Kubernetes” inflated Fit matched_skills (65→77.5) | Preferences stay on `TargetPreference` only | `tests/test_preference_skills_not_resume_evidence.py` |

### Reproduction (NEW preference-skills)

1. Candidate with resume-grounded skills `["Python", "SQL"]` only.
2. `POST /api/preferences` with `skill_preferences: ["Kubernetes"]`.
3. **Before:** `Candidate.skills` became `["Python","SQL","Kubernetes"]`; scoring a job requiring Kubernetes listed it in `matched_skills`.
4. **After:** `skill_preferences` persist on preferences; `Candidate.skills` unchanged; Fit still reports Kubernetes missing.

## Explicit saved-search policy

- Unlimited saved searches per user.
- ≤ `MAX_SEARCHES_PER_TICK` (5) attempts per scheduler tick.
- Round-robin cursor advances on success, scout failure, and 429.
- `last_run_at` set only after successful scout+persist.
- `SCHEDULED_SCOUT` = 6 events / 6 hours / user caps actual scouts; independent of fairness.

## Remaining issues

- Historical DBs that already merged preference skills into `Candidate.skills` are not auto-scrubbed (cannot reliably separate resume vs preference provenance). Users can re-parse resume / edit profile to restore grounded skills.
- Open Dependabot / showcase PRs are out of scope for this remediation.
- Live A8 Greenhouse/Lever Fill was not re-run (no Fill/attachment code path changes beyond URL matching helpers from #127 — re-run A8 if shipping Fill-facing changes to production-like use).

## Release readiness

**GO** for merging this remediation PR after GitHub CI + Security are green, subject to normal review. Not a recertification of A8/A9 runtime SHA.
