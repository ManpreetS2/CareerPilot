import { useId, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { AuthFrame } from "../components/AuthFrame";
import { ErrorBanner } from "../components/ErrorBanner";
import { useAuth } from "../lib/auth";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const redirectTo = (location.state as { from?: string } | null)?.from || "/dashboard";
  const errorId = useId();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (loading) return;
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
    <AuthFrame title="Log in">
      <div id={errorId}>
        <ErrorBanner error={error} heading="Couldn't sign in" />
      </div>
      <form onSubmit={onSubmit} className="space-y-4" aria-describedby={error ? errorId : undefined}>
        <label htmlFor="login-email">
          <span className="label">Email</span>
          <input
            id="login-email"
            className="input"
            type="email"
            autoComplete="email"
            required
            aria-invalid={Boolean(error)}
            aria-describedby={error ? errorId : undefined}
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>
        <label htmlFor="login-password">
          <span className="label">Password</span>
          <input
            id="login-password"
            className="input"
            type="password"
            autoComplete="current-password"
            required
            aria-invalid={Boolean(error)}
            aria-describedby={error ? errorId : undefined}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <button
          type="submit"
          className="btn-primary w-full justify-center"
          disabled={loading}
          aria-busy={loading}
        >
          {loading ? "Logging in…" : "Log in"}
        </button>
      </form>
      <p className="text-center text-sm text-muted-foreground">
        Don&apos;t have an account?{" "}
        <Link to="/signup" className="public-focus font-semibold text-primary">
          Sign up
        </Link>
      </p>
    </AuthFrame>
  );
}
