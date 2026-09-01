import { AlertTriangle } from "lucide-react";
import { ApiClientError } from "../lib/api";

export function ErrorBanner({ error, heading }: { error: unknown; heading?: string }) {
  if (!error) return null;
  const status = error instanceof ApiClientError ? error.status : null;
  const message =
    error instanceof ApiClientError
      ? error.message
      : error instanceof Error
        ? error.message
        : "Something went wrong";
  const title =
    heading ??
    (status === 409
      ? "Needs a decision"
      : status === 422
        ? "Could not use that input"
        : status === 404
          ? "Not found"
          : status === 401 || status === 403
            ? "Sign in required"
            : status === 0
              ? "Backend unreachable"
              : status && status >= 500
                ? "Server error"
                : null);

  return (
    <div
      role="alert"
      className="notice-danger mb-4 rounded-[var(--radius-md)] p-4 text-danger"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" aria-hidden />
        <div>
          {title ? <p className="font-semibold">{title}</p> : null}
          <p className={title ? "mt-1 text-sm" : "font-semibold"}>{message}</p>
        </div>
      </div>
    </div>
  );
}
