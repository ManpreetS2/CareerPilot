import { useId, useState, type ReactNode } from "react";
import { useReducedMotion } from "motion/react";
import { Sheet, SheetContent } from "../ui/sheet";
import { cn } from "../../lib/cn";
import type { FactorStatus } from "../../lib/types";

export type EvidenceDrawerModel = {
  factor: string;
  result: string;
  resultKind?: FactorStatus;
  jobEvidence: string[];
  candidateEvidence: string[];
  rule: string;
  explanation: string;
  missingCandidate?: boolean;
};

function HighlightedText({ text }: { text: string }) {
  return (
    <p className="mt-1 text-sm leading-relaxed">
      <mark className="rounded-sm bg-primary/15 px-0.5 text-foreground">{text}</mark>
    </p>
  );
}

function StatusLabel({ kind, label }: { kind?: FactorStatus; label: string }) {
  if (kind === "unknown") {
    return <p className="mt-1 text-sm font-semibold text-ink-600 dark:text-ink-300">? {label}</p>;
  }
  if (kind === "not_satisfied") {
    return <p className="mt-1 text-sm font-semibold text-danger-600">✕ {label}</p>;
  }
  if (kind === "satisfied") {
    return <p className="mt-1 text-sm font-semibold text-success">✓ {label}</p>;
  }
  if (kind === "partially_satisfied") {
    return <p className="mt-1 text-sm font-semibold">~ {label}</p>;
  }
  return <p className="mt-1 text-sm font-semibold">{label}</p>;
}

export function EvidencePathButton({
  claim,
  evidence,
  detail,
  children,
  className,
}: {
  claim: string;
  evidence: string;
  detail?: EvidenceDrawerModel;
  children: ReactNode;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const pathId = useId();
  const reduce = useReducedMotion();

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
        <SheetContent side="right" title="Evidence" className="glass-floating w-[min(28rem,100%)]">
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
                className={reduce ? undefined : "path-stroke"}
                pathLength={1}
              />
              <circle cx="272" cy="24" r="4" fill="var(--accent)" />
            </svg>
            {detail ? (
              <ol className="space-y-3 text-sm">
                <li>
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Job claim</p>
                  <p className="mt-1 font-medium">{detail.factor}</p>
                </li>
                <li className="border-l border-border/80 pl-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Rule</p>
                  <p className="mt-1">{detail.rule}</p>
                </li>
                <li className="border-l border-border/80 pl-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Job evidence</p>
                  {detail.jobEvidence.length ? (
                    detail.jobEvidence.map((item) => <HighlightedText key={item} text={item} />)
                  ) : (
                    <p className="mt-1 text-muted-foreground">No posting clause stored.</p>
                  )}
                </li>
                <li className="border-l border-border/80 pl-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Candidate evidence</p>
                  {detail.missingCandidate || detail.candidateEvidence.length === 0 ? (
                    <p className="mt-1 text-muted-foreground">No supporting candidate evidence found.</p>
                  ) : (
                    detail.candidateEvidence.map((item) => (
                      <p key={item} className="mt-1 leading-relaxed">
                        {item}
                      </p>
                    ))
                  )}
                </li>
                <li>
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Result</p>
                  <StatusLabel kind={detail.resultKind} label={detail.result} />
                  <p className="mt-1 text-muted-foreground">{detail.explanation}</p>
                </li>
              </ol>
            ) : (
              <>
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
              </>
            )}
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
