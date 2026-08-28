import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ResumeVersionPanel } from "./ResumeVersionPanel";
import { api, resumeVersionFileUrl } from "../lib/api";
import { renderWithApp } from "../test/render";
import type { ApplicationPackage, ResumeVersion } from "../lib/types";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      listResumeVersions: vi.fn(),
      createResumeVersion: vi.fn(),
    },
  };
});

const VERSION: ResumeVersion = {
  id: "rv-owned-1",
  job_id: "job-1",
  version_number: 1,
  tailored_bullets: ["Built APIs in Python."],
  source_traceability_notes: ["Python is listed in stored skills."],
  created_at: "2026-08-01T12:00:00Z",
};

function approvedPackage(): ApplicationPackage {
  return {
    job_id: "job-1",
    tailored_bullets: ["Built APIs in Python."],
    source_traceability_notes: ["Python is listed in stored skills."],
    approval_status: "approved",
    eligibility_confirmed: true,
  };
}

describe("ResumeVersionPanel downloads", () => {
  beforeEach(() => {
    vi.mocked(api.listResumeVersions).mockReset();
    vi.mocked(api.listResumeVersions).mockResolvedValue([VERSION]);
  });

  it("renders accessible PDF and DOCX links for each saved version", async () => {
    renderWithApp(<ResumeVersionPanel jobId="job-1" materials={approvedPackage()} />);

    const pdf = await screen.findByRole("link", { name: "Download resume version 1 as PDF" });
    const docx = screen.getByRole("link", { name: "Download resume version 1 as DOCX" });
    expect(pdf).toHaveAttribute("href", resumeVersionFileUrl("rv-owned-1", "pdf"));
    expect(docx).toHaveAttribute("href", resumeVersionFileUrl("rv-owned-1", "docx"));
    expect(pdf).toHaveAttribute("download");
    expect(docx).toHaveAttribute("download");
    await waitFor(() => {
      expect(api.listResumeVersions).toHaveBeenCalledWith("job-1");
    });
  });
});
