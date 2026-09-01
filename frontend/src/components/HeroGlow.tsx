export function HeroGlow() {
  return (
    <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden" aria-hidden>
      <div
        className="absolute left-1/2 top-0 h-[36rem] w-[50rem] -translate-x-1/2 -translate-y-1/3 rounded-full blur-3xl"
        style={{
          background: "radial-gradient(ellipse at center, var(--halo), transparent 70%)",
          animation: "glow-pulse 8s ease-in-out infinite",
        }}
      />
      <div
        className="absolute left-1/2 top-16 h-[22rem] w-[34rem] -translate-x-1/2 rounded-full opacity-70 blur-2xl"
        style={{
          background: "radial-gradient(ellipse at center, var(--atmosphere-b), transparent 75%)",
          animation: "glow-pulse 10s ease-in-out infinite reverse",
        }}
      />
    </div>
  );
}
