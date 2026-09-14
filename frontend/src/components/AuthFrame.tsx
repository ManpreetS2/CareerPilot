import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { HeroAtmosphere } from "./HeroAtmosphere";
import { PublicStage } from "./PublicStage";
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
    <div className="cp-atmosphere public-shell relative min-h-[100dvh] overflow-x-clip bg-background">
      <a href="#auth-main" className="skip-link">
        Skip to form
      </a>
      <HeroAtmosphere />
      <div className="relative mx-auto grid min-h-[100dvh] w-full max-w-6xl lg:grid-cols-[minmax(0,1fr)_minmax(20rem,26rem)]">
        <div className="relative hidden items-center px-8 py-12 lg:flex">
          <PublicStage />
        </div>
        <div className="relative z-10 flex items-center justify-center px-4 py-10 sm:px-6">
          <div className="relative w-full max-w-md space-y-6">
            <div className="text-center">
              <Link to="/" className="public-focus font-display text-2xl font-semibold tracking-tight text-foreground">
                {APP_NAME}
              </Link>
              <p className="mt-1 text-sm text-muted-foreground">{APP_TAGLINE}</p>
            </div>
            <Glass variant="floating" className="space-y-5 rounded-[var(--radius-lg)] p-6 sm:p-7">
              <h1 id="auth-main" className="font-display text-xl font-semibold text-foreground" tabIndex={-1}>
                {title}
              </h1>
              {children}
            </Glass>
            <p className="text-center text-xs text-muted-foreground">
              <Link to="/privacy" className="public-focus font-medium hover:text-foreground">
                Privacy
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
