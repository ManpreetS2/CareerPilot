import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { formatPostedDate, RequirementGroupView, WorkLocationPanel } from "./job-analysis-panels";
import type { JobRequirementProfile, RequirementGroup } from "../lib/types";

describe("job analysis panels", () => {
  it("describes alternative requirements without JSON operator names", () => {
    const group: RequirementGroup = {
      id: "g1",
      operator: "any_of",
      requirement_ids: ["r1", "r2"],
      text: "Final year or recent graduate",
      evidence_text: "",
      importance: "required",
    };
    render(
      <RequirementGroupView
        group={group}
        requirements={[
          {
            id: "r1",
            category: "education",
            text: "Final-year student",
            importance: "required",
            evidence_text: "",
          },
          {
            id: "r2",
            category: "education",
            text: "Graduated within previous 12 months",
            importance: "required",
            evidence_text: "",
          },
        ]}
      />,
    );
    expect(screen.getByText("You must satisfy one")).toBeInTheDocument();
    expect(screen.getByText("Final-year student")).toBeInTheDocument();
    expect(screen.getByText("or")).toBeInTheDocument();
    expect(screen.getByText(/Group result: Not evaluated yet/)).toBeInTheDocument();
    expect(screen.queryByText(/any_of/)).not.toBeInTheDocument();
  });

  it("does not collapse Remote US-only into Remote", () => {
    const profile: JobRequirementProfile = {
      required_skills: [],
      preferred_skills: [],
      primary_responsibilities: [],
      requirements: [],
      requirement_groups: [],
      locations: [{ label: "United States" }],
      work_mode: "remote",
      remote_scope: "United States only",
      timezone_requirements: "Pacific–Eastern overlap",
      travel_requirements: [],
      relocation_requirements: [],
      source_fingerprint: "abc",
    };
    render(<WorkLocationPanel profile={profile} />);
    expect(screen.getByText("United States only")).toBeInTheDocument();
    expect(screen.getByText("Pacific–Eastern overlap")).toBeInTheDocument();
    expect(screen.getAllByText("Not stated").length).toBeGreaterThan(0);
  });

  it("does not treat unix-epoch posted dates as real posting dates", () => {
    expect(formatPostedDate("0")).toBe("Not stated");
    expect(formatPostedDate("1970-01-01")).toBe("Not stated");
    expect(formatPostedDate(null)).toBe("Not stated");
  });
});
