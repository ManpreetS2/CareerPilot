import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { JobDetailPage } from "./JobDetailPage";
import { api, ApiClientError } from "../lib/api";
import { bindSessionUser } from "../lib/session";
import { saveJobsNavIds } from "../lib/jobs-workspace";
import { ThemeProvider } from "../lib/theme";
import { createTestQueryClient } from "../test/render";
import type { Job, JobRequirementProfile } from "../lib/types";
import "../index.css";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      getJob: vi.fn(),
      getJobIntelligence: vi.fn(),
      extractJobIntelligence: vi.fn(),
      getJobs: vi.fn(),
      queryJobs: vi.fn(),
      getStoredScores: vi.fn(),
      getStoredScore: vi.fn(),
      scoreJob: vi.fn(),
      getInterviewPrep: vi.fn(),
      prepareInterview: vi.fn(),
      verifyJob: vi.fn(),
      getRequirementProfile: vi.fn(),
      extractRequirementProfile: vi.fn(),
      getMatchEvidence: vi.fn(),
    },
  };
});

function requirementProfile(overrides: Partial<JobRequirementProfile> = {}): JobRequirementProfile {
  return {
    required_skills: [],
    preferred_skills: [],
    primary_responsibilities: [],
    requirements: [],
    requirement_groups: [],
    locations: [],
    travel_requirements: [],
    relocation_requirements: [],
    source_fingerprint: "fp",
    ...overrides,
  };
}

function mockJob(overrides: Partial<Job> = {}) {
  vi.mocked(api.getJob).mockResolvedValue({
    id: "job-1",
    title: "Software Engineer Intern",
    company: "Harborline Analytics",
    url: "https://example.com/showcase/harborline-intern",
    description: "DEMO",
    source: "manual",
    status: "verified",
    ...overrides,
  });
}

function renderJob() {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <ThemeProvider>
        <MemoryRouter initialEntries={["/jobs/job-1"]}>
          <Routes>
            <Route path="/jobs/:jobId" element={<JobDetailPage />} />
          </Routes>
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("JobDetailPage", () => {
  beforeEach(() => {
    sessionStorage.clear();
    bindSessionUser(null);
    vi.mocked(api.getJob).mockResolvedValue({
      id: "job-1",
      title: "Staff Platform Engineer for Extremely-Long-Company-Name-That-Must-Wrap",
      company: "Northwind Analytics International",
      url: "https://jobs.example.com/very/long/path/to/a/posting",
      description: "Python",
      source: "manual",
      status: "verified",
    });
    vi.mocked(api.getJobIntelligence).mockRejectedValue(new ApiClientError(404, "None"));
    vi.mocked(api.getJobs).mockResolvedValue([]);
    vi.mocked(api.queryJobs).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 40,
      verified_count: 0,
      potential_count: 0,
      ids: [],
    });
    vi.mocked(api.getStoredScores).mockResolvedValue([]);
    vi.mocked(api.getStoredScore).mockRejectedValue(new ApiClientError(404, "None"));
    vi.mocked(api.getInterviewPrep).mockRejectedValue(new ApiClientError(404, "None"));
    vi.mocked(api.getRequirementProfile).mockRejectedValue(new ApiClientError(404, "None"));
    vi.mocked(api.getMatchEvidence).mockRejectedValue(new ApiClientError(404, "None"));
    vi.mocked(api.extractJobIntelligence).mockReset();
    vi.mocked(api.scoreJob).mockReset();
    vi.mocked(api.prepareInterview).mockReset();
    vi.mocked(api.getRequirementProfile).mockRejectedValue(new ApiClientError(404, "None"));
    vi.mocked(api.extractRequirementProfile).mockReset();
  });

  it("loads stored job evidence without extracting, scoring, or generating interview prep", async () => {
    renderJob();
    expect(await screen.findByRole("heading", { name: /Staff Platform Engineer/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(api.getJob).toHaveBeenCalled();
      expect(api.getJobIntelligence).toHaveBeenCalled();
      expect(api.getStoredScore).toHaveBeenCalled();
    });
    expect(api.extractJobIntelligence).not.toHaveBeenCalled();
    expect(api.extractRequirementProfile).not.toHaveBeenCalled();
    expect(api.scoreJob).not.toHaveBeenCalled();
    expect(api.prepareInterview).not.toHaveBeenCalled();
  });

  it("wraps long job titles instead of truncating them", async () => {
    renderJob();
    const heading = await screen.findByRole("heading", { name: /Staff Platform Engineer/i });
    expect(heading).toHaveClass("wrap-anywhere");
    expect(getComputedStyle(heading).overflowWrap).toBe("anywhere");
  });

  it("moves Previous and Next within the stored result context without wrapping", async () => {
    bindSessionUser(1);
    saveJobsNavIds(["job-0", "job-1", "job-2"]);
    renderJob();
    expect(await screen.findByRole("link", { name: /Previous job/i })).toHaveAttribute("href", "/jobs/job-0");
    expect(screen.getByRole("link", { name: /Next job/i })).toHaveAttribute("href", "/jobs/job-2");
  });

  it("clears an old Fit score when employer requirements are re-extracted", async () => {
    vi.mocked(api.getStoredScore).mockResolvedValue({
      job_id: "job-1", overall_score: 96,
      matched_skills: ["Python"], partial_matches: [], missing_skills: [],
      recommendation: "apply", rationale: "Old requirements",
      score_kind: "verified", match_tier: "strong_match",
    });
    vi.mocked(api.getRequirementProfile).mockResolvedValue(
      requirementProfile({ required_skills: ["Python"] }),
    );
    vi.mocked(api.extractJobIntelligence).mockResolvedValue({
      job_id: "job-1", required_skills: ["Go"], preferred_skills: [],
      education_requirements: [], tech_stack: ["Go"],
      responsibilities: [], likely_interview_focus: [],
    });
    renderJob();
    expect(await screen.findByText(/96% Strong Match/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Extract requirements" }));
    await waitFor(() => expect(screen.queryByText(/96% Strong Match/)).not.toBeInTheDocument());
    await userEvent.click(screen.getByRole("tab", { name: "Match" }));
    expect(screen.getByText(/No fit score yet/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "What they're looking for" })).not.toBeInTheDocument();
    expect(screen.getAllByText("Go").length).toBeGreaterThan(0);
  });

  it("ignores a previous job's verification result after navigating to the next job", async () => {
    bindSessionUser(1);
    saveJobsNavIds(["job-1", "job-2"]);
    const firstJob: Job = {
      id: "job-1", title: "First role", company: "First Employer",
      url: "https://example.com/first", description: "First description",
      source: "manual", status: "discovered",
    };
    const secondJob: Job = {
      id: "job-2", title: "Second role", company: "Second Employer",
      url: "https://example.com/second", description: "Second description",
      source: "manual", status: "discovered",
    };
    vi.mocked(api.getJob).mockImplementation(async (id) => id === "job-2" ? secondJob : firstJob);
    let completeVerification: (value: Job) => void = () => undefined;
    vi.mocked(api.verifyJob).mockImplementation(
      () => new Promise<Job>((resolve) => { completeVerification = resolve; }),
    );
    renderJob();
    expect(await screen.findByRole("heading", { name: "First role" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Verify", exact: true }));
    expect(api.verifyJob).toHaveBeenCalledWith("job-1");
    await userEvent.click(screen.getByRole("link", { name: /Next job/i }));
    expect(await screen.findByRole("heading", { name: "Second role" })).toBeInTheDocument();
    await act(async () => {
      completeVerification({ ...firstJob, status: "flagged", verification_notes: "First posting closed." });
    });
    expect(screen.getByRole("heading", { name: "Second role" })).toBeInTheDocument();
    expect(screen.queryByText("First posting closed.")).not.toBeInTheDocument();
  });

  it("does not show a previous job's late Fit result in the next job header", async () => {
    bindSessionUser(1);
    saveJobsNavIds(["job-1", "job-2"]);
    vi.mocked(api.getJob).mockImplementation(async (id) => ({
      id,
      title: id === "job-1" ? "First scoring role" : "Second scoring role",
      company: "Example Employer",
      url: "https://example.com/job",
      description: "Requirements",
      source: "manual",
      status: "discovered",
    }));
    let completeScore: (value: Awaited<ReturnType<typeof api.scoreJob>>) => void = () => undefined;
    vi.mocked(api.scoreJob).mockImplementation(
      () => new Promise((resolve) => { completeScore = resolve; }),
    );
    renderJob();
    expect(await screen.findByRole("heading", { name: "First scoring role" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Match" }));
    await userEvent.click(screen.getByRole("button", { name: "Calculate fit" }));
    expect(api.scoreJob).toHaveBeenCalledWith("job-1");
    await userEvent.click(screen.getByRole("link", { name: /Next job/i }));
    expect(await screen.findByRole("heading", { name: "Second scoring role" })).toBeInTheDocument();
    await act(async () => {
      completeScore({
        job_id: "job-1", overall_score: 98.0,
        matched_skills: ["Python"], partial_matches: [], missing_skills: [],
        recommendation: "apply", rationale: "Old posting only.", score_kind: "verified",
        match_tier: "strong_match", apply_recommendation: "apply", confidence_level: "high",
      });
    });
    expect(screen.getByRole("heading", { name: "Second scoring role" })).toBeInTheDocument();
    expect(screen.queryByText(/98% Strong Match/)).not.toBeInTheDocument();
    expect(screen.queryByText("Old posting only.")).not.toBeInTheDocument();
  });

  it("keeps Potential Match until a verified score exists", async () => {
    vi.mocked(api.getStoredScore).mockResolvedValue({
      job_id: "job-1",
      overall_score: 91,
      matched_skills: [],
      partial_matches: [],
      missing_skills: [],
      recommendation: "apply",
      rationale: "preliminary",
      score_kind: "preliminary",
    });
    vi.mocked(api.extractRequirementProfile).mockRejectedValue(new ApiClientError(502, "unavailable"));
    renderJob();
    expect((await screen.findAllByText(/Potential Match/)).length).toBeGreaterThan(0);
    expect(screen.queryByText("91%")).not.toBeInTheDocument();
    expect(api.scoreJob).not.toHaveBeenCalled();
    expect(api.extractRequirementProfile).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /Retry verification/i })).not.toBeInTheDocument();
  });

  it("loads stored match evidence when the Evidence tab is opened", async () => {
    vi.mocked(api.getMatchEvidence).mockResolvedValue({
      job_id: "job-1",
      full_evidence: true,
      notice: null,
      provenance: { scoring_version: 2, evidence_version: 1, stale: false, stale_reasons: [], score_kind: "verified" },
      factors: [
        {
          id: "factor_skill_python",
          job_id: "job-1",
          category: "skill",
          section: "qualifications",
          label: "Python",
          status: "satisfied",
          rule_id: "required_skills_v2",
          rule_version: "v2",
          explanation: "Exact skill match",
          job_evidence_refs: [],
          candidate_evidence_refs: [],
        },
      ],
      evaluations: [],
      groups: [],
      evidence: {},
    });
    const user = userEvent.setup();
    renderJob();
    await screen.findByRole("heading", { name: /Staff Platform Engineer/i });
    await user.click(screen.getByRole("tab", { name: "Evidence" }));
    expect(await screen.findByText("Why CareerPilot gave this match")).toBeInTheDocument();
    expect(api.getMatchEvidence).toHaveBeenCalled();
    expect(api.scoreJob).not.toHaveBeenCalled();
  });

  it("distinguishes a catalog Verified status from a recorded live posting check", async () => {
    mockJob({ status: "verified", verified_at: null, verification_notes: null });
    renderJob();
    expect(await screen.findByText(/Catalog status:/)).toHaveTextContent("Catalog status: verified");
    expect(screen.getByText(/No live posting check has been recorded/)).toBeInTheDocument();
    expect(screen.queryByText(/Not verified yet/)).not.toBeInTheDocument();
  });

  it("shows the recorded live verification details without a false not-verified warning", async () => {
    mockJob({
      status: "verified",
      verified_at: "2026-09-22T12:00:00Z",
      verification_notes: "Posting was checked against employer evidence.",
    });
    renderJob();
    expect(await screen.findByText(/Catalog status:/)).toHaveTextContent("Catalog status: verified");
    expect(screen.getByText("Posting was checked against employer evidence.")).toBeInTheDocument();
    expect(screen.getByText(/Last checked/)).toBeInTheDocument();
    expect(screen.queryByText(/No live posting check has been recorded/)).not.toBeInTheDocument();
  });

  it("discloses the fictional showcase posting in Analyze", async () => {
    mockJob({ id: "showcase-harborline-intern" });
    renderJob();
    expect(await screen.findByText(/Synthetic demo · not a real posting/)).toBeInTheDocument();
  });

  it("shows Remote once when location and work mode are both Remote", async () => {
    mockJob({ location: "Remote" });
    vi.mocked(api.getRequirementProfile).mockResolvedValue(
      requirementProfile({ work_mode: "remote", employment_type: "internship" }),
    );
    renderJob();
    expect(await screen.findByText("Remote · Internship")).toBeInTheDocument();
    expect(screen.queryByText("Remote · Remote · Internship")).not.toBeInTheDocument();
  });

  it("keeps a city location next to Hybrid", async () => {
    mockJob({ location: "San Francisco, CA" });
    vi.mocked(api.getRequirementProfile).mockResolvedValue(requirementProfile({ work_mode: "hybrid" }));
    renderJob();
    expect(await screen.findByText("San Francisco, CA · Hybrid")).toBeInTheDocument();
  });

  it("keeps a city location next to On-site", async () => {
    mockJob({ location: "New York, NY" });
    vi.mocked(api.getRequirementProfile).mockResolvedValue(requirementProfile({ work_mode: "onsite" }));
    renderJob();
    expect(await screen.findByText("New York, NY · On-site")).toBeInTheDocument();
  });

  it("keeps salary after location, work mode, and employment type", async () => {
    mockJob({ location: "Remote", salary: "$120k–$150k" });
    vi.mocked(api.getRequirementProfile).mockResolvedValue(
      requirementProfile({ work_mode: "remote", employment_type: "internship" }),
    );
    renderJob();
    expect(await screen.findByText("Remote · Internship · $120k–$150k")).toBeInTheDocument();
  });

  it("does not leak an unknown work mode into the header", async () => {
    mockJob({ location: "Austin, TX" });
    vi.mocked(api.getRequirementProfile).mockResolvedValue(
      requirementProfile({ work_mode: "unknown", employment_type: "internship" }),
    );
    renderJob();
    expect(await screen.findByText("Austin, TX · Internship")).toBeInTheDocument();
    expect(screen.queryByText(/unknown/i)).not.toBeInTheDocument();
  });

  it("does not leak an unknown employment type into the header", async () => {
    mockJob({ location: "Austin, TX", salary: "$120k–$150k" });
    vi.mocked(api.getRequirementProfile).mockResolvedValue(
      requirementProfile({ work_mode: "hybrid", employment_type: "unknown" }),
    );
    renderJob();
    expect(await screen.findByText("Austin, TX · Hybrid · $120k–$150k")).toBeInTheDocument();
    expect(screen.queryByText(/unknown/i)).not.toBeInTheDocument();
  });
});
