import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { Delta } from "../../components/charts";
import { get } from "../../lib/api";
import { currentMonth, rupees, todayIso } from "../../lib/format";
import type { AlertItem, Budgets, NetWorth, SpendByCategory, Summary } from "../../lib/types";

/** Pace, month-on-month, net worth and alerts: the small facts that sit under the headline numbers. */
export default function FolioExtras({ month, summary, budgets }: { month: string; summary?: Summary; budgets?: Budgets }) {
  const cats = useQuery({ queryKey: ["spend-cats", month], queryFn: () => get<SpendByCategory>("/me/spend-by-category", { month }) });
  const nw = useQuery({ queryKey: ["networth"], queryFn: () => get<NetWorth>("/me/networth") });
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: () => get<{ count: number; alerts: AlertItem[] }>("/me/alerts") });
  if (!summary) return null;

  const [y, m] = month.split("-").map(Number);
  const daysIn = new Date(y, m, 0).getDate();
  const live = month === currentMonth();
  const elapsed = live ? Number(todayIso().slice(8)) : month < currentMonth() ? daysIn : 0;
  const left = live ? daysIn - elapsed : 0;
  const avg = elapsed > 0 ? Math.round(summary.spend_paise / elapsed) : 0;
  const projected = live ? avg * daysIn : summary.spend_paise;
  const limit = budgets?.total_budget_paise ?? 0;
  const room = limit > 0 && live ? limit - summary.spend_paise : null;
  const safeDaily = room !== null && left > 0 ? Math.max(0, Math.floor(room / left)) : null;
  const top = alerts.data?.alerts.slice(0, 3) ?? [];

  return (
    <div className="grid gap-4 md:grid-cols-3 mb-6">
      <div className="info-card">
        <p className="text-sm font-bold uppercase tracking-wider text-muted">Pace</p>
        <p className="text-2xl font-semibold mt-1 num">₹{rupees(avg)} <span className="text-sm font-normal text-muted">a day</span></p>
        <p className="text-sm text-muted mt-1">
          {live ? <>{left} day{left === 1 ? "" : "s"} left. At this rate the month ends near <b className="text-ink">₹{rupees(projected)}</b>.</> : "Average over the days in that month."}
          {safeDaily !== null && (room as number) >= 0 && <> To stay inside your limits, keep it under <b className="text-ink">₹{rupees(safeDaily)}</b> a day.</>}
          {room !== null && room < 0 && <> You are <b className="text-red">₹{rupees(room)}</b> over the total of your limits.</>}
        </p>
      </div>
      <div className="info-card">
        <p className="text-sm font-bold uppercase tracking-wider text-muted">Against last month</p>
        {cats.data ? (
          <>
            <p className="text-2xl font-semibold mt-1"><Delta paise={cats.data.change_paise} /></p>
            <p className="text-sm text-muted mt-1">Compared with ₹{rupees(cats.data.total_paise - cats.data.change_paise)} then. <Link to={`/spend?month=${month}`}>See where</Link></p>
          </>
        ) : <p className="text-sm text-muted mt-2">Loading…</p>}
      </div>
      <div className="info-card">
        <p className="text-sm font-bold uppercase tracking-wider text-muted">Net worth</p>
        {nw.data ? (
          <>
            <p className={`text-2xl font-semibold mt-1 num ${nw.data.net_worth_paise < 0 ? "text-red" : ""}`}>{nw.data.net_worth_paise < 0 ? "−" : ""}₹{rupees(nw.data.net_worth_paise)}</p>
            <p className="text-sm text-muted mt-1">Own ₹{rupees(nw.data.assets_paise)}, owe ₹{rupees(nw.data.liabilities_paise)}. <Link to="/bills">Cards and bills</Link></p>
          </>
        ) : <p className="text-sm text-muted mt-2">Loading…</p>}
      </div>
      {top.length > 0 && (
        <ul className="alert-card md:col-span-3 text-sm space-y-1.5" aria-label="Needs a look">
          {top.map((a, i) => <li key={i}><b className={a.severity === "ALERT" ? "text-red" : ""}>{a.title}</b> <span className="text-muted">{a.detail}</span></li>)}
          {(alerts.data?.count ?? 0) > top.length && <li><Link to="/bills">See all {alerts.data?.count}</Link></li>}
        </ul>
      )}
    </div>
  );
}
