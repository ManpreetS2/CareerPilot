import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { DottedGlobe } from "./DottedGlobe";
import { SignalLattice } from "./SignalLattice";
import { HeroAtmosphere } from "./HeroAtmosphere";
import { Glass } from "./ui/glass";
import { APP_NAME, APP_TAGLINE } from "../lib/config";

export function AuthFrame({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="cp-atmosphere relative min-h-[100dvh] overflow-x-clip bg-background">
      <HeroAtmosphere />
      <div className="relative mx-auto grid min-h-[100dvh] max-w-6xl lg:grid-cols-2">
        <div className="relative hidden min-h-[100dvh] overflow-hidden lg:block">
          <DottedGlobe />
          <SignalLattice className="absolute inset-0" />
        </div>

        <div className="relative z-10 flex items-center justify-center px-4 py-10 sm:px-6">
          <div className="pointer-events-none absolute inset-0 opacity-[0.22] lg:hidden" aria-hidden>
            <DottedGlobe compact />
            <SignalLattice className="absolute inset-0 opacity-70" />
          </div>
          <div className="relative w-full max-w-sm space-y-6">
            <div className="text-center">
              <Link to="/" className="font-display text-2xl font-semibold tracking-tight text-foreground">
                {APP_NAME}
              </Link>
              <p className="mt-1 text-sm text-muted-foreground">{APP_TAGLINE}</p>
            </div>
            <Glass variant="floating" className="space-y-5 rounded-[var(--radius-lg)] p-6">
              <h1 className="font-display text-xl font-semibold text-foreground">{title}</h1>
              {children}
            </Glass>
            <p className="text-center text-xs text-muted-foreground">
              <Link to="/privacy" className="font-medium hover:text-foreground">
                Privacy
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
