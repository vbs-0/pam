import { useState, type ReactNode } from "react";
import { rupees, rupeesShort } from "../lib/format";

/* Hand-built SVG charts (no library). Colours are the console's own tokens plus four extra categorical hues; every chart
   has a legend or labels, and nothing relies on colour alone. Bars and slices grow in once and respect reduced motion. */
export const PALETTE = ["var(--blue)", "var(--red)", "var(--green)", "var(--amber)", "#7a5ab8", "#1f8a9e", "#b5497a", "#6b7b3a"];

export interface Slice { key: string; label: string; value: number; hint?: string }

/** Ring chart with a centre total and a ranked legend; hovering or focusing a row highlights its slice. */
export function Donut({ slices, total, centre, onPick }: { slices: Slice[]; total: number; centre: ReactNode; onPick?: (key: string) => void }) {
  const [hot, setHot] = useState<string | null>(null);
  const R = 70, C = 2 * Math.PI * R;
  let acc = 0;
  const shown = slices.slice(0, 7);
  const rest = slices.slice(7).reduce((s, x) => s + x.value, 0);
  const all = rest > 0 ? [...shown, { key: "_other", label: "Everything else", value: rest }] : shown;
  return (
    <div className="grid gap-6 md:grid-cols-[220px_1fr] items-center">
      <div className="relative mx-auto w-[200px] h-[200px]">
        <svg viewBox="0 0 200 200" className="w-full h-full -rotate-90" role="img" aria-label="Spend by category">
          <circle cx="100" cy="100" r={R} fill="none" stroke="var(--rule)" strokeWidth="26" />
          {total > 0 && all.map((s, i) => {
            const len = (s.value / total) * C;
            const el = (
              <circle key={s.key} cx="100" cy="100" r={R} fill="none" stroke={PALETTE[i % PALETTE.length]} strokeWidth={hot === s.key ? 32 : 26}
                strokeDasharray={`${Math.max(len - 2, 0)} ${C}`} strokeDashoffset={-acc} className="donut-slice" style={{ transition: "stroke-width .15s" }}
                onMouseEnter={() => setHot(s.key)} onMouseLeave={() => setHot(null)} />
            );
            acc += len;
            return el;
          })}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center text-center px-8 pointer-events-none">{centre}</div>
      </div>
      <ol className="space-y-1">
        {all.map((s, i) => (
          <li key={s.key}>
            <button type="button" className={`w-full flex items-center gap-3 py-1.5 px-2 text-left rounded-sm ${hot === s.key ? "bg-blue-soft" : ""}`}
              onMouseEnter={() => setHot(s.key)} onMouseLeave={() => setHot(null)} onFocus={() => setHot(s.key)} onBlur={() => setHot(null)}
              onClick={() => onPick && s.key !== "_other" && onPick(s.key)} disabled={!onPick || s.key === "_other"}>
              <span aria-hidden className="inline-block w-3 h-3 shrink-0" style={{ background: PALETTE[i % PALETTE.length] }} />
              <span className="flex-1 truncate">{s.label}</span>
              {s.hint && <span className="text-xs text-muted">{s.hint}</span>}
              <span className="num tabular-nums text-sm w-12 text-right text-muted">{total ? Math.round((s.value / total) * 100) : 0}%</span>
              <span className="num tabular-nums w-24 text-right">₹{rupeesShort(s.value)}</span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}

/** Horizontal bars with labels; the longest bar is full width. */
export function BarList({ rows, format = (v: number) => `₹${rupeesShort(v)}`, onPick }: {
  rows: { key: string; label: string; value: number; sub?: string }[]; format?: (v: number) => string; onPick?: (key: string) => void;
}) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <ul className="space-y-2">
      {rows.map((r) => (
        <li key={r.key}>
          <button type="button" className="w-full text-left group" onClick={() => onPick?.(r.key)} disabled={!onPick}>
            <div className="flex justify-between gap-3 text-sm"><span className="truncate">{r.label}{r.sub && <span className="text-muted"> · {r.sub}</span>}</span><span className="num tabular-nums">{format(r.value)}</span></div>
            <div className="h-2.5 bg-[var(--rule)] mt-1" aria-hidden><div className="h-full bg-blue bar-grow group-hover:opacity-80" style={{ width: `${(r.value / max) * 100}%` }} /></div>
          </button>
        </li>
      ))}
    </ul>
  );
}

/** Seven columns for Monday to Sunday; the highest day is drawn in red so it stands out. */
export function WeekdayBars({ days }: { days: { name: string; value: number; sub: string }[] }) {
  const max = Math.max(1, ...days.map((d) => d.value));
  const top = days.reduce((a, d, i) => (d.value > days[a].value ? i : a), 0);
  return (
    <div className="grid grid-cols-7 gap-2 items-end h-44" role="img" aria-label="Average spend by day of week">
      {days.map((d, i) => (
        <div key={d.name} className="flex flex-col items-center justify-end h-full gap-1" title={`${d.name}: ${d.sub}`}>
          <span className="text-xs num text-muted">₹{rupeesShort(d.value)}</span>
          <div className="w-full max-w-[44px] bar-grow-y" style={{ height: `${Math.max((d.value / max) * 100, 2)}%`, background: i === top && d.value > 0 ? "var(--red)" : "var(--blue)" }} />
          <span className="text-xs font-semibold">{d.name}</span>
        </div>
      ))}
    </div>
  );
}

/** Twelve-month style comparison: spend bars with an income tick. */
export function TrendBars({ rows }: { rows: { label: string; spend: number; income: number }[] }) {
  const max = Math.max(1, ...rows.flatMap((r) => [r.spend, r.income]));
  return (
    <div className="flex items-end gap-2 h-48 overflow-x-auto pb-1" role="img" aria-label="Spend and income by month">
      {rows.map((r) => (
        <div key={r.label} className="flex-1 min-w-[34px] h-full flex flex-col justify-end items-center gap-1" title={`${r.label}: spent ₹${rupees(r.spend)}, income ₹${rupees(r.income)}`}>
          <div className="relative w-full flex-1 flex items-end">
            <div className="w-full bar-grow-y bg-blue" style={{ height: `${(r.spend / max) * 100}%` }} />
            {r.income > 0 && <span aria-hidden className="absolute left-0 right-0 h-[2px] bg-green" style={{ bottom: `${(r.income / max) * 100}%` }} />}
          </div>
          <span className="text-[11px] text-muted">{r.label}</span>
        </div>
      ))}
    </div>
  );
}

export function Delta({ paise, goodWhenDown = true }: { paise: number; goodWhenDown?: boolean }) {
  if (paise === 0) return <span className="text-muted">no change</span>;
  const up = paise > 0, good = goodWhenDown ? !up : up;
  return <span className={good ? "text-green" : "text-red"}>{up ? "▲" : "▼"} ₹{rupeesShort(paise)}</span>;
}
