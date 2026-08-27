import { Link, Navigate } from "react-router-dom";
import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/ui/page-header";
import { getSelectedJobId } from "../lib/session";

export function WorkflowJobRedirect({ kind }: { kind: "analyze" | "prepare" }) {
  const jobId = getSelectedJobId();
  if (jobId) {
    return (
      <Navigate
        to={kind === "prepare" ? `/jobs/${jobId}/prepare` : `/jobs/${jobId}`}
        replace
      />
    );
  }
  return (
    <div className="space-y-6">
      <PageHeader
        title={kind === "prepare" ? "Prepare" : "Analyze"}
        description="These steps stay attached to a specific job. Discover a role first, then open it from here."
      />
      <EmptyState
        title={kind === "prepare" ? "Pick a job to prepare" : "Pick a job to analyze"}
        description="Discover a role first. Analyze and Prepare stay contextual under that job — CareerPilot does not invent a workspace without one."
        action={
          <Link to="/jobs" className="btn-primary">
            Open Discover
          </Link>
        }
      />
    </div>
  );
}
