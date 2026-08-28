import { useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiClientError } from "./api";
import { clearAuthenticatedQueryCache } from "./query-client";
import {
  applyServerProfile,
  bindSessionUser,
  clearCurrentUserSensitiveCache,
} from "./session";
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

async function hydrateProfile(): Promise<void> {
  try {
    const profile = await api.getProfile();
    applyServerProfile(profile.candidate ?? null, profile.preferences ?? null);
  } catch {
    // Keep this user's existing cache if the read fails.
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api
      .me()
      .then(async (current) => {
        bindSessionUser(current.id);
        await hydrateProfile();
        if (!cancelled) setUser(current);
      })
      .catch(async (err) => {
        if (cancelled) return;
        const status = err instanceof ApiClientError ? err.status : undefined;
        if (status === 401 || status === 403) {
          await clearAuthenticatedQueryCache(queryClient);
          bindSessionUser(null);
          setUser(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [queryClient]);

  async function login(email: string, password: string) {
    const current = await api.login(email, password);
    await clearAuthenticatedQueryCache(queryClient);
    bindSessionUser(current.id);
    await hydrateProfile();
    setUser(current);
  }

  async function signup(email: string, password: string) {
    const current = await api.signup(email, password);
    await clearAuthenticatedQueryCache(queryClient);
    bindSessionUser(current.id);
    await hydrateProfile();
    setUser(current);
  }

  async function logout() {
    try {
      await api.logout();
    } catch (err) {
      const status = err instanceof ApiClientError ? err.status : undefined;
      if (status === 0) {
        throw err;
      }
      if (status !== 401 && status !== 204) {
        throw err;
      }
    }
    await clearAuthenticatedQueryCache(queryClient);
    clearCurrentUserSensitiveCache();
    setUser(null);
    bindSessionUser(null);
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
