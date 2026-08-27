import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState, type ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PrepareApplicationWorkspace } from "../components/PrepareApplicationWorkspace";
import { api, ApiClientError } from "../lib/api";
import { ThemeProvider } from "../lib/theme";
import type { ApplicationPackage } from "../lib/types";
import { ApplicationPage } from "../pages/ApplicationPage";
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

const GROUNDING_REFUSAL =
  "Application materials contained claims that are not supported by stored evidence.";

function pendingPackage(overrides: Partial<ApplicationPackage> = {}): ApplicationPackage {
  return {
    job_id: "job-1",
    tailored_bullets: ["Built APIs"],
    source_traceability_notes: ["Python is listed in the stored candidate skill evidence."],
    approval_status: "pending_review",
    eligibility_confirmed: false,
    ...overrides,
  };
}

function AppProviders({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={createTestQueryClient()}>
      <ThemeProvider>{children}</ThemeProvider>
    </QueryClientProvider>
  );
}

function renderPrepare(jobId = "job-1") {
  return render(
    <AppProviders>
      <MemoryRouter>
        <PrepareApplicationWorkspace jobId={jobId} />
      </MemoryRouter>
    </AppProviders>,
  );
}

describe("PrepareApplicationWorkspace", () => {
  beforeEach(() => {
    vi.mocked(api.getJob).mockImplementation(async (id: string) => ({
      id,
      title: "Engineer",
      company: "Acme",
      url: "https://example.com",
      description: "Python",
      source: "manual",
      status: "verified",
    }));
    vi.mocked(api.getStoredScore).mockRejectedValue(new ApiClientError(404, "No stored score"));
    vi.mocked(api.getStoredMaterials).mockReset();
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
    vi.mocked(api.getStoredMaterials).mockResolvedValue(pendingPackage());
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
    vi.mocked(api.getStoredMaterials).mockResolvedValue(pendingPackage());
    renderPrepare();
    expect(await screen.findByTestId("approval-status")).toHaveTextContent("pending review");
    const rail = screen.getByRole("button", { name: "Approve" }).closest("section");
    expect(rail).toHaveClass("sticky-action-rail");
    expect(getComputedStyle(rail as HTMLElement).position).toBe("sticky");
  });

  it("passes false for a normal generate", async () => {
    vi.mocked(api.getStoredMaterials).mockRejectedValue(new ApiClientError(404, "No stored materials"));
    const generated = pendingPackage();
    vi.mocked(api.generateMaterials).mockImplementation(async () => {
      vi.mocked(api.getStoredMaterials).mockResolvedValue(generated);
      return generated;
    });
    renderPrepare();
    await userEvent.click(await screen.findByTestId("generate-materials"));
    await waitFor(() => {
      expect(api.generateMaterials).toHaveBeenCalledWith("job-1", false);
    });
  });

  it("does not reveal the override after an unrelated 409", async () => {
    vi.mocked(api.getStoredMaterials).mockRejectedValue(new ApiClientError(404, "No stored materials"));
    vi.mocked(api.generateMaterials).mockRejectedValue(
      new ApiClientError(409, "A protected package already exists for this job"),
    );
    renderPrepare();
    await userEvent.click(await screen.findByTestId("generate-materials"));
    expect(await screen.findByRole("alert")).toHaveTextContent("A protected package already exists for this job");
    expect(screen.queryByTestId("generate-materials-override")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Generate anyway for this job" })).not.toBeInTheDocument();
  });

  it("shows the override only after the exact grounding refusal", async () => {
    vi.mocked(api.getStoredMaterials).mockRejectedValue(new ApiClientError(404, "No stored materials"));
    vi.mocked(api.generateMaterials).mockRejectedValue(new ApiClientError(409, GROUNDING_REFUSAL));
    renderPrepare();
    await userEvent.click(await screen.findByTestId("generate-materials"));
    expect(await screen.findByTestId("generate-materials-override")).toBeInTheDocument();
    expect(screen.getByText("Nothing was saved.", { exact: false })).toBeInTheDocument();
    expect(api.generateMaterials).toHaveBeenCalledWith("job-1", false);
  });

  it("passes true when generating anyway after a grounding refusal", async () => {
    vi.mocked(api.getStoredMaterials).mockRejectedValue(new ApiClientError(404, "No stored materials"));
    vi.mocked(api.generateMaterials).mockRejectedValueOnce(new ApiClientError(409, GROUNDING_REFUSAL));
    const overridden = pendingPackage({ grounding_override: true, unsupported_claims: ["led_team"] });
    vi.mocked(api.generateMaterials).mockImplementationOnce(async () => {
      vi.mocked(api.getStoredMaterials).mockResolvedValue(overridden);
      return overridden;
    });
    renderPrepare();
    await userEvent.click(await screen.findByTestId("generate-materials"));
    await userEvent.click(await screen.findByTestId("generate-materials-override"));
    await waitFor(() => {
      expect(api.generateMaterials).toHaveBeenLastCalledWith("job-1", true);
    });
  });

  it("clears the refusal after a successful generate", async () => {
    vi.mocked(api.getStoredMaterials).mockRejectedValue(new ApiClientError(404, "No stored materials"));
    vi.mocked(api.generateMaterials).mockRejectedValueOnce(new ApiClientError(409, GROUNDING_REFUSAL));
    const overridden = pendingPackage({ grounding_override: true });
    vi.mocked(api.generateMaterials).mockImplementationOnce(async () => {
      vi.mocked(api.getStoredMaterials).mockResolvedValue(overridden);
      return overridden;
    });
    renderPrepare();
    await userEvent.click(await screen.findByTestId("generate-materials"));
    expect(await screen.findByTestId("generate-materials-override")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("generate-materials-override"));
    await waitFor(() => {
      expect(screen.queryByTestId("generate-materials-override")).not.toBeInTheDocument();
    });
  });

  it("clears the refusal when the job id changes", async () => {
    vi.mocked(api.getStoredMaterials).mockRejectedValue(new ApiClientError(404, "No stored materials"));
    vi.mocked(api.generateMaterials).mockRejectedValue(new ApiClientError(409, GROUNDING_REFUSAL));

    function Harness() {
      const [jobId, setJobId] = useState("job-1");
      return (
        <>
          <button type="button" onClick={() => setJobId("job-2")}>
            Switch job
          </button>
          <PrepareApplicationWorkspace jobId={jobId} />
        </>
      );
    }

    render(
      <AppProviders>
        <MemoryRouter>
          <Harness />
        </MemoryRouter>
      </AppProviders>,
    );
    await userEvent.click(await screen.findByTestId("generate-materials"));
    expect(await screen.findByTestId("generate-materials-override")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Switch job" }));
    expect(await screen.findByTestId("prepare-application")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByTestId("generate-materials-override")).not.toBeInTheDocument();
    });
  });

  it("shows an unverified warning for overridden materials", async () => {
    vi.mocked(api.getStoredMaterials).mockResolvedValue(
      pendingPackage({ grounding_override: true, unsupported_claims: [] }),
    );
    renderPrepare();
    expect(await screen.findByText("Unverified materials")).toBeInTheDocument();
    expect(screen.getByText(/Unsupported claims require careful human review/)).toBeInTheDocument();
  });

  it("renders unsupported claims as text", async () => {
    vi.mocked(api.getStoredMaterials).mockResolvedValue(
      pendingPackage({
        grounding_override: true,
        unsupported_claims: ["led_team", "<img src=x onerror=alert(1)>"],
      }),
    );
    renderPrepare();
    expect(await screen.findByText("led team", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("<img src=x onerror=alert(1)>", { exact: false })).toBeInTheDocument();
    expect(document.querySelector("img[src='x']")).toBeNull();
  });

  it("legacy ApplicationPage redirects to /jobs when no job is selected", () => {
    render(
      <MemoryRouter initialEntries={["/applications"]}>
        <Routes>
          <Route path="/applications" element={<ApplicationPage />} />
          <Route path="/jobs" element={<p>Jobs list</p>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("Jobs list")).toBeInTheDocument();
  });

  it("legacy ApplicationPage renders the workspace when a job id is present", async () => {
    vi.mocked(api.getStoredMaterials).mockRejectedValue(new ApiClientError(404, "No stored materials"));
    render(
      <AppProviders>
        <MemoryRouter initialEntries={["/applications/job-1"]}>
          <Routes>
            <Route path="/applications/:jobId" element={<ApplicationPage />} />
          </Routes>
        </MemoryRouter>
      </AppProviders>,
    );
    expect(await screen.findByTestId("prepare-application")).toBeInTheDocument();
    expect(api.generateMaterials).not.toHaveBeenCalled();
  });
});
