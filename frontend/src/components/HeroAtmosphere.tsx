export function HeroAtmosphere() {
  return (
    <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden" aria-hidden>
      <div
        className="absolute left-1/2 top-0 h-[34rem] w-[52rem] -translate-x-1/2 -translate-y-[40%] rounded-full blur-3xl"
        style={{
          background: "radial-gradient(ellipse at center, var(--halo), transparent 72%)",
          animation: "glow-pulse 8s ease-in-out infinite",
        }}
      />
      <div
        className="absolute left-[18%] top-24 h-[18rem] w-[26rem] rounded-full opacity-60 blur-3xl"
        style={{
          background: "radial-gradient(ellipse at center, var(--atmosphere-a), transparent 74%)",
          animation: "glow-pulse 11s ease-in-out infinite reverse",
        }}
      />
      <div
        className="absolute right-[12%] top-32 h-[16rem] w-[22rem] rounded-full opacity-50 blur-3xl"
        style={{
          background: "radial-gradient(ellipse at center, var(--atmosphere-b), transparent 76%)",
          animation: "glow-pulse 13s ease-in-out infinite",
        }}
      />
    </div>
  );
}
