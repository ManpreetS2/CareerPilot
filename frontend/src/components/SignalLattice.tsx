const CELL = 14;
const GAP = 4;
const STEP = CELL + GAP;

type Cell = { x: number; y: number };
type Cluster = {
  left: string;
  top: string;
  tone: "core" | "accent" | "muted";
  cells: Cell[];
};

const CLUSTERS: Cluster[] = [
  {
    left: "8%",
    top: "18%",
    tone: "core",
    cells: [
      { x: 1, y: 0 },
      { x: 0, y: 1 },
      { x: 1, y: 1 },
      { x: 2, y: 1 },
    ],
  },
  {
    left: "62%",
    top: "12%",
    tone: "accent",
    cells: [
      { x: 0, y: 0 },
      { x: 0, y: 1 },
      { x: 0, y: 2 },
      { x: 1, y: 2 },
    ],
  },
  {
    left: "28%",
    top: "58%",
    tone: "muted",
    cells: [
      { x: 0, y: 0 },
      { x: 1, y: 0 },
      { x: 0, y: 1 },
      { x: 1, y: 1 },
    ],
  },
  {
    left: "72%",
    top: "48%",
    tone: "core",
    cells: [
      { x: 1, y: 0 },
      { x: 2, y: 0 },
      { x: 0, y: 1 },
      { x: 1, y: 1 },
    ],
  },
  {
    left: "14%",
    top: "78%",
    tone: "accent",
    cells: [
      { x: 0, y: 0 },
      { x: 1, y: 0 },
      { x: 2, y: 0 },
      { x: 3, y: 0 },
    ],
  },
];

export function SignalLattice({ className = "" }: { className?: string }) {
  return (
    <div className={`signal-lattice pointer-events-none ${className}`} aria-hidden data-testid="signal-lattice">
      {CLUSTERS.map((cluster, clusterIndex) => (
        <div
          key={`${cluster.left}-${cluster.top}`}
          className={`signal-cluster signal-cluster-${cluster.tone}`}
          style={{
            left: cluster.left,
            top: cluster.top,
            animationDelay: `${clusterIndex * 0.55}s`,
          }}
        >
          {cluster.cells.map((cell, cellIndex) => (
            <span
              key={`${cell.x}-${cell.y}`}
              className="signal-cell"
              style={{
                left: cell.x * STEP,
                top: cell.y * STEP,
                animationDelay: `${clusterIndex * 0.4 + cellIndex * 0.12}s`,
              }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}
