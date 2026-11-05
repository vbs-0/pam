import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { Drawer, Empty, ErrorBox, Money, MonthBar, PageHead, QueryState, Skeleton, useCategoryName, useMonth } from "../../components/ui";
import { get } from "../../lib/api";
import { dayLabel, monthName, rupees, rupeesShort, titleCase, todayIso } from "../../lib/format";
import type { Daily, DailyDay, TxnPage } from "../../lib/types";

const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** Month grid: each day shows what was spent, shaded by how heavy it was. Tap a day to read its entries. */
export default function Calendar() {
  const [month, setMonth] = useMonth();
  const [day, setDay] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["daily", month], queryFn: () => get<Daily>("/me/daily", { month }) });
  return (
    <>
      <PageHead title={`Calendar · ${monthName(month)}`} sub="What you spent on each day. Pick a day to see what made it." right={<MonthBar month={month} onChange={(m) => { setDay(null); setMonth(m); }} />} />
      <QueryState q={q} rows={8}>
        {(d) => {
          const empty = d.days.every((x) => x.count === 0);
          return (
            <>
              <dl className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                <Stat label="Spent this month" value={<>₹{rupees(d.total_spend_paise)}</>} />
                <Stat label="Daily average" value={<>₹{rupeesShort(d.daily_average_paise)}</>} sub={d.days_elapsed ? `over ${d.days_elapsed} day${d.days_elapsed > 1 ? "s" : ""}` : undefined} />
                <Stat label="Busiest day" value={d.busiest ? dayLabel(d.busiest) : "—"} sub={d.busiest ? `₹${rupeesShort(d.days.find((x) => x.date === d.busiest)?.spend_paise ?? 0)}` : undefined} />
                <Stat label="Days left" value={d.days_left > 0 ? String(d.days_left) : "—"} sub={d.days_left > 0 ? "in this month" : "month is over"} />
              </dl>
              {empty ? <Empty title="Nothing written for this month" hint="Add entries and each day fills in here." action={<Link to="/entries?add=1" className="btn btn-solid">Add an entry</Link>} /> : <Grid d={d} onPick={setDay} picked={day} />}
              <p className="text-sm text-muted mt-3">Darker means a heavier day. A small green mark means money came in that day. Transfers between your own accounts are not counted.</p>
            </>
          );
        }}
      </QueryState>
      {day && <DayDrawer date={day} onClose={() => setDay(null)} />}
    </>
  );
}

function Stat({ label, value, sub }: { label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div className="border border-rule-strong bg-sheet px-4 py-3">
      <dt className="text-xs font-bold tracking-wider uppercase text-muted">{label}</dt>
      <dd className="text-2xl font-semibold tracking-tight num mt-1">{value}</dd>
      {sub && <p className="text-xs text-muted">{sub}</p>}
    </div>
  );
}

function Grid({ d, onPick, picked }: { d: Daily; onPick: (date: string) => void; picked: string | null }) {
  const first = new Date(`${d.days[0].date}T00:00:00`);
  const lead = (first.getDay() + 6) % 7;                                   // Monday-first
  const max = Math.max(1, ...d.days.map((x) => x.spend_paise));
  const today = todayIso();
  const cells: (DailyDay | null)[] = [...Array(lead).fill(null), ...d.days];
  return (
    <div role="grid" aria-label="Spending by day" className="grid grid-cols-7 gap-1.5 sm:gap-2">
      {DOW.map((n) => <div key={n} role="columnheader" className="text-xs font-bold tracking-wider uppercase text-muted text-center pb-1">{n}</div>)}
      {cells.map((c, i) => {
        if (!c) return <div key={`b${i}`} aria-hidden />;
        const n = Number(c.date.slice(8));
        const heat = c.spend_paise / max;
        const label = `${dayLabel(c.date)}: ${c.count ? `spent ₹${rupees(c.spend_paise)}${c.income_paise ? `, received ₹${rupees(c.income_paise)}` : ""}, ${c.count} entr${c.count > 1 ? "ies" : "y"}` : "no entries"}`;
        return (
          <button key={c.date} type="button" role="gridcell" aria-label={label} onClick={() => onPick(c.date)} aria-pressed={picked === c.date}
            className={`cal-cell relative text-left p-1.5 sm:p-2 min-h-[64px] sm:min-h-[84px] border ${picked === c.date ? "border-blue ring-2 ring-blue" : c.date === today ? "border-red" : "border-rule"}`}
            style={{ background: c.spend_paise > 0 ? `color-mix(in srgb, var(--blue) ${Math.round(8 + heat * 52)}%, var(--sheet))` : "var(--sheet)" }}>
            <span className={`text-xs font-semibold ${c.date === today ? "text-red" : "text-muted"}`}>{n}</span>
            {c.spend_paise > 0 && <span className="block mt-1 text-[11px] sm:text-sm font-semibold num leading-tight">₹{rupeesShort(c.spend_paise)}</span>}
            {c.income_paise > 0 && <span aria-hidden className="absolute right-1.5 top-1.5 w-2 h-2 rounded-full bg-green" />}
          </button>
        );
      })}
    </div>
  );
}

function DayDrawer({ date, onClose }: { date: string; onClose: () => void }) {
  const catName = useCategoryName();
  const q = useQuery({ queryKey: ["day", date], queryFn: () => get<TxnPage>("/me/transactions", { date_from: date, date_to: date, limit: 100 }) });
  const rows = q.data?.items ?? [];
  const spent = rows.filter((t) => ["EXPENSE", "REFUND"].includes(t.kind) || (t.kind === "UNKNOWN" && t.amount_paise < 0)).reduce((s, t) => s - t.amount_paise, 0);
  return (
    <Drawer title={dayLabel(date)} onClose={onClose}>
      {q.isPending ? <Skeleton rows={5} /> : q.isError ? <ErrorBox error={q.error} retry={() => q.refetch()} /> : rows.length === 0 ? <Empty title="Nothing on this day" /> : (
        <div className="space-y-4">
          <p className="text-sm text-muted">{rows.length} entr{rows.length > 1 ? "ies" : "y"} · spent <b className="text-ink">₹{rupees(spent)}</b></p>
          <ul className="border-t border-rule">
            {rows.map((t) => (
              <li key={t.txn_id} className="py-2.5 border-b border-rule flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <p className={`truncate ${t.kind === "TRANSFER" ? "struck" : ""}`}>{t.merchant_name ?? t.descriptor}</p>
                  <p className="text-xs text-muted">{catName(t.category_code)} · {titleCase(t.channel)}{t.note ? ` · ${t.note}` : ""}</p>
                </div>
                <Money paise={t.amount_paise} sign struck={t.kind === "TRANSFER" || t.kind === "REVERSAL"} tone={t.amount_paise > 0 ? "blue" : undefined} />
              </li>
            ))}
          </ul>
          <Link className="btn" to={`/entries?month=${date.slice(0, 7)}&from=${date}&to=${date}`}>Open in Entries</Link>
        </div>
      )}
    </Drawer>
  );
}
