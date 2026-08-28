import { describe, expect, it } from "vitest";
import { EXTENSION_PANEL_STATES } from "../src/panel-states";

describe("extension panel states", () => {
  it("covers the contracted side-panel states without adding submit", () => {
    expect(EXTENSION_PANEL_STATES).toContain("signed_out");
    expect(EXTENSION_PANEL_STATES).toContain("verified_fit_ready");
    expect(EXTENSION_PANEL_STATES).toContain("potential_match");
    expect(EXTENSION_PANEL_STATES).toContain("no_submit");
    expect(EXTENSION_PANEL_STATES).not.toContain("auto_submit");
  });
});
