import { BookOpen, ClipboardList, Download, FileSearch, Gauge, Home, LogOut, Moon, Repeat, ScrollText, Search, Sun, Target, Users, Wallet, Wrench, Lightbulb, ListChecks, ShieldCheck, Briefcase } from "lucide-react";
import { useEffect, useState, type ComponentType } from "react";
import { NavLink, Outlet } from "react-router";
import { household } from "../lib/api";
import { Logo } from "./ui";
import { useAuth } from "../lib/auth";
import type { Role } from "../lib/types";

interface Item { to: string; label: string; icon: ComponentType<{ size?: number; "aria-hidden"?: boolean }>; end?: boolean }
const CUSTOMER: Item[] = [
  { to: "/", label: "Folio", icon: Home, end: true },
  { to: "/entries", label: "Entries", icon: ScrollText },
  { to: "/budgets", label: "Budgets", icon: Target },
  { to: "/recurring", label: "Recurring", icon: Repeat },
  { to: "/insights", label: "Notes", icon: Lightbulb },
  { to: "/books", label: "Books", icon: Wallet },
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

export default function Shell() {
  const { me, logout } = useAuth();
  const [theme, toggle] = useTheme();
  if (!me) return null;
  const groups = NAV[me.role];
  const viewing = household.get();
  return (
    <div className="min-h-screen md:grid md:grid-cols-[232px_1fr]">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-paper focus:p-3">Skip to content</a>
      <aside className="md:sticky md:top-0 md:h-screen border-b md:border-b-0 md:border-r border-rule-strong bg-sheet flex md:flex-col">
        <div className="md:hidden flex items-center px-3 border-r border-rule"><Logo size={28} /></div>
        <div className="hidden md:block px-5 pt-6 pb-5 border-b border-rule">
          <div className="flex items-center gap-2.5">
            <Logo size={34} />
            <div><div className="font-bold leading-none tracking-tight">PAM</div><div className="text-xs text-muted mt-1">Payment Account Manager</div></div>
          </div>
        </div>
        <nav aria-label="Sections" className="flex md:flex-col md:flex-1 overflow-x-auto md:overflow-y-auto md:px-3 md:py-4 gap-x-1 md:gap-y-5">
          {groups.map((g) => (
            <div key={g.label} className="flex md:block">
              {groups.length > 1 && <div className="hidden md:block px-2 pb-1 text-[11px] font-bold uppercase tracking-wider text-muted">{g.label}</div>}
              <ul className="flex md:block">
                {g.items.map(({ to, label, icon: Icon, end }) => (
                  <li key={to}>
                    <NavLink
                      to={to} end={end}
                      className={({ isActive }) => `flex items-center gap-2.5 px-3 min-h-[44px] md:min-h-[38px] whitespace-nowrap no-underline text-[15px] border-b-2 md:border-b-0 md:border-l-2 ${isActive ? "border-red text-blue font-semibold bg-blue-soft" : "border-transparent text-ink hover:bg-blue-soft"}`}
                    ><Icon size={17} aria-hidden />{label}</NavLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
        <div className="hidden md:block border-t border-rule p-3 text-sm">
          <div className="px-2 pb-2 truncate" title={me.email}>{me.email}<div className="text-xs text-muted">{me.role.toLowerCase()}</div></div>
          <div className="flex gap-1">
            <button className="btn btn-ghost flex-1" onClick={toggle} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>{theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}</button>
            <button className="btn btn-ghost flex-[3]" onClick={logout}><LogOut size={16} aria-hidden />Sign out</button>
          </div>
        </div>
        <div className="md:hidden flex items-center border-l border-rule">
          <button className="btn btn-ghost" onClick={toggle} aria-label="Toggle theme">{theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}</button>
          <button className="btn btn-ghost" onClick={logout} aria-label="Sign out"><LogOut size={17} /></button>
        </div>
      </aside>
      <main id="main" className="min-w-0">
        {viewing && me.role === "ADMIN" && (
          <div className="bg-red-soft text-red border-b border-red px-6 py-2 flex items-center justify-between text-sm">
            <span>Support view: you are looking at household <b>{viewing}</b> as an admin.</span>
            <button className="btn btn-danger" onClick={() => { household.set(null); location.assign("/admin/households"); }}>Leave household</button>
          </div>
        )}
        <div className="max-w-[1180px] mx-auto px-4 md:px-8 py-6 md:py-9"><Outlet /></div>
      </main>
    </div>
  );
}
