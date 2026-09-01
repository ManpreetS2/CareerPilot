export type SpherePoint = { x: number; y: number; z: number };
export type GeoNode = { lat: number; lon: number };
export type ProjectedNode = SpherePoint & { index: number; visible: boolean };

export const GLOBE_HOLD_MS = 4200;
export const GLOBE_TRAVEL_MS = 1600;
export const GLOBE_SETTLE_MS = 700;
export const GLOBE_REV_MS = 125000;
export const FRONT_THRESHOLD = 0.14;

export const GLOBE_NODES: GeoNode[] = [
  { lat: 48, lon: -2 },
  { lat: 41, lon: -74 },
  { lat: 52, lon: 13 },
  { lat: 35, lon: 139 },
  { lat: 1, lon: 104 },
  { lat: 19, lon: 73 },
  { lat: -23, lon: -47 },
  { lat: -34, lon: 151 },
  { lat: 37, lon: -122 },
  { lat: 55, lon: 37 },
  { lat: 31, lon: 121 },
  { lat: -26, lon: 28 },
];

export function projectSphere(
  latDeg: number,
  lonDeg: number,
  lonOffsetDeg: number,
  radius: number,
): SpherePoint {
  const lat = (latDeg * Math.PI) / 180;
  const lon = ((lonDeg + lonOffsetDeg) * Math.PI) / 180;
  return {
    x: radius * Math.cos(lat) * Math.sin(lon),
    y: -radius * Math.sin(lat),
    z: radius * Math.cos(lat) * Math.cos(lon),
  };
}

export function isFrontFacing(z: number, radius: number, threshold = FRONT_THRESHOLD): boolean {
  return z > radius * threshold;
}

export function projectNodes(lonOffsetDeg: number, radius: number): ProjectedNode[] {
  return GLOBE_NODES.map((node, index) => {
    const point = projectSphere(node.lat, node.lon, lonOffsetDeg, radius);
    return { ...point, index, visible: isFrontFacing(point.z, radius) };
  });
}

export function visibleNodeIndices(nodes: ProjectedNode[]): number[] {
  return nodes.filter((node) => node.visible).map((node) => node.index);
}

export function pickNextVisible(current: number, nodes: ProjectedNode[]): number | null {
  const count = nodes.length;
  if (count < 2) return null;
  for (let step = 1; step < count; step++) {
    const index = (current + step) % count;
    if (nodes[index]?.visible && index !== current) return index;
  }
  return null;
}

export function ensureVisibleActive(current: number, nodes: ProjectedNode[]): number {
  if (nodes[current]?.visible) return current;
  return visibleNodeIndices(nodes)[0] ?? current;
}

export type CometPhase =
  | { kind: "hold"; active: number; elapsed: number }
  | { kind: "travel"; from: number; to: number; progress: number }
  | { kind: "settle"; active: number; from: number; elapsed: number };

export function createHoldPhase(active = 0): CometPhase {
  return { kind: "hold", active, elapsed: 0 };
}

export function advanceCometPhase(
  phase: CometPhase,
  dtMs: number,
  nodes: ProjectedNode[],
  timing: { holdMs: number; travelMs: number; settleMs: number } = {
    holdMs: GLOBE_HOLD_MS,
    travelMs: GLOBE_TRAVEL_MS,
    settleMs: GLOBE_SETTLE_MS,
  },
): CometPhase {
  if (phase.kind === "hold") {
    const active = ensureVisibleActive(phase.active, nodes);
    const elapsed = phase.elapsed + dtMs;
    if (elapsed < timing.holdMs) {
      return active === phase.active && elapsed === phase.elapsed
        ? phase
        : { kind: "hold", active, elapsed };
    }
    const next = pickNextVisible(active, nodes);
    if (next == null) return { kind: "hold", active, elapsed: 0 };
    return { kind: "travel", from: active, to: next, progress: 0 };
  }

  if (phase.kind === "travel") {
    const fromVisible = nodes[phase.from]?.visible;
    const toVisible = nodes[phase.to]?.visible;
    if (!fromVisible || !toVisible) {
      const fallback = ensureVisibleActive(phase.from, nodes);
      return { kind: "hold", active: fallback, elapsed: 0 };
    }
    const progress = Math.min(1, phase.progress + dtMs / timing.travelMs);
    if (progress >= 1) {
      return { kind: "settle", active: phase.to, from: phase.from, elapsed: 0 };
    }
    return { ...phase, progress };
  }

  const elapsed = phase.elapsed + dtMs;
  if (elapsed >= timing.settleMs) {
    return { kind: "hold", active: ensureVisibleActive(phase.active, nodes), elapsed: 0 };
  }
  return { ...phase, elapsed };
}

export function activeNodeIndex(phase: CometPhase): number {
  if (phase.kind === "travel") return phase.from;
  return phase.active;
}

export function easeInOutCubic(t: number) {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

export function quadPoint(
  from: { x: number; y: number },
  to: { x: number; y: number },
  t: number,
  lift: number,
) {
  const mx = (from.x + to.x) / 2;
  const my = (from.y + to.y) / 2 - lift;
  return {
    x: (1 - t) * (1 - t) * from.x + 2 * (1 - t) * t * mx + t * t * to.x,
    y: (1 - t) * (1 - t) * from.y + 2 * (1 - t) * t * my + t * t * to.y,
  };
}

export function cometTrailPoints(
  from: { x: number; y: number },
  to: { x: number; y: number },
  progress: number,
) {
  const span = Math.hypot(to.x - from.x, to.y - from.y);
  const lift = 18 + span * 0.12;
  const t = easeInOutCubic(Math.min(1, Math.max(0, progress)));
  const head = quadPoint(from, to, t, lift);
  const trail = Array.from({ length: 10 }, (_, index) => {
    const behind = Math.max(0, t - index * 0.036);
    const point = quadPoint(from, to, behind, lift);
    return {
      ...point,
      r: Math.max(0.8, 3.1 - index * 0.22),
      o: (1 - index / 10) * (1 - t) * 0.72,
    };
  });
  return { head, trail, lift, t };
}

export type GlobeDot = { lat: number; lon: number; size: number };

export function buildGlobeDots(compact: boolean): GlobeDot[] {
  const latBands = compact ? 16 : 38;
  const dots: GlobeDot[] = [];
  for (let j = 0; j < latBands; j++) {
    const lat = 4 + (j / (latBands - 1)) * 82;
    const lonSteps = Math.max(16, Math.round((compact ? 42 : 118) * Math.cos((lat * Math.PI) / 180)));
    const size = lat > 64 ? 0.82 : lat > 42 ? 1.05 : 1.28;
    for (let i = 0; i < lonSteps; i++) {
      dots.push({
        lat,
        lon: (i / lonSteps) * 360 - 180,
        size,
      });
    }
  }
  return dots;
}

export function globeLayout(width: number, height: number, compact: boolean) {
  const diameter = Math.min(
    Math.max(width * (compact ? 0.88 : 1.06), compact ? 200 : 900),
    compact ? 320 : 1100,
  );
  return {
    diameter,
    radius: diameter / 2,
    cx: width / 2,
    cy: height + (compact ? 8 : 12),
  };
}

export const GLOBE_LATITUDES = [10, 22, 34, 46, 58, 70];
export const GLOBE_MERIDIANS = [-150, -90, -30, 30, 90, 150];
