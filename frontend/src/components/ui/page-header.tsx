import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

export function PageHeader({
  title,
  description,
  actions,
  className,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("flex flex-wrap items-end justify-between gap-4", className)}>
      <div className="min-w-0 w-full max-w-3xl">
        <h1 className="title-fluid font-display font-semibold text-foreground">{title}</h1>
        {description ? (
          <p className="mt-2 max-w-2xl text-pretty text-sm text-muted-foreground sm:text-[15px]">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
    </header>
  );
}
