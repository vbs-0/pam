import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, RefreshCw, X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";
import { useSearchParams } from "react-router";
import { ApiError, get } from "../lib/api";
import { currentMonth, monthName, shiftMonth, split, titleCase } from "../lib/format";
import type { Category } from "../lib/types";

/* ---------- stamps: states are printed marks, never glows ---------- */
type Tone = "blue" | "red" | "muted" | "amber" | "green";
const TONE: Record<Tone, string> = { blue: "text-blue", red: "text-red", muted: "text-muted", amber: "text-amber", green: "text-green" };
export const Stamp = ({ tone = "muted", children, title }: { tone?: Tone; children: ReactNode; title?: string }) => (
  <span className={`stamp ${TONE[tone]}`} title={title}>{children}</span>
);

const STATUS_TONE: Record<string, Tone> = {
  OVER: "red", NEAR: "amber", UNDER: "green", NO_BUDGET: "muted", ACTIVE: "green", MISSED: "red", ENDED: "muted",
  OPEN: "red", IN_REVIEW: "amber", RESOLVED: "green", DISMISSED: "muted", SUCCEEDED: "green", FAILED: "red",
  RUNNING: "amber", QUEUED: "muted", CAUGHT: "green", MISSED_: "red", ALERT: "red", WARN: "amber", INFO: "muted",
  PASS: "green", FAIL: "red", TRANSFER: "muted", REFUND: "blue", REVERSAL: "muted", UNKNOWN: "red",
};
const STATUS_TEXT: Record<string, string> = { NO_BUDGET: "No budget", TRANSFER: "Contra", UNKNOWN: "Unsorted" };
export const StatusStamp = ({ status }: { status: string }) => (
  <Stamp tone={STATUS_TONE[status] ?? "muted"}>{STATUS_TEXT[status] ?? titleCase(status)}</Stamp>
);

/* ---------- money: rupees and paise in their own columns ---------- */
export function Money({ paise, sign = false, struck = false, tone, big = false }:
  { paise: number; sign?: boolean; struck?: boolean; tone?: "ink" | "red" | "blue" | "muted"; big?: boolean }) {
  const { r, p } = split(paise);
  const color = tone === "red" ? "text-red" : tone === "blue" ? "text-blue" : tone === "muted" ? "text-muted" : "";
  return (
    <span className={`num ${color} ${struck ? "struck" : ""} ${big ? "font-semibold" : ""}`}>
      {sign && (paise < 0 ? "−" : paise > 0 ? "+" : "")}₹{r}<span className="opacity-60">.{p}</span>
    </span>
  );
}

/* ---------- query states: loading skeleton, empty, error with retry ---------- */
export function Skeleton({ rows = 5, h = 18 }: { rows?: number; h?: number }) {
  return (
    <div aria-busy="true" aria-label="Loading" className="space-y-3 py-2">
      {Array.from({ length: rows }, (_, i) => <div key={i} className="skeleton" style={{ height: h, width: `${96 - (i % 3) * 11}%` }} />)}
    </div>
  );
}
export function ErrorBox({ error, retry }: { error: unknown; retry?: () => void }) {
  const e = error as ApiError;
  return (
    <div role="alert" className="border border-red p-4 text-red bg-red-soft">
      <p className="font-semibold">{e.message || "Something went wrong."}</p>
      {e.requestId && <p className="text-xs mt-1 opacity-80">Request {e.requestId}</p>}
      {retry && <button className="btn btn-danger mt-3" onClick={retry}><RefreshCw size={15} aria-hidden /> Try again</button>}
    </div>
  );
}
export const Empty = ({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) => (
  <div className="py-10 text-center border-y border-dashed border-rule-strong">
    <p className="font-semibold">{title}</p>
    {hint && <p className="text-muted mt-1 max-w-md mx-auto">{hint}</p>}
    {action && <div className="mt-4">{action}</div>}
  </div>
);
export function QueryState<T>({ q, rows = 5, children }: { q: UseQueryResult<T>; rows?: number; children: (data: T) => ReactNode }) {
  if (q.isPending) return <Skeleton rows={rows} />;
  if (q.isError) return <ErrorBox error={q.error} retry={() => q.refetch()} />;
  return <>{children(q.data)}</>;
}

/* ---------- page furniture ---------- */
export const PageHead = ({ title, sub, right }: { title: string; sub?: ReactNode; right?: ReactNode }) => (
  <header className="flex flex-wrap items-end justify-between gap-3 pb-4 border-b border-rule-strong mb-6">
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      {sub && <p className="text-muted mt-1">{sub}</p>}
    </div>
    <div className="flex items-center gap-2 flex-wrap">{right}</div>
  </header>
);
export const Section = ({ title, right, children }: { title: string; right?: ReactNode; children: ReactNode }) => (
  <section className="mb-9">
    <div className="flex items-baseline justify-between border-b border-rule-strong pb-1.5 mb-2">
      <h2 className="text-sm font-bold uppercase tracking-wider text-muted">{title}</h2>
      {right}
    </div>
    {children}
  </section>
);

/* ---------- month: lives in the URL ---------- */
export function useMonth(): [string, (m: string) => void] {
  const [sp, setSp] = useSearchParams();
  const raw = sp.get("month");
  const month = raw && /^\d{4}-(0[1-9]|1[0-2])$/.test(raw) ? raw : currentMonth();
  return [month, (m) => setSp((p) => { p.set("month", m); return p; }, { replace: true })];
}
export function MonthBar({ month, onChange }: { month: string; onChange: (m: string) => void }) {
  return (
    <div className="flex items-center border border-rule-strong rounded-sm bg-sheet" role="group" aria-label="Month">
      <button className="btn btn-ghost" aria-label="Previous month" onClick={() => onChange(shiftMonth(month, -1))}><ChevronLeft size={18} /></button>
      <input
        type="month" aria-label="Pick month" value={month} onChange={(e) => e.target.value && onChange(e.target.value)}
        className="bg-transparent border-0 text-center font-semibold w-40 min-h-[38px]" min="2020-01" max="2030-12"
      />
      <span className="sr-only" aria-live="polite">{monthName(month)}</span>
      <button className="btn btn-ghost" aria-label="Next month" onClick={() => onChange(shiftMonth(month, 1))}><ChevronRight size={18} /></button>
    </div>
  );
}

/* ---------- categories ---------- */
export const useCategories = () => useQuery({ queryKey: ["categories"], queryFn: () => get<Category[]>("/categories"), staleTime: 3_600_000 });
export const useCategoryName = () => {
  const q = useCategories();
  const names = new Map((q.data ?? []).map((c) => [c.code, c.name]));
  return (code: string) => names.get(code) ?? titleCase(code);
};
export function CategorySelect({ value, onChange, kinds, id, includeBlank = "Choose a category" }:
  { value: string; onChange: (v: string) => void; kinds?: string[]; id?: string; includeBlank?: string }) {
  const q = useCategories();
  const groups = new Map<string, Category[]>();
  (q.data ?? []).filter((c) => c.active && (!kinds || kinds.includes(c.kind))).forEach((c) => groups.set(c.group, [...(groups.get(c.group) ?? []), c]));
  return (
    <select id={id} className="field" value={value} onChange={(e) => onChange(e.target.value)} disabled={q.isPending}>
      <option value="">{includeBlank}</option>
      {[...groups].map(([g, cs]) => (
        <optgroup key={g} label={titleCase(g)}>{cs.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}</optgroup>
      ))}
    </select>
  );
}

/* ---------- form field ---------- */
export function Field({ label, hint, error, children }: { label: string; hint?: string; error?: string; children: (id: string) => ReactNode }) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-semibold mb-1">{label}</label>
      {children(id)}
      {hint && !error && <p className="text-xs text-muted mt-1">{hint}</p>}
      {error && <p className="text-xs text-red mt-1" role="alert">{error}</p>}
    </div>
  );
}

/* ---------- drawer: a loose leaf slid onto the page; Escape closes, focus is trapped ---------- */
export function Drawer({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key !== "Tab" || !ref.current) return;
      const f = ref.current.querySelectorAll<HTMLElement>("a[href],button:not(:disabled),input,select,textarea,[tabindex]:not([tabindex='-1'])");
      if (!f.length) return;
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = ""; prev?.focus(); };
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-ink/40" onClick={onClose} aria-hidden />
      <div
        ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title}
        className={`sheet-in relative bg-paper border-l border-rule-strong shadow-[-8px_0_24px_-12px_rgba(0,0,0,.35)] w-full ${wide ? "max-w-2xl" : "max-w-lg"} h-full overflow-y-auto outline-none`}
      >
        <div className="sticky top-0 bg-paper border-b border-rule-strong px-5 h-14 flex items-center justify-between z-10">
          <h2 className="font-semibold text-lg">{title}</h2>
          <button className="btn btn-ghost" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

/* ---------- budget limit bar: bar length is exact, the red tick is the limit ---------- */
export function LimitBar({ actual, budget, status }: { actual: number; budget: number | null; status: string }) {
  const max = Math.max(actual, budget ?? 0, 1) * 1.04;
  const color = status === "OVER" ? "var(--red)" : status === "NEAR" ? "var(--amber)" : "var(--blue)";
  return (
    <div className="relative h-3 border-y border-rule bg-transparent" role="img" aria-label={budget === null ? "No budget set" : `Spent ${Math.round((actual / (budget || 1)) * 100)}% of budget`}>
      <div className="absolute inset-y-0 left-0 rounded-r-[4px]" style={{ width: `${(Math.max(actual, 0) / max) * 100}%`, background: color }} />
      {budget !== null && <div className="absolute -inset-y-1 w-0.5 bg-red" style={{ left: `${(budget / max) * 100}%` }} />}
    </div>
  );
}
