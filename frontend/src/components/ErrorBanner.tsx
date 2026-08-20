import { AlertTriangle } from "lucide-react";
import { ApiClientError } from "../lib/api";

export function ErrorBanner({ error }: { error: unknown }) {
  if (!error) return null;
  const message =
    error instanceof ApiClientError
      ? error.message
      : error instanceof Error
        ? error.message
        : "Something went wrong";

  return (
    <div
      role="alert"
      className="card mb-4 border-rose-300/70 bg-rose-50/80 p-4 text-danger-600 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-200"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" aria-hidden />
        <p className="font-semibold">{message}</p>
      </div>
    </div>
  );
}
