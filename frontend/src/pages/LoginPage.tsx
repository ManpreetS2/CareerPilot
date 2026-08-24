import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Plane } from "lucide-react";
import { ErrorBanner } from "../components/ErrorBanner";
import { APP_NAME, APP_TAGLINE } from "../lib/config";
import { useAuth } from "../lib/auth";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const redirectTo = (location.state as { from?: string } | null)?.from || "/dashboard";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await login(email, password);
      navigate(redirectTo, { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--bg)] px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex flex-col items-center gap-2 text-center">
          <span className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-accent-600/10 text-accent-700 dark:bg-accent-400/10 dark:text-accent-300">
            <Plane className="h-5 w-5" aria-hidden />
          </span>
          <h1 className="font-display text-2xl font-semibold">{APP_NAME}</h1>
          <p className="text-sm text-ink-500">{APP_TAGLINE}</p>
        </div>

        <div className="card space-y-5 p-6">
          <h2 className="font-display text-xl font-semibold">Log in</h2>
          <ErrorBanner error={error} />
          <form onSubmit={onSubmit} className="space-y-4">
            <label>
              <span className="label">Email</span>
              <input
                className="input"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </label>
            <label>
              <span className="label">Password</span>
              <input
                className="input"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            <button type="submit" className="btn-primary w-full justify-center" disabled={loading}>
              {loading ? "Logging in…" : "Log in"}
            </button>
          </form>
          <p className="text-center text-sm text-ink-500">
            Don&apos;t have an account?{" "}
            <Link to="/signup" className="font-semibold text-accent-700 dark:text-accent-300">
              Sign up
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
