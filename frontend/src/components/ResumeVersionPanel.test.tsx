import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ResumeVersionPanel } from "./ResumeVersionPanel";
import { api, ApiClientError } from "../lib/api";
import { createTestQueryClient } from "../test/render";
import type { ApplicationPackage, ResumeVersion } from "../lib/types";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      listResumeVersions: vi.fn(),
      createResumeVersion: vi.fn(),
      downloadResumeVersion: vi.fn(),
    },
  };
});

const approvedMaterials: ApplicationPackage = {
  job_id: "greenhouse-abc",
  tailored_bullets: ["Shipped a feature"],
  source_traceability_notes: ["note"],
  approval_status: "approved",
  eligibility_confirmed: true,
};

const oneVersion: ResumeVersion[] = [
  {
    id: "rv-1",
    job_id: "greenhouse-abc",
    version_number: 1,
    tailored_bullets: ["Shipped a feature"],
    source_traceability_notes: ["note"],
    created_at: "2026-08-28T00:00:00Z",
  },
];

function renderPanel() {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <ResumeVersionPanel jobId="greenhouse-abc" materials={approvedMaterials} />
    </QueryClientProvider>,
  );
}

describe("ResumeVersionPanel — export", () => {
  it("downloads a version in the requested format", async () => {
    vi.mocked(api.listResumeVersions).mockResolvedValue(oneVersion);
    vi.mocked(api.downloadResumeVersion).mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderPanel();

    await screen.findByTestId("resume-version-1");
    await user.click(screen.getByTestId("download-resume-1-pdf"));

    await waitFor(() => expect(api.downloadResumeVersion).toHaveBeenCalledWith("rv-1", "pdf"));
  });

  it("surfaces a download failure without losing the version list", async () => {
    vi.mocked(api.listResumeVersions).mockResolvedValue(oneVersion);
    vi.mocked(api.downloadResumeVersion).mockRejectedValue(
      new ApiClientError(500, "Unable to export resume."),
    );
    const user = userEvent.setup();
    renderPanel();

    await screen.findByTestId("resume-version-1");
    await user.click(screen.getByTestId("download-resume-1-docx"));

    expect(await screen.findByText("Unable to export resume.")).toBeInTheDocument();
    expect(screen.getByTestId("resume-version-1")).toBeInTheDocument();
  });

  it("disables the other download buttons while one is in flight", async () => {
    vi.mocked(api.listResumeVersions).mockResolvedValue(oneVersion);
    let resolveDownload: () => void = () => {};
    vi.mocked(api.downloadResumeVersion).mockReturnValue(
      new Promise((resolve) => {
        resolveDownload = () => resolve(undefined);
      }),
    );
    const user = userEvent.setup();
    renderPanel();

    await screen.findByTestId("resume-version-1");
    await user.click(screen.getByTestId("download-resume-1-pdf"));

    expect(screen.getByTestId("download-resume-1-docx")).toBeDisabled();

    resolveDownload();
    await waitFor(() => expect(screen.getByTestId("download-resume-1-docx")).not.toBeDisabled());
  });
});
