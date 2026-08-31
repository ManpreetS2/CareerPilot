import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { AuthProvider } from "./auth";
import { api, ApiClientError } from "./api";
import { createQueryClient } from "./query-client";
import { ThemeProvider } from "./theme";
import type { Job, JobListPage, ResumeVersionSummary, User } from "./types";

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      me: vi.fn(),
      login: vi.fn(),
      signup: vi.fn(),
      logout: vi.fn(),
      getProfile: vi.fn(),
      getJobs: vi.fn(),
      queryJobs: vi.fn(),
      getStoredScores: vi.fn(),
      listAllResumeVersions: vi.fn(),
      getResumeVersionDetail: vi.fn(),
      getDashboardSummary: vi.fn(),
    },
  };
});

const PASSWORD = "SyntheticPass123!";

const userA: User = { id: 11, email: "alice-cache@example.com", created_at: "2026-01-01T00:00:00Z" };
const userB: User = { id: 22, email: "bob-cache@example.com", created_at: "2026-01-02T00:00:00Z" };

const aJob: Job = {
  id: "job-alice-private",
  title: "A-Only Saved Fintech Internship",
  company: "Alice Corp",
  url: "https://example.com/jobs/alice",
  description: "Alice private role.",
  source: "manual",
  status: "discovered",
  saved: true,
};

const bJob: Job = {
  id: "job-bob-private",
  title: "B-Only Backend Role",
  company: "Bob Labs",
  url: "https://example.com/jobs/bob",
  description: "Bob private role.",
  source: "manual",
  status: "discovered",
  saved: true,
};

const aResume: ResumeVersionSummary = {
  id: "rv-alice",
  job_id: "job-alice-private",
  job_title: "A-Only Saved Fintech Internship",
  company: "A-Only Resume Labs",
  version_number: 1,
  created_at: "2026-01-02T00:00:00Z",
  bullet_count: 1,
  provenance_status: "approved_snapshot",
  matches_current_profile: true,
};

const bResume: ResumeVersionSummary = {
  id: "rv-bob",
  job_id: "job-bob-private",
  job_title: "B-Only Backend Role",
  company: "B-Only Resume Shop",
  version_number: 1,
  created_at: "2026-01-03T00:00:00Z",
  bullet_count: 1,
  provenance_status: "approved_snapshot",
  matches_current_profile: true,
};

function pageOf(jobs: Job[]): JobListPage {
  return {
    items: jobs.map((job) => ({
      job,
      match: job.id === aJob.id
        ? {
            job_id: job.id!,
            overall_score: 97,
            matched_skills: ["Python"],
            partial_matches: [],
            missing_skills: [],
            recommendation: "apply",
            rationale: "Alice private score",
            score_kind: "verified",
          }
        : null,
      saved: Boolean(job.saved),
    })),
    total: jobs.length,
    page: 1,
    page_size: 40,
    verified_count: jobs.some((job) => job.id === aJob.id) ? 1 : 0,
    potential_count: jobs.filter((job) => job.id !== aJob.id).length,
    ids: jobs.map((job) => job.id!).filter(Boolean),
  };
}

const emptySummary = {
  profile_completion: 0,
  skills_count: 0,
  target_roles: [] as string[],
  jobs_discovered: 0,
  jobs_verified: 0,
  high_matches: 0,
  ready_to_apply: 0,
  applications_saved: 0,
  applications_ready: 0,
  applications_applied: 0,
  interviews: 0,
};

function renderApp(route: string) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <ThemeProvider>
        <MemoryRouter initialEntries={[route]}>
          <AuthProvider>
            <App />
          </AuthProvider>
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("authenticated query cache isolation", () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    vi.mocked(api.me).mockRejectedValue(new ApiClientError(401, "Not authenticated"));
    vi.mocked(api.logout).mockResolvedValue(undefined);
    vi.mocked(api.getDashboardSummary).mockResolvedValue(emptySummary);
    vi.mocked(api.getJobs).mockResolvedValue([]);
    vi.mocked(api.getStoredScores).mockResolvedValue([]);
    vi.mocked(api.getResumeVersionDetail).mockImplementation(async (id: string) => {
      if (id === aResume.id) {
        return {
          ...aResume,
          tailored_bullets: ["Alice private bullet"],
          source_traceability_notes: [],
          profile: { name: "Alice-Only-Cache", skills: ["Python"], experience: [], projects: [], education: [], certifications: [] },
        };
      }
      return {
        ...bResume,
        tailored_bullets: ["Bob private bullet"],
        source_traceability_notes: [],
        profile: { name: "Bob-Only-Cache", skills: ["Go"], experience: [], projects: [], education: [], certifications: [] },
      };
    });
  });

  it("does not render User A's jobs, scores, or resume versions after User B logs in", async () => {
    vi.mocked(api.me).mockResolvedValue(userA);
    vi.mocked(api.getProfile).mockResolvedValue({
      candidate: {
        name: "Alice-Only-Cache",
        skills: ["Python"],
        projects: [],
        experience: [],
        education: [],
        certifications: [],
        strengths: [],
        evidence_links: [],
      },
      preferences: null,
    });
    vi.mocked(api.queryJobs).mockResolvedValue(pageOf([aJob]));
    vi.mocked(api.getJobs).mockResolvedValue([aJob]);
    vi.mocked(api.listAllResumeVersions).mockResolvedValue([aResume]);
    vi.mocked(api.getStoredScores).mockResolvedValue([
      {
        job_id: aJob.id!,
        overall_score: 97,
        matched_skills: ["Python"],
        partial_matches: [],
        missing_skills: [],
        recommendation: "apply",
        rationale: "Alice private score",
        score_kind: "verified",
      },
    ]);

    const user = userEvent.setup();
    renderApp("/resume");
    expect((await screen.findAllByText(/A-Only Resume Labs/)).length).toBeGreaterThan(0);

    await user.click(screen.getAllByRole("link", { name: "Jobs" })[0]!);
    await user.click(await screen.findByRole("tab", { name: "Saved" }));
    expect(await screen.findByText("A-Only Saved Fintech Internship")).toBeInTheDocument();
    expect(screen.getByText(/97% Verified Fit/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Log out" }));
    expect(await screen.findByRole("heading", { name: "Log in" })).toBeInTheDocument();

    let releaseBNetwork: (() => void) | undefined;
    const bNetwork = new Promise<void>((resolve) => {
      releaseBNetwork = resolve;
    });
    vi.mocked(api.login).mockResolvedValue(userB);
    vi.mocked(api.getProfile).mockResolvedValue({
      candidate: {
        name: "Bob-Only-Cache",
        skills: ["Go"],
        projects: [],
        experience: [],
        education: [],
        certifications: [],
        strengths: [],
        evidence_links: [],
      },
      preferences: null,
    });
    vi.mocked(api.queryJobs).mockImplementation(async () => {
      await bNetwork;
      return pageOf([bJob]);
    });
    vi.mocked(api.getJobs).mockImplementation(
      () =>
        new Promise(() => {
          /* hang so B cannot replace Jobs cache via network */
        }),
    );
    vi.mocked(api.listAllResumeVersions).mockImplementation(async () => {
      await bNetwork;
      return [bResume];
    });
    vi.mocked(api.getStoredScores).mockImplementation(
      () =>
        new Promise(() => {
          /* hang */
        }),
    );

    await user.type(screen.getByLabelText("Email"), userB.email);
    await user.type(screen.getByLabelText("Password"), PASSWORD);
    await user.click(screen.getByRole("button", { name: "Log in" }));

    await waitFor(() => {
      expect(screen.queryByText("Alice-Only-Cache")).not.toBeInTheDocument();
      expect(screen.queryByText("A-Only Saved Fintech Internship")).not.toBeInTheDocument();
      expect(screen.queryAllByText(/A-Only Resume Labs/)).toHaveLength(0);
      expect(screen.queryByText(/97% Verified Fit/)).not.toBeInTheDocument();
    });

    await user.click(screen.getAllByRole("link", { name: "Jobs" })[0]!);
    await user.click(await screen.findByRole("tab", { name: "Saved" }));
    expect(screen.queryByText("A-Only Saved Fintech Internship")).not.toBeInTheDocument();
    expect(screen.queryByText(/97% Verified Fit/)).not.toBeInTheDocument();

    await user.click(screen.getAllByRole("link", { name: "Resume" })[0]!);
    expect(screen.queryAllByText(/A-Only Resume Labs/)).toHaveLength(0);

    releaseBNetwork?.();
    expect((await screen.findAllByText(/B-Only Resume Shop/)).length).toBeGreaterThan(0);
    expect(screen.queryAllByText(/A-Only Resume Labs/)).toHaveLength(0);

    await user.click(screen.getAllByRole("link", { name: "Jobs" })[0]!);
    await user.click(await screen.findByRole("tab", { name: "Saved" }));
    expect(await screen.findByText("B-Only Backend Role")).toBeInTheDocument();
    expect(screen.queryByText("A-Only Saved Fintech Internship")).not.toBeInTheDocument();
  });
});
