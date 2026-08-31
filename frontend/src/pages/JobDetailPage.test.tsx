import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { JobDetailPage } from "./JobDetailPage";
import { api, ApiClientError } from "../lib/api";
import { bindSessionUser } from "../lib/session";
import { saveJobsNavIds } from "../lib/jobs-workspace";
import { ThemeProvider } from "../lib/theme";
import { createTestQueryClient } from "../test/render";
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
});
