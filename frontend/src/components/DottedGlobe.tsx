import { useReducedMotion } from "motion/react";

export function DottedGlobe() {
  const reduceMotion = useReducedMotion();

  const dots: Array<{ x: number; y: number; opacity: number; delay: number }> = [];
  const gridSize = 32;
  const radius = 140;
  const centerX = 180;
  const centerY = 180;

  for (let i = 0; i < gridSize; i++) {
    for (let j = 0; j < gridSize; j++) {
      const x = (i / gridSize) * 360 - 180;
      const y = (j / gridSize) * 180 - 90;

      const lat = (y * Math.PI) / 180;
      const lon = (x * Math.PI) / 180;

      const plotX = centerX + radius * Math.cos(lat) * Math.sin(lon);
      const plotY = centerY - radius * Math.sin(lat);
      const plotZ = radius * Math.cos(lat) * Math.cos(lon);

      if (plotZ > -20) {
        const depth = (plotZ + 140) / 280;
        dots.push({
          x: plotX,
          y: plotY,
          opacity: depth * 0.6 + 0.15,
          delay: (i * gridSize + j) * 0.002,
        });
      }
    }
  }

  return (
    <div className="relative flex h-96 items-center justify-center">
      <div
        className="pointer-events-none absolute inset-0 opacity-40 blur-3xl"
        style={{
          background:
            "radial-gradient(circle at center, rgba(139, 92, 246, 0.3) 0%, transparent 60%)",
        }}
      />
      <svg
        width="360"
        height="360"
        viewBox="0 0 360 360"
        className="relative z-10"
        style={{
          animation: reduceMotion ? undefined : "rotate-slow 120s linear infinite",
        }}
      >
        <g>
          {dots.map((dot, index) => (
            <circle
              key={index}
              cx={dot.x}
              cy={dot.y}
              r={1.2}
              fill="currentColor"
              className="text-purple-300"
              opacity={dot.opacity}
              style={{
                animation: reduceMotion
                  ? undefined
                  : `glow-pulse ${4 + (index % 3)}s ease-in-out infinite`,
                animationDelay: `${dot.delay}s`,
              }}
            />
          ))}
        </g>
        <circle
          cx={centerX}
          cy={centerY}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth="0.5"
          className="text-purple-400/30"
        />
        <ellipse
          cx={centerX}
          cy={centerY}
          rx={radius}
          ry={radius * 0.3}
          fill="none"
          stroke="currentColor"
          strokeWidth="0.5"
          className="text-purple-400/30"
        />
      </svg>
    </div>
  );
}
