import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  JobDiscoveryProgress,
  JOB_DISCOVERY_STAGES,
  JOB_DISCOVERY_STAGE_THRESHOLDS_MS,
} from "./JobDiscoveryProgress";

describe("JobDiscoveryProgress", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("shows stage copy immediately while remaining unresolved", () => {
    render(<JobDiscoveryProgress active />);
    expect(screen.getByTestId("job-discovery-progress")).toBeInTheDocument();
    for (const label of JOB_DISCOVERY_STAGES) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(
      screen.getByText(
        "CareerPilot is searching live job sources and ranking opportunities against your profile.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByTestId("job-discovery-stage-0")).toHaveAttribute("data-state", "active");
    expect(screen.getByTestId("job-discovery-stage-5")).toHaveAttribute("data-state", "pending");
    expect(screen.queryByText("%")).not.toBeInTheDocument();
    expect(screen.queryByText(/LLM|SQL|score_job|database|API call/i)).not.toBeInTheDocument();
  });

  it("keeps Almost ready active instead of claiming completion", () => {
    vi.useFakeTimers();
    render(<JobDiscoveryProgress active />);
    act(() => {
      vi.advanceTimersByTime(JOB_DISCOVERY_STAGE_THRESHOLDS_MS[5] + 12000);
    });
    expect(screen.getByTestId("job-discovery-stage-0")).toHaveAttribute("data-state", "complete");
    expect(screen.getByTestId("job-discovery-stage-4")).toHaveAttribute("data-state", "complete");
    expect(screen.getByTestId("job-discovery-stage-5")).toHaveAttribute("data-state", "active");
    expect(screen.getByTestId("job-discovery-stage-5")).not.toHaveAttribute("data-state", "complete");
    expect(screen.getByTestId("job-discovery-progress")).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByText(/opportunities found/i)).not.toBeInTheDocument();
  });

  it("omits motion when reduced motion is requested", () => {
    render(<JobDiscoveryProgress active reduceMotion />);
    expect(screen.getByTestId("job-discovery-stage-0").querySelector(".job-discovery-pulse")).toBeNull();
    expect(document.querySelector(".job-discovery-spin")).toBeNull();
  });
});
