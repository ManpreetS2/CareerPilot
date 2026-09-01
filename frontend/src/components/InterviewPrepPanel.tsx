import { useState } from "react";
import { MessagesSquare, Sparkles } from "lucide-react";
import { ErrorBanner } from "./ErrorBanner";
import { LoadingState } from "./LoadingState";
import { api, ApiClientError } from "../lib/api";
import type { InterviewAnswerFeedback, InterviewPrep } from "../lib/types";

function TextList({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) {
    return <p className="mt-2 text-sm text-muted-foreground">{empty}</p>;
  }
  return (
    <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

function AnswerPractice({ jobId, questions }: { jobId: string; questions: string[] }) {
  const [question, setQuestion] = useState(questions[0] ?? "");
  const [answer, setAnswer] = useState("");
  const [feedback, setFeedback] = useState<InterviewAnswerFeedback | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function handleSubmit() {
    if (!question || !answer.trim()) return;
    setSubmitting(true);
    setError(null);
    setFeedback(null);
    try {
      const result = await api.getInterviewAnswerFeedback(jobId, question, answer);
      setFeedback(result);
    } catch (err) {
      setError(err instanceof ApiClientError ? err : err);
    } finally {
      setSubmitting(false);
    }
  }

  if (questions.length === 0) return null;

  return (
    <div className="border-t border-[var(--line)] pt-4">
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        <Sparkles className="h-4 w-4 text-accent-600 dark:text-accent-300" aria-hidden />
        Practice an answer
      </h3>
      <p className="mt-1 text-sm text-muted-foreground">
        Pick one of the questions above, type how you'd answer it, and get brief feedback on how
        it's delivered. Feedback is generated fresh each time and never saved.
      </p>

      <div className="mt-3 space-y-3">
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-muted-foreground">Question</span>
          <select
            className="input"
            value={question}
            onChange={(event) => {
              setQuestion(event.target.value);
              setFeedback(null);
            }}
          >
            {questions.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-sm">
          <span className="text-muted-foreground">Your answer</span>
          <textarea
            className="input min-h-[6rem] resize-y"
            value={answer}
            onChange={(event) => setAnswer(event.target.value)}
            placeholder="Type how you'd answer this out loud…"
          />
        </label>

        <button
          type="button"
          className="btn-primary"
          onClick={() => void handleSubmit()}
          disabled={submitting || !answer.trim()}
          aria-busy={submitting}
        >
          {submitting ? "Getting feedback…" : "Get feedback"}
        </button>

        <ErrorBanner error={error} />

        {feedback ? (
          <div
            role="status"
            className="card border-accent-300/60 bg-accent-50/70 p-4 text-sm text-accent-900 dark:border-accent-800 dark:bg-accent-950/30 dark:text-accent-100"
          >
            {feedback.feedback}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function InterviewPrepPanel({
  jobId,
  prep,
  loading,
  generating,
  error,
  onPrepare,
}: {
  jobId: string;
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
          <p className="mt-1 text-sm text-muted-foreground">
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
        <p className="text-sm text-muted-foreground">
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
          <AnswerPractice jobId={jobId} questions={prep.likely_questions} />
        </div>
      ) : null}
    </section>
  );
}
