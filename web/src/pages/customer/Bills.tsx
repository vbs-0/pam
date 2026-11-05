import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { Empty, PageHead, QueryState, Section, Stamp } from "../../components/ui";
import { get } from "../../lib/api";
import { dayLabel, rupees } from "../../lib/format";
import type { AlertItem, NetWorth, Upcoming } from "../../lib/types";

const TONE = { ALERT: "red", WARN: "amber", INFO: "blue" } as const;

/** Everything that needs attention: alerts, bills and income due soon, credit cards, and what you are worth. */
export default function Bills() {
  const [days, setDays] = useState(30);
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: () => get<{ count: number; alerts: AlertItem[] }>("/me/alerts") });
  const up = useQuery({ queryKey: ["upcoming", days], queryFn: () => get<Upcoming>("/me/upcoming", { days }) });
  const nw = useQuery({ queryKey: ["networth"], queryFn: () => get<NetWorth>("/me/networth") });
  return (
    <>
      <PageHead title="Bills & alerts" sub="What needs a look today, what is due soon, and where your cards stand." />
      <Section title="Needs a look">
        <QueryState q={alerts} rows={3}>
          {(d) => d.alerts.length === 0 ? <Empty title="All clear" hint="No bills due, no budget over its limit, no card close to its limit." /> : (
            <ul className="border-t border-rule">
              {d.alerts.map((a, i) => (
                <li key={i} className="py-3 border-b border-rule flex gap-3 items-start">
                  <Stamp tone={TONE[a.severity]}>{a.severity === "ALERT" ? "Over" : a.severity === "WARN" ? "Watch" : "Info"}</Stamp>
                  <div className="flex-1"><p className="font-medium">{a.title}</p><p className="text-sm text-muted">{a.detail}</p></div>
                </li>
              ))}
            </ul>
          )}
        </QueryState>
      </Section>

      <Section title="Coming up" right={
        <div className="inline-flex border border-rule-strong" role="group" aria-label="Look ahead">
          {[7, 30, 90].map((n) => <button key={n} type="button" aria-pressed={days === n} className={`px-3 py-1.5 text-sm ${days === n ? "bg-blue text-paper" : ""}`} onClick={() => setDays(n)}>{n} days</button>)}
        </div>
      }>
        <QueryState q={up} rows={4}>
          {(d) => d.items.length === 0 ? <Empty title={`Nothing due in the next ${days} days`} hint="Bills and income appear once PAM sees a payment repeat." /> : (
            <>
              <p className="text-sm mb-3">Going out <b>₹{rupees(d.due_out_paise)}</b>{d.due_in_paise > 0 && <> · coming in <b className="text-blue">₹{rupees(d.due_in_paise)}</b></>}</p>
              <ul className="border-t border-rule">
                {d.items.map((i) => (
                  <li key={`${i.kind}-${i.id}`} className="py-3 border-b border-rule flex items-center gap-3">
                    <div className={`w-14 text-center shrink-0 ${i.overdue ? "text-red" : "text-blue"}`}>
                      <p className="text-xs font-bold uppercase">{i.overdue ? "Late" : i.days_away === 0 ? "Today" : `${i.days_away}d`}</p>
                      <p className="text-xs text-muted">{dayLabel(i.due)}</p>
                    </div>
                    <div className="flex-1 min-w-0"><p className="truncate font-medium">{i.name}</p><p className="text-xs text-muted">{i.kind === "CARD" ? "Credit card bill" : `${i.series_type === "INCOME" ? "Income" : "Recurring"} · ${i.cadence.toLowerCase()}`}</p></div>
                    <p className={`num font-semibold ${i.direction === "CR" ? "text-blue" : ""}`}>{i.direction === "CR" ? "+" : ""}₹{rupees(i.amount_paise)}</p>
                  </li>
                ))}
              </ul>
              <p className="text-sm mt-3"><Link to="/recurring" className="underline">All recurring payments</Link></p>
            </>
          )}
        </QueryState>
      </Section>

      <Section title="Net worth">
        <QueryState q={nw} rows={3}>
          {(d) => (
            <div className="space-y-6">
              <dl className="grid grid-cols-3 gap-4 max-w-2xl">
                <div><dt className="text-xs uppercase tracking-wider font-bold text-muted">You own</dt><dd className="text-xl font-semibold num">₹{rupees(d.assets_paise)}</dd></div>
                <div><dt className="text-xs uppercase tracking-wider font-bold text-muted">You owe</dt><dd className="text-xl font-semibold num text-red">₹{rupees(d.liabilities_paise)}</dd></div>
                <div><dt className="text-xs uppercase tracking-wider font-bold text-muted">Net</dt><dd className={`text-xl font-semibold num ${d.net_worth_paise < 0 ? "text-red" : "text-blue"}`}>{d.net_worth_paise < 0 ? "−" : ""}₹{rupees(d.net_worth_paise)}</dd></div>
              </dl>
              {d.cards.length > 0 && (
                <div className="grid gap-4 sm:grid-cols-2">
                  {d.cards.map((c) => (
                    <div key={c.account_id} className="border border-rule-strong bg-sheet p-4">
                      <p className="font-semibold">{c.display_name}</p>
                      <p className="text-sm text-muted">₹{rupees(c.used_paise)} used{c.limit_paise ? ` of ₹${rupees(c.limit_paise)}` : ""}</p>
                      {c.utilisation !== null && (
                        <div className="h-2.5 bg-[var(--rule)] mt-2" role="img" aria-label={`${Math.round(c.utilisation * 100)} percent of the limit used`}>
                          <div className={`h-full ${c.utilisation >= 0.8 ? "bg-red" : c.utilisation >= 0.5 ? "bg-amber" : "bg-blue"} bar-grow`} style={{ width: `${Math.min(c.utilisation, 1) * 100}%` }} />
                        </div>
                      )}
                      <p className="text-sm mt-2">{c.due_date ? <>Due <b>{dayLabel(c.due_date)}</b>{c.days_to_due !== null && <span className="text-muted"> · in {c.days_to_due} day{c.days_to_due === 1 ? "" : "s"}</span>}</> : <Link to="/books" className="underline">Set the due day in Books</Link>}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </QueryState>
      </Section>
    </>
  );
}
