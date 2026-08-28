import { describe, expect, it } from "vitest";
import { EXTENSION_PANEL_STATES, resolvePanelState } from "../src/panel-states";

describe("extension panel states", () => {
  it("covers the contracted side-panel states without adding submit", () => {
    expect(EXTENSION_PANEL_STATES).toContain("signed_out");
    expect(EXTENSION_PANEL_STATES).toContain("verified_fit_ready");
    expect(EXTENSION_PANEL_STATES).toContain("potential_match");
    expect(EXTENSION_PANEL_STATES).toContain("no_submit");
    expect(EXTENSION_PANEL_STATES).toContain("unsupported_site");
    expect(EXTENSION_PANEL_STATES).toContain("autofill_preview");
    expect(EXTENSION_PANEL_STATES).toContain("verification_running");
    expect(EXTENSION_PANEL_STATES).toContain("likely_ineligible");
    expect(EXTENSION_PANEL_STATES).not.toContain("auto_submit");
  });

  it("maps signed-out, backend, unsupported, greenhouse, and lever states", () => {
    expect(resolvePanelState({ signedOut: true })).toBe("signed_out");
    expect(resolvePanelState({ backendUnavailable: true })).toBe("backend_unavailable");
    expect(resolvePanelState({ url: "https://example.com/jobs/1", data: { tracked: false } as never })).toBe(
      "unsupported_site",
    );
    expect(
      resolvePanelState({
        url: "https://boards.greenhouse.io/acme/jobs/1",
        data: { tracked: false } as never,
      }),
    ).toBe("supported_greenhouse");
    expect(
      resolvePanelState({
        url: "https://jobs.lever.co/acme/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        data: { tracked: false } as never,
      }),
    ).toBe("supported_lever");
  });

  it("maps Potential, Verified, ineligible, and preview", () => {
    expect(
      resolvePanelState({
        url: "https://boards.greenhouse.io/acme/jobs/1",
        data: { tracked: true, score: { score_kind: "preliminary" }, job: { status: "discovered" } } as never,
      }),
    ).toBe("potential_match");
    expect(
      resolvePanelState({
        url: "https://boards.greenhouse.io/acme/jobs/1",
        data: { tracked: true, score: { score_kind: "verified" }, job: { status: "discovered" } } as never,
      }),
    ).toBe("verified_fit_ready");
    expect(
      resolvePanelState({
        url: "https://boards.greenhouse.io/acme/jobs/1",
        data: {
          tracked: true,
          score: { score_kind: "verified", eligibility_status: "likely_ineligible" },
          job: { status: "discovered" },
        } as never,
      }),
    ).toBe("likely_ineligible");
    expect(
      resolvePanelState({
        url: "https://boards.greenhouse.io/acme/jobs/1",
        data: { tracked: true, score: { score_kind: "verified" }, job: { status: "discovered" } } as never,
        autofillPreview: true,
      }),
    ).toBe("autofill_preview");
  });
});
