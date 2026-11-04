import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Empty, Money, PageHead, QueryState, StatusStamp, useCategoryName } from "../../components/ui";
import { get } from "../../lib/api";
import { dayLabel, titleCase } from "../../lib/format";
import type { Series } from "../../lib/types";

const FILTERS = ["ALL", "ACTIVE", "MISSED", "ENDED"] as const;

export default function Recurring() {
  const q = useQuery({ queryKey: ["recurring"], queryFn: () => get<Series[]>("/me/recurring") });
  const catName = useCategoryName();
  const [f, setF] = useState<(typeof FILTERS)[number]>("ALL");
  const [open, setOpen] = useState<string | null>(null);
  return (
    <>
      <PageHead title="Recurring payments" sub="Bills, subscriptions, EMIs and salary that repeat. PAM finds them; a missed one is flagged." />
      <div className="flex gap-1 mb-4" role="tablist" aria-label="Status">
        {FILTERS.map((x) => <button key={x} role="tab" aria-selected={f === x} className={`btn ${f === x ? "btn-solid" : ""}`} onClick={() => setF(x)}>{titleCase(x)}</button>)}
      </div>
      <QueryState q={q}>
        {(all) => {
          const rows = all.filter((s) => f === "ALL" || s.status === f);
          if (rows.length === 0) return <Empty title="Nothing here" hint={all.length === 0 ? "Recurring payments show up once PAM sees a payment repeat at least three times." : "No series with this status."} />;
          return (
            <div className="overflow-x-auto"><table className="register min-w-[720px]">
              <thead><tr><th>Payee</th><th>Cadence</th><th className="num">Usual amount</th><th>Last paid</th><th>Next due</th><th>Status</th></tr></thead>
              <tbody>
                {rows.map((s) => (
                  <>
                    <tr key={s.series_id} className="clickable" tabIndex={0} onClick={() => setOpen(open === s.series_id ? null : s.series_id)} onKeyDown={(e) => e.key === "Enter" && setOpen(open === s.series_id ? null : s.series_id)} aria-expanded={open === s.series_id}>
                      <td><div>{s.merchant_name ?? catName(s.category_code)}</div><div className="text-xs text-muted">{catName(s.category_code)} · {titleCase(s.series_type)}{s.direction === "CR" ? " · money in" : ""}</div></td>
                      <td>{titleCase(s.cadence)}<div className="text-xs text-muted">every ~{s.median_gap_days} days</div></td>
                      <td className="num"><Money paise={s.typical_amount_paise} /></td>
                      <td>{dayLabel(s.last_seen)}</td>
                      <td className={s.status === "MISSED" ? "text-red font-semibold" : ""}>{s.next_expected ? dayLabel(s.next_expected) : "—"}</td>
                      <td><StatusStamp status={s.status} /></td>
                    </tr>
                    {open === s.series_id && (
                      <tr key={`${s.series_id}-e`}><td colSpan={6} className="bg-blue-soft">
                        <p className="text-sm font-semibold mb-1">Last {s.events.length} events · seen {s.occurrences} times since {dayLabel(s.first_seen)}</p>
                        <ul className="text-sm columns-1 sm:columns-2">{s.events.map((e) => <li key={e.seq}>{dayLabel(e.date)} · {titleCase(e.type)}{e.detail && "amount_paise" in e.detail && <> · <Money paise={Number(e.detail.amount_paise)} /></>}</li>)}</ul>
                      </td></tr>
                    )}
                  </>
                ))}
              </tbody>
            </table></div>
          );
        }}
      </QueryState>
    </>
  );
}
