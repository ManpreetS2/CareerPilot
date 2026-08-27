import { useId, useState, type ReactNode } from "react";
import { Sheet, SheetContent } from "../ui/sheet";
import { cn } from "../../lib/cn";

export function EvidencePathButton({
  claim,
  evidence,
  children,
  className,
}: {
  claim: string;
  evidence: string;
  children: ReactNode;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const pathId = useId();

  return (
    <>
      <button
        type="button"
        className={cn(
          "rounded-lg border border-border bg-muted/60 px-2.5 py-1 text-left text-xs font-medium hover:border-primary/40",
          className,
        )}
        onClick={() => setOpen(true)}
      >
        {children}
      </button>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="right" title="Evidence" className="glass-floating">
          <div className="space-y-4" data-testid="evidence-drawer">
            <svg viewBox="0 0 280 48" className="h-12 w-full text-primary" aria-hidden>
              <defs>
                <linearGradient id={pathId} x1="0" x2="1">
                  <stop offset="0%" stopColor="currentColor" />
                  <stop offset="100%" stopColor="var(--accent)" />
                </linearGradient>
              </defs>
              <circle cx="8" cy="24" r="4" fill="currentColor" />
              <path
                d="M12 24 C 80 24, 120 8, 272 24"
                fill="none"
                stroke={`url(#${pathId})`}
                strokeWidth="1.4"
                className="path-stroke"
                pathLength={1}
              />
              <circle cx="272" cy="24" r="4" fill="var(--accent)" />
            </svg>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Claim</p>
              <p className="mt-1 text-sm font-medium">{claim}</p>
            </div>
            <div className="rounded-[var(--radius-md)] border border-border bg-surface p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Stored evidence
              </p>
              <p className="mt-1 text-sm leading-relaxed">{evidence}</p>
            </div>
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
