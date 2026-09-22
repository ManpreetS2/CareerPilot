import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { JobCard, selectJobCardLabel } from "./JobCard";
import type { Job, MatchScore } from "../lib/types";

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

function potentialMatch(): MatchScore {
  return {
    job_id: "job-1",
    overall_score: 72,
    matched_skills: ["Python", "SQL"],
    partial_matches: [],
    missing_skills: ["Docker"],
    recommendation: "consider",
    rationale: "Matched Python and SQL from stored evidence.",
    score_kind: "preliminary",
  };
}

function interactiveDescendants(element: HTMLElement): HTMLElement[] {
  return Array.from(element.querySelectorAll("a, button, input, select, textarea"));
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
    expect(control).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText("Software Engineer Intern")).toBeInTheDocument();
    expect(screen.getByText("Harborline Analytics")).toBeInTheDocument();
    expect(screen.getByText("Remote · Internship")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Potential Match/i })).not.toBeInTheDocument();
    await userEvent.click(control);
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("marks only the reserved fictional showcase postings as synthetic", () => {
    const { rerender } = render(<JobCard job={job({ id: "showcase-harborline-intern" })} />);
    expect(screen.getByText(/Synthetic demo · not a real posting/)).toBeInTheDocument();
    rerender(<JobCard job={job({ id: "real-harborline-job" })} />);
    expect(screen.queryByText(/Synthetic demo · not a real posting/)).not.toBeInTheDocument();
  });

  it("marks the select control as pressed when the card is selected", () => {
    render(
      <JobCard
        job={job()}
        selected
        onSelect={() => undefined}
      />,
    );
    expect(
      screen.getByRole("button", { name: selectJobCardLabel("Software Engineer Intern", "Harborline Analytics") }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("uses CareerPilot's purple focus-visible ring on the select control", () => {
    const css = readFileSync(resolve(__dirname, "../index.css"), "utf8");
    expect(css).toMatch(
      /\.job-card-select:focus-visible[\s\S]*?outline:\s*2px solid var\(--ring\);[\s\S]*?outline-offset:\s*2px;/,
    );
  });

  it("selects the job from the match badge, timestamp, non-link source badge, and card whitespace", async () => {
    const onSelect = vi.fn();
    const { container } = render(
      <JobCard
        job={job({
          source: "manual",
          date_scraped: new Date().toISOString(),
        })}
        match={potentialMatch()}
        onSelect={onSelect}
      />,
    );

    await userEvent.click(screen.getByText("Potential Match"));
    expect(onSelect).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByText("Seen today"));
    expect(onSelect).toHaveBeenCalledTimes(2);

    await userEvent.click(screen.getByText("Manual"));
    expect(onSelect).toHaveBeenCalledTimes(3);

    const card = container.querySelector("article");
    expect(card).toBeTruthy();
    await userEvent.click(card as HTMLElement);
    expect(onSelect).toHaveBeenCalledTimes(4);
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
    expect(link).toHaveAttribute("href", "https://remoteok.com/remote-jobs/123");
    await userEvent.click(link);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("does not nest the source link or save control inside the select button", () => {
    const onSelect = vi.fn();
    const onToggleSave = vi.fn();
    render(
      <JobCard
        job={job({ source: "remoteok", url: "https://remoteok.com/remote-jobs/123" })}
        onSelect={onSelect}
        onToggleSave={onToggleSave}
      />,
    );
    const select = screen.getByRole("button", {
      name: selectJobCardLabel("Software Engineer Intern", "Harborline Analytics"),
    });
    expect(interactiveDescendants(select)).toEqual([]);
    const link = screen.getByRole("link", { name: /RemoteOK — open original listing/i });
    expect(select.contains(link)).toBe(false);
    const save = screen.getByRole("button", { name: "Save job" });
    expect(select.contains(save)).toBe(false);
  });

  it("selects from the keyboard without activating the source link", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(
      <JobCard
        job={job({ source: "remoteok", url: "https://remoteok.com/remote-jobs/123" })}
        onSelect={onSelect}
      />,
    );
    const select = screen.getByRole("button", {
      name: selectJobCardLabel("Software Engineer Intern", "Harborline Analytics"),
    });
    select.focus();
    expect(select).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenCalledTimes(1);
    await user.keyboard(" ");
    expect(onSelect).toHaveBeenCalledTimes(2);

    const link = screen.getByRole("link", { name: /RemoteOK — open original listing/i });
    link.focus();
    expect(link).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenCalledTimes(2);
  });

  it("keeps the save control independent of job selection", async () => {
    const onSelect = vi.fn();
    const onToggleSave = vi.fn();
    render(<JobCard job={job()} onSelect={onSelect} onToggleSave={onToggleSave} />);
    await userEvent.click(screen.getByRole("button", { name: "Save job" }));
    expect(onToggleSave).toHaveBeenCalledTimes(1);
    expect(onSelect).not.toHaveBeenCalled();
  });
});
