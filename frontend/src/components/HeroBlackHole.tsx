function bumpPath(baseY: number, amp: number, sigma: number, width = 1600, step = 16) {
  const parts: string[] = [];
  for (let x = 0; x <= width; x += step) {
    const y = baseY - amp * Math.exp(-((x - 800) ** 2) / (2 * sigma * sigma));
    parts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
  }
  return `M ${parts.join(" L ")}`;
}

const DISKS = [
  { base: 648, amp: 118, sigma: 248, opacity: 0.95, width: 3.4, glow: true },
  { base: 658, amp: 104, sigma: 292, opacity: 0.58, width: 1.8, glow: true },
  { base: 670, amp: 90, sigma: 348, opacity: 0.42, width: 1.45, glow: false },
  { base: 684, amp: 74, sigma: 430, opacity: 0.3, width: 1.15, glow: false },
  { base: 698, amp: 56, sigma: 530, opacity: 0.2, width: 0.95, glow: false },
  { base: 710, amp: 38, sigma: 650, opacity: 0.13, width: 0.8, glow: false },
  { base: 720, amp: 22, sigma: 780, opacity: 0.08, width: 0.65, glow: false },
].map((disk) => ({ ...disk, d: bumpPath(disk.base, disk.amp, disk.sigma) }));

const STARS = Array.from({ length: 52 }, (_, index) => {
  const t = index / 51;
  const spread = 90 + t * 620;
  const x = 800 + Math.cos(index * 2.47) * spread * (0.35 + (index % 5) * 0.13);
  const y = 210 + (index * 83.1) % 300;
  return {
    x,
    y,
    r: 0.45 + (index % 6) * 0.22,
    delay: (index % 9) * 0.48,
  };
});

export function HeroBlackHole() {
  return (
    <div className="hero-blackhole" aria-hidden data-testid="hero-blackhole">
      <div className="hero-blackhole-bloom" />
      <div className="hero-blackhole-haze" />
      <div className="hero-blackhole-flow" />
      <svg className="hero-blackhole-svg" viewBox="0 0 1600 720" preserveAspectRatio="xMidYMax slice">
        <defs>
          <linearGradient id="cp-hero-disk" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="var(--hole-disk)" stopOpacity="0" />
            <stop offset="18%" stopColor="var(--accent)" stopOpacity="0.35" />
            <stop offset="50%" stopColor="var(--hole-core)" stopOpacity="1" />
            <stop offset="82%" stopColor="var(--accent)" stopOpacity="0.35" />
            <stop offset="100%" stopColor="var(--hole-disk)" stopOpacity="0" />
          </linearGradient>
          <radialGradient id="cp-hero-bloom" cx="50%" cy="78%" r="52%">
            <stop offset="0%" stopColor="var(--hole-core)" stopOpacity="0.55" />
            <stop offset="28%" stopColor="var(--accent)" stopOpacity="0.28" />
            <stop offset="100%" stopColor="var(--primary)" stopOpacity="0" />
          </radialGradient>
          <filter id="cp-hero-disk-glow" x="-8%" y="-120%" width="116%" height="340%">
            <feGaussianBlur stdDeviation="7" />
          </filter>
          <filter id="cp-hero-rim-glow" x="-30%" y="-80%" width="160%" height="240%">
            <feGaussianBlur stdDeviation="8" />
          </filter>
        </defs>
        <ellipse cx="800" cy="700" rx="560" ry="240" fill="url(#cp-hero-bloom)" opacity="0.7" />
        {DISKS.map((disk, index) => (
          <g key={disk.base} className="hero-blackhole-band" style={{ animationDelay: `${index * 0.85}s` }}>
            {disk.glow ? (
              <path
                d={disk.d}
                fill="none"
                stroke="url(#cp-hero-disk)"
                strokeWidth={disk.width * 4}
                opacity={disk.opacity * 0.32}
                filter="url(#cp-hero-disk-glow)"
              />
            ) : null}
            <path
              d={disk.d}
              fill="none"
              stroke="url(#cp-hero-disk)"
              strokeWidth={disk.width}
              opacity={disk.opacity}
              strokeLinecap="round"
            />
          </g>
        ))}
        <ellipse className="hero-blackhole-void" cx="800" cy="760" rx="430" ry="188" fill="var(--hole-void)" />
        <ellipse
          className="hero-blackhole-rim"
          cx="800"
          cy="760"
          rx="452"
          ry="204"
          fill="none"
          stroke="var(--hole-core)"
          strokeWidth="22"
          filter="url(#cp-hero-rim-glow)"
          opacity="0.78"
        />
        <ellipse
          className="hero-blackhole-rim"
          cx="800"
          cy="760"
          rx="444"
          ry="198"
          fill="none"
          stroke="var(--hole-core)"
          strokeWidth="8"
          opacity="0.98"
        />
        {STARS.map((star) => (
          <circle
            key={`${star.x}-${star.y}`}
            className="hero-blackhole-star"
            cx={star.x}
            cy={star.y}
            r={star.r}
            fill="var(--hole-core)"
            style={{ animationDelay: `${star.delay}s` }}
          />
        ))}
      </svg>
    </div>
  );
}
