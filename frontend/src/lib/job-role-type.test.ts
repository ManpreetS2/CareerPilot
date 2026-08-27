import { describe, expect, it } from "vitest";
import {
  jobLooksLikeInternship,
  matchesRoleTypeFilter,
  readRoleType,
  writeRoleType,
} from "./job-role-type";

describe("jobLooksLikeInternship", () => {
  it("matches explicit internship titles and seniority", () => {
    expect(jobLooksLikeInternship("Software Engineer Intern")).toBe(true);
    expect(jobLooksLikeInternship("Summer Internship")).toBe(true);
    expect(jobLooksLikeInternship("Software Engineer", "intern")).toBe(true);
    expect(jobLooksLikeInternship("Software Engineer")).toBe(false);
    expect(jobLooksLikeInternship("Internal Tools Engineer")).toBe(false);
  });
});

describe("matchesRoleTypeFilter", () => {
  it("keeps internships, full-time, or both from the title heuristic", () => {
    expect(matchesRoleTypeFilter("Backend Intern", "internships")).toBe(true);
    expect(matchesRoleTypeFilter("Backend Intern", "full_time")).toBe(false);
    expect(matchesRoleTypeFilter("Staff Engineer", "full_time")).toBe(true);
    expect(matchesRoleTypeFilter("Staff Engineer", "both")).toBe(true);
  });
});

describe("role type constraints", () => {
  it("round-trips through existing preferences.constraints without dropping other values", () => {
    const next = writeRoleType(["visa sponsorship", "role_type:both"], "internships");
    expect(next).toEqual(["visa sponsorship", "role_type:internships"]);
    expect(readRoleType(next)).toBe("internships");
    expect(readRoleType([])).toBe("both");
  });
});
