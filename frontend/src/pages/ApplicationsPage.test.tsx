import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApplicationsPage } from "./ApplicationsPage";
import { api } from "../lib/api";
import { ThemeProvider } from "../lib/theme";
import { createTestQueryClient, testUser } from "../test/render";
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
      listApplications: vi.fn(),
      updateTracking: vi.fn(),
    },
  };
});

function renderTracker() {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <ThemeProvider>
        <MemoryRouter>
          <ApplicationsPage />
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("ApplicationsPage", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(api.listApplications).mockResolvedValue([
      {
        job_id: "job-1",
        title: "Senior Distributed Systems Platform Engineer With An Extra Long Title",
        company: "Very-Long-Company-Name-International",
        tracker_status: "saved",
        updated_at: "2026-08-01T00:00:00Z",
        allowed_statuses: ["saved", "applied"],
      },
    ]);
  });

  it("keeps the kanban board inside the page with internal horizontal scroll", async () => {
    const user = userEvent.setup();
    renderTracker();
    const title = await screen.findByText(/Extra Long Title/i);
    expect(title).toHaveClass("wrap-anywhere");
    await user.click(screen.getByRole("button", { name: /Kanban/i }));
    const board = await screen.findByTestId("tracker-kanban");
    const style = getComputedStyle(board);
    expect(style.display).toBe("flex");
    expect(style.maxWidth).toBe("100%");
    expect(style.overflowX).toBe("auto");
    expect(localStorage.getItem("careerpilot.tracker-view.u1")).toBe("kanban");
    expect(screen.getByText(/Extra Long Title/i)).toHaveClass("wrap-anywhere");
  });
});
