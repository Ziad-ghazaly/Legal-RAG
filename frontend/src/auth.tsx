import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { api, getTokens, logout as apiLogout, type Me } from "./api";

type Auth = { me: Me | undefined; loading: boolean; logout: () => Promise<void> };
const Ctx = createContext<Auth>({ me: undefined, loading: true, logout: async () => {} });

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["me"],
    queryFn: () => api<Me>("/auth/me"),
    enabled: !!getTokens(),
    retry: false,
  });
  useEffect(() => {
    const onLogout = () => qc.clear();
    window.addEventListener("auth:logout", onLogout);
    return () => window.removeEventListener("auth:logout", onLogout);
  }, [qc]);
  const logout = async () => {
    await apiLogout();
    qc.clear();
  };
  return (
    <Ctx.Provider value={{ me: getTokens() ? data : undefined, loading: !!getTokens() && isLoading, logout }}>
      {children}
    </Ctx.Provider>
  );
}

export const useAuth = () => useContext(Ctx);

export function RequireAuth({ children, roles }: { children: ReactNode; roles?: string[] }) {
  const { me, loading } = useAuth();
  const location = useLocation();
  if (loading) return <p className="p-8 text-muted">جارٍ التحميل…</p>;
  if (!me) return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  if (roles && !roles.includes(me.role)) return <Navigate to="/" replace />;
  return <>{children}</>;
}
