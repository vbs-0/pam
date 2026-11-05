import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { get, household, post, setUnauthorizedHandler, tokenStore } from "./api";
import { googleIdToken } from "./firebase";
import type { LoginOut, Me } from "./types";

interface AuthState {
  me: Me | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string) => Promise<void>;
  google: () => Promise<void>;
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
    household.set(null);          // an admin's "viewing household X" must never leak into the next sign-in
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
    household.set(null);
    setExpired(false);
    setMe(r.user);
  }, []);

  const register = useCallback(async (email: string, password: string, name: string) => {
    const r = await post<LoginOut>("/auth/register", { email, password, name });
    tokenStore.set(r.access_token);
    household.set(null);
    setExpired(false);
    setMe(r.user);
  }, []);

  const google = useCallback(async () => {
    const id_token = await googleIdToken();
    if (!id_token) return;
    const r = await post<LoginOut>("/auth/firebase", { id_token });
    tokenStore.set(r.access_token);
    household.set(null);
    setExpired(false);
    setMe(r.user);
  }, []);

  const value = useMemo(() => ({ me, loading, login, register, google, logout, expired }), [me, loading, login, register, google, logout, expired]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
