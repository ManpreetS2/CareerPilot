import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { GrowthPage } from "./GrowthPage";
import { api, ApiClientError } from "../lib/api";
import { ThemeProvider } from "../lib/theme";
import { createTestQueryClient, testUser } from "../test/render";
import type { CareerGrowthSummary, SkillGrowthItem } from "../lib/types";
import "../index.css";

vi.mock("../lib/auth", () => ({
  useAuth: () => ({
    user: testUser,
    loading: false,
    login: vi.fn(),
    signup: vi.fn(),
    logout: vi.fn(),
    deleteAccount: vi.fn(),
  }),
}));

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      getCareerGrowth: vi.fn(),
    },
  };
});

const sqlGap: SkillGrowthItem = {
  canonical_key: "SQL",
  label: "SQL",
  jobs_count: 8,
  denominator: 10,
  required_count: 5,
  preferred_count: 3,
  satisfied_count: 0,
  partial_count: 0,
  unknown_count: 8,
  not_satisfied_count: 0,
  candidate_evidence_state: "unknown",
  candidate_evidence_count: 0,
  priority: "high",
  reason: "SQL appears in 8 of 10 analyzed jobs (5 required, 3 preferred). CareerPilot does not currently have evidence for SQL.",
  suggested_action: "If you already use SQL, add truthful evidence to your profile. Otherwise consider a small project demonstrating SQL.",
  related_jobs: [
    {
      job_id: "sql-1",
      title: "Data Intern",
      company: "Acme",
      importance: "required",
      evidence_state: "unknown",
      saved: true,
    },
  ],
};

const awsGap: SkillGrowthItem = {
  ...sqlGap,
  canonical_key: "AWS",
  label: "AWS",
  jobs_count: 4,
  required_count: 2,
  preferred_count: 2,
  unknown_count: 0,
  partial_count: 4,
  candidate_evidence_state: "partial",
  candidate_evidence_count: 4,
  priority: "medium",
  reason: "CareerPilot has some profile evidence for AWS, but not enough for full support.",
  suggested_action: "Strengthen your existing AWS evidence with a project, responsibility, or measurable outcome.",
  related_jobs: [
    {
      job_id: "aws-1",
      title: "Cloud Intern",
      company: "Northstar",
      importance: "required",
      evidence_state: "partial",
      saved: false,
    },
  ],
};

const pythonStrength: SkillGrowthItem = {
  canonical_key: "Python",
  label: "Python",
  jobs_count: 7,
  denominator: 10,
  required_count: 6,
  preferred_count: 1,
  satisfied_count: 7,
  partial_count: 0,
  unknown_count: 0,
  not_satisfied_count: 0,
  candidate_evidence_state: "satisfied",
  candidate_evidence_count: 7,
  priority: "low",
  reason: "Python appears in 7 of 10 analyzed jobs. CareerPilot has verified profile evidence for Python.",
  suggested_action: "Python is already supported by current profile evidence.",
  related_jobs: [
    {
      job_id: "py-1",
      title: "Backend Intern",
      company: "Acme",
      importance: "required",
      evidence_state: "satisfied",
      saved: true,
    },
  ],
};

const populated: CareerGrowthSummary = {
  jobs_considered: 11,
  jobs_with_current_evidence: 10,
  saved_jobs_considered: 6,
  matched_jobs_considered: 5,
  stale_jobs_excluded: 1,
  unavailable_jobs_excluded: 0,
  generated_at: "2026-09-02T00:00:00Z",
  skill_gaps: [sqlGap, awsGap],
  strengths: [pythonStrength],
  notice: null,
};

function renderGrowth(route = "/growth") {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <ThemeProvider>
        <MemoryRouter initialEntries={[route]}>
          <Routes>
            <Route path="/growth" element={<GrowthPage />} />
            <Route path="/profile" element={<p>Profile destination</p>} />
            <Route path="/jobs/:jobId" element={<p>Job detail destination</p>} />
            <Route path="/jobs" element={<p>Discover destination</p>} />
          </Routes>
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("GrowthPage", () => {
  beforeEach(() => {
    vi.mocked(api.getCareerGrowth).mockReset();
  });

  it("renders the Career Growth route heading", async () => {
    vi.mocked(api.getCareerGrowth).mockResolvedValue(populated);
    renderGrowth();
    expect(await screen.findByRole("heading", { name: "Career Growth" })).toBeInTheDocument();
    expect(await screen.findByText(/Based on 11 relevant jobs: 6 Saved \+ 5 Top Matches/)).toBeInTheDocument();
  });

  it("shows a profile-required empty state", async () => {
    vi.mocked(api.getCareerGrowth).mockRejectedValue(
      new ApiClientError(409, "Complete your profile", {
        code: "profile_required",
        next_route: "/profile",
        missing: ["candidate_profile"],
      }),
    );
    renderGrowth();
    expect(await screen.findByRole("heading", { name: "Complete your profile first" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to Profile" })).toHaveAttribute("href", "/profile");
    expect(screen.queryByText("You're perfect")).not.toBeInTheDocument();
  });

  it("shows a loading state while the summary is pending", async () => {
    vi.mocked(api.getCareerGrowth).mockReturnValue(new Promise(() => undefined));
    renderGrowth();
    expect(await screen.findByText("Loading career growth…")).toBeInTheDocument();
  });

  it("shows an API error with retry", async () => {
    vi.mocked(api.getCareerGrowth).mockRejectedValue(new ApiClientError(500, "growth failed"));
    renderGrowth();
    expect(await screen.findByText("growth failed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("shows discover-first empty state", async () => {
    vi.mocked(api.getCareerGrowth).mockResolvedValue({
      ...populated,
      jobs_considered: 0,
      jobs_with_current_evidence: 0,
      saved_jobs_considered: 0,
      matched_jobs_considered: 0,
      skill_gaps: [],
      strengths: [],
      notice: "Discover or save some jobs first.",
    });
    renderGrowth();
    expect(await screen.findByRole("heading", { name: "Discover or save some jobs first" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Discover" })).toHaveAttribute("href", "/jobs");
  });

  it("shows growth items, strengths, required/preferred counts, and honest wording", async () => {
    vi.mocked(api.getCareerGrowth).mockResolvedValue(populated);
    renderGrowth();
    expect(await screen.findByRole("heading", { name: "SQL" })).toBeInTheDocument();
    expect(screen.getByText("Appears in 8 / 10 analyzed jobs")).toBeInTheDocument();
    expect(screen.getByText("Required in 5 · Preferred in 3")).toBeInTheDocument();
    expect(screen.getByText("Your evidence: No verified profile evidence")).toBeInTheDocument();
    expect(screen.getByText(/If you already use SQL/)).toBeInTheDocument();
    expect(screen.queryByText(/You don't know SQL/)).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "AWS" })).toBeInTheDocument();
    expect(screen.getByText("Your evidence: Partial — strengthen evidence")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Strengths already working for you" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Python" })).toBeInTheDocument();
    expect(screen.getByText("Your evidence: Verified across profile evidence")).toBeInTheDocument();
  });

  it("links supporting jobs to Job Detail and Update profile to Profile", async () => {
    const user = userEvent.setup();
    vi.mocked(api.getCareerGrowth).mockResolvedValue(populated);
    renderGrowth();
    const sqlHeading = await screen.findByRole("heading", { name: "SQL" });
    const sqlCard = sqlHeading.closest("li") as HTMLElement;
    const viewJobs = within(sqlCard).getByRole("button", { name: "View jobs" });
    expect(viewJobs).toHaveAttribute("aria-expanded", "false");
    await user.click(viewJobs);
    expect(viewJobs).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("link", { name: /Data Intern/ })).toHaveAttribute("href", "/jobs/sql-1");
    await user.click(within(sqlCard).getByRole("link", { name: "Update profile" }));
    expect(await screen.findByText("Profile destination")).toBeInTheDocument();
  });

  it("expands jobs from the keyboard", async () => {
    const user = userEvent.setup();
    vi.mocked(api.getCareerGrowth).mockResolvedValue(populated);
    renderGrowth();
    const sqlHeading = await screen.findByRole("heading", { name: "SQL" });
    const sqlCard = sqlHeading.closest("li") as HTMLElement;
    const viewJobs = within(sqlCard).getByRole("button", { name: "View jobs" });
    viewJobs.focus();
    await user.keyboard("{Enter}");
    expect(viewJobs).toHaveAttribute("aria-expanded", "true");
  });

  it("filters high priority and unknown evidence", async () => {
    const user = userEvent.setup();
    vi.mocked(api.getCareerGrowth).mockResolvedValue(populated);
    renderGrowth();
    await screen.findByRole("heading", { name: "SQL" });
    await user.click(screen.getByRole("button", { name: "High priority" }));
    expect(screen.getByRole("heading", { name: "SQL" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "AWS" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Partial evidence" }));
    expect(screen.getByRole("heading", { name: "AWS" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "SQL" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "No verified evidence" }));
    expect(screen.getByRole("heading", { name: "SQL" })).toBeInTheDocument();
  });

  it("uses dark and light tokens without cyan or beige", async () => {
    vi.mocked(api.getCareerGrowth).mockResolvedValue(populated);
    renderGrowth();
    await screen.findByRole("heading", { name: "Career Growth" });
    const page = screen.getByTestId("growth-page");
    expect(page.className).not.toMatch(/cyan|beige/);
    document.documentElement.classList.add("dark");
    expect(getComputedStyle(page).color).not.toBe("rgb(0, 255, 255)");
    document.documentElement.classList.remove("dark");
  });

  it("stacks on a 390px-wide surface without a giant table", async () => {
    vi.mocked(api.getCareerGrowth).mockResolvedValue(populated);
    const { container } = renderGrowth();
    await screen.findByTestId("growth-summary");
    const page = screen.getByTestId("growth-page");
    expect(page).toHaveClass("max-w-full");
    expect(container.querySelector("table")).toBeNull();
    expect(page.className).toMatch(/space-y-6/);
  });
});
