import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ResumePage } from "./ResumePage";
import { api } from "../lib/api";
import { ThemeProvider } from "../lib/theme";
import { createTestQueryClient } from "../test/render";
import type { ResumeVersionDetail, ResumeVersionSummary } from "../lib/types";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, api: { ...actual.api, listAllResumeVersions: vi.fn(), getResumeVersionDetail: vi.fn() } };
});

const summaries: ResumeVersionSummary[] = [
  {
    id: "ver-1",
    job_id: "job-1",
    job_title: "Engineer",
    company: "Acme",
    version_number: 1,
    created_at: "2026-01-02T00:00:00Z",
    bullet_count: 1,
    provenance_status: "approved_snapshot",
    matches_current_profile: true,
  },
  {
    id: "ver-2",
    job_id: "job-2",
    job_title: "Scientist",
    company: "Globex",
    version_number: 2,
    created_at: "2026-02-02T00:00:00Z",
    bullet_count: 2,
    provenance_status: "approved_snapshot",
    matches_current_profile: false,
  },
];

const details: Record<string, ResumeVersionDetail> = {
  "ver-1": {
    ...summaries[0]!,
    tailored_bullets: ["Shipped Python APIs"],
    source_traceability_notes: ["Grounded in stored experience"],
    profile: {
      name: "Historical Ada",
      email: "ada@example.com",
      skills: ["Python"],
      experience: [],
      projects: [],
      education: [],
      certifications: [],
    },
  },
  "ver-2": {
    ...summaries[1]!,
    tailored_bullets: ["Led experiments"],
    source_traceability_notes: [],
    profile: {
      name: "Historical Ada v2",
      skills: ["R"],
      experience: [],
      projects: [],
      education: [],
      certifications: [],
    },
  },
};

function renderResume(route: string) {
  vi.mocked(api.listAllResumeVersions).mockResolvedValue(summaries);
  vi.mocked(api.getResumeVersionDetail).mockImplementation(async (id: string) => details[id]!);
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <ThemeProvider>
        <MemoryRouter initialEntries={[route]}>
          <Routes>
            <Route path="/resume" element={<ResumePage />} />
            <Route path="/resume/:versionId" element={<ResumePage />} />
          </Routes>
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("ResumePage", () => {
  it("renders compact version rows instead of a card wall", async () => {
    renderResume("/resume");
    const list = await screen.findByTestId("resume-version-list");
    expect(list.querySelectorAll("a").length).toBe(2);
    expect(screen.getAllByText("Version 1").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Acme/).length).toBeGreaterThan(0);
  });

  it("restores a selected version from the deep link", async () => {
    renderResume("/resume/ver-2");
    expect(await screen.findByTestId("resume-preview")).toBeInTheDocument();
    expect(screen.getByText("Historical Ada v2")).toBeInTheDocument();
    expect(screen.queryByText("content_hash")).not.toBeInTheDocument();
    expect(screen.queryByText("candidate_profile_fingerprint")).not.toBeInTheDocument();
  });

  it("selects a version from the library", async () => {
    const user = userEvent.setup();
    renderResume("/resume");
    await screen.findByTestId("resume-version-list");
    await user.click(screen.getByText("Version 2"));
    expect(await screen.findByText("Historical Ada v2")).toBeInTheDocument();
  });
});
