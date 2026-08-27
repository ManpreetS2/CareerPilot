import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ResumeParsingProgress,
  RESUME_PARSE_STAGES,
  RESUME_PARSE_STAGE_THRESHOLDS_MS,
} from "./ResumeParsingProgress";

describe("ResumeParsingProgress", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("shows stage copy immediately while remaining unresolved", () => {
    render(<ResumeParsingProgress active />);
    expect(screen.getByTestId("resume-parsing-progress")).toBeInTheDocument();
    for (const label of RESUME_PARSE_STAGES) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(
      screen.getByText("CareerPilot is grounding your profile in the information on your resume."),
    ).toBeInTheDocument();
    expect(screen.getByTestId("resume-parse-stage-0")).toHaveAttribute("data-state", "active");
    expect(screen.getByTestId("resume-parse-stage-4")).toHaveAttribute("data-state", "pending");
    expect(screen.queryByText("%")).not.toBeInTheDocument();
    expect(screen.queryByText(/LLM|Pydantic|OCR|JSON schema|provider/i)).not.toBeInTheDocument();
  });

  it("advances timed stages but never marks the last stage complete", () => {
    vi.useFakeTimers();
    render(<ResumeParsingProgress active />);
    act(() => {
      vi.advanceTimersByTime(RESUME_PARSE_STAGE_THRESHOLDS_MS[4] + 8000);
    });
    expect(screen.getByTestId("resume-parse-stage-0")).toHaveAttribute("data-state", "complete");
    expect(screen.getByTestId("resume-parse-stage-3")).toHaveAttribute("data-state", "complete");
    expect(screen.getByTestId("resume-parse-stage-4")).toHaveAttribute("data-state", "active");
    expect(screen.getByTestId("resume-parse-stage-4")).not.toHaveAttribute("data-state", "complete");
    expect(screen.getByTestId("resume-parsing-progress")).toHaveAttribute("aria-busy", "true");
  });

  it("omits pulse motion when reduced motion is requested", () => {
    render(<ResumeParsingProgress active reduceMotion />);
    expect(screen.getByTestId("resume-parse-stage-0").querySelector(".resume-parse-pulse")).toBeNull();
  });
});
