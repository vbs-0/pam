import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { get, post, setUnauthorizedHandler, tokenStore } from "./api";
import type { LoginOut, Me } from "./types";

interface AuthState {
  me: Me | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  expired: boolean;
}
const Ctx = createContext<AuthState | null>(null);
export const useAuth = () => {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(!!tokenStore.get());
  const [expired, setExpired] = useState(false);

  const logout = useCallback(() => {
    tokenStore.clear();
    setMe(null);
    qc.clear();
  }, [qc]);

  useEffect(() => {
    setUnauthorizedHandler(() => { setExpired(true); logout(); });
    if (!tokenStore.get()) return;
    get<Me>("/auth/me").then(setMe).catch(() => tokenStore.clear()).finally(() => setLoading(false));
  }, [logout]);

  const login = useCallback(async (email: string, password: string) => {
    const r = await post<LoginOut>("/auth/login", { email, password });
    tokenStore.set(r.access_token);
    setExpired(false);
    setMe(r.user);
  }, []);

  const value = useMemo(() => ({ me, loading, login, logout, expired }), [me, loading, login, logout, expired]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
