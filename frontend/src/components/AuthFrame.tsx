import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { IntelligenceField } from "./signature/IntelligenceField";
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
    <div className="cp-atmosphere relative flex min-h-[100dvh] items-center justify-center bg-background px-4 py-8">
      <IntelligenceField />
      <div className="relative z-10 w-full max-w-sm space-y-6">
        <div className="text-center">
          <Link to="/" className="font-display text-2xl font-semibold tracking-tight">
            {APP_NAME}
          </Link>
          <p className="mt-1 text-sm text-muted-foreground">{APP_TAGLINE}</p>
        </div>
        <Glass variant="floating" className="space-y-5 rounded-[var(--radius-lg)] p-6">
          <h1 className="font-display text-xl font-semibold">{title}</h1>
          {children}
        </Glass>
      </div>
    </div>
  );
}
