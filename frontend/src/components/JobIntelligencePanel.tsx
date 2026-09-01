import { FileSearch } from "lucide-react";
import { ErrorBanner } from "./ErrorBanner";
import { LoadingState } from "./LoadingState";
import type { JobIntelligence } from "../lib/types";

function ChipList({ items }: { items: string[] }) {
  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {items.map((item) => (
        <span
          key={item}
          className="rounded-lg bg-muted px-2.5 py-1 text-xs font-medium text-foreground"
        >
          {item}
        </span>
      ))}
    </div>
  );
}

function TextList({ items }: { items: string[] }) {
  return (
    <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

export function JobIntelligencePanel({
  intelligence,
  loading,
  extracting,
  disabled = false,
  error,
  onExtract,
}: {
  intelligence: JobIntelligence | null;
  loading: boolean;
  extracting: boolean;
  disabled?: boolean;
  error: unknown;
  onExtract: () => void;
}) {
  return (
    <section
      className="card space-y-4 p-6"
      aria-labelledby="job-intelligence-heading"
      aria-busy={loading || extracting}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="job-intelligence-heading" className="font-display text-2xl font-semibold">
            Extracted requirements
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Generate grounded requirements from the stored posting only when you choose.
          </p>
        </div>
        <button
          type="button"
          className={intelligence ? "btn-secondary" : "btn-primary"}
          onClick={onExtract}
          disabled={loading || extracting || disabled}
          aria-busy={extracting}
        >
          <FileSearch className="h-4 w-4" aria-hidden />
          {extracting
            ? "Extracting…"
            : intelligence
              ? "Re-extract requirements"
              : "Extract requirements"}
        </button>
      </div>

      <ErrorBanner error={error} />

      {loading ? (
        <div role="status" aria-live="polite">
          <LoadingState label="Loading stored requirements…" />
        </div>
      ) : null}

      {!loading && !intelligence ? (
        <p className="text-sm text-muted-foreground">
          Requirements have not been extracted for this job.
        </p>
      ) : null}

      {intelligence ? (
        <div className="space-y-4">
          {intelligence.required_skills.length ? (
            <div>
              <h3 className="text-sm font-semibold">Required skills</h3>
              <ChipList items={intelligence.required_skills} />
            </div>
          ) : null}
          {intelligence.preferred_skills.length ? (
            <div>
              <h3 className="text-sm font-semibold">Preferred skills</h3>
              <ChipList items={intelligence.preferred_skills} />
            </div>
          ) : null}
          {intelligence.tech_stack.length ? (
            <div>
              <h3 className="text-sm font-semibold">Technology stack</h3>
              <ChipList items={intelligence.tech_stack} />
            </div>
          ) : null}
          {intelligence.years_experience != null ? (
            <p className="text-sm">
              Experience requirement:{" "}
              <strong>
                {intelligence.years_experience}{" "}
                {intelligence.years_experience === 1 ? "year" : "years"}
              </strong>
            </p>
          ) : null}
          {intelligence.education_requirements.length ? (
            <div>
              <h3 className="text-sm font-semibold">Education requirements</h3>
              <TextList items={intelligence.education_requirements} />
            </div>
          ) : null}
          {intelligence.seniority ? (
            <p className="text-sm">
              Seniority: <strong>{intelligence.seniority}</strong>
            </p>
          ) : null}
          {intelligence.responsibilities.length ? (
            <div>
              <h3 className="text-sm font-semibold">Responsibilities</h3>
              <TextList items={intelligence.responsibilities} />
            </div>
          ) : null}
          {intelligence.likely_interview_focus.length ? (
            <div>
              <h3 className="text-sm font-semibold">Likely interview focus</h3>
              <TextList items={intelligence.likely_interview_focus} />
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
