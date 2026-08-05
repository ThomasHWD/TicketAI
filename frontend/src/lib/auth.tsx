import { createContext, useContext, useState, useCallback, useEffect } from "react";
import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  login as apiLogin,
  apiFetch,
  TOKEN_KEY,
  USER_KEY,
  type AuthUser,
} from "./api";

interface AuthContextValue {
  user: AuthUser | null;
  token: string | null;
  isAuthenticated: boolean;
  isBackoffice: boolean;
  userDomaines: string[];
  isChef: boolean;
  groupesChef: { id: string; nom: string; domaine: string }[];
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function readStoredUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

function readStoredToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(readStoredUser);
  const [token, setToken] = useState<string | null>(readStoredToken);

  const refreshUser = useCallback(async () => {
    const res = await apiFetch("/api/v1/auth/me");
    if (!res.ok) return;
    const fresh: AuthUser = await res.json();
    try { localStorage.setItem(USER_KEY, JSON.stringify(fresh)); } catch { /* ignore */ }
    setUser(fresh);
  }, []);

  const { data: freshUser } = useQuery({
    queryKey: ["auth", "me"],
    queryFn: async () => {
      const res = await apiFetch("/api/v1/auth/me");
      if (!res.ok) return null;
      return res.json() as Promise<AuthUser>;
    },
    enabled: !!token,
  });

  useEffect(() => {
    if (!freshUser) return;
    try { localStorage.setItem(USER_KEY, JSON.stringify(freshUser)); } catch { /* ignore */ }
    setUser(freshUser);
  }, [freshUser]);

  const login = useCallback(async (username: string, password: string) => {
    const res = await apiLogin(username, password);
    try {
      localStorage.setItem(TOKEN_KEY, res.access_token);
      localStorage.setItem(USER_KEY, JSON.stringify(res.user));
    } catch {
      /* mode privé, etc. */
    }
    setToken(res.access_token);
    setUser(res.user);
  }, []);

  const logout = useCallback(() => {
    try {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    } catch {
      /* ignore */
    }
    setToken(null);
    setUser(null);
  }, []);

  const userDomaines = (user?.groupes ?? [])
    .map((g) => g.domaine)
    .filter((d): d is string => !!d);

  const groupesChef = (user?.groupes ?? []).filter((g) => g.is_chef);
  const isChef = groupesChef.length > 0;
  const isBackoffice = userDomaines.length > 0 || user?.role === "ADMIN";

  return (
    <AuthContext.Provider
      value={{ user, token, isAuthenticated: !!token, isBackoffice, userDomaines, isChef, groupesChef, login, logout, refreshUser }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth doit être utilisé dans un <AuthProvider>");
  return ctx;
}
