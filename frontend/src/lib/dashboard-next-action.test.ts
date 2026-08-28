import { describe, expect, it } from "vitest";
import { resolveNextAction } from "./dashboard-next-action";
import type { CandidateProfile, Job, MatchScore, ResumeVersionSummary } from "./types";

const candidate: CandidateProfile = {
  name: "Ada",
  skills: ["Python"],
  projects: [],
  experience: [{ title: "Intern", company: "Labs", highlights: [] }],
  education: [],
  certifications: [],
  strengths: [],
  evidence_links: [],
};

const job: Job = {
  id: "job-1",
  title: "Engineer",
  company: "Acme",
  url: "https://example.com",
  description: "Python",
  source: "manual",
  status: "verified",
};

describe("resolveNextAction", () => {
  it("asks to build a profile when none exists", () => {
    expect(
      resolveNextAction({
        candidate: null,
        preferences: null,
        jobs: [],
        scores: [],
        resumeVersions: [],
      }).id,
    ).toBe("profile");
  });

  it("asks to finish setup when preferences are missing", () => {
    expect(
      resolveNextAction({
        candidate,
        preferences: { target_roles: [], preferred_locations: [], constraints: [] },
        jobs: [],
        scores: [],
        resumeVersions: [],
      }).id,
    ).toBe("preferences");
  });

  it("asks to find jobs when none are stored", () => {
    expect(
      resolveNextAction({
        candidate,
        preferences: { target_roles: ["Engineer"], preferred_locations: ["Remote"], constraints: [] },
        jobs: [],
        scores: [],
        resumeVersions: [],
      }).id,
    ).toBe("jobs");
  });

  it("points at strongest matches when scores are strong", () => {
    const score: MatchScore = {
      job_id: "job-1",
      overall_score: 88,
      matched_skills: ["Python"],
      partial_matches: [],
      missing_skills: [],
      recommendation: "apply",
      rationale: "Strong",
    };
    expect(
      resolveNextAction({
        candidate,
        preferences: { target_roles: ["Engineer"], preferred_locations: [], constraints: [] },
        jobs: [job],
        scores: [score],
        resumeVersions: [],
      }).to,
    ).toBe("/jobs?tab=matches");
  });

  it("points at the latest resume version when no strong matches exist", () => {
    const version: ResumeVersionSummary = {
      id: "ver-1",
      job_id: "job-1",
      job_title: "Engineer",
      company: "Acme",
      version_number: 1,
      created_at: "2026-01-01T00:00:00Z",
      bullet_count: 2,
      provenance_status: "approved_snapshot",
      matches_current_profile: true,
    };
    expect(
      resolveNextAction({
        candidate,
        preferences: { target_roles: ["Engineer"], preferred_locations: [], constraints: [] },
        jobs: [job],
        scores: [],
        resumeVersions: [version],
      }).to,
    ).toBe("/resume/ver-1");
  });
});
