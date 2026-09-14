import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EncryptionSection } from "./EncryptionSection";

vi.mock("motion/react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("motion/react")>();
  return {
    ...actual,
    useReducedMotion: () => false,
  };
});

const FORBIDDEN_CLAIMS = [/end-to-end/i, /zero-knowledge/i, /server cannot decrypt/i];

describe("EncryptionSection", () => {
  it("does not claim end-to-end encryption, zero-knowledge, or server-inaccessible data", () => {
    const { container } = render(<EncryptionSection />);
    expect(screen.getByRole("heading", { name: "Your resume stays protected" })).toBeInTheDocument();
    const text = container.textContent || "";
    for (const pattern of FORBIDDEN_CLAIMS) {
      expect(text).not.toMatch(pattern);
    }
    expect(text).toMatch(/local and self-hostable/i);
    expect(text).toMatch(/deployment you run/i);
    expect(text).toMatch(/never submits an application/i);
    expect(text).toMatch(/local SQLite/i);
    expect(text).toMatch(/CareerPilot deployment/i);
  });
});
