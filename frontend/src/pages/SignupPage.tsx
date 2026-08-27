import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AuthFrame } from "../components/AuthFrame";
import { ErrorBanner } from "../components/ErrorBanner";
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
      navigate("/onboarding", { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthFrame title="Create your account">
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
          <span className="mt-1 block text-xs text-muted-foreground">
            At least {MIN_PASSWORD_LENGTH} characters.
          </span>
        </label>
        <button type="submit" className="btn-primary w-full justify-center" disabled={loading}>
          {loading ? "Creating account…" : "Sign up"}
        </button>
      </form>
      <p className="text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link to="/login" className="font-semibold text-primary">
          Log in
        </Link>
      </p>
    </AuthFrame>
  );
}
