import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { LoadingState } from "./LoadingState";

export function ProtectedRoute() {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--bg)]">
        <LoadingState label="Checking your session…" />
      </div>
    );
  }

  if (!user) {
    // Jobs keeps its tab, filters, and selection in the query string.
    return <Navigate to="/login" state={{ from: `${location.pathname}${location.search}${location.hash}` }} replace />;
  }

  return <Outlet />;
}
