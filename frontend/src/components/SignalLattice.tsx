const CELL = 13;
const GAP = 5;
const STEP = CELL + GAP;

type Cell = { x: number; y: number };

const MOTIF: Cell[] = [
  { x: 1, y: 0 },
  { x: 2, y: 0 },
  { x: 0, y: 1 },
  { x: 1, y: 1 },
  { x: 2, y: 1 },
  { x: 3, y: 1 },
  { x: 1, y: 2 },
  { x: 2, y: 2 },
  { x: 3, y: 2 },
  { x: 2, y: 3 },
];

export function SignalLattice({ className = "" }: { className?: string }) {
  return (
    <div className={`signal-lattice pointer-events-none ${className}`} aria-hidden data-testid="signal-lattice">
      <div className="signal-cluster signal-cluster-core">
        {MOTIF.map((cell, cellIndex) => (
          <span
            key={`${cell.x}-${cell.y}`}
            className="signal-cell"
            style={{
              left: cell.x * STEP,
              top: cell.y * STEP,
              animationDelay: `${cellIndex * 0.14}s`,
            }}
          />
        ))}
      </div>
    </div>
  );
}
