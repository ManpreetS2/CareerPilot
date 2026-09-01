import { WorldPulseGlobe } from "./DottedGlobe";

export function DashboardAtmosphere() {
  return (
    <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden" aria-hidden>
      <div
        className="absolute left-[42%] top-8 h-[30rem] w-[38rem] -translate-x-1/2 rounded-full blur-3xl"
        style={{
          background: "radial-gradient(ellipse at center, var(--halo), transparent 68%)",
          animation: "glow-pulse 9s ease-in-out infinite",
        }}
      />
      <div className="absolute right-[-1.5rem] top-28 hidden opacity-70 lg:block">
        <WorldPulseGlobe compact />
      </div>
    </div>
  );
}
