import { MessagesSquare } from "lucide-react";
import { ErrorBanner } from "./ErrorBanner";
import { LoadingState } from "./LoadingState";
import type { InterviewPrep } from "../lib/types";

function TextList({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) {
    return <p className="mt-2 text-sm text-ink-500">{empty}</p>;
  }
  return (
    <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink-600 dark:text-ink-300">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

export function InterviewPrepPanel({
  prep,
  loading,
  generating,
  error,
  onPrepare,
}: {
  prep: InterviewPrep | null;
  loading: boolean;
  generating: boolean;
  error: unknown;
  onPrepare: () => void;
}) {
  return (
    <section
      className="card space-y-4 p-6"
      aria-labelledby="interview-prep-heading"
      aria-busy={loading || generating}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="interview-prep-heading" className="font-display text-2xl font-semibold">
            Interview prep
          </h2>
          <p className="mt-1 text-sm text-ink-600 dark:text-ink-300">
            Uses stored Job Intelligence, fit-score gaps, and candidate evidence. Generation runs
            only when you ask — this page never calls a provider automatically.
          </p>
        </div>
        <button
          type="button"
          className="btn-primary"
          onClick={onPrepare}
          disabled={loading || generating}
          aria-busy={generating}
        >
          <MessagesSquare className="h-4 w-4" aria-hidden />
          {generating ? "Preparing…" : prep ? "Refresh interview prep" : "Prepare interview"}
        </button>
      </div>

      <ErrorBanner error={error} />
      {loading ? (
        <div role="status" aria-live="polite">
          <LoadingState label="Loading interview prep…" />
        </div>
      ) : null}

      {!loading && !prep ? (
        <p className="text-sm text-ink-500">
          No interview prep stored yet. Prepare interview to generate a grounded baseline.
        </p>
      ) : null}

      {prep ? (
        <div className="space-y-4">
          <div>
            <h3 className="text-sm font-semibold">Likely questions</h3>
            <TextList items={prep.likely_questions} empty="None generated." />
          </div>
          <div>
            <h3 className="text-sm font-semibold">Candidate-supported talking points</h3>
            <TextList
              items={prep.talking_points}
              empty="None. Missing skills are listed as gaps, not strengths."
            />
          </div>
          <div>
            <h3 className="text-sm font-semibold">Gaps to address</h3>
            <TextList items={prep.gaps_to_address} empty="No stored gaps." />
          </div>
        </div>
      ) : null}
    </section>
  );
}
