import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SignalLattice } from "./SignalLattice";

describe("SignalLattice", () => {
  it("renders a decorative assembling lattice without labels", () => {
    render(<SignalLattice />);
    expect(screen.getByTestId("signal-lattice")).toBeInTheDocument();
    expect(screen.getByTestId("signal-lattice")).toHaveAttribute("aria-hidden");
  });
});
