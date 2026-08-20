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
    <div className="card flex flex-col items-start gap-4 p-8">
      <div>
        <h2 className="font-display text-2xl font-semibold">{title}</h2>
        <p className="mt-2 max-w-xl text-ink-600 dark:text-ink-300">{description}</p>
      </div>
      {action}
    </div>
  );
}
