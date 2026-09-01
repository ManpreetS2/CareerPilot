import { EvidencePathButton, type EvidenceDrawerModel } from "./signature/EvidencePath";
import type {
  FactorStatus,
  GroupEvaluation,
  MatchEvidence,
  MatchFactor,
  RequirementEvaluation,
} from "../lib/types";
import { cn } from "../lib/cn";

const SECTION_TITLE: Record<MatchFactor["section"], string> = {
  required_skills: "Required skills",
  preferred_skills: "Preferred skills",
  qualifications: "Qualifications",
  eligibility: "Eligibility",
  work_location: "Work & location",
  preferences: "Preferences",
};

const IMPORTANCE_LABEL: Record<string, string> = {
  required: "Required",
  hard_required: "Hard required",
  preferred: "Preferred",
};

const RESULT_LABEL: Record<FactorStatus, string> = {
  satisfied: "Satisfied",
  partially_satisfied: "Partially satisfied",
  not_satisfied: "Not satisfied",
  unknown: "Unknown / Watch out",
  not_applicable: "Not applicable",
};

function texts(ids: string[], evidence: MatchEvidence["evidence"]): string[] {
  return ids.map((id) => evidence[id]?.exact_text).filter((item): item is string => Boolean(item));
}

function statusMark(status: FactorStatus): string {
  if (status === "satisfied") return "✓";
  if (status === "not_satisfied") return "✕";
  if (status === "unknown") return "?";
  if (status === "partially_satisfied") return "~";
  return "–";
}

function factorDetail(
  factor: MatchFactor,
  evidence: MatchEvidence["evidence"],
): EvidenceDrawerModel {
  const candidate = texts(factor.candidate_evidence_refs, evidence);
  return {
    factor: factor.label,
    result: RESULT_LABEL[factor.status],
    resultKind: factor.status,
    importance: factor.importance ? IMPORTANCE_LABEL[factor.importance] || factor.importance : null,
    scoringEffect: factor.scoring_effect,
    jobEvidence: texts(factor.job_evidence_refs, evidence),
    candidateEvidence: candidate,
    rule: `${factor.rule_id} ${factor.rule_version}`,
    explanation: factor.explanation,
    missingCandidate: factor.status === "not_satisfied" && candidate.length === 0,
  };
}

function FactorRow({
  factor,
  evidence,
}: {
  factor: MatchFactor;
  evidence: MatchEvidence["evidence"];
}) {
  const contribution =
    factor.score_contribution != null && factor.max_contribution != null
      ? `${factor.score_contribution} / ${factor.max_contribution}`
      : null;
  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border/70 px-3 py-2",
        factor.hard_blocker && "notice-danger",
        factor.status === "unknown" && "border-border",
      )}
      data-testid={`factor-${factor.id}`}
    >
      <div>
        <p className="text-sm font-medium">
          <span className="mr-2 font-semibold" aria-hidden>
            {statusMark(factor.status)}
          </span>
          {factor.label}
        </p>
        <p className="text-xs text-muted-foreground">
          {factor.importance ? `${IMPORTANCE_LABEL[factor.importance] || factor.importance} · ` : ""}
          {RESULT_LABEL[factor.status]}
          {contribution ? ` · ${contribution}` : ""}
          {factor.hard_blocker ? " · Hard requirement" : ""}
        </p>
        {factor.id === "factor_required_skills" || factor.id === "factor_preferred_skills" ? (
          <p className="mt-1 text-xs text-muted-foreground">{factor.explanation}</p>
        ) : null}
      </div>
      <EvidencePathButton
        claim={factor.label}
        evidence={factor.explanation}
        detail={factorDetail(factor, evidence)}
      >
        View evidence
      </EvidencePathButton>
    </div>
  );
}

function GroupCard({
  group,
  evaluations,
  evidence,
}: {
  group: GroupEvaluation;
  evaluations: RequirementEvaluation[];
  evidence: MatchEvidence["evidence"];
}) {
  const branches = group.branch_ids
    .map((id) => evaluations.find((item) => item.requirement_id === id))
    .filter((item): item is RequirementEvaluation => Boolean(item));
  return (
    <div className="rounded-lg border border-border/70 p-3" data-testid={`group-${group.group_id}`}>
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {group.operator === "any_of" ? "You must satisfy one" : "You must satisfy all"}
      </p>
      <p className="mt-1 text-sm font-medium">{group.text}</p>
      <ul className="mt-2 space-y-2 text-sm">
        {branches.map((branch, index) => (
          <li key={branch.requirement_id}>
            {index > 0 && group.operator === "any_of" ? (
              <p className="mb-1 text-xs uppercase text-muted-foreground">or</p>
            ) : null}
            <p>
              <span className="mr-2 font-semibold" aria-hidden>
                {statusMark(branch.result)}
              </span>
              {branch.explanation}
            </p>
            {texts(branch.candidate_evidence_refs, evidence).map((item) => (
              <p key={item} className="mt-1 pl-5 text-xs text-muted-foreground">
                {item}
              </p>
            ))}
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs font-semibold">
        Group: {RESULT_LABEL[group.status]}
        {group.hard_blocker ? " · Why this became Probably Skip" : ""}
      </p>
      <div className="mt-2">
        <EvidencePathButton
          claim={group.text}
          evidence={group.explanation}
          detail={{
            factor: group.text,
            result: RESULT_LABEL[group.status],
            resultKind: group.status,
            jobEvidence: texts(group.job_evidence_refs, evidence),
            candidateEvidence: branches.flatMap((item) => texts(item.candidate_evidence_refs, evidence)),
            rule: "graduation_eligibility_v1 v1",
            explanation: group.explanation,
            missingCandidate: group.status === "not_satisfied" && branches.every((item) => item.candidate_evidence_refs.length === 0),
          }}
        >
          View evidence
        </EvidencePathButton>
      </div>
    </div>
  );
}

export function MatchEvidencePanel({
  data,
  loading,
  error,
  onRetry,
}: {
  data: MatchEvidence | null;
  loading: boolean;
  error: unknown;
  onRetry: () => void;
}) {
  if (loading) {
    return (
      <section className="rounded-[var(--radius-lg)] border border-border/70 bg-surface/90 p-6" data-testid="evidence-loading">
        <h2 className="font-display text-2xl font-semibold">Evidence</h2>
        <p className="mt-2 text-sm text-muted-foreground">Loading stored match evidence…</p>
      </section>
    );
  }
  if (error) {
    return (
      <section className="rounded-[var(--radius-lg)] border border-border/70 bg-surface/90 p-6" data-testid="evidence-error">
        <h2 className="font-display text-2xl font-semibold">Evidence</h2>
        <p className="mt-2 text-sm text-muted-foreground">Could not load match evidence.</p>
        <button type="button" className="btn-secondary mt-3" onClick={onRetry}>
          Retry
        </button>
      </section>
    );
  }
  if (!data) {
    return (
      <section className="rounded-[var(--radius-lg)] border border-border/70 bg-surface/90 p-6">
        <h2 className="font-display text-2xl font-semibold">Evidence</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Calculate Fit to store grounded evidence for this job.
        </p>
      </section>
    );
  }

  const sections: MatchFactor["section"][] = [
    "required_skills",
    "preferred_skills",
    "qualifications",
    "eligibility",
    "work_location",
    "preferences",
  ];
  const groupedIds = new Set(data.groups.flatMap((group) => group.branch_ids));

  return (
    <section className="rounded-[var(--radius-lg)] border border-border/70 bg-surface/90 p-6 space-y-5" data-testid="match-evidence">
      <div>
        <h2 className="font-display text-2xl font-semibold">Why CareerPilot gave this match</h2>
        {data.notice ? <p className="mt-2 text-sm text-muted-foreground">{data.notice}</p> : null}
        {data.provenance.stale ? (
          <p className="mt-2 text-sm font-semibold" data-testid="evidence-stale">
            This evidence is stale and is not shown as current.
          </p>
        ) : null}
      </div>
      {data.provenance.stale ? null : data.groups.map((group) => (
        <GroupCard key={group.group_id} group={group} evaluations={data.evaluations} evidence={data.evidence} />
      ))}
      {data.provenance.stale
        ? null
        : sections.map((section) => {
        const rows = data.factors.filter((factor) => {
          if (factor.section !== section) return false;
          if (factor.group_id) return false;
          if (factor.requirement_id && groupedIds.has(factor.requirement_id)) return false;
          return true;
        });
        if (rows.length === 0) return null;
        return (
          <div key={section} data-testid={`evidence-section-${section}`}>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{SECTION_TITLE[section]}</h3>
            <div className="mt-2 space-y-2">
              {rows.map((factor) => (
                <FactorRow key={factor.id} factor={factor} evidence={data.evidence} />
              ))}
            </div>
          </div>
        );
      })}
    </section>
  );
}
