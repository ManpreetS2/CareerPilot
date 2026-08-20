import { CheckCircle2, CircleDashed, ShieldCheck } from "lucide-react";

export function StatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  const tone =
    normalized === "verified" || normalized === "approved"
      ? "bg-accent-100 text-accent-800 dark:bg-accent-900/40 dark:text-accent-200"
      : normalized === "rejected"
        ? "bg-rose-100 text-danger-600 dark:bg-rose-950/40 dark:text-rose-200"
        : normalized === "pending_review" || normalized === "discovered"
          ? "bg-amber-100 text-warn-600 dark:bg-amber-950/40 dark:text-amber-200"
          : "bg-ink-100 text-ink-700 dark:bg-ink-800 dark:text-ink-100";

  const Icon =
    normalized === "verified" || normalized === "approved"
      ? ShieldCheck
      : normalized === "rejected"
        ? CircleDashed
        : CheckCircle2;

  return (
    <span className={`status-pill capitalize ${tone}`}>
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {status.replaceAll("_", " ")}
    </span>
  );
}
