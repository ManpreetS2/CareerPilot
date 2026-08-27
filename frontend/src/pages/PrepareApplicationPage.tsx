import { Link, useParams } from "react-router-dom";
import { EmptyState } from "../components/EmptyState";
import { PrepareApplicationWorkspace } from "../components/PrepareApplicationWorkspace";
import { getSelectedJobId } from "../lib/session";

export function PrepareApplicationPage() {
  const params = useParams();
  const jobId = params.jobId || getSelectedJobId();
  if (!jobId) {
    return (
      <EmptyState
        title="No application selected"
        description="Pick a role from Jobs to review tailored materials."
        action={
          <Link to="/jobs" className="btn-primary">
            Browse jobs
          </Link>
        }
      />
    );
  }
  return <PrepareApplicationWorkspace jobId={jobId} />;
}
