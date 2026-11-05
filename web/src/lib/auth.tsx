import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, get, household, post, setUnauthorizedHandler, tokenStore } from "./api";
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

  // keepQueue: a session that ran out keeps the changes made offline for the next sign-in of the same account
  const leave = useCallback((keepQueue: boolean) => {
    tokenStore.clear();
    navigator.serviceWorker?.controller?.postMessage("clear");   // the offline copy belongs to the person who just left
    if (!keepQueue) { try { localStorage.removeItem("pam.queue"); localStorage.removeItem("pam.queue.owner"); } catch { /* ignore */ } }
    household.set(null);          // an admin's "viewing household X" must never leak into the next sign-in
    setMe(null);
    qc.clear();
  }, [qc]);
  const logout = useCallback(() => leave(false), [leave]);

  useEffect(() => {
    setUnauthorizedHandler(() => { setExpired(true); leave(true); });
    if (!tokenStore.get()) return;
    get<Me>("/auth/me").then(setMe).catch((e) => { if (e instanceof ApiError && e.status === 401) tokenStore.clear(); }).finally(() => setLoading(false));
  }, [leave]);

  // changes queued by someone else are never sent as the person who just signed in
  const adopt = (u: Me) => {
    try {
      if (localStorage.getItem("pam.queue.owner") !== u.email) localStorage.removeItem("pam.queue");
      localStorage.setItem("pam.queue.owner", u.email);
    } catch { /* ignore */ }
  };

  const login = useCallback(async (email: string, password: string) => {
    const r = await post<LoginOut>("/auth/login", { email, password });
    tokenStore.set(r.access_token);
    household.set(null);
    setExpired(false);
    adopt(r.user);
    setMe(r.user);
  }, []);

  const register = useCallback(async (email: string, password: string, name: string) => {
    const r = await post<LoginOut>("/auth/register", { email, password, name });
    tokenStore.set(r.access_token);
    household.set(null);
    setExpired(false);
    adopt(r.user);
    setMe(r.user);
  }, []);

  const google = useCallback(async () => {
    const id_token = await googleIdToken();
    if (!id_token) return;
    const r = await post<LoginOut>("/auth/firebase", { id_token });
    tokenStore.set(r.access_token);
    household.set(null);
    setExpired(false);
    adopt(r.user);
    setMe(r.user);
  }, []);

  const value = useMemo(() => ({ me, loading, login, register, google, logout, expired }), [me, loading, login, register, google, logout, expired]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
