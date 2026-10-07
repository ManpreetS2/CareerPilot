# 09 — Interview stories (STAR / TPM)

Concise stories for internship / TPM / EM interviews. No invented interpersonal conflict. No fake metrics.

---

## Story A — Scope control

**Theme:** Keeping auto-submit, universal ATS, and hosted SaaS out of v1.

**Situation:** The natural product pull was “apply everywhere automatically” and “support every ATS,” plus pressure to sound like a hosted SaaS.

**Task:** Define a shippable v1 that was still impressive in interviews without crossing safety and honesty lines.

**Action:** Wrote explicit exclusions into release invariants: never submit; EEO/terms manual; only Greenhouse + Lever certified for Fill; local/self-hostable positioning; immutable tag discipline. Chose depth (live A8 on two ATS) over brochure breadth.

**Result:** Tagged `v1.0.0` with certifiable Fill and privacy gates; showcase copy forbids SaaS/universal-ATS claims.

**What I learned:** Saying no to automation can be the product-quality decision, not a failure of ambition.

---

## Story B — Risk discovered during implementation

**Theme:** Incomplete posting → misleading Fit → requirements/evidence redesign.

**Situation:** Early Fit/Job Intelligence presentation could look authoritative when posting content was incomplete.

**Task:** Stop Fit from overclaiming without throwing away discovery/scoring progress.

**Action:** Drove a cross-workstream redesign: requirement profiles, content status, deterministic mining, Verified vs Potential Fit, UI that qualifies unverified percentages, Top-N full-posting verification without dumping every listing into Gemini. Kept Job Intelligence scoped to materials/interview.

**Result:** Fit V2 became the scoring contract; incomplete evidence is visible rather than papered over. Documented in the agile gap audit.

**What I learned:** Mid-program risk discovery is normal; the TPM job is to change the contract and acceptance criteria, not to hide the gap.

---

## Story C — Cross-workstream dependency

**Theme:** Developer A / Developer B meet at stable API/product contracts.

**Situation:** UI/Prepare (A) and discovery/ATS/extension (B) could drift if Fit payloads, approval eligibility, and ATS identity were informal.

**Task:** Keep the critical path integrable: evidence → Fit → materials → approval → Fill.

**Action:** Treated Shared/platform contracts as first-class: session ownership, Fit/evidence shapes, fingerprint invalidation, approval ≠ applied, ATS-ID identity for extension. Used handoff docs and release checklist invariants as the integration checklist.

**Result:** Extension Fill depends on approved owner-scoped materials and exact posting identity; UI can explain boundaries without re-implementing backend rules.

**What I learned:** In a small team, “ownership split” only works if the seam is a tested contract, not a personality handshake.

---

## Story D — Release blocker

**Theme:** Live / adversarial QA finding that CI alone would miss.

**Situation:** Automated tests were green, but Fill/privacy behavior had to be proven on real Chrome ATS pages and second-user isolation — A8/A9/Phase 6.

**Task:** Refuse to ship on unit tests alone when browser/provider/privacy behavior was the risk.

**Action:** Froze a certified runtime SHA (`7b6c3ee…`), ran live Greenhouse + Lever Fill (Chrome 152), verified no Submit, EEO/terms manual, truthful attachment (filename ≠ proof), then A9 isolation/deletion and Phase 6 adversarial with a **no open P0/P1** bar.

**Result:** Release decision tied to that runtime; later docs/version and tag SHAs documented separately so provenance stayed honest.

**What I learned:** A green CI badge is not an ATS certification. External gates need an explicit SHA.

---

## Story E — Quality vs schedule

**Theme:** Deferring non-critical UX/showcase issues instead of destabilizing runtime.

**Situation:** Showcase/visual QA found presentation and copy gaps (boundary clarity, screenshot inventory polish) after runtime certification.

**Task:** Improve portfolio honesty without moving Fill code or the release tag.

**Action:** Kept certified runtime and `v1.0.0` immutable; landed showcase/docs as post-tag work; recorded visual QA notes; triaged leftover correctness into post-v1 PRs rather than emergency tag moves.

**Result:** Interview assets improved; Fill certification provenance preserved; open maintenance PRs remain explicitly post-v1.

**What I learned:** Not every bug belongs in the release train. Sequencing polish vs safety is a core TPM skill.

---

## Story F — Technical disagreement / tradeoff

**Theme:** Deterministic Fit vs “AI everywhere.”

**Situation:** It is tempting to let an LLM produce Fit scores for demos.

**Task:** Choose an architecture that stays explainable under provider outage and incomplete postings.

**Action:** Kept Fit deterministic from structured evidence; used providers for extract/materials/interview where designed; made grounding failures visible (`grounding_override`) instead of silent invention.

**Result:** Fit remains available when generation is not; overclaim risk drops; messaging stays “evidence score,” not “AI magic.”

**What I learned:** The impressive demo is often the constrained system you can defend under failure.

---

## Story G — Post-launch maintenance

**Theme:** Open post-v1 PRs do not rewrite v1 release truth.

**Situation:** After tag, correctness/docs/dependency PRs exist (#125–#127, #131, Dependabot #132–#135).

**Task:** Talk about continuous improvement without implying the tagged release was fake or silently upgraded.

**Action:** Triage PRs as backlog/maintenance/docs/deps; refuse to merge them “into the case study narrative”; keep certified runtime, Phase 7 docs SHA, and tag SHA distinct; re-certify live gates only if Fill/session/deletion surfaces change.

**Result:** Honest portfolio story: v1 shipped with evidence; residual issues are managed openly.

**What I learned:** Release truth is a managed artifact. Maintenance is progress — rewriting history is not.
