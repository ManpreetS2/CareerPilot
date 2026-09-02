import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { AuthProvider } from "../lib/auth";
import { api, ApiClientError } from "../lib/api";
import { ThemeProvider } from "../lib/theme";
import { createTestQueryClient, testUser } from "../test/render";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      me: vi.fn(),
      login: vi.fn(),
      signup: vi.fn(),
      logout: vi.fn(),
      deleteAccount: vi.fn(),
      getProfile: vi.fn(),
      getJobs: vi.fn(),
      getStoredScores: vi.fn(),
      listAllResumeVersions: vi.fn(),
      getDashboardSummary: vi.fn(),
    },
  };
});

const SECRET_PASSWORD = "SyntheticPass123!";

function renderApp(route: string) {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
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

describe("auth pages", () => {
  beforeEach(() => {
    vi.mocked(api.me).mockRejectedValue(new ApiClientError(401, "Not authenticated"));
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
    vi.mocked(api.login).mockReset();
    vi.mocked(api.signup).mockReset();
    vi.mocked(api.logout).mockReset();
  });

  it("sends signup to onboarding then into the dashboard", async () => {
    vi.mocked(api.signup).mockResolvedValue(testUser);
    renderApp("/signup");
    await userEvent.type(screen.getByLabelText("Email"), testUser.email);
    await userEvent.type(document.querySelector("input[type='password']") as HTMLInputElement, SECRET_PASSWORD);
    await userEvent.click(screen.getByRole("button", { name: "Sign up" }));
    expect(await screen.findByTestId("onboarding-step-1")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("onboarding-skip"));
    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
  });

  it("returns to login after logout and can sign back in to the dashboard", async () => {
    vi.mocked(api.me).mockResolvedValue(testUser);
    vi.mocked(api.logout).mockResolvedValue(undefined);
    vi.mocked(api.login).mockResolvedValue(testUser);
    renderApp("/dashboard");
    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Log out" }));
    expect(await screen.findByRole("heading", { name: "Log in" })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Email"), testUser.email);
    await userEvent.type(screen.getByLabelText("Password"), SECRET_PASSWORD);
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
  });

  it("keeps the session after a reload when /api/auth/me succeeds", async () => {
    vi.mocked(api.me).mockResolvedValue(testUser);
    renderApp("/dashboard");
    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Log in" })).not.toBeInTheDocument();
    expect(api.login).not.toHaveBeenCalled();
  });

  it("does not render a cursor-following pointer halo on login or dashboard", async () => {
    renderApp("/login");
    expect(await screen.findByRole("heading", { name: "Log in" })).toBeInTheDocument();
    expect(screen.queryByTestId("pointer-halo")).not.toBeInTheDocument();
    expect(document.querySelector(".pointer-halo")).toBeNull();
  });

  it("keeps invalid credentials on /login with the sanitized backend message", async () => {
    vi.mocked(api.login).mockRejectedValue(new ApiClientError(401, "Invalid email or password."));
    renderApp("/login");
    await userEvent.type(screen.getByLabelText("Email"), testUser.email);
    await userEvent.type(screen.getByLabelText("Password"), SECRET_PASSWORD);
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Couldn't sign in");
    expect(alert).toHaveTextContent("Invalid email or password.");
    expect(alert).not.toHaveTextContent(SECRET_PASSWORD);
    expect(alert).not.toHaveTextContent("careerpilot_session");
    expect(screen.getByRole("heading", { name: "Log in" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Overview" })).not.toBeInTheDocument();
  });

  it("never puts submitted passwords or session values into a login error", async () => {
    vi.mocked(api.login).mockRejectedValue(
      new ApiClientError(401, "Invalid email or password.", { cookie: "careerpilot_session=abc" }),
    );
    renderApp("/login");
    await userEvent.type(screen.getByLabelText("Email"), testUser.email);
    await userEvent.type(screen.getByLabelText("Password"), SECRET_PASSWORD);
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    const alert = screen.getByRole("alert");
    expect(alert.textContent).not.toContain(SECRET_PASSWORD);
    expect(alert.textContent).not.toContain("careerpilot_session=abc");
    expect(document.body.textContent).not.toContain("careerpilot_session=abc");
  });

  it("opens /privacy without requiring a session", async () => {
    renderApp("/privacy");
    expect(await screen.findByRole("heading", { name: "Privacy" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Log in" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Overview" })).not.toBeInTheDocument();
  });
});
