import { BookOpen, ClipboardList, Download, FileSearch, Gauge, Home, LogOut, Moon, Repeat, ScrollText, Search, Sun, Target, Users, Wallet, Wrench, Lightbulb, ListChecks, ShieldCheck, Briefcase, CalendarDays, PieChart, Bell, PiggyBank, Settings as Cog } from "lucide-react";
import { useEffect, useState, type ComponentType } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { NavLink, Outlet } from "react-router";
import { discardFailed, flushQueue, household, queueState, retryFailed } from "../lib/api";
import { Logo } from "./ui";
import { initMotion } from "../lib/motion";
import { useAuth } from "../lib/auth";
import type { Role } from "../lib/types";

interface Item { to: string; label: string; icon: ComponentType<{ size?: number; "aria-hidden"?: boolean }>; end?: boolean }
const CUSTOMER: Item[] = [
  { to: "/", label: "Folio", icon: Home, end: true },
  { to: "/entries", label: "Entries", icon: ScrollText },
  { to: "/calendar", label: "Calendar", icon: CalendarDays },
  { to: "/spend", label: "Spend", icon: PieChart },
  { to: "/budgets", label: "Budgets", icon: Target },
  { to: "/bills", label: "Bills", icon: Bell },
  { to: "/goals", label: "Goals", icon: PiggyBank },
  { to: "/recurring", label: "Recurring", icon: Repeat },
  { to: "/insights", label: "Notes", icon: Lightbulb },
  { to: "/books", label: "Books", icon: Wallet },
  { to: "/settings", label: "Settings", icon: Cog },
];
const ANALYST: Item[] = [
  { to: "/exceptions", label: "Exceptions", icon: ListChecks },
  { to: "/rules", label: "Rules", icon: Wrench },
  { to: "/metrics", label: "Metrics", icon: Gauge },
  { to: "/trace", label: "Trace", icon: Search },
];
const REVIEWER: Item[] = [
  { to: "/anomalies", label: "Anomalies", icon: ShieldCheck },
  { to: "/audit", label: "Audit log", icon: FileSearch },
  { to: "/trace", label: "Trace", icon: Search },
];
const ADMIN: Item[] = [
  { to: "/admin", label: "Overview", icon: Briefcase, end: true },
  { to: "/admin/jobs", label: "Jobs", icon: ClipboardList },
  { to: "/admin/users", label: "Logins", icon: Users },
  { to: "/admin/exports", label: "Exports", icon: Download },
  { to: "/admin/households", label: "Households", icon: BookOpen },
];
export const NAV: Record<Role, { label: string; items: Item[] }[]> = {
  CUSTOMER: [{ label: "My month", items: CUSTOMER }],
  ANALYST: [{ label: "Analyst", items: ANALYST }],
  REVIEWER: [{ label: "Reviewer", items: REVIEWER }],
  ADMIN: [
    { label: "Admin", items: ADMIN },
    { label: "Analyst", items: ANALYST },
    { label: "Reviewer", items: REVIEWER.slice(0, 2) },
  ],
};
export const homeFor = (role: Role) => (role === "CUSTOMER" ? "/" : role === "ANALYST" ? "/exceptions" : role === "REVIEWER" ? "/anomalies" : "/admin");

function useTheme() {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    try { const t = localStorage.getItem("pam.theme"); if (t === "light" || t === "dark") return t; } catch { /* ignore */ }
    return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "dark" ? "#0E1420" : "#F7F9FC");
    try { localStorage.setItem("pam.theme", theme); } catch { /* ignore */ }
  }, [theme]);
  return [theme, () => setTheme((t) => (t === "dark" ? "light" : "dark"))] as const;
}

/** One line that says what the browser is doing with changes made offline. */
function SyncBar() {
  const qc = useQueryClient();
  const [online, setOnline] = useState(navigator.onLine);
  const [q, setQ] = useState(queueState());
  useEffect(() => {
    const upd = () => setQ(queueState());
    const on = () => { setOnline(true); void flushQueue(); }, off = () => setOnline(false);
    const synced = () => { upd(); void qc.invalidateQueries(); };
    window.addEventListener("pam-queue", upd); window.addEventListener("pam-synced", synced);
    window.addEventListener("online", on); window.addEventListener("offline", off);
    return () => { window.removeEventListener("pam-queue", upd); window.removeEventListener("pam-synced", synced); window.removeEventListener("online", on); window.removeEventListener("offline", off); };
  }, [qc]);
  const n = q.pending.length, bad = q.failed.length;
  if (online && !n && !bad) return null;
  return (
    <div role="status" className={`text-center text-sm font-semibold px-3 py-1.5 text-paper ${bad ? "bg-red" : online ? "bg-blue" : "bg-amber"}`}>
      {bad ? <>{bad} change{bad > 1 ? "s" : ""} could not be saved. <button className="underline" onClick={retryFailed}>Try again</button> · <button className="underline" onClick={discardFailed}>Discard</button></>
        : !online ? <>Offline. {n ? `${n} change${n > 1 ? "s" : ""} saved in this browser and sent automatically when you are back.` : "You can still look around; changes are saved and sent when you are back."}</>
        : <>Sending {n} saved change{n > 1 ? "s" : ""}…</>}
    </div>
  );
}

export default function Shell() {
  const { me, logout } = useAuth();
  const [theme, toggle] = useTheme();
  useEffect(() => initMotion(), []);
  if (!me) return null;
  const groups = NAV[me.role];
  const viewing = household.get();
  return (
    <div className="vx-app">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-paper focus:p-3">Skip to content</a>
      <div className="vx-progress" aria-hidden />
      <header className="vx-head">
        <div className="vx-brand"><Logo size={30} /><span>pam</span></div>
        <nav aria-label="Sections" className="vx-nav">
          {groups.flatMap((g) => g.items).map(({ to, label, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => `vx-link ${isActive ? "active" : ""}`}>{label}</NavLink>
          ))}
        </nav>
        <div className="vx-actions">
          <span className="vx-who" title={me.email}>{me.role.toLowerCase()}</span>
          <button className="vx-icon" onClick={toggle} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>{theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}</button>
          <button className="vx-pill" onClick={logout}><LogOut size={15} aria-hidden />Sign out</button>
        </div>
      </header>
      <main id="main" className="min-w-0">
        <SyncBar />
        {viewing && me.role === "ADMIN" && (
          <div className="bg-red-soft text-red border-b border-red px-6 py-2 flex items-center justify-between text-sm">
            <span>Support view: you are looking at household <b>{viewing}</b> as an admin.</span>
            <button className="btn btn-danger" onClick={() => { household.set(null); location.assign("/admin/households"); }}>Leave household</button>
          </div>
        )}
        <div className="vx-wrap"><Outlet /></div>
      </main>
    </div>
  );
}
