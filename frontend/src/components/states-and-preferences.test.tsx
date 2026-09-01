import { render, screen, waitFor } from "@testing-library/react";
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

  it("does not render a decorative Try again control when no action is provided", () => {
    render(<ErrorState title="Backend unreachable" description="Start the API and retry." />);
    expect(screen.queryByRole("button", { name: /try again/i })).not.toBeInTheDocument();
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

  it("saves a custom role losslessly", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <PreferenceForm preferences={null} onSave={onSave} saving={false} error={null} success={null} />,
    );
    const input = screen.getByRole("combobox", { name: "Target roles" });
    await user.click(input);
    await user.type(input, "Quant Researcher");
    await user.keyboard("{Enter}");
    await user.click(screen.getByRole("button", { name: /Save job preferences/i }));
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    const saved = onSave.mock.calls[0]?.[0];
    expect(saved.target_roles).toEqual(["Quant Researcher"]);
  });
});
