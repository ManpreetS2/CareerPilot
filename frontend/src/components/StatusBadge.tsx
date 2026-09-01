import { AlertTriangle, CheckCircle2, CircleDashed, Clock, ShieldCheck } from "lucide-react";

export function StatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  const tone =
    normalized === "verified" || normalized === "approved" || normalized === "offer"
      ? "bg-muted text-primary"
      : normalized === "rejected" || normalized === "flagged" || normalized === "withdrawn"
        ? "bg-muted text-danger"
        : normalized === "pending_review" || normalized === "discovered" || normalized === "interviewing"
          ? "bg-muted text-warning"
          : "bg-muted text-muted-foreground";

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
