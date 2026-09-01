import { WorldPulseGlobe } from "./DottedGlobe";

export function DashboardAtmosphere({ showGlobe = true }: { showGlobe?: boolean }) {
  return (
    <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden" aria-hidden>
      <div
        className="absolute left-1/2 top-4 h-[28rem] w-[40rem] -translate-x-1/2 rounded-full blur-3xl"
        style={{
          background: "radial-gradient(ellipse at center, var(--halo), transparent 68%)",
          animation: "glow-pulse 9s ease-in-out infinite",
        }}
      />
      <div
        className="absolute -left-10 bottom-8 h-[22rem] w-[22rem] rounded-full opacity-70 blur-3xl"
        style={{
          background: "radial-gradient(circle, var(--atmosphere-a), transparent 70%)",
        }}
      />
      <div
        className="absolute -right-6 top-32 h-[18rem] w-[24rem] rounded-full opacity-55 blur-3xl"
        style={{
          background: "radial-gradient(circle, var(--atmosphere-c), transparent 72%)",
        }}
      />
      {showGlobe ? (
        <div className="pointer-events-none absolute right-0 top-16 hidden h-48 w-56 overflow-hidden opacity-45 lg:block">
          <WorldPulseGlobe compact />
        </div>
      ) : null}
    </div>
  );
}
