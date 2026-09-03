import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProfilePage } from "./ProfilePage";
import { api, ApiClientError } from "../lib/api";
import { ThemeProvider } from "../lib/theme";
import { createTestQueryClient, testUser } from "../test/render";

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
      getProfile: vi.fn().mockResolvedValue({
        candidate: null,
        preferences: null,
        readiness: {
          ready: false,
          code: "profile_required",
          missing: ["candidate_profile", "candidate_evidence", "target_roles"],
          next_route: "/profile",
        },
      }),
      parseResume: vi.fn(),
      savePreferences: vi.fn(),
    },
  };
});

const parsedResume = {
  candidate: {
    id: "cand-001",
    name: "Alex Rivera",
    skills: ["Python"],
    projects: [],
    experience: [],
    education: [],
    certifications: [],
    strengths: [],
    evidence_links: [],
  },
  preferences: null,
  note: "Grounded",
};

function renderProfile() {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <ThemeProvider>
        <MemoryRouter>
          <ProfilePage />
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("ProfilePage resume parsing", () => {
  beforeEach(() => {
    vi.mocked(api.parseResume).mockReset();
    vi.mocked(api.getProfile).mockResolvedValue({
      candidate: null,
      preferences: null,
      readiness: {
        ready: false,
        code: "profile_required",
        missing: ["candidate_profile", "candidate_evidence", "target_roles"],
        next_route: "/profile",
      },
    });
  });
  it("uses the shared parsing progress while parseResume is unresolved", async () => {
    const user = userEvent.setup();
    let resolveParse: (value: typeof parsedResume) => void = () => {};
    vi.mocked(api.parseResume).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveParse = resolve;
        }),
    );
    renderProfile();
    const file = new File(["%PDF-1.4 test"], "resume.pdf", { type: "application/pdf" });
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, file);
    await user.click(screen.getByRole("button", { name: /Upload \/ Replace Resume/i }));
    expect(await screen.findByTestId("resume-parsing-progress")).toBeInTheDocument();
    expect(screen.getByText("Identifying skills & strengths")).toBeInTheDocument();
    expect(screen.getByTestId("resume-parse-stage-4")).not.toHaveAttribute("data-state", "complete");
    resolveParse(parsedResume);
    expect(await screen.findByText("Alex Rivera")).toBeInTheDocument();
    expect(screen.queryByTestId("resume-parsing-progress")).not.toBeInTheDocument();
  });

  it("shows a useful error and Retry after a failed parse", async () => {
    const user = userEvent.setup();
    vi.mocked(api.parseResume)
      .mockRejectedValueOnce(new ApiClientError(504, "Resume analysis timed out. Please try again."))
      .mockResolvedValueOnce(parsedResume);
    renderProfile();
    const file = new File(["%PDF-1.4 test"], "resume.pdf", { type: "application/pdf" });
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, file);
    await user.click(screen.getByRole("button", { name: /Upload \/ Replace Resume/i }));
    expect(await screen.findByText("Resume analysis timed out")).toBeInTheDocument();
    expect(screen.queryByTestId("resume-parsing-progress")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Alex Rivera")).toBeInTheDocument();
    expect(api.parseResume).toHaveBeenCalledTimes(2);
  });
});

describe("ProfilePage readiness visualization", () => {
  beforeEach(() => {
    vi.mocked(api.getProfile).mockReset();
  });

  it("shows Identity, Grounded evidence, and Target role as Open for an empty profile", async () => {
    vi.mocked(api.getProfile).mockResolvedValue({
      candidate: null,
      preferences: null,
      readiness: {
        ready: false,
        code: "profile_required",
        missing: ["candidate_profile", "candidate_evidence", "target_roles"],
        next_route: "/profile",
      },
    });
    renderProfile();
    await waitFor(() => {
      expect(screen.getByTestId("readiness-required-identity")).toHaveTextContent("Open");
      expect(screen.getByTestId("readiness-required-grounded_evidence")).toHaveTextContent("Open");
      expect(screen.getByTestId("readiness-required-target_role")).toHaveTextContent("Open");
    });
    expect(await screen.findByText(/No profile yet/)).toBeInTheDocument();
    expect(screen.getByText(/Add at least one skill, education item, experience item, or project/)).toBeInTheDocument();
    expect(screen.queryByTestId("readiness-required-experience")).not.toBeInTheDocument();
    expect(screen.queryByTestId("readiness-required-projects")).not.toBeInTheDocument();
  });

  it("marks the three required gates Ready when name, a skill, and a target role exist without experience or projects", async () => {
    vi.mocked(api.getProfile).mockResolvedValue({
      candidate: {
        name: "QA Test User",
        skills: ["Python"],
        education: [],
        experience: [],
        projects: [],
        certifications: [],
        strengths: [],
        evidence_links: [],
      },
      preferences: { target_roles: ["Software Engineer"], preferred_locations: [], constraints: [] },
      readiness: { ready: true, missing: [], code: null, next_route: null },
    });
    renderProfile();
    await waitFor(() => {
      expect(screen.getByTestId("readiness-required-identity")).toHaveTextContent("Ready");
      expect(screen.getByTestId("readiness-required-grounded_evidence")).toHaveTextContent("Ready");
      expect(screen.getByTestId("readiness-required-target_role")).toHaveTextContent("Ready");
    });
    expect(screen.getByTestId("readiness-source-skills")).toHaveTextContent("Present");
    expect(screen.getByTestId("readiness-source-education")).toHaveTextContent("None");
    expect(screen.getByTestId("readiness-source-experience")).toHaveTextContent("None");
    expect(screen.getByTestId("readiness-source-projects")).toHaveTextContent("None");
    expect(screen.getByText("Evidence sources — not individually required")).toBeInTheDocument();
  });

  it("keeps Identity and Grounded evidence Open when only a target role is saved", async () => {
    vi.mocked(api.getProfile).mockResolvedValue({
      candidate: null,
      preferences: { target_roles: ["Software Engineer"], preferred_locations: [], constraints: [] },
      readiness: {
        ready: false,
        code: "profile_required",
        missing: ["candidate_profile", "candidate_evidence"],
        next_route: "/profile",
      },
    });
    renderProfile();
    await waitFor(() => {
      expect(screen.getByTestId("readiness-required-identity")).toHaveTextContent("Open");
      expect(screen.getByTestId("readiness-required-grounded_evidence")).toHaveTextContent("Open");
      expect(screen.getByTestId("readiness-required-target_role")).toHaveTextContent("Ready");
    });
  });
});
