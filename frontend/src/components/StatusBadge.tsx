import { AlertTriangle, CheckCircle2, CircleDashed, Clock, ShieldCheck } from "lucide-react";

export function StatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  const tone =
    normalized === "verified" || normalized === "approved" || normalized === "offer"
      ? "border border-primary/25 bg-primary/10 text-primary"
      : normalized === "rejected" || normalized === "flagged" || normalized === "withdrawn"
        ? "border border-danger/25 bg-danger/10 text-danger"
        : normalized === "pending_review" || normalized === "discovered" || normalized === "interviewing"
          ? "border border-warning/25 bg-warning/10 text-warning"
          : "border border-border/70 bg-muted/80 text-muted-foreground";

  const Icon =
    normalized === "verified" || normalized === "approved"
      ? ShieldCheck
      : normalized === "rejected" || normalized === "flagged"
        ? AlertTriangle
        : normalized === "stale"
          ? Clock
          : normalized === "discovered" || normalized === "pending_review"
            ? CircleDashed
            : CheckCircle2;

  return (
    <span className={`status-pill capitalize ${tone}`}>
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {status.replaceAll("_", " ")}
    </span>
  );
}
