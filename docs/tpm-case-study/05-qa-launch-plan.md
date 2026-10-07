# 05 — QA and launch plan

TPM-quality launch plan derived from CareerPilot’s real release gates.

Source of truth: [`docs/V1_RELEASE_CHECKLIST.md`](../V1_RELEASE_CHECKLIST.md), [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml), [`.github/workflows/security.yml`](../../.github/workflows/security.yml).

## Why automation does not replace live gates

CI proves unit/integration behavior in controlled environments. It cannot fully prove:

- real Greenhouse/Lever DOM and attachment widgets in Chrome
- that Submit is never triggered on a live posting
- that EEO/terms fields stay untouched on real forms
- second-user session isolation and account deletion side effects on a realistic DB shape
- adversarial cross-feature break attempts that span web + extension + providers

Therefore A8/A9/Phase 6 remain **manual / external acceptance** on a frozen runtime SHA.

---

## Automated gates (current workflows)

### CI — `.github/workflows/ci.yml`

Typical jobs / steps (verify on current tree before citing in interviews):

- Backend: `python -m pytest -q`
- Frontend: `npm run test:run`, `npm run typecheck`, `npm run build`
- Extension: `npm test`, typecheck, build
- Mapped path / repo-map checks (AI repo map validity)
- Python `pip-audit` on `requirements.txt`
- Frontend and extension `npm audit --omit=dev --audit-level=high`
- MVP foundation + job intelligence browser workflows (as configured)
- Normal-browser CORS/cookie security check
- Committed-range whitespace check
- Tracked secret and artifact audit

### Security — `.github/workflows/security.yml`

- Full-history Gitleaks secret scan

### Local / contributor gates commonly paired with CI

- `python scripts/check_tracked_secrets.py`
- `git diff --check`
- Isolated/temp SQLite only — never mutate `data/careerpilot.db` in tests

---

## Manual / external gates

| Gate | What it proves |
| --- | --- |
| **A8 — Chrome Greenhouse Fill** | Supported path, fill preview, **never** Submit, EEO/terms manual |
| **A8 — Chrome Lever Fill** | Same for Lever |
| **Resume attachment verification** | Live Resume/CV input or group widget after attempt; filename ≠ proof |
| **No Submit** | No submit/requestSubmit/Enter-to-submit from extension |
| **EEO / terms untouched** | Sensitive fields remain manual |
| **A9 — second-user isolation** | No flash of prior user’s profile, scores, tracker, analytics, saved searches |
| **A9 — IDOR fail-closed** | Cross-user resource access denied |
| **A9 — account deletion** | Owner-scoped private data + sessions removed; shared jobs remain |
| **Phase 6 adversarial** | Cross-feature try-to-break; **no open P0/P1** |
| **Visual / a11y sweep** | Frozen black/white/violet system at listed breakpoints (re-check after UI changes) |

Certified on runtime SHA `7b6c3ee100ca4fe6399ac29441bece8df71783c7` (Chrome 152 for A8).

---

## Release decision record

| Criterion | Decision rule |
| --- | --- |
| Defect bar | No open P0/P1 after Phase 6 on certified runtime |
| Runtime proof | A8 + A9 on known SHA `7b6c3ee…` |
| Docs/version afterward | Phase 7 `3196e18…` does **not** inherit A8/A9 |
| Immutable tag | `v1.0.0` → `b73a983…`; do not move |
| Post-release | Showcase + maintenance triage; Dependabot and correctness PRs are post-v1 unless separately accepted |

**Certification provenance is the release-management story:** live ATS behavior was tested on a known runtime; later documentation/version metadata did not magically inherit runtime certification; later showcase/mainline improvements are not automatically recertified.

---

## Rollback (real strategy — not invented cloud rollback)

CareerPilot v1 is local / self-hostable. There is no multi-region deployment rollback system.

Practical fallback:

1. **Do not move or retag `v1.0.0`.** Keep the annotated tag as the immutable shipped pointer.
2. **Prefer the certified runtime SHA** (`7b6c3ee…`) when reasoning about Fill/privacy acceptance evidence.
3. **For a broken local checkout:** `git checkout` / reset to tag or certified SHA; restore from the user’s own DB backup if they have one — tests must never have been writing to production-like `data/careerpilot.db`.
4. **For a bad post-tag main commit:** revert or fix-forward on a branch; re-run automated gates; re-run A8/A9 **only if** Fill, attachment, session, or deletion behavior changed.
5. **Do not claim** “instant SaaS rollback” or traffic shifting.

---

## Launch sequence (as executed)

1. Feature freeze candidate runtime
2. Automated CI + audits green
3. A8 live ATS + A9 privacy on that SHA
4. Phase 6 adversarial — close or fix P0/P1
5. Phase 7 release-truth docs/version
6. Phase 8 annotated tag + GitHub Release
7. Phase 9+ showcase / portfolio; triage post-v1 PRs without rewriting release truth

---

## Re-certification triggers

Re-run live A8/A9 (and consider Phase 6) when changing:

- extension fill / attachment / submit guards
- ATS identity parsing
- auth/session/ownership
- account deletion scope
- grounding/approval gates that affect Fill eligibility
