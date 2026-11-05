// Thin typed fetch client. The token lives in localStorage so a sign-in lasts the server's 7 days; the server decides roles and expiry.
export const BASE = "/api/v1";
const KEY = "pam.token";

export const tokenStore = {
  get: () => { try { return localStorage.getItem(KEY); } catch { return null; } },
  set: (t: string) => { try { localStorage.setItem(KEY, t); } catch { /* private mode: nothing to do */ } },
  clear: () => { try { localStorage.removeItem(KEY); } catch { /* ignore */ } },
};

// ADMIN support view: customer endpoints take ?user_id=; the shell sets this when an admin opens a household.
const HKEY = "pam.household";
export const household = {
  get: () => { try { return sessionStorage.getItem(HKEY); } catch { return null; } },
  set: (v: string | null) => { try { if (v) sessionStorage.setItem(HKEY, v); else sessionStorage.removeItem(HKEY); } catch { /* ignore */ } },
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

// ---- changes made with no connection ----
// A write that cannot reach the server is kept in this browser and sent later with an Idempotency-Key, so a send that
// was cut off after the server acted is recognised and not applied twice. Sign-in, password and upload calls need the
// server and are never queued.
const QKEY = "pam.queue";
export interface Queued { id: string; method: string; path: string; body?: unknown; error?: string }
const readQ = (): Queued[] => { try { return JSON.parse(localStorage.getItem(QKEY) ?? "[]"); } catch { return []; } };
const writeQ = (q: Queued[]) => { try { localStorage.setItem(QKEY, JSON.stringify(q)); } catch { /* storage full or blocked */ } window.dispatchEvent(new Event("pam-queue")); };
export const queueState = () => { const q = readQ(); return { pending: q.filter((x) => !x.error), failed: q.filter((x) => x.error) }; };
export const discardFailed = () => writeQ(readQ().filter((x) => !x.error));
export const retryFailed = () => { writeQ(readQ().map((x) => ({ ...x, error: undefined }))); void flushQueue(); };
const queueable = (m: string, p: string) => m !== "GET" && p.startsWith("/me/") && !/^\/me\/(import|restore|household|export|backup)/.test(p);
const newId = () => (crypto.randomUUID?.() ?? `${Date.now()}${Math.random().toString(36).slice(2)}`).replace(/-/g, "");

let flushing = false;
export async function flushQueue(): Promise<void> {
  if (flushing || !tokenStore.get()) return;
  flushing = true;
  let sent = 0;
  try {
    for (;;) {
      const q = readQ();
      const op = q.find((x) => !x.error);
      if (!op) break;
      try {
        await api(op.method, op.path, { body: op.body, key: op.id, noQueue: true });
        writeQ(readQ().filter((x) => x.id !== op.id)); sent++;
      } catch (e) {
        const st = e instanceof ApiError ? e.status : 0;
        if (st === 0 || st === 401 || st >= 500 || st === 408 || st === 429) break;
        if (op.method === "DELETE" && st === 404) { writeQ(readQ().filter((x) => x.id !== op.id)); sent++; continue; }
        writeQ(readQ().map((x) => (x.id === op.id ? { ...x, error: (e as Error).message } : x)));
      }
    }
  } finally { flushing = false; }
  if (sent) window.dispatchEvent(new Event("pam-synced"));
}
if (typeof window !== "undefined") {
  window.addEventListener("online", () => void flushQueue());
  setInterval(() => void flushQueue(), 20000);
  setTimeout(() => void flushQueue(), 1500);
}

export async function api<T = unknown>(method: string, path: string, opts: { query?: Query; body?: unknown; auth?: boolean; key?: string; noQueue?: boolean } = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const hh = household.get();
  if (hh && path.startsWith("/me")) opts = { ...opts, query: { ...opts.query, user_id: hh } };
  const token = tokenStore.get();
  if (token && opts.auth !== false) headers.Authorization = `Bearer ${token}`;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  const canQueue = !opts.noQueue && queueable(method, path);
  const key = opts.key ?? (canQueue ? newId() : undefined);
  if (key && method !== "GET") headers["Idempotency-Key"] = key;
  if (canQueue && queueState().pending.length) {      // keep the order of changes: nothing jumps the queue
    writeQ([...readQ(), { id: key!, method, path, body: opts.body }]);
    void flushQueue();
    return undefined as T;
  }
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}${qs(opts.query)}`, { method, headers, body: opts.body === undefined ? undefined : JSON.stringify(opts.body) });
  } catch {
    if (canQueue) { writeQ([...readQ(), { id: key!, method, path, body: opts.body }]); return undefined as T; }
    throw new ApiError(0, "Can't reach the server. Check your connection and try again.");
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: { detail?: unknown; request_id?: string; errors?: { field: string; message: string }[] } | null = null;
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

/** Fetch a file with the sign-in header and hand it to the browser as a download (links cannot carry the token). */
export async function download(path: string, query: Query, filename: string): Promise<void> {
  const token = tokenStore.get();
  const hh = household.get();
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}${qs({ ...query, ...(hh ? { user_id: hh } : {}) })}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check your connection and try again.");
  }
  if (!res.ok) throw new ApiError(res.status, res.status >= 500 ? "Something went wrong on the server." : "Could not download that file.");
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}
