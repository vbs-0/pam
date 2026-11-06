import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
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

      {summary.isPending ? <CardSkeleton /> : <QueryState q={summary} rows={3}>
        {(s) => {
          const noData = s.income_paise === 0 && s.spend_paise === 0 && s.naive_spend_paise === 0;
          if (noData && profile.data && !sample) return (
            <Empty title="Nothing written for this month yet" hint="Add an account and a few entries and PAM will categorise them, pair your own transfers and compare spending with budgets."
              action={<Link className="btn btn-solid no-underline" to="/books">Set up your books</Link>} />
          );
          const gap = s.naive_spend_paise - s.spend_paise;
          return (
            <div key={month} className="reinked grid md:grid-cols-[1.6fr_1fr_1fr] gap-4 mb-9">
              <div className="hero-card p-6 rounded-2xl">
                <p className="text-sm font-bold uppercase tracking-wider text-muted">True spend</p>
                <p className="text-5xl font-semibold tracking-tight mt-1"><Money paise={s.spend_paise} /></p>
                {gap > 0 && (
                  <p className="mt-3 text-muted text-sm">
                    A plain ledger would show <span className="strike-draw font-semibold"><Money paise={s.naive_spend_paise} /></span>.
                    PAM leaves out <b className="text-ink"><Money paise={gap} /></b>
                    {s.transfers_out_paise > 0 && <> — <Money paise={s.transfers_out_paise} /> moved between your own accounts <Stamp>Contra</Stamp></>}, plus refunds and reversals.
                  </p>
                )}
              </div>
              <div className="stat-card p-6 rounded-2xl">
                <p className="text-sm font-bold uppercase tracking-wider text-muted">Income</p>
                <p className="text-3xl font-semibold mt-2"><Money paise={s.income_paise} /></p>
              </div>
              <div className="stat-card p-6 rounded-2xl">
                <p className="text-sm font-bold uppercase tracking-wider text-muted">Kept</p>
                <p className={`text-3xl font-semibold mt-2 ${s.savings_rate !== null && s.savings_rate < 0 ? "text-red" : ""}`}>
                  {s.savings_rate === null ? "—" : `${Math.round(s.savings_rate * 100)}%`}
                </p>
                <p className="text-sm text-muted mt-1">{s.savings_rate === null ? "No income recorded" : s.savings_rate < 0 ? "Spent more than came in" : "of income"}</p>
              </div>
            </div>
          );
        }}
      </QueryState>}

      {!sample || summary.data ? <FolioExtras month={month} summary={summary.data} budgets={budgets.data} /> : null}

      <div className="panels grid lg:grid-cols-[1.55fr_1fr] gap-6 mb-6">
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

      <div className="panel">
      <Section title="Twelve months">
        <QueryState q={trend} rows={3}>{(t) => t.length < 2 ? <p className="text-muted py-3">Trends appear after a second month of entries.</p> : <TrendChart data={t} current={month} />}</QueryState>
      </Section>
      </div>
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

/** Spend per month as one line (the Vestox graph). The dot rides the line from January to the selected month when the page opens,
    and glides along it to whichever month you hover. Where spend rises above income the line glows red. */
export function TrendChart({ data, current }: { data: Trend[]; current: string }) {
  const W = 760, H = 220, L = 18, R = 18, B = 30, T = 34;
  const max = Math.max(...data.map((d) => Math.max(d.spend_paise, d.income_paise)), 1);
  const x = (i: number) => L + ((W - L - R) * i) / Math.max(data.length - 1, 1);
  const y = (v: number) => T + (H - T - B) * (1 - v / max);
  const curve = (vals: number[]) => vals.map((v, i) => {
    if (i === 0) return `M${x(0)} ${y(v)}`;
    const mx = (x(i - 1) + x(i)) / 2;
    return `C${mx} ${y(vals[i - 1])} ${mx} ${y(v)} ${x(i)} ${y(v)}`;
  }).join(" ");
  const spend = data.map((d) => d.spend_paise), income = data.map((d) => d.income_paise);
  const nowIdx = Math.max(data.findIndex((d) => d.month === current), 0);
  const [hot, setHot] = useState<number | null>(null);
  const [ready, setReady] = useState(false);
  const at = hot ?? nowIdx, d = data[at];
  const peak = data.reduce((a, dd) => (dd.spend_paise > a.spend_paise ? dd : a), data[0]);
  const uid = useId().replace(/:/g, "");
  const spendPath = curve(spend), incomePath = curve(income);
  const area = `${spendPath} L${x(data.length - 1)} ${H - B} L${x(0)} ${H - B} Z`;
  const above = `${incomePath} L${x(data.length - 1)} 0 L${x(0)} 0 Z`;   // everything above the income line
  const below = `${incomePath} L${x(data.length - 1)} ${H} L${x(0)} ${H} Z`;   // everything below it
  const incomeArea = `${incomePath} L${x(data.length - 1)} ${H - B} L${x(0)} ${H - B} Z`;
  const pathRef = useRef<SVGPathElement>(null), dotRef = useRef<SVGGElement>(null), labRef = useRef<SVGTextElement>(null), guideRef = useRef<SVGLineElement>(null);
  const lenRef = useRef(0), raf = useRef(0);

  const place = (len: number) => {
    const pt = pathRef.current?.getPointAtLength(len);
    if (!pt || !dotRef.current) return;
    dotRef.current.style.transform = `translate(${pt.x}px, ${pt.y}px)`;
    labRef.current?.setAttribute("x", String(pt.x)); labRef.current?.setAttribute("y", String(Math.max(pt.y - 16, 14)));
    guideRef.current?.setAttribute("x1", String(pt.x)); guideRef.current?.setAttribute("x2", String(pt.x));
  };
  const lenAtX = (xt: number) => {
    const p = pathRef.current!;
    let lo = 0, hi = p.getTotalLength();
    for (let i = 0; i < 26; i++) { const mid = (lo + hi) / 2; if (p.getPointAtLength(mid).x < xt) lo = mid; else hi = mid; }
    return hi;
  };
  const go = (to: number, dur: number, done?: () => void) => {
    cancelAnimationFrame(raf.current);
    const from = lenRef.current, t0 = performance.now();
    const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
    const step = (now: number) => {
      const t = dur <= 0 ? 1 : Math.min(1, (now - t0) / dur);
      lenRef.current = from + (to - from) * ease(t);
      place(lenRef.current);
      if (t < 1) raf.current = requestAnimationFrame(step); else done?.();
    };
    raf.current = requestAnimationFrame(step);
  };
  // page open: start at the beginning of the line and ride it to the selected month while the line draws
  useLayoutEffect(() => {
    setReady(false); lenRef.current = 0; place(0);
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches && document.documentElement.dataset.motion !== "on";
    go(lenAtX(x(nowIdx)), still ? 0 : 2000, () => setReady(true));
    return () => cancelAnimationFrame(raf.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, current]);
  // hover or focus: glide along the line to that month
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!ready) return;
    // a short hover-intent pause, then a slow float along the line (longer trips take longer)
    const t = window.setTimeout(() => { const to = lenAtX(x(at)); go(to, Math.min(2400, Math.max(800, 700 + Math.abs(to - lenRef.current) * 1.5))); }, 140);
    return () => window.clearTimeout(t);
  }, [at, ready]);

  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label={`Spend per month, ${data.length} months. Highest ${monthName(peak.month)} at ₹${rupeesShort(peak.spend_paise)}.`}>
        <defs><clipPath id={`above-${uid}`}><path d={above} /></clipPath><clipPath id={`below-${uid}`}><path d={below} /></clipPath></defs>
        {[0, 0.5, 1].map((f) => <line key={f} x1={L} x2={W - R} y1={y(max * f)} y2={y(max * f)} stroke="var(--rule-strong)" strokeDasharray="3 6" />)}
        <path d={area} className="tl-area" />
        <path d={area} className="tl-over-area" clipPath={`url(#above-${uid})`} />
        <path d={`${incomeArea} ${area}`} fillRule="evenodd" className="tl-under-area" clipPath={`url(#below-${uid})`} />
        <path d={incomePath} className="tl-income tl-draw" pathLength={1} />
        <path ref={pathRef} d={spendPath} className="tl-spend tl-draw" pathLength={1} />
        <path d={spendPath} className="tl-over-line tl-draw" pathLength={1} clipPath={`url(#above-${uid})`} />
        <path d={spendPath} className="tl-under-line tl-draw" pathLength={1} clipPath={`url(#below-${uid})`} />
        <line ref={guideRef} y1={T - 6} y2={H - B} className="tl-guide" />
        <g ref={dotRef} className="tl-dot">
          <g className="tl-bob">
            <circle r="16" className="tl-dot-halo" />
            <circle r="8" className="tl-dot-ring" />
            <circle r="5" className="tl-dot-core" />
          </g>
        </g>
        <text ref={labRef} textAnchor="middle" className="tl-label" style={{ visibility: ready ? "visible" : "hidden" }}>₹{rupeesShort(d.spend_paise)}{d.spend_paise > d.income_paise ? " · over income" : ""}</text>
        {data.map((dd, i) => (
          <g key={dd.month} tabIndex={0} aria-label={`${monthName(dd.month)}: spend ₹${rupeesShort(dd.spend_paise)}, income ₹${rupeesShort(dd.income_paise)}`}
            onMouseEnter={() => setHot(i)} onMouseLeave={() => setHot(null)} onFocus={() => setHot(i)} onBlur={() => setHot(null)}>
            <title>{`${monthName(dd.month)} · spent ₹${rupeesShort(dd.spend_paise)} · income ₹${rupeesShort(dd.income_paise)}`}</title>
            <rect x={x(i) - (W - L - R) / data.length / 2} y={T - 10} width={(W - L - R) / data.length} height={H - T - B + 10} fill="transparent" />
            <text x={x(i)} y={H - 8} textAnchor="middle" fontSize="11" fill={i === at ? "var(--ink)" : "var(--muted)"} fontWeight={i === at ? 700 : 400}>{monthName(dd.month, true).slice(0, 3)}</text>
          </g>
        ))}
      </svg>
      <figcaption className="text-sm text-muted flex flex-wrap gap-x-5 gap-y-1 mt-1">
        <span><span className="inline-block w-4 h-[3px] rounded-full bg-ink align-middle mr-1.5" />Spend</span>
        <span><span className="inline-block w-4 h-[2px] rounded-full align-middle mr-1.5" style={{ background: "var(--orange)" }} />Income</span>
        <span><span className="inline-block w-4 h-[3px] rounded-full align-middle mr-1.5" style={{ background: "var(--red)", boxShadow: "0 0 6px var(--red)" }} />Spend above income</span>
        <span><span className="inline-block w-4 h-[3px] rounded-full align-middle mr-1.5" style={{ background: "var(--ok)", boxShadow: "0 0 6px var(--ok)" }} />Spend below income</span>
        <span>Hover a month to move the dot</span>
      </figcaption>
    </figure>
  );
}

function CardSkeleton() {
  const label = "text-sm font-bold uppercase tracking-wider";
  return (
    <div className="grid md:grid-cols-[1.6fr_1fr_1fr] gap-4 mb-9" aria-hidden>
      <div className="sk-card sk-hero" style={{ animationDelay: "0s" }}><p className={label}>True spend</p><div className="sk-num" /><div className="sk-line" /><div className="sk-line short" /></div>
      <div className="sk-card sk-sand" style={{ animationDelay: ".1s" }}><p className={label}>Income</p><div className="sk-num" /></div>
      <div className="sk-card sk-ink" style={{ animationDelay: ".2s" }}><p className={label}>Kept</p><div className="sk-num" /><div className="sk-line short" /></div>
    </div>
  );
}
