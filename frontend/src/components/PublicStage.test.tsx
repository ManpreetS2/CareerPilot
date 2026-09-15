import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PublicStage } from "./PublicStage";

describe("PublicStage", () => {
  it("renders the existing product tagline without globe or lattice decoration", () => {
    render(<PublicStage />);
    expect(screen.getByText("Grounded job search. Human-approved applications.")).toBeInTheDocument();
    expect(screen.getByText("Grounded candidate profile")).toBeInTheDocument();
    expect(screen.queryByTestId("dotted-globe")).not.toBeInTheDocument();
    expect(screen.queryByTestId("signal-lattice")).not.toBeInTheDocument();
  });
});
