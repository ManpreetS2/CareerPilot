import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SourceBadge } from "./SourceBadge";

describe("SourceBadge", () => {
  it("links an aggregator source to its job url when no source_url is set", () => {
    render(<SourceBadge source="remoteok" url="https://remoteok.com/remote-jobs/123" />);
    const link = screen.getByRole("link", { name: /RemoteOK — open original listing/i });
    expect(link).toHaveAttribute("href", "https://remoteok.com/remote-jobs/123");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer");
  });

  it("links Himalayas to its own listing page, not the direct application url", () => {
    render(
      <SourceBadge
        source="himalayas"
        url="https://stripe.com/careers/senior-engineer"
        sourceUrl="https://himalayas.app/jobs/stripe-senior-software-engineer-abc123"
      />,
    );
    const link = screen.getByRole("link", { name: /Himalayas — open original listing/i });
    expect(link).toHaveAttribute("href", "https://himalayas.app/jobs/stripe-senior-software-engineer-abc123");
  });

  it("renders an ATS source as a plain, non-link badge", () => {
    render(<SourceBadge source="greenhouse" url="https://boards.greenhouse.io/acme/jobs/1" />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText("Greenhouse")).toBeInTheDocument();
  });

  it("renders an aggregator source with no url as a plain, non-link badge", () => {
    render(<SourceBadge source="remotive" />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText("Remotive")).toBeInTheDocument();
  });
});
