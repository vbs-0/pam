import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router";
import { Empty, ErrorBox, Field, Money, PageHead, QueryState, Section, Skeleton, StatusStamp } from "../../components/ui";
import { ApiError, get } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { dateTime, titleCase } from "../../lib/format";
import type { Page, TraceOut } from "../../lib/types";

interface Summary { run_id: string; all_pass: boolean; by_issue: { issue_type: string; labelled: number; caught: number; recall: number | null }[] }
interface Anomaly { anomaly_id: string; issue_type: string; entity_type: string; entity_id: string; expected_decision: string; note: string | null; outcome: "CAUGHT" | "MISSED"; observed: string | null }
interface Audit { id: number; at: string; actor: string; action: string; entity_type: string; entity_id: string; request_id: string | null; detail: unknown }

const NoEval = ({ error, retry }: { error: unknown; retry: () => void }) => (error as ApiError).status === 404
  ? <Empty title="No evaluation yet" hint="An admin can run one from Jobs." /> : <ErrorBox error={error} retry={retry} />;

export function Anomalies() {
  const [issue, setIssue] = useState(""), [outcome, setOutcome] = useState("");
  const sum = useQuery({ queryKey: ["review-summary"], queryFn: () => get<Summary>("/review/summary"), retry: false });
  const list = useQuery({ queryKey: ["anomalies", issue, outcome], queryFn: () => get<Anomaly[]>("/review/anomalies", { issue_type: issue, outcome }), retry: false });
  return (
    <>
      <PageHead title="Anomalies" sub="Each planted issue in the data and whether the engine caught it." />
      {sum.isError ? <NoEval error={sum.error} retry={() => sum.refetch()} /> : (
        <Section title="Recall by issue type" right={sum.data && <StatusStamp status={sum.data.all_pass ? "PASS" : "FAIL"} />}>
          <QueryState q={sum} rows={4}>{(s) => (
            <figure>
              <ul className="space-y-2" aria-label="Recall per issue type">
                {s.by_issue.map((b) => (
                  <li key={b.issue_type} className="grid grid-cols-[minmax(150px,230px)_1fr_90px] items-center gap-3">
                    <span className="text-sm">{titleCase(b.issue_type)}</span>
                    <div className="relative h-4 border-y border-rule" role="img" aria-label={`${b.caught} of ${b.labelled} caught`}>
                      <div className="absolute inset-y-0 left-0 rounded-r-[4px]" style={{ width: `${(b.recall ?? 0) * 100}%`, background: (b.recall ?? 0) >= 0.9 ? "var(--blue)" : "var(--red)" }} />
                    </div>
                    <span className="num text-sm"><b>{b.caught}</b>/{b.labelled} · {b.recall == null ? "—" : `${Math.round(b.recall * 100)}%`}</span>
                  </li>
                ))}
              </ul>
              <figcaption className="text-xs text-muted mt-2">Run {s.run_id}. Bars below 90% turn red.</figcaption>
            </figure>
          )}</QueryState>
        </Section>
      )}
      <Section title="Cases">
        <div className="grid sm:grid-cols-2 gap-3 max-w-xl mb-3">
          <Field label="Issue type">{(id) => <select id={id} className="field" value={issue} onChange={(e) => setIssue(e.target.value)}><option value="">All</option>{sum.data?.by_issue.map((b) => <option key={b.issue_type} value={b.issue_type}>{titleCase(b.issue_type)}</option>)}</select>}</Field>
          <Field label="Outcome">{(id) => <select id={id} className="field" value={outcome} onChange={(e) => setOutcome(e.target.value)}><option value="">All</option><option value="CAUGHT">Caught</option><option value="MISSED">Missed</option></select>}</Field>
        </div>
        {list.isPending ? <Skeleton rows={6} /> : list.isError ? null : list.data.length === 0 ? <Empty title="No cases match" /> : (
          <div className="overflow-x-auto"><table className="register min-w-[760px]">
            <thead><tr><th>Case</th><th>Issue</th><th>Entity</th><th>Expected</th><th>Observed</th><th>Outcome</th></tr></thead>
            <tbody>{list.data.map((a) => (
              <tr key={a.anomaly_id}><td className="font-mono text-xs">{a.anomaly_id}</td><td>{titleCase(a.issue_type)}</td>
                <td className="font-mono text-xs"><a href={a.entity_type === "TXN" ? `/trace?txn=${a.entity_id}` : undefined}>{a.entity_id.length > 34 ? `${a.entity_id.slice(0, 34)}…` : a.entity_id}</a></td>
                <td className="text-sm">{a.expected_decision}</td><td className="text-sm text-muted">{a.observed ?? "—"}</td>
                <td><StatusStamp status={a.outcome === "MISSED" ? "FAILED" : "SUCCEEDED"} /> <span className="sr-only">{a.outcome}</span></td></tr>
            ))}</tbody>
          </table></div>
        )}
      </Section>
    </>
  );
}

export function AuditLog() {
  const [f, setF] = useState({ actor: "", action: "", entity_id: "" });
  const list = useInfiniteQuery({
    queryKey: ["audit", f],
    queryFn: ({ pageParam }) => get<Page<Audit>>("/review/audit", { ...f, cursor: pageParam, limit: 50 }),
    initialPageParam: undefined as string | undefined, getNextPageParam: (l) => l.next_cursor ?? undefined,
  });
  const rows = list.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <>
      <PageHead title="Audit log" sub="Append-only record of who did what, newest first." />
      <div className="grid sm:grid-cols-3 gap-3 mb-4">
        {(["actor", "action", "entity_id"] as const).map((k) => <Field key={k} label={titleCase(k)}>{(id) => <input id={id} className="field" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} placeholder={k === "action" ? "CATEGORY_OVERRIDE" : ""} />}</Field>)}
      </div>
      {list.isPending ? <Skeleton rows={8} /> : list.isError ? <ErrorBox error={list.error} retry={() => list.refetch()} /> : rows.length === 0 ? <Empty title="Nothing logged yet" /> : (
        <div className="overflow-x-auto"><table className="register min-w-[760px]">
          <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Entity</th><th>Detail</th></tr></thead>
          <tbody>{rows.map((a) => (
            <tr key={a.id}><td className="text-sm whitespace-nowrap">{dateTime(a.at)}</td><td className="text-sm">{a.actor}</td><td><span className="stamp text-blue">{a.action.toLowerCase().replace(/_/g, " ")}</span></td>
              <td className="font-mono text-xs">{a.entity_type} {a.entity_id}</td>
              <td className="text-xs text-muted max-w-[320px] truncate" title={a.detail ? JSON.stringify(a.detail) : ""}>{a.detail ? JSON.stringify(a.detail) : ""}</td></tr>
          ))}</tbody>
        </table>
          <div className="py-4 text-center">{list.hasNextPage ? <button className="btn" disabled={list.isFetchingNextPage} onClick={() => list.fetchNextPage()}>Load older</button> : <span className="text-sm text-muted">Start of the log</span>}</div></div>
      )}
    </>
  );
}

export function Trace() {
  const { me } = useAuth();
  const [sp, setSp] = useSearchParams();
  const txn = sp.get("txn") ?? "";
  const [input, setInput] = useState(txn);
  const q = useQuery({ queryKey: ["trace", txn], queryFn: () => get<TraceOut>(`/ops/transactions/${txn}`), enabled: !!txn, retry: false });
  const d = q.data as TraceOut;   // only read in the branch where the query has succeeded
  return (
    <>
      <PageHead title="Transaction trace" sub="Every decision about one transaction, across runs." />
      <form className="flex gap-2 max-w-xl mb-6" onSubmit={(e) => { e.preventDefault(); setSp({ txn: input.trim() }); }}>
        <input aria-label="Transaction id" className="field font-mono" value={input} onChange={(e) => setInput(e.target.value)} placeholder="TXN-2026-00000123" />
        <button className="btn btn-solid" disabled={!input.trim()}>Trace</button>
      </form>
      {!txn ? <Empty title="Enter a transaction id" /> : q.isPending ? <Skeleton rows={6} /> : q.isError ? <ErrorBox error={q.error} retry={() => q.refetch()} /> : (
        <div className="space-y-8">
          <Section title="Transaction">
            <dl className="grid grid-cols-[150px_1fr] gap-y-1 text-sm">
              <dt className="text-muted">Amount</dt><dd><Money paise={d.txn.amount_paise} sign /></dd>
              <dt className="text-muted">Narration</dt><dd className="font-mono break-all">{d.txn.descriptor}</dd>
              <dt className="text-muted">Posted</dt><dd>{dateTime(d.txn.posted_at)} IST · {d.txn.channel}</dd>
              <dt className="text-muted">Account</dt><dd>{d.txn.account_id} ({titleCase(d.txn.account_type)}, {d.txn.account_status.toLowerCase()})</dd>
              {d.current && <><dt className="text-muted">Now filed as</dt><dd><b>{titleCase(d.current.category_code)}</b> · {titleCase(d.current.kind)}</dd></>}
            </dl>
          </Section>
          <Section title="Decision per run">
            <table className="register"><thead><tr><th>Run</th><th>Category</th><th>Kind</th><th>Rule</th><th>Decision</th><th>Link</th></tr></thead>
              <tbody>{d.runs.map((r) => <tr key={r.run_id}><td className="font-mono text-xs">{r.run_id}</td><td>{titleCase(r.category_code)}</td><td>{titleCase(r.kind)}</td><td className="font-mono text-xs">{r.rule_id ? `${r.rule_id} v${r.rule_version}` : "—"}</td><td className="text-sm">{r.decision}</td><td className="font-mono text-xs">{r.link_txn_id ?? "—"}</td></tr>)}</tbody></table>
          </Section>
          {d.overrides.length > 0 && <Section title="Overrides"><ul className="text-sm">{d.overrides.map((o) => <li key={o.override_id} className="py-1.5 border-b border-rule">{o.override_id} · {titleCase(o.category_code)} · {o.actor} · {dateTime(o.created_at)} {o.reason && `— ${o.reason}`}</li>)}</ul></Section>}
          {d.exceptions.map((x) => (
            <Section key={x.exception_id} title={`${x.exception_id} · ${titleCase(x.exception_type)}`} right={<StatusStamp status={x.status} />}>
              <ol className="text-sm">{x.events.map((e) => <li key={e.seq} className="py-1 border-b border-rule">{e.from_status ?? "—"} → <b>{e.to_status}</b> · {e.actor} · {dateTime(e.at)}{e.note && ` — ${e.note}`}</li>)}</ol>
            </Section>
          ))}
          {(me?.role === "REVIEWER" || me?.role === "ADMIN") && d.truth !== undefined && (
            <Section title="Ground truth (reviewers only)">
              {d.truth ? <dl className="grid grid-cols-[150px_1fr] gap-y-1 text-sm">{Object.entries(d.truth).map(([k, v]) => <><dt key={k} className="text-muted">{titleCase(k)}</dt><dd key={`${k}v`}>{String(v ?? "—")}</dd></>)}</dl> : <p className="text-muted">No label for this transaction (a real household entry).</p>}
            </Section>
          )}
        </div>
      )}
    </>
  );
}
