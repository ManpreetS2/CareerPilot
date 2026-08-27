import { useState } from "react";
import { Clipboard, ClipboardCheck, ExternalLink, Wand2 } from "lucide-react";
import { ErrorBanner } from "./ErrorBanner";
import { api } from "../lib/api";
import type { ApplicationPackage, FormFillResult, Job } from "../lib/types";

export function AssistedApplyPanel({
  job,
  materials,
}: {
  job: Job;
  materials: ApplicationPackage;
}) {
  const [filling, setFilling] = useState(false);
  const [fillResult, setFillResult] = useState<FormFillResult | null>(null);
  const [fillError, setFillError] = useState<unknown>(null);
  const [copiedField, setCopiedField] = useState<string | null>(null);

  async function fillApplication() {
    if (!job.id) return;
    setFilling(true);
    setFillError(null);
    try {
      setFillResult(await api.fillApplication(job.id));
    } catch (err) {
      setFillError(err);
    } finally {
      setFilling(false);
    }
  }

  async function copyValue(field: string, value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopiedField(field);
      setTimeout(() => setCopiedField((current) => (current === field ? null : current)), 1500);
    } catch {
      // Clipboard access can be denied; values remain visible.
    }
  }

  return (
    <section className="card p-6">
      <h2 className="font-display text-2xl font-semibold">Assisted apply</h2>
      {materials.approval_status !== "approved" ? (
        <p className="mt-2 text-sm text-muted-foreground">
          Unlocks once this application is approved above. Supports Greenhouse and Lever postings.
        </p>
      ) : (
        <>
          <p className="mt-2 text-sm text-muted-foreground">
            Runs on the server against the real application form (Greenhouse or Lever) to work out
            what can be confidently filled and what can&apos;t — it never submits, and it has no
            connection to your own browser. Copy each value below into the form you open yourself.
          </p>
          <ErrorBanner error={fillError} />
          <button
            type="button"
            className="btn-primary mt-4"
            disabled={filling}
            onClick={() => void fillApplication()}
          >
            <Wand2 className={`h-4 w-4 ${filling ? "animate-pulse" : ""}`} aria-hidden />
            {filling ? "Filling…" : "Fill Application Form"}
          </button>
          {fillResult ? (
            <div className="mt-4 space-y-3">
              {fillResult.ats_platform === "unsupported" ? (
                <p className="text-sm text-muted-foreground">{fillResult.error_message}</p>
              ) : fillResult.status === "failed" ? (
                <p className="text-sm text-danger">{fillResult.error_message}</p>
              ) : (
                <>
                  <p className="text-sm text-muted-foreground">
                    Detected <strong className="capitalize">{fillResult.ats_platform}</strong> —{" "}
                    {fillResult.filled_fields.length} value(s) matched,{" "}
                    {fillResult.flagged_fields.length} need your input.
                  </p>
                  {fillResult.filled_fields.length > 0 ? (
                    <div>
                      <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                        Copy these into the form
                      </h3>
                      <ul className="mt-1 space-y-1.5">
                        {fillResult.filled_fields.map((field) => (
                          <li
                            key={field.field}
                            className="flex items-center justify-between gap-3 rounded-[var(--radius-sm)] border border-border px-3 py-2 text-sm"
                          >
                            <span className="min-w-0">
                              <span className="capitalize text-muted-foreground">
                                {field.field.replaceAll("_", " ")}:
                              </span>{" "}
                              <span className="font-medium">{field.value}</span>
                            </span>
                            <button
                              type="button"
                              className="btn-ghost shrink-0 px-2 py-1 text-xs"
                              onClick={() => void copyValue(field.field, field.value)}
                            >
                              {copiedField === field.field ? (
                                <>
                                  <ClipboardCheck className="h-3.5 w-3.5" aria-hidden />
                                  Copied
                                </>
                              ) : (
                                <>
                                  <Clipboard className="h-3.5 w-3.5" aria-hidden />
                                  Copy
                                </>
                              )}
                            </button>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {fillResult.flagged_fields.length > 0 ? (
                    <div>
                      <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                        Needs your input
                      </h3>
                      <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                        {fillResult.flagged_fields.map((field) => (
                          <li key={field.field}>
                            <span className="font-medium">{field.field.replaceAll("_", " ")}</span> —{" "}
                            {field.reason}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  <a href={job.url} target="_blank" rel="noreferrer" className="btn-secondary">
                    <ExternalLink className="h-4 w-4" aria-hidden />
                    Open form to finish and submit
                  </a>
                </>
              )}
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}
