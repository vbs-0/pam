// Thin typed fetch client. Tokens live in sessionStorage (cleared when the tab closes); the server decides roles.
export const BASE = "/api/v1";
const KEY = "pam.token";

export const tokenStore = {
  get: () => { try { return sessionStorage.getItem(KEY); } catch { return null; } },
  set: (t: string) => { try { sessionStorage.setItem(KEY, t); } catch { /* private mode: nothing to do */ } },
  clear: () => { try { sessionStorage.removeItem(KEY); } catch { /* ignore */ } },
};

// ADMIN support view: customer endpoints take ?user_id=; the shell sets this when an admin opens a household.
const HKEY = "pam.household";
export const household = {
  get: () => { try { return sessionStorage.getItem(HKEY); } catch { return null; } },
  set: (v: string | null) => { try { v ? sessionStorage.setItem(HKEY, v) : sessionStorage.removeItem(HKEY); } catch { /* ignore */ } },
};

export class ApiError extends Error {
  status: number;
  requestId?: string;
  fields?: { field: string; message: string }[];
  constructor(status: number, message: string, requestId?: string, fields?: { field: string; message: string }[]) {
    super(message);
    this.status = status; this.requestId = requestId; this.fields = fields;
  }
}

let onUnauthorized: () => void = () => {};
export const setUnauthorizedHandler = (fn: () => void) => { onUnauthorized = fn; };

type Query = Record<string, string | number | boolean | null | undefined>;
const qs = (q?: Query) => {
  const p = new URLSearchParams();
  Object.entries(q ?? {}).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") p.set(k, String(v)); });
  const s = p.toString();
  return s ? `?${s}` : "";
};

export async function api<T = unknown>(method: string, path: string, opts: { query?: Query; body?: unknown; auth?: boolean } = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const hh = household.get();
  if (hh && path.startsWith("/me")) opts = { ...opts, query: { ...opts.query, user_id: hh } };
  const token = tokenStore.get();
  if (token && opts.auth !== false) headers.Authorization = `Bearer ${token}`;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}${qs(opts.query)}`, { method, headers, body: opts.body === undefined ? undefined : JSON.stringify(opts.body) });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check your connection and try again.");
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: any = null;
  try { data = text ? JSON.parse(text) : null; } catch { /* non-JSON error page from a proxy */ }
  if (!res.ok) {
    if (res.status === 401 && token && opts.auth !== false) onUnauthorized();
    const detail = data?.detail ?? (res.status >= 500 ? "Something went wrong on the server. Try again in a moment." : res.statusText);
    throw new ApiError(res.status, typeof detail === "string" ? detail : "Request failed", data?.request_id, data?.errors);
  }
  return data as T;
}

export const get = <T,>(path: string, query?: Query) => api<T>("GET", path, { query });
export const post = <T,>(path: string, body?: unknown) => api<T>("POST", path, { body: body ?? {} });
export const patch = <T,>(path: string, body: unknown) => api<T>("PATCH", path, { body });
export const put = <T,>(path: string, body: unknown) => api<T>("PUT", path, { body });
export const del = <T,>(path: string) => api<T>("DELETE", path);
