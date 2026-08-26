import { Link, Navigate } from "react-router-dom";
import { EmptyState } from "../components/EmptyState";
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
    <EmptyState
      title={kind === "prepare" ? "Pick a job to prepare" : "Pick a job to analyze"}
      description="Discover a role first. Analyze and Prepare stay contextual under that job — CareerPilot does not invent a workspace without one."
      action={
        <Link to="/jobs" className="btn-primary">
          Open Discover
        </Link>
      }
    />
  );
}
