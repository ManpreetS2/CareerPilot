import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PreferenceForm } from "../components/PreferenceForm";

describe("loading empty and error primitives", () => {
  it("renders loading, empty, and error states without a blank screen", () => {
    const { rerender } = render(<LoadingState label="Loading dashboard…" />);
    expect(screen.getByText("Loading dashboard…")).toBeInTheDocument();
    rerender(
      <EmptyState title="No resume versions" description="Approve materials first." />,
    );
    expect(screen.getByText("No resume versions")).toBeInTheDocument();
    rerender(
      <ErrorState title="Backend unreachable" description="Start the API and retry." />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Backend unreachable");
  });
});

describe("PreferenceForm", () => {
  it("validates that at least one target role is required", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(
      <PreferenceForm preferences={null} onSave={onSave} saving={false} error={null} success={null} />,
    );
    await user.click(screen.getByRole("button", { name: /Save job preferences/i }));
    expect(await screen.findByText("Enter at least one target role.")).toBeInTheDocument();
    expect(onSave).not.toHaveBeenCalled();
  });
});
