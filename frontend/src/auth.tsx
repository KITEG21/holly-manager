import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { api, hasToken, onUnauthorized, post, setToken, type Role, type User } from "./api";

interface Session {
  token: string;
  user: User;
}

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (name: string, email: string, password: string) => Promise<User>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

/** A dónde va cada rol al entrar. */
export function homeFor(role: Role): string {
  return { client: "/chat", developer: "/dev", admin: "/admin/leads" }[role];
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(hasToken());

  // Si hay token guardado, recuperamos el usuario
  useEffect(() => {
    if (!hasToken()) return;
    api<User>("/api/auth/me")
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setLoading(false));
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    qc.clear();
  }, [qc]);

  useEffect(() => {
    const handler = () => logout();
    onUnauthorized.addEventListener("unauthorized", handler);
    return () => onUnauthorized.removeEventListener("unauthorized", handler);
  }, [logout]);

  const start = (s: Session) => {
    setToken(s.token);
    setUser(s.user);
    return s.user;
  };

  const value: AuthState = {
    user,
    loading,
    login: async (email, password) => start(await post<Session>("/api/auth/login", { email, password })),
    register: async (name, email, password) =>
      start(await post<Session>("/api/auth/register", { name, email, password })),
    logout,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth used outside AuthProvider");
  return ctx;
}

/** Protege una ruta: sin sesión → login; con otro rol → su propia pantalla de inicio. */
export function RequireRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <div className="p-8 text-sm text-slate-500">Loading…</div>;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (!roles.includes(user.role)) return <Navigate to={homeFor(user.role)} replace />;
  return <>{children}</>;
}
