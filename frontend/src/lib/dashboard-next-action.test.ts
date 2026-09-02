import { describe, expect, it } from "vitest";
import { resolveNextAction } from "./dashboard-next-action";
import type { Job, MatchScore, ResumeVersionSummary } from "./types";

const ready = { ready: true, missing: [] as string[], code: null, next_route: null };
const incomplete = {
  ready: false,
  code: "profile_required",
  missing: ["candidate_profile", "candidate_evidence", "target_roles"],
  next_route: "/profile",
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
  it("asks to complete the profile when readiness is missing", () => {
    const next = resolveNextAction({
      readiness: incomplete,
      jobs: [],
      scores: [],
      resumeVersions: [],
    });
    expect(next.id).toBe("profile");
    expect(next.title).toBe("Complete your profile");
    expect(next.cta).toBe("Complete your profile");
    expect(next.to).toBe("/profile");
  });

  it("asks to complete the profile when readiness is omitted", () => {
    expect(
      resolveNextAction({
        jobs: [job],
        scores: [],
        resumeVersions: [],
      }).cta,
    ).toBe("Complete your profile");
  });

  it("asks to find jobs when the profile is ready and none are stored", () => {
    expect(
      resolveNextAction({
        readiness: ready,
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
        readiness: ready,
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
        readiness: ready,
        jobs: [job],
        scores: [],
        resumeVersions: [version],
      }).to,
    ).toBe("/resume/ver-1");
  });
});
