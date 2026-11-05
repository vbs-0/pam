import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { Link } from "react-router";
import { Empty, ErrorBox, LimitBar, Money, MonthBar, PageHead, QueryState, Section, Skeleton, Stamp, StatusStamp, useCategoryName, useMonth } from "../../components/ui";
import { get } from "../../lib/api";
import FolioExtras from "./FolioExtras";
import { dayLabel, monthName, rupeesShort } from "../../lib/format";
import type { Budgets, Insight, Profile, Series, Summary, Trend, TxnPage } from "../../lib/types";

export default function Folio() {
  const [month, setMonth] = useMonth();
  const catName = useCategoryName();
  const profile = useQuery({ queryKey: ["profile"], queryFn: () => get<Profile>("/me/profile") });
  const summary = useQuery({ queryKey: ["summary", month], queryFn: () => get<Summary>("/me/summary", { month }) });
  const budgets = useQuery({ queryKey: ["budgets", month], queryFn: () => get<Budgets>("/me/budgets", { month }) });
  const insights = useQuery({ queryKey: ["insights", month], queryFn: () => get<Insight[]>("/me/insights", { month }) });
  const recurring = useQuery({ queryKey: ["recurring"], queryFn: () => get<Series[]>("/me/recurring") });
  const unsorted = useQuery({ queryKey: ["unsorted", month], queryFn: () => get<TxnPage>("/me/transactions", { month, kind: "UNKNOWN", limit: 100 }) });
  const trend = useQuery({ queryKey: ["trend"], queryFn: () => get<Trend[]>("/me/trend", { months: 12 }) });
  const sample = profile.data?.sample;

  return (
    <>
      <PageHead
        title={`Folio · ${monthName(month)}`}
        sub={profile.data ? <>{profile.data.display_name}{sample && <> · <Stamp tone="blue">Sample household · read-only</Stamp></>}</> : undefined}
        right={<>
          <MonthBar month={month} onChange={setMonth} />
          {profile.data && !sample && <Link className="btn btn-solid no-underline" to="/entries?add=1"><Plus size={16} aria-hidden /> Add entry</Link>}
        </>}
      />

      <QueryState q={summary} rows={3}>
        {(s) => {
          const noData = s.income_paise === 0 && s.spend_paise === 0 && s.naive_spend_paise === 0;
          if (noData && profile.data && !sample) return (
            <Empty title="Nothing written for this month yet" hint="Add an account and a few entries and PAM will categorise them, pair your own transfers and compare spending with budgets."
              action={<Link className="btn btn-solid no-underline" to="/books">Set up your books</Link>} />
          );
          const gap = s.naive_spend_paise - s.spend_paise;
          return (
            <div key={month} className="reinked grid md:grid-cols-[1.6fr_1fr_1fr] border-y border-rule-strong mb-9">
              <div className="p-5 md:border-r border-rule">
                <p className="text-sm font-bold uppercase tracking-wider text-muted">True spend</p>
                <p className="text-5xl font-semibold tracking-tight text-blue mt-1"><Money paise={s.spend_paise} /></p>
                {gap > 0 && (
                  <p className="mt-3 text-muted text-sm">
                    A plain ledger would show <span className="strike-draw font-semibold"><Money paise={s.naive_spend_paise} /></span>.
                    PAM leaves out <b className="text-ink"><Money paise={gap} /></b>
                    {s.transfers_out_paise > 0 && <> — <Money paise={s.transfers_out_paise} /> moved between your own accounts <Stamp>Contra</Stamp></>}, plus refunds and reversals.
                  </p>
                )}
              </div>
              <div className="p-5 md:border-r border-rule">
                <p className="text-sm font-bold uppercase tracking-wider text-muted">Income</p>
                <p className="text-3xl font-semibold mt-2"><Money paise={s.income_paise} /></p>
              </div>
              <div className="p-5">
                <p className="text-sm font-bold uppercase tracking-wider text-muted">Kept</p>
                <p className={`text-3xl font-semibold mt-2 ${s.savings_rate !== null && s.savings_rate < 0 ? "text-red" : ""}`}>
                  {s.savings_rate === null ? "—" : `${Math.round(s.savings_rate * 100)}%`}
                </p>
                <p className="text-sm text-muted mt-1">{s.savings_rate === null ? "No income recorded" : s.savings_rate < 0 ? "Spent more than came in" : "of income"}</p>
              </div>
            </div>
          );
        }}
      </QueryState>

      {!sample || summary.data ? <FolioExtras month={month} summary={summary.data} budgets={budgets.data} /> : null}

      <div className="grid lg:grid-cols-[1.55fr_1fr] gap-x-10">
        <Section title="Against budget" right={<Link to={`/budgets?month=${month}`} className="text-sm">All budgets</Link>}>
          <QueryState q={budgets}>
            {(b) => b.lines.length === 0 ? <Empty title="No spending or budgets this month" /> : (
              <table className="register">
                <thead><tr><th>Category</th><th className="num">Spent</th><th className="num">Limit</th><th className="w-[28%]"><span className="sr-only">Progress</span></th><th><span className="sr-only">Status</span></th></tr></thead>
                <tbody>
                  {[...b.lines].sort((x, y) => (y.ratio ?? -1) - (x.ratio ?? -1) || y.actual_paise - x.actual_paise).slice(0, 9).map((l) => (
                    <tr key={l.category_code}>
                      <td>{l.category_name ?? catName(l.category_code)}</td>
                      <td className="num"><Money paise={l.actual_paise} tone={l.status === "OVER" ? "red" : undefined} /></td>
                      <td className="num">{l.budget_paise === null ? <span className="text-muted">—</span> : <Money paise={l.budget_paise} tone="muted" />}</td>
                      <td className="align-middle"><LimitBar actual={l.actual_paise} budget={l.budget_paise} status={l.status} /></td>
                      <td><StatusStamp status={l.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </QueryState>
        </Section>

        <Section title="Margin notes">
          <ul className="space-y-0">
            {unsorted.data && unsorted.data.items.length > 0 && (
              <Note tone="red" to={`/entries?month=${month}&kind=UNKNOWN`}>
                <b>{unsorted.data.items.length}{unsorted.data.next_cursor ? "+" : ""} entries</b> could not be sorted. Pick a category and PAM remembers it.
              </Note>
            )}
            {recurring.data?.filter((r) => r.status === "MISSED").slice(0, 3).map((r) => (
              <Note key={r.series_id} tone="red" to="/recurring">
                <b>{r.merchant_name ?? catName(r.category_code)}</b> looks missed — expected {r.next_expected ? dayLabel(r.next_expected) : "recently"}, usually <Money paise={r.typical_amount_paise} />.
              </Note>
            ))}
            {insights.data?.slice(0, 4).map((i) => (
              <Note key={i.insight_id} tone={i.severity === "ALERT" ? "red" : i.severity === "WARN" ? "amber" : "muted"} to={`/insights?month=${month}`}>{i.message}</Note>
            ))}
          </ul>
          {insights.isPending && <Skeleton rows={3} />}
          {insights.isError && <ErrorBox error={insights.error} retry={() => insights.refetch()} />}
          {insights.data?.length === 0 && !unsorted.data?.items.length && !recurring.data?.some((r) => r.status === "MISSED") &&
            <p className="text-muted py-3">Nothing needs your attention this month.</p>}
        </Section>
      </div>

      <Section title="Twelve months">
        <QueryState q={trend} rows={3}>{(t) => t.length < 2 ? <p className="text-muted py-3">Trends appear after a second month of entries.</p> : <TrendChart data={t} current={month} />}</QueryState>
      </Section>
    </>
  );
}

function Note({ tone, to, children }: { tone: "red" | "amber" | "muted"; to: string; children: React.ReactNode }) {
  const c = tone === "red" ? "text-red" : tone === "amber" ? "text-amber" : "text-muted";
  return (
    <li className="border-b border-rule py-2.5 flex gap-3">
      <span className={`mt-1.5 w-2 h-2 shrink-0 rounded-full ${tone === "red" ? "bg-red" : tone === "amber" ? "bg-amber" : "bg-muted"}`} aria-hidden />
      <Link to={to} className="no-underline text-ink hover:underline flex-1">{children}</Link>
      <span className={`sr-only ${c}`}>{tone}</span>
    </li>
  );
}

/** Spend per month as ruled columns; income is the blue tick above. Hover or focus a column for its figures. */
function TrendChart({ data, current }: { data: Trend[]; current: string }) {
  const W = 760, H = 190, L = 6, B = 26, T = 22;
  const max = Math.max(...data.map((d) => Math.max(d.spend_paise, d.income_paise)), 1);
  const step = (W - L) / data.length, bw = Math.min(34, step * 0.56);
  const y = (v: number) => T + (H - T - B) * (1 - v / max);
  const peak = data.reduce((a, d) => (d.spend_paise > a.spend_paise ? d : a), data[0]);
  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label={`Spend per month, ${data.length} months. Highest ${monthName(peak.month)} at ₹${rupeesShort(peak.spend_paise)}.`}>
        {[0, 0.5, 1].map((f) => <line key={f} x1={L} x2={W} y1={y(max * f)} y2={y(max * f)} stroke="var(--rule)" />)}
        {data.map((d, i) => {
          const x = L + i * step + (step - bw) / 2, isNow = d.month === current;
          return (
            <g key={d.month} tabIndex={0} aria-label={`${monthName(d.month)}: spend ₹${rupeesShort(d.spend_paise)}, income ₹${rupeesShort(d.income_paise)}`}>
              <title>{`${monthName(d.month)} · spent ₹${rupeesShort(d.spend_paise)} · income ₹${rupeesShort(d.income_paise)}`}</title>
              <rect x={L + i * step} y={T} width={step} height={H - T - B} fill="transparent" />
              <rect x={x} y={y(d.spend_paise)} width={bw} height={Math.max(H - B - y(d.spend_paise), 0)} fill={isNow ? "var(--blue)" : "var(--rule-strong)"} rx="3" />
              <line x1={x - 3} x2={x + bw + 3} y1={y(d.income_paise)} y2={y(d.income_paise)} stroke="var(--red)" strokeWidth="2" />
              <text x={x + bw / 2} y={H - 8} textAnchor="middle" fontSize="11" fill="var(--muted)">{monthName(d.month, true).slice(0, 3)}</text>
              {(d === peak || isNow) && <text x={x + bw / 2} y={y(d.spend_paise) - 6} textAnchor="middle" fontSize="11" fontWeight="700" fill="var(--ink)">₹{rupeesShort(d.spend_paise)}</text>}
            </g>
          );
        })}
      </svg>
      <figcaption className="text-sm text-muted flex gap-5 mt-1">
        <span><span className="inline-block w-3 h-3 bg-rule-strong align-[-2px] mr-1.5" />Spend</span>
        <span><span className="inline-block w-3 h-0.5 bg-red align-middle mr-1.5" />Income</span>
        <span>Selected month in ink</span>
      </figcaption>
    </figure>
  );
}
