import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { JobCard, selectJobCardLabel } from "./JobCard";
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

describe("JobCard", () => {
  it("shows Remote once when location and work mode are both Remote", () => {
    render(<JobCard job={job({ location: "Remote", work_mode: "remote", employment_type: "internship" })} />);
    expect(screen.getByText("Remote · Internship")).toBeInTheDocument();
    expect(screen.queryByText("Remote · Remote · Internship")).not.toBeInTheDocument();
  });

  it("keeps a concise accessible name with title and company only", async () => {
    const onSelect = vi.fn();
    render(
      <JobCard
        job={job({ location: "Remote", work_mode: "remote", employment_type: "internship" })}
        onSelect={onSelect}
      />,
    );
    const name = selectJobCardLabel("Software Engineer Intern", "Harborline Analytics");
    const control = screen.getByRole("button", { name });
    expect(control).toHaveClass("job-card-select");
    expect(control).toHaveAccessibleName("Select Software Engineer Intern at Harborline Analytics");
    expect(screen.getByText("Software Engineer Intern")).toBeInTheDocument();
    expect(screen.getByText("Harborline Analytics")).toBeInTheDocument();
    expect(screen.getByText("Remote · Internship")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Potential Match/i })).not.toBeInTheDocument();
    await userEvent.click(control);
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("uses CareerPilot's purple focus-visible ring on the select control", () => {
    const css = readFileSync(resolve(__dirname, "../index.css"), "utf8");
    expect(css).toMatch(
      /\.job-card-select:focus-visible[\s\S]*?outline:\s*2px solid var\(--ring\);[\s\S]*?outline-offset:\s*2px;/,
    );
  });

  it("opens an aggregator source's link without also selecting the card", async () => {
    const onSelect = vi.fn();
    render(
      <JobCard
        job={job({ source: "remoteok", url: "https://remoteok.com/remote-jobs/123" })}
        onSelect={onSelect}
      />,
    );
    const link = screen.getByRole("link", { name: /RemoteOK — open original listing/i });
    await userEvent.click(link);
    expect(onSelect).not.toHaveBeenCalled();
  });
});
