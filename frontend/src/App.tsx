import { Navigate, Route, Routes, useParams } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { LoadingState } from "./components/LoadingState";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { useAuth } from "./lib/auth";
import { ApplicationsPage } from "./pages/ApplicationsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { JobDetailPage } from "./pages/JobDetailPage";
import { JobsPage } from "./pages/JobsPage";
import { LandingPage } from "./pages/LandingPage";
import { LoginPage } from "./pages/LoginPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { PrepareApplicationPage } from "./pages/PrepareApplicationPage";
import { PrivacyPage } from "./pages/PrivacyPage";
import { ProfilePage } from "./pages/ProfilePage";
import { ResumePage } from "./pages/ResumePage";
import { SettingsPage } from "./pages/SettingsPage";
import { SignupPage } from "./pages/SignupPage";
import { GrowthPage } from "./pages/GrowthPage";
import { WorkflowJobRedirect } from "./pages/WorkflowJobRedirect";

function HomeRoute() {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <LoadingState label="Loading…" />
      </div>
    );
  }
  if (user) return <Navigate to="/dashboard" replace />;
  return <LandingPage />;
}

function LegacyPrepareRedirect() {
  const { jobId } = useParams();
  return <Navigate to={`/jobs/${jobId}/prepare`} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomeRoute />} />
      <Route path="login" element={<LoginPage />} />
      <Route path="signup" element={<SignupPage />} />
      <Route path="privacy" element={<PrivacyPage />} />
      <Route element={<ProtectedRoute />}>
        <Route path="onboarding" element={<OnboardingPage />} />
        <Route element={<AppShell />}>
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="profile" element={<ProfilePage />} />
          <Route path="jobs" element={<JobsPage />} />
          <Route path="jobs/:jobId" element={<JobDetailPage />} />
          <Route path="jobs/:jobId/prepare" element={<PrepareApplicationPage />} />
          <Route path="analyze" element={<WorkflowJobRedirect kind="analyze" />} />
          <Route path="prepare" element={<WorkflowJobRedirect kind="prepare" />} />
          <Route path="track" element={<ApplicationsPage />} />
          <Route path="growth" element={<GrowthPage />} />
          <Route path="career-growth" element={<Navigate to="/growth" replace />} />
          <Route path="resume" element={<ResumePage />} />
          <Route path="resume/:versionId" element={<ResumePage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="applications" element={<ApplicationsPage />} />
          <Route path="applications/:jobId" element={<LegacyPrepareRedirect />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Route>
      </Route>
    </Routes>
  );
}
