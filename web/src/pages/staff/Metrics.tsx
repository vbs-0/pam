import { useQuery } from "@tanstack/react-query";
import { Empty, ErrorBox, PageHead, QueryState, Section, StatusStamp } from "../../components/ui";
import { ApiError, get } from "../../lib/api";
import { dateTime, titleCase } from "../../lib/format";

interface Metrics {
  run_id: string; evaluated_at: string; all_pass: boolean;
  thresholds: Record<string, { value: number; target: string; pass: boolean }>;
  naive_baseline?: { naive_overstatement?: number; system_error?: number };
  categorization?: { accuracy?: number; macro_f1?: number };
}
interface Run { run_id: string; status: string; started_at: string; finished_at: string | null; stats: Record<string, number> | null; error: string | null }

export default function MetricsPage() {
  const m = useQuery({ queryKey: ["metrics"], queryFn: () => get<Metrics>("/analyst/metrics"), retry: false });
  const runs = useQuery({ queryKey: ["runs"], queryFn: () => get<Run[]>("/analyst/runs") });
  return (
    <>
      <PageHead title="Metrics" sub="How the latest pipeline run scored against the labelled ground truth." />
      {m.isPending ? null : m.isError ? ((m.error as ApiError).status === 404 ? <Empty title="No evaluation yet" hint="An admin can start one from Jobs." /> : <ErrorBox error={m.error} retry={() => m.refetch()} />) : (
        <Section title={`Thresholds · ${m.data.run_id} · ${dateTime(m.data.evaluated_at)}`} right={<StatusStamp status={m.data.all_pass ? "PASS" : "FAIL"} />}>
          <table className="register">
            <thead><tr><th>Measure</th><th className="num">Value</th><th>Target</th><th>Result</th></tr></thead>
            <tbody>{Object.entries(m.data.thresholds).map(([k, t]) => (
              <tr key={k}><td>{titleCase(k)}</td><td className="num font-semibold">{(t.value * 100).toFixed(1)}%</td><td className="text-muted">{t.target}</td><td><StatusStamp status={t.pass ? "PASS" : "FAIL"} /></td></tr>
            ))}</tbody>
          </table>
          {m.data.naive_baseline?.naive_overstatement != null && (
            <p className="mt-4">A plain ledger overstates spend by <b>{Math.round(m.data.naive_baseline.naive_overstatement * 100)}%</b>; PAM's spend total is off by <b>{((m.data.naive_baseline.system_error ?? 0) * 100).toFixed(2)}%</b>.</p>
          )}
        </Section>
      )}
      <Section title="Pipeline runs">
        <QueryState q={runs}>{(rows) => (
          <table className="register">
            <thead><tr><th>Run</th><th>Status</th><th>Started</th><th className="num">Transactions</th><th className="num">Series</th><th className="num">Exceptions</th></tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.run_id}><td className="font-mono text-xs">{r.run_id}</td><td><StatusStamp status={r.status} />{r.error && <div className="text-xs text-red mt-1">{r.error}</div>}</td><td className="text-sm">{dateTime(r.started_at)}</td>
                <td className="num">{r.stats?.txns?.toLocaleString("en-IN") ?? "—"}</td><td className="num">{r.stats?.series ?? "—"}</td><td className="num">{r.stats?.exceptions ?? "—"}</td></tr>
            ))}</tbody>
          </table>
        )}</QueryState>
      </Section>
    </>
  );
}
