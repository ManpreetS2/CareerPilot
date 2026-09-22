import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { JobPreviewPanel } from "./JobPreviewPanel";
import type { Job } from "../lib/types";

function job(overrides: Partial<Job> = {}): Job {
  return {
    id: "job-1",
    title: "Software Engineer Intern",
    company: "Harborline Analytics",
    location: "Remote",
    url: "https://example.com/showcase/harborline-intern",
    description: "DEMO",
    source: "manual",
    status: "verified",
    ...overrides,
  };
}

function renderPreview(overrides: Partial<Job> = {}) {
  return render(
    <MemoryRouter>
      <JobPreviewPanel job={job(overrides)} />
    </MemoryRouter>,
  );
}

describe("JobPreviewPanel metadata", () => {
  it("shows Remote once when location and work mode are both Remote", () => {
    renderPreview({ location: "Remote", work_mode: "remote", employment_type: "internship" });
    expect(screen.getByText("Remote · Internship")).toBeInTheDocument();
    expect(screen.queryByText("Remote · Remote · Internship")).not.toBeInTheDocument();
  });

  it("discloses the synthetic demo without labeling a real job from the same company", () => {
    const { rerender } = renderPreview({ id: "showcase-harborline-intern" });
    expect(screen.getByText(/Synthetic demo · not a real posting/)).toBeInTheDocument();
    rerender(
      <MemoryRouter>
        <JobPreviewPanel job={job({ id: "real-job" })} />
      </MemoryRouter>,
    );
    expect(screen.queryByText(/Synthetic demo · not a real posting/)).not.toBeInTheDocument();
  });

  it("keeps a city location next to a different work mode", () => {
    renderPreview({ location: "San Francisco, CA", work_mode: "hybrid" });
    expect(screen.getByText("San Francisco, CA · Hybrid")).toBeInTheDocument();
  });

  it("keeps New York on-site as a distinct combination", () => {
    renderPreview({ location: "New York, NY", work_mode: "onsite" });
    expect(screen.getByText("New York, NY · On-site")).toBeInTheDocument();
  });
});
