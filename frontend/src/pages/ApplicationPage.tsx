import { Navigate, useParams } from "react-router-dom";
import { PrepareApplicationWorkspace } from "../components/PrepareApplicationWorkspace";
import { getSelectedJobId } from "../lib/session";

/** Legacy route wrapper. Prefer /jobs/:jobId/prepare. */
export function ApplicationPage() {
  const params = useParams();
  const jobId = params.jobId || getSelectedJobId();
  if (!jobId) return <Navigate to="/jobs" replace />;
  return <PrepareApplicationWorkspace jobId={jobId} />;
}
