import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "./api";
import { clearCandidateSession } from "./session";
import type { User } from "./types";

type AuthState = {
  user: User | null;
  /** True only while the initial /api/auth/me check is in flight — lets
   * ProtectedRoute avoid a flash-redirect to /login before we actually
   * know whether the session cookie is valid. */
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api
      .me()
      .then((current) => {
        if (!cancelled) setUser(current);
      })
      .catch(() => {
        if (!cancelled) setUser(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function login(email: string, password: string) {
    const current = await api.login(email, password);
    setUser(current);
  }

  async function signup(email: string, password: string) {
    const current = await api.signup(email, password);
    setUser(current);
  }

  async function logout() {
    try {
      await api.logout();
    } finally {
      // Clear client state even if the network call itself failed — an
      // already-invalid/expired session shouldn't leave the user stuck
      // looking logged in.
      setUser(null);
      clearCandidateSession();
    }
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth requires AuthProvider");
  return ctx;
}
