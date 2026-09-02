import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { MatchEvidencePanel } from "./MatchEvidencePanel";
import { ThemeProvider } from "../lib/theme";
import type { MatchEvidence } from "../lib/types";

function wrap(ui: React.ReactNode) {
  return render(<ThemeProvider>{ui}</ThemeProvider>);
}

function evidence(overrides: Partial<MatchEvidence> = {}): MatchEvidence {
  return {
    job_id: "job-1",
    full_evidence: true,
    notice: null,
    provenance: {
      scoring_version: 2,
      evidence_version: 1,
      score_kind: "verified",
      stale: false,
      stale_reasons: [],
    },
    factors: [
      {
        id: "factor_required_skills",
        job_id: "job-1",
        category: "skill",
        section: "required_skills",
        label: "Required skills",
        importance: "required",
        status: "not_applicable",
        rule_id: "required_skills_v2",
        rule_version: "v2",
        explanation:
          "No required technical skills were structured for Fit V2. Preferred and plus skills do not count toward the Required Skills component.",
        scoring_effect: "This posting has no required-skill dimension. Preferred skills do not contribute to Required Skills.",
        job_evidence_refs: [],
        candidate_evidence_refs: [],
      },
      {
        id: "factor_preferred_skills",
        job_id: "job-1",
        category: "skill",
        section: "preferred_skills",
        label: "Preferred skills",
        importance: "preferred",
        status: "satisfied",
        score_contribution: 10,
        max_contribution: 10,
        rule_id: "preferred_skills_v2",
        rule_version: "v2",
        explanation: "Preferred skills matched. These do not count toward the Required Skills component.",
        scoring_effect: "Contributes to the Fit V2 preferred-skill dimension, not Required Skills.",
        job_evidence_refs: [],
        candidate_evidence_refs: [],
      },
      {
        id: "factor_skill_python",
        job_id: "job-1",
        category: "skill",
        section: "preferred_skills",
        label: "Python",
        importance: "preferred",
        status: "satisfied",
        rule_id: "preferred_skills_v2",
        rule_version: "v2",
        explanation: "Exact skill match against stored candidate evidence. Employer wording: Python a plus.",
        scoring_effect: "Does not contribute to the Required Skills component. Contributes to Preferred qualifications when Fit V2 scores preferred skills.",
        job_evidence_refs: ["ev_job"],
        candidate_evidence_refs: ["ev_cand"],
      },
      {
        id: "factor_skill_docker",
        job_id: "job-1",
        category: "skill",
        section: "required_skills",
        label: "Docker",
        importance: "required",
        status: "unknown",
        rule_id: "required_skills_v2",
        rule_version: "v2",
        explanation: "CareerPilot does not have enough evidence to verify this requirement.",
        scoring_effect: "Contributes to the Required Skills component. Individual skills are not assigned separate point values.",
        job_evidence_refs: ["ev_docker"],
        candidate_evidence_refs: [],
      },
      {
        id: "factor_auth",
        job_id: "job-1",
        category: "work_authorization",
        section: "eligibility",
        label: "Work authorization",
        status: "unknown",
        rule_id: "work_authorization_v1",
        rule_version: "v1",
        explanation: "Employer requirement: not stated",
        job_evidence_refs: [],
        candidate_evidence_refs: [],
      },
    ],
    evaluations: [
      {
        requirement_id: "req-final",
        result: "not_satisfied",
        candidate_evidence_refs: ["ev_year"],
        job_evidence_refs: ["ev_group"],
        explanation: "Not in the final year of the program.",
        rule_id: "graduation_eligibility_v1",
        group_id: "grp-1",
      },
      {
        requirement_id: "req-grad",
        result: "not_satisfied",
        candidate_evidence_refs: ["ev_grad"],
        job_evidence_refs: ["ev_group"],
        explanation: "Graduation is outside the recent-graduate window.",
        rule_id: "graduation_eligibility_v1",
        group_id: "grp-1",
      },
    ],
    groups: [
      {
        group_id: "grp-1",
        operator: "any_of",
        text: "Final year OR graduated within 12 months",
        status: "not_satisfied",
        importance: "hard_required",
        job_evidence_refs: ["ev_group"],
        branch_ids: ["req-final", "req-grad"],
        explanation: "Neither condition satisfied",
        hard_blocker: true,
      },
    ],
    evidence: {
      ev_job: {
        id: "ev_job",
        source_type: "job_requirement",
        exact_text: "Python a plus",
      },
      ev_cand: {
        id: "ev_cand",
        source_type: "candidate_project",
        exact_text: "Built PagePulse backend using Python",
      },
      ev_docker: {
        id: "ev_docker",
        source_type: "job_posting",
        exact_text: "Docker required",
      },
      ev_group: {
        id: "ev_group",
        source_type: "job_requirement",
        exact_text: "Candidates must either be in the final year or have graduated within 12 months.",
      },
      ev_year: {
        id: "ev_year",
        source_type: "candidate_preference",
        field: "academic_year",
        exact_text: "junior",
      },
      ev_grad: {
        id: "ev_grad",
        source_type: "candidate_education",
        exact_text: "State University · B.S. · 2028",
      },
    },
    ...overrides,
  };
}

describe("MatchEvidencePanel", () => {
  it("groups required and preferred factors and opens the evidence drawer", async () => {
    const user = userEvent.setup();
    wrap(<MatchEvidencePanel data={evidence()} loading={false} error={null} onRetry={() => undefined} />);
    expect(screen.getByText("Why CareerPilot gave this match")).toBeInTheDocument();
    expect(screen.getByTestId("evidence-section-required_skills")).toBeInTheDocument();
    expect(screen.getByTestId("evidence-section-preferred_skills")).toBeInTheDocument();
    expect(screen.getByText("Eligibility")).toBeInTheDocument();
    expect(screen.getByText(/Probably Skip/)).toBeInTheDocument();
    const python = screen.getByTestId("factor-factor_skill_python");
    await user.click(python.querySelector("button")!);
    expect(await screen.findByTestId("evidence-drawer")).toBeInTheDocument();
    expect(screen.getByText("Built PagePulse backend using Python")).toBeInTheDocument();
    expect(screen.getByText("Python a plus")).toBeInTheDocument();
    expect(screen.getByText(/Employer importance:\s*Preferred/)).toBeInTheDocument();
    expect(screen.getByTestId("evidence-scoring-effect")).toHaveTextContent(
      "Does not contribute to the Required Skills component",
    );
  });

  it("explains N/A required skills next to satisfied preferred skills", () => {
    wrap(<MatchEvidencePanel data={evidence()} loading={false} error={null} onRetry={() => undefined} />);
    const required = screen.getByTestId("factor-factor_required_skills");
    expect(required).toHaveTextContent("Not applicable");
    expect(required).toHaveTextContent("Preferred");
    expect(required).not.toHaveTextContent("0 / 25");
    const python = screen.getByTestId("factor-factor_skill_python");
    expect(python).toHaveTextContent("Satisfied");
    expect(python).toHaveTextContent("Preferred");
    expect(python).not.toHaveTextContent("18 / 25");
    expect(screen.getAllByText("Python")).toHaveLength(1);
  });

  it("does not render duplicate contradictory Python rows", () => {
    wrap(<MatchEvidencePanel data={evidence()} loading={false} error={null} onRetry={() => undefined} />);
    const pythonRows = screen.getAllByText("Python");
    expect(pythonRows).toHaveLength(1);
    expect(screen.queryByText("Python a plus")).not.toBeInTheDocument();
  });

  it("shows 0/25 required skills without implying preferred skills earned those points", () => {
    wrap(
      <MatchEvidencePanel
        data={evidence({
          factors: evidence().factors.map((factor) =>
            factor.id === "factor_required_skills"
              ? {
                  ...factor,
                  status: "not_satisfied",
                  score_contribution: 0,
                  max_contribution: 25,
                  explanation: "0 / 4 required skills matched. Preferred skills do not count toward this component.",
                }
              : factor,
          ),
        })}
        loading={false}
        error={null}
        onRetry={() => undefined}
      />,
    );
    const required = screen.getByTestId("factor-factor_required_skills");
    expect(required).toHaveTextContent("0 / 25");
    expect(required).toHaveTextContent("Preferred skills do not count toward this component");
    expect(screen.getByTestId("factor-factor_skill_python")).toHaveTextContent("Preferred");
    expect(screen.getByTestId("factor-factor_skill_python")).not.toHaveTextContent("0 / 25");
  });

  it("shows missing candidate evidence without claiming the candidate lacks the skill", async () => {
    const user = userEvent.setup();
    wrap(<MatchEvidencePanel data={evidence()} loading={false} error={null} onRetry={() => undefined} />);
    const docker = screen.getByTestId("factor-factor_skill_docker");
    await user.click(docker.querySelector("button")!);
    expect((await screen.findAllByText("CareerPilot does not have enough evidence to verify this requirement.")).length).toBeGreaterThan(0);
    expect(screen.queryByText(/does not know Docker/i)).toBeNull();
  });

  it("renders unknown without a red X", () => {
    wrap(<MatchEvidencePanel data={evidence()} loading={false} error={null} onRetry={() => undefined} />);
    const unknown = screen.getByTestId("factor-factor_auth");
    expect(unknown).toHaveTextContent("?");
    expect(unknown).not.toHaveTextContent("✕");
    expect(unknown).toHaveTextContent("Not enough evidence");
  });

  it("shows stale and loading states", () => {
    wrap(
      <MatchEvidencePanel
        data={evidence({ provenance: { scoring_version: 2, evidence_version: 1, stale: true, stale_reasons: ["candidate"] } })}
        loading={false}
        error={null}
        onRetry={() => undefined}
      />,
    );
    expect(screen.getByTestId("evidence-stale")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "View evidence" })).not.toBeInTheDocument();
    wrap(<MatchEvidencePanel data={null} loading error={null} onRetry={() => undefined} />);
    expect(screen.getByTestId("evidence-loading")).toBeInTheDocument();
  });
});
