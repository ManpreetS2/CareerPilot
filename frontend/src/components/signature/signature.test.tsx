import type { ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { ConstellationProgress } from "./ConstellationProgress";
import { EvidencePathButton } from "./EvidencePath";
import { LockIn } from "./LockIn";
import { ScoreAssembly } from "./ScoreAssembly";
import { ThemeProvider } from "../../lib/theme";
import { WorkflowPath } from "./WorkflowPath";

function wrap(ui: ReactNode) {
  return render(
    <ThemeProvider>
      <MemoryRouter>{ui}</MemoryRouter>
    </ThemeProvider>,
  );
}

describe("signature motion language", () => {
  it("renders onboarding constellation nodes", () => {
    wrap(<ConstellationProgress step={1} />);
    expect(screen.getByTestId("onboarding-constellation")).toBeInTheDocument();
    expect(screen.getAllByText("Welcome").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Finish").length).toBeGreaterThan(0);
  });

  it("shows score immediately when not assembling", () => {
    wrap(
      <ScoreAssembly
        assembling={false}
        match={{
          job_id: "job-1",
          overall_score: 86,
          skill_score: 90,
          qualification_score: 88,
          preference_score: 80,
          scoring_version: 2,
          match_tier: "good_match",
          match_reasons: ["You match 1 of 1 required technical skills."],
          matched_skills: ["Python"],
          partial_matches: [],
          missing_skills: [],
          recommendation: "apply",
          rationale: "Python appears in the stored candidate skills.",
        }}
      />,
    );
    expect(screen.getByTestId("score-assembly")).toHaveTextContent("86");
    expect(screen.getByTestId("score-assembly")).toHaveTextContent("Qualification Fit");
    expect(screen.getByTestId("score-assembly")).toHaveTextContent("Why you match");
    expect(screen.getByRole("button", { name: "Python" })).toBeInTheDocument();
  });

  it("opens the evidence drawer from a claim", async () => {
    const user = userEvent.setup();
    wrap(
      <EvidencePathButton claim="Python is a matched skill" evidence="Listed in the stored candidate skill evidence.">
        Python
      </EvidencePathButton>,
    );
    await user.click(screen.getByRole("button", { name: "Python" }));
    expect(await screen.findByTestId("evidence-drawer")).toBeInTheDocument();
    expect(screen.getByText("Listed in the stored candidate skill evidence.")).toBeInTheDocument();
  });

  it("renders lock-in without requiring animation to understand success", () => {
    wrap(<LockIn active message="Preferences saved and locked in." />);
    expect(screen.getByTestId("lock-in")).toHaveTextContent("Preferences saved and locked in.");
  });

  it("exposes workflow path labels for screen readers", () => {
    wrap(
      <WorkflowPath
        nodes={[
          { id: "a", label: "Generate", state: "complete" },
          { id: "b", label: "Review", state: "current" },
          { id: "c", label: "Approve", state: "upcoming" },
        ]}
      />,
    );
    expect(screen.getByTestId("workflow-path")).toHaveTextContent("Generate");
    expect(screen.getByTestId("workflow-path")).toHaveTextContent("Review");
  });
});
