import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { AuthProvider } from "../lib/auth";
import { api, ApiClientError } from "../lib/api";
import { ThemeProvider } from "../lib/theme";
import { createTestQueryClient } from "../test/render";

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
    },
  };
});

function renderLanding() {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <ThemeProvider>
        <MemoryRouter initialEntries={["/"]}>
          <AuthProvider>
            <App />
          </AuthProvider>
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("landing page", () => {
  beforeEach(() => {
    vi.mocked(api.me).mockRejectedValue(new ApiClientError(401, "Not authenticated"));
  });

  it("routes Sign In, Get Started, and Privacy without globe or lattice visuals", async () => {
    renderLanding();
    expect(await screen.findByRole("heading", { name: /Find better roles with/i })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Sign In" }).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "Get Started" })).toHaveAttribute("href", "/signup");
    expect(screen.getByRole("link", { name: "Privacy" })).toHaveAttribute("href", "/privacy");
    expect(screen.getAllByRole("link", { name: /Get Started Free/i }).length).toBeGreaterThan(0);
    expect(screen.queryByTestId("dotted-globe")).not.toBeInTheDocument();
    expect(screen.queryByTestId("signal-lattice")).not.toBeInTheDocument();
    expect(screen.getAllByText("Grounded job search. Human-approved applications.").length).toBeGreaterThan(0);
    expect(screen.getByText("CareerPilot", { selector: "h1 span" })).toHaveClass("whitespace-nowrap");
  });
});
