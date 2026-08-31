export function HeroGlow() {
  return (
    <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
      <div
        className="absolute left-1/2 top-0 h-[600px] w-[800px] -translate-x-1/2 -translate-y-1/3 rounded-full opacity-40 blur-3xl"
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(139, 92, 246, 0.35) 0%, rgba(168, 85, 247, 0.22) 35%, transparent 70%)",
          animation: "glow-pulse 8s ease-in-out infinite",
        }}
      />
      <div
        className="absolute left-1/2 top-12 h-[400px] w-[600px] -translate-x-1/2 rounded-full opacity-30 blur-2xl"
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(192, 132, 252, 0.28) 0%, rgba(168, 85, 247, 0.18) 40%, transparent 75%)",
          animation: "glow-pulse 10s ease-in-out infinite reverse",
        }}
      />
    </div>
  );
}
