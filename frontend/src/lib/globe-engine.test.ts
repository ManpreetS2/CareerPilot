import { describe, expect, it } from "vitest";
import {
  GLOBE_HOLD_MS,
  GLOBE_REV_MS,
  GLOBE_SETTLE_MS,
  GLOBE_TRAVEL_MS,
  activeNodeIndex,
  advanceCometPhase,
  buildGlobeDots,
  createHoldPhase,
  globeLayout,
  isFrontFacing,
  pickNextVisible,
  projectNodes,
  projectSphere,
  visibleNodeIndices,
} from "./globe-engine";

const RADIUS = 200;

describe("globe projection", () => {
  it("rotates longitude around the vertical axis without flipping the sphere", () => {
    const a = projectSphere(30, 0, 0, RADIUS);
    const b = projectSphere(30, 0, 90, RADIUS);
    expect(a.y).toBeCloseTo(b.y, 8);
    expect(a.z).toBeGreaterThan(0);
    expect(b.x).toBeGreaterThan(0);
    expect(Math.abs(b.z)).toBeLessThan(Math.abs(a.z));
  });

  it("treats only the front hemisphere as visible", () => {
    expect(isFrontFacing(RADIUS, RADIUS)).toBe(true);
    expect(isFrontFacing(-RADIUS, RADIUS)).toBe(false);
    expect(isFrontFacing(RADIUS * 0.05, RADIUS)).toBe(false);
  });

  it("never returns a back-facing destination", () => {
    const nodes = projectNodes(0, RADIUS);
    const visible = new Set(visibleNodeIndices(nodes));
    expect(visible.size).toBeGreaterThan(0);
    for (const index of visible) {
      const next = pickNextVisible(index, nodes);
      if (next == null) continue;
      expect(nodes[next]?.visible).toBe(true);
    }
  });

  it("sizes the desktop globe as a large cropped hemisphere", () => {
    const desktop = globeLayout(1440, 576, false);
    expect(desktop.diameter).toBeGreaterThanOrEqual(900);
    expect(desktop.diameter).toBeLessThanOrEqual(1100);
    expect(desktop.cy).toBeGreaterThan(576);
    expect(GLOBE_REV_MS).toBeGreaterThanOrEqual(110_000);
    expect(GLOBE_REV_MS).toBeLessThanOrEqual(140_000);
    expect(buildGlobeDots(false).length).toBeGreaterThan(2000);
  });
});

describe("comet phase machine", () => {
  it("keeps the source active during travel and settles only after arrival", () => {
    const nodes = projectNodes(12, RADIUS).map((node) => ({ ...node, visible: true }));
    let phase = createHoldPhase(0);
    phase = advanceCometPhase(phase, GLOBE_HOLD_MS, nodes);
    expect(phase.kind).toBe("travel");
    if (phase.kind !== "travel") throw new Error("expected travel");
    expect(activeNodeIndex(phase)).toBe(phase.from);
    expect(phase.to).not.toBe(phase.from);

    phase = advanceCometPhase(phase, GLOBE_TRAVEL_MS / 2, nodes);
    expect(phase.kind).toBe("travel");
    if (phase.kind !== "travel") throw new Error("expected travel");
    expect(activeNodeIndex(phase)).toBe(phase.from);

    phase = advanceCometPhase(phase, GLOBE_TRAVEL_MS, nodes);
    expect(phase.kind).toBe("settle");
    if (phase.kind !== "settle") throw new Error("expected settle");
    expect(phase.active).toBe(1);
    expect(activeNodeIndex(phase)).toBe(1);

    phase = advanceCometPhase(phase, GLOBE_SETTLE_MS, nodes);
    expect(phase.kind).toBe("hold");
    if (phase.kind !== "hold") throw new Error("expected hold");
    expect(phase.active).toBe(1);
  });

  it("skips travel when the destination leaves the front hemisphere", () => {
    const nodes = projectNodes(0, RADIUS);
    const visible = visibleNodeIndices(nodes);
    const from = visible[0] ?? 0;
    const hidden = nodes.findIndex((node) => !node.visible);
    let phase: ReturnType<typeof createHoldPhase> | ReturnType<typeof advanceCometPhase> = {
      kind: "travel",
      from,
      to: hidden === -1 ? from : hidden,
      progress: 0.2,
    };
    phase = advanceCometPhase(phase, 16, nodes);
    expect(phase.kind).toBe("hold");
    expect(activeNodeIndex(phase)).toBe(from);
  });

  it("always has one active node after a hold snap to a visible index", () => {
    const nodes = projectNodes(40, RADIUS);
    const hidden = nodes.findIndex((node) => !node.visible);
    const phase = advanceCometPhase(createHoldPhase(hidden === -1 ? 0 : hidden), 16, nodes);
    expect(nodes[activeNodeIndex(phase)]?.visible).toBe(true);
  });
});
