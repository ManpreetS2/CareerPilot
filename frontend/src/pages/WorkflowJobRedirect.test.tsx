import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { WorkflowJobRedirect } from "./WorkflowJobRedirect";

describe("WorkflowJobRedirect", () => {
  it("keeps an Analyze page heading when no job is selected", () => {
    render(
      <MemoryRouter>
        <WorkflowJobRedirect kind="analyze" />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "Analyze" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Pick a job to analyze" })).toBeInTheDocument();
  });
});
