import type { HTMLAttributes } from "react";
import { cn } from "../../lib/cn";

export function Surface({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-[var(--radius-md)] border border-border bg-surface", className)}
      {...props}
    />
  );
}
