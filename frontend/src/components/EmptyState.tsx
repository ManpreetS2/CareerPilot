import type { ReactNode } from "react";
import { Sparkles } from "lucide-react";

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-start gap-4 border-t border-border pt-8">
      <svg width="48" height="16" viewBox="0 0 48 16" aria-hidden className="text-primary">
        <circle cx="4" cy="8" r="3" fill="currentColor" />
        <path
          d="M8 8 H44"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.2"
          className="path-stroke"
          pathLength={1}
        />
        <circle cx="44" cy="8" r="3" fill="var(--accent)" />
      </svg>
      <div>
        <h2 className="flex items-center gap-2 font-display text-2xl font-semibold">
          <Sparkles className="h-4 w-4 text-primary" aria-hidden />
          {title}
        </h2>
        <p className="mt-2 max-w-xl text-muted-foreground">{description}</p>
      </div>
      {action}
    </div>
  );
}
