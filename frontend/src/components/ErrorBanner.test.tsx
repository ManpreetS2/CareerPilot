import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ErrorBanner } from "./ErrorBanner";
import { ApiClientError } from "../lib/api";

describe("ErrorBanner", () => {
  it.each([
    [0, "Can't connect"],
    [500, "Server error"],
    [502, "Temporarily unavailable"],
    [503, "Temporarily unavailable"],
    [504, "Temporarily unavailable"],
  ])("labels status %i as %s", (status, heading) => {
    render(<ErrorBanner error={new ApiClientError(status, "detail text")} />);
    expect(screen.getByRole("alert")).toHaveTextContent(heading);
    expect(screen.getByRole("alert")).toHaveTextContent("detail text");
  });
});
