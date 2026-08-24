import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Plane } from "lucide-react";
import { ErrorBanner } from "../components/ErrorBanner";
import { APP_NAME, APP_TAGLINE } from "../lib/config";
import { useAuth } from "../lib/auth";

const MIN_PASSWORD_LENGTH = 8;

export function SignupPage() {
  const { signup } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(new Error(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`));
      return;
    }
    setLoading(true);
    try {
      await signup(email, password);
      navigate("/dashboard", { replace: true });
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
          <h2 className="font-display text-xl font-semibold">Create your account</h2>
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
                autoComplete="new-password"
                required
                minLength={MIN_PASSWORD_LENGTH}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
              <span className="mt-1 block text-xs text-ink-500">
                At least {MIN_PASSWORD_LENGTH} characters.
              </span>
            </label>
            <button type="submit" className="btn-primary w-full justify-center" disabled={loading}>
              {loading ? "Creating account…" : "Sign up"}
            </button>
          </form>
          <p className="text-center text-sm text-ink-500">
            Already have an account?{" "}
            <Link to="/login" className="font-semibold text-accent-700 dark:text-accent-300">
              Log in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
