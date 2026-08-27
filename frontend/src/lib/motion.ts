export const motionDuration = {
  instant: 0.08,
  fast: 0.12,
  base: 0.18,
  panel: 0.24,
  emphasis: 0.32,
  hero: 0.45,
  score: 0.82,
} as const;

export const motionEase = {
  standard: [0.2, 0.8, 0.2, 1] as const,
  expressive: [0.16, 1, 0.3, 1] as const,
  panel: [0.22, 1, 0.36, 1] as const,
  springSoft: [0.34, 1.15, 0.64, 1] as const,
};

export function motionMs(seconds: number) {
  return `${Math.round(seconds * 1000)}ms`;
}
