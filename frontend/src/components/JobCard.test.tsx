import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { formatJobCardMeta, JobCard, selectJobCardLabel } from "./JobCard";
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

describe("formatJobCardMeta", () => {
  it("deduplicates adjacent equivalent values such as Remote + Remote", () => {
    expect(formatJobCardMeta(["Remote", "Remote", "Internship"])).toBe("Remote · Internship");
    expect(formatJobCardMeta([" remote ", "Remote", "Internship"])).toBe("remote · Internship");
  });

  it("keeps location and a different work mode", () => {
    expect(formatJobCardMeta(["San Francisco, CA", "Hybrid"])).toBe("San Francisco, CA · Hybrid");
    expect(formatJobCardMeta(["New York", "On-site"])).toBe("New York · On-site");
  });

  it("skips unknown and missing values without inventing labels", () => {
    expect(formatJobCardMeta([null, undefined, "", "Internship"])).toBe("Internship");
  });
});

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
    expect(control).toHaveAccessibleName("Select Software Engineer Intern at Harborline Analytics");
    expect(screen.getByText("Software Engineer Intern")).toBeInTheDocument();
    expect(screen.getByText("Harborline Analytics")).toBeInTheDocument();
    expect(screen.getByText("Remote · Internship")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Potential Match/i })).not.toBeInTheDocument();
    await userEvent.click(control);
    expect(onSelect).toHaveBeenCalledTimes(1);
  });
});
