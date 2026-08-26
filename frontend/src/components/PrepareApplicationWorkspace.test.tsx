import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PrepareApplicationWorkspace } from "../components/PrepareApplicationWorkspace";
import { api, ApiClientError } from "../lib/api";
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
      getStoredScore: vi.fn(),
      getStoredMaterials: vi.fn(),
      generateMaterials: vi.fn(),
      scoreJob: vi.fn(),
      discardStaleMaterials: vi.fn(),
      approveApplication: vi.fn(),
      fillApplication: vi.fn(),
      listResumeVersions: vi.fn(async () => []),
      createResumeVersion: vi.fn(),
    },
  };
});

function renderPrepare() {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <ThemeProvider>
        <MemoryRouter>
          <PrepareApplicationWorkspace jobId="job-1" />
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("PrepareApplicationWorkspace", () => {
  beforeEach(() => {
    vi.mocked(api.getJob).mockResolvedValue({
      id: "job-1",
      title: "Engineer",
      company: "Acme",
      url: "https://example.com",
      description: "Python",
      source: "manual",
      status: "verified",
    });
    vi.mocked(api.getStoredScore).mockRejectedValue(new ApiClientError(404, "No stored score"));
    vi.mocked(api.generateMaterials).mockReset();
    vi.mocked(api.scoreJob).mockReset();
  });

  it("does not generate materials on page open", async () => {
    vi.mocked(api.getStoredMaterials).mockRejectedValue(new ApiClientError(404, "No stored materials"));
    renderPrepare();
    expect(await screen.findByTestId("prepare-application")).toBeInTheDocument();
    expect(api.generateMaterials).not.toHaveBeenCalled();
    expect(api.scoreJob).not.toHaveBeenCalled();
  });

  it("keeps Approve disabled until eligibility is confirmed", async () => {
    vi.mocked(api.getStoredMaterials).mockResolvedValue({
      job_id: "job-1",
      tailored_bullets: ["Built APIs"],
      source_traceability_notes: ["Python is listed in the stored candidate skill evidence."],
      approval_status: "pending_review",
      eligibility_confirmed: false,
    });
    renderPrepare();
    const approve = await screen.findByRole("button", { name: "Approve" });
    expect(approve).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox"));
    expect(approve).toBeEnabled();
  });

  it("explains stale reviewed materials and requires discard before regenerate", async () => {
    vi.mocked(api.getStoredMaterials).mockRejectedValue(
      new ApiClientError(409, "Reviewed materials belong to a previous candidate and were not replaced"),
    );
    renderPrepare();
    expect(await screen.findByTestId("discard-stale-materials")).toBeInTheDocument();
    expect(screen.queryByTestId("generate-materials")).not.toBeInTheDocument();
    expect(api.generateMaterials).not.toHaveBeenCalled();
  });

  it("keeps the approval rail sticky so actions stay reachable", async () => {
    vi.mocked(api.getStoredMaterials).mockResolvedValue({
      job_id: "job-1",
      tailored_bullets: ["Built APIs"],
      source_traceability_notes: ["Python is listed in the stored candidate skill evidence."],
      approval_status: "pending_review",
      eligibility_confirmed: false,
    });
    renderPrepare();
    expect(await screen.findByTestId("approval-status")).toHaveTextContent("pending review");
    const rail = screen.getByRole("button", { name: "Approve" }).closest("section");
    expect(rail).toHaveClass("sticky-action-rail");
    expect(getComputedStyle(rail as HTMLElement).position).toBe("sticky");
  });
});
