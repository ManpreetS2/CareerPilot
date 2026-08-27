import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProfilePage } from "./ProfilePage";
import { api, ApiClientError } from "../lib/api";
import { ThemeProvider } from "../lib/theme";
import { createTestQueryClient } from "../test/render";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      getProfile: vi.fn().mockResolvedValue({ candidate: null, preferences: null }),
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
    vi.mocked(api.getProfile).mockResolvedValue({ candidate: null, preferences: null });
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
