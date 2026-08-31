import type { ReactNode } from "react";

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
    <div className="flex flex-col items-start gap-3 py-6">
      <div>
        <h2 className="section-title font-display text-foreground">{title}</h2>
        <p className="mt-1.5 max-w-xl text-sm text-muted-foreground">{description}</p>
      </div>
      {action}
    </div>
  );
}
