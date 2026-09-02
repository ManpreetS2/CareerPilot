import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DashboardPage } from "./DashboardPage";
import { api } from "../lib/api";
import { ThemeProvider } from "../lib/theme";
import { createTestQueryClient, testUser } from "../test/render";
import type { CandidateProfile, CurrentProfile } from "../lib/types";

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
      getProfile: vi.fn(),
      getJobs: vi.fn(),
      getStoredScores: vi.fn(),
      listAllResumeVersions: vi.fn(),
      getDashboardSummary: vi.fn(),
    },
  };
});

const candidate: CandidateProfile = {
  name: "Ada Lovelace",
  skills: ["Python"],
  projects: [],
  experience: [],
  education: [],
  certifications: [],
  strengths: [],
  evidence_links: [],
};

const incompleteProfile: CurrentProfile = {
  candidate: null,
  preferences: null,
  readiness: {
    ready: false,
    code: "profile_required",
    missing: ["candidate_profile", "candidate_evidence", "target_roles"],
    next_route: "/profile",
  },
};

const completeProfile: CurrentProfile = {
  candidate,
  preferences: { target_roles: ["Software Engineer"], preferred_locations: [], constraints: [] },
  readiness: { ready: true, missing: [], code: null, next_route: null },
};

function renderDashboard() {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <ThemeProvider>
        <MemoryRouter>
          <DashboardPage />
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("DashboardPage profile-first CTA", () => {
  beforeEach(() => {
    vi.mocked(api.getJobs).mockResolvedValue([]);
    vi.mocked(api.getStoredScores).mockResolvedValue([]);
    vi.mocked(api.listAllResumeVersions).mockResolvedValue([]);
    vi.mocked(api.getDashboardSummary).mockResolvedValue({
      profile_completion: 0,
      skills_count: 0,
      target_roles: [],
      jobs_discovered: 0,
      jobs_verified: 0,
      high_matches: 0,
      ready_to_apply: 0,
      applications_saved: 0,
      applications_ready: 0,
      applications_applied: 0,
      interviews: 0,
    });
  });

  it("uses Complete your profile as the primary action when readiness fails", async () => {
    vi.mocked(api.getProfile).mockResolvedValue(incompleteProfile);
    renderDashboard();
    expect(await screen.findByTestId("dashboard-next-action")).toHaveTextContent("Complete your profile");
    expect(screen.getByRole("heading", { name: "Complete your profile" })).toBeInTheDocument();
    expect(screen.getByTestId("dashboard-matches-gate")).toHaveTextContent("Complete your profile to see matches.");
  });

  it("does not treat a pending profile as missing or ready", async () => {
    vi.mocked(api.getProfile).mockImplementation(() => new Promise(() => undefined));
    renderDashboard();
    expect(screen.queryByTestId("dashboard-next-action")).not.toBeInTheDocument();
    expect(screen.queryByTestId("dashboard-profile-error")).not.toBeInTheDocument();
    expect(screen.queryByTestId("dashboard-matches-gate")).not.toBeInTheDocument();
  });

  it("does not treat a profile load failure as missing or ready", async () => {
    vi.mocked(api.getProfile).mockRejectedValue(new Error("profile down"));
    renderDashboard();
    expect(await screen.findByTestId("dashboard-profile-error")).toHaveTextContent("Couldn't load your profile");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.queryByTestId("dashboard-next-action")).not.toBeInTheDocument();
  });

  it("unlocks Find jobs after the profile becomes ready", async () => {
    vi.mocked(api.getProfile).mockResolvedValue(completeProfile);
    renderDashboard();
    expect(await screen.findByTestId("dashboard-next-action")).toHaveTextContent("Open jobs");
  });
});
