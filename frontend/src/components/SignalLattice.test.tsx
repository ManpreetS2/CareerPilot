import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SignalLattice } from "./SignalLattice";

describe("SignalLattice", () => {
  it("renders one compact motif without labels", () => {
    render(<SignalLattice />);
    const lattice = screen.getByTestId("signal-lattice");
    expect(lattice).toBeInTheDocument();
    expect(lattice).toHaveAttribute("aria-hidden");
    expect(lattice.querySelectorAll(".signal-cluster")).toHaveLength(1);
    expect(lattice.querySelectorAll(".signal-cell").length).toBeGreaterThanOrEqual(5);
    expect(lattice.querySelectorAll(".signal-cell").length).toBeLessThanOrEqual(12);
  });
});
