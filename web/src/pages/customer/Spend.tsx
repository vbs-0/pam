import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { BarList, Delta, Donut, TrendBars, WeekdayBars } from "../../components/charts";
import { Empty, MonthBar, PageHead, QueryState, Section, useMonth } from "../../components/ui";
import { get } from "../../lib/api";
import { monthName, rupees } from "../../lib/format";
import type { MerchantSpend, SpendByCategory, WeekdaySpend } from "../../lib/types";

interface TrendRow { month: string; spend_paise: number; income_paise: number }

/** Where the money went: categories with change against last month, top payees, the weekly pattern, and a year of months. */
export default function Spend() {
  const [month, setMonth] = useMonth();
  const nav = useNavigate();
  const cats = useQuery({ queryKey: ["spend-cats", month], queryFn: () => get<SpendByCategory>("/me/spend-by-category", { month }) });
  const merchants = useQuery({ queryKey: ["merchants"], queryFn: () => get<MerchantSpend[]>("/me/merchants", { months: 6, limit: 10 }) });
  const week = useQuery({ queryKey: ["weekday"], queryFn: () => get<WeekdaySpend[]>("/me/weekday", { months: 6 }) });
  const trend = useQuery({ queryKey: ["trend", 12], queryFn: () => get<TrendRow[]>("/me/trend", { months: 12 }) });
  return (
    <>
      <PageHead title={`Spend · ${monthName(month)}`} sub="Where the money went, and how it compares with last month." right={<MonthBar month={month} onChange={setMonth} />} />
      <Section title="By category">
        <QueryState q={cats} rows={6}>
          {(d) => d.categories.length === 0 ? <Empty title="No spending this month" hint="Entries you add show up here by category." /> : (
            <div className="space-y-6">
              <Donut
                slices={d.categories.filter((c) => c.spend_paise > 0).map((c) => ({ key: c.code, label: c.name, value: c.spend_paise }))}
                total={d.total_paise}
                centre={<><span className="text-xs text-muted">Spent</span><span className="text-xl font-semibold num">₹{rupees(d.total_paise)}</span></>}
                onPick={(code) => nav(`/entries?month=${month}&category=${code}`)}
              />
              <div className="overflow-x-auto">
                <table className="register min-w-[520px]">
                  <caption className="text-left text-sm text-muted pb-2">Against {monthName(d.previous_month)}: total <Delta paise={d.change_paise} /></caption>
                  <thead><tr><th>Category</th><th className="num">This month</th><th className="num">Last month</th><th className="num">Change</th></tr></thead>
                  <tbody>{d.categories.map((c) => (
                    <tr key={c.code} className="clickable" tabIndex={0} onClick={() => nav(`/entries?month=${month}&category=${c.code}`)} onKeyDown={(e) => e.key === "Enter" && nav(`/entries?month=${month}&category=${c.code}`)}>
                      <td>{c.name}</td><td className="num">₹{rupees(c.spend_paise)}</td><td className="num text-muted">₹{rupees(c.previous_paise)}</td><td className="num"><Delta paise={c.change_paise} /></td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            </div>
          )}
        </QueryState>
      </Section>

      <div className="grid gap-8 lg:grid-cols-2">
        <Section title="Top payees · last 6 months">
          <QueryState q={merchants} rows={5}>
            {(rows) => rows.length === 0 ? <Empty title="No payees yet" /> : (
              <BarList rows={rows.map((m) => ({ key: m.name, label: m.name, value: m.spend_paise, sub: `${m.count} payment${m.count > 1 ? "s" : ""}` }))} onPick={(name) => nav(`/entries?month=all&merchant=${encodeURIComponent(name)}`)} />
            )}
          </QueryState>
        </Section>
        <Section title="Which days you spend most">
          <QueryState q={week} rows={4}>
            {(rows) => rows.every((r) => r.spend_paise === 0) ? <Empty title="Not enough yet" hint="A few weeks of entries show your weekly rhythm." /> : (
              <>
                <WeekdayBars days={rows.map((r) => ({ name: r.name, value: r.average_paise, sub: `₹${rupees(r.average_paise)} on an average ${r.name}` }))} />
                <p className="text-sm text-muted mt-3">Average spend on each weekday over the last six months.</p>
              </>
            )}
          </QueryState>
        </Section>
      </div>

      <Section title="Twelve months">
        <QueryState q={trend} rows={4}>
          {(rows) => rows.length === 0 ? <Empty title="No history yet" /> : (
            <>
              <TrendBars rows={rows.map((r) => ({ label: monthName(r.month, true), spend: r.spend_paise, income: r.income_paise }))} />
              <p className="text-sm text-muted mt-2"><span className="inline-block w-3 h-3 bg-blue align-middle mr-1" aria-hidden />Spent <span className="inline-block w-3 h-[2px] bg-green align-middle ml-4 mr-1" aria-hidden />Income</p>
            </>
          )}
        </QueryState>
      </Section>
    </>
  );
}
