import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { NaturalSearchBar } from "./NaturalSearchBar";

const indexCss = readFileSync(resolve(__dirname, "../index.css"), "utf8");

describe("Discover search keyboard focus", () => {
  it("marks the search input for CareerPilot's purple focus-visible ring", () => {
    render(<NaturalSearchBar value="" onChange={() => {}} onSubmit={() => {}} chips={[]} />);
    expect(screen.getByTestId("jobs-search-input")).toHaveClass("jobs-search-input");
    expect(indexCss).toMatch(
      /\.jobs-search-input:focus-visible[\s\S]*?outline:\s*2px solid var\(--ring\);[\s\S]*?outline-offset:\s*2px;/,
    );
  });
});
