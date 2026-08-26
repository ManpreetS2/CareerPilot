import { beforeEach, describe, expect, it } from "vitest";
import { readTrackerView, saveTrackerView } from "./tracker-view";

describe("tracker view preference", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("persists a user-scoped kanban or list preference", () => {
    saveTrackerView(7, "list");
    expect(readTrackerView(7)).toBe("list");
    expect(localStorage.getItem("careerpilot.tracker-view.u7")).toBe("list");
    saveTrackerView(7, "kanban");
    expect(readTrackerView(7)).toBe("kanban");
  });
});
