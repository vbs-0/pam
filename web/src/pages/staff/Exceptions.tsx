import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { CategorySelect, Empty, ErrorBox, Field, Money, PageHead, Skeleton, Stamp, StatusStamp, useCategoryName } from "../../components/ui";
import { ApiError, get, post } from "../../lib/api";
import { dateTime, titleCase } from "../../lib/format";
import type { ExceptionRow, Page } from "../../lib/types";

const TYPES = ["UNCATEGORIZED", "UNMATCHED_TRANSFER", "ORPHAN_REFUND", "BUDGET_CATEGORY_UNMAPPED", "RECURRING_MISSED"];
const STATUSES = ["OPEN", "IN_REVIEW", "RESOLVED", "DISMISSED"];
const NEXT: Record<string, string[]> = { OPEN: ["IN_REVIEW", "RESOLVED", "DISMISSED"], IN_REVIEW: ["RESOLVED", "DISMISSED", "OPEN"], RESOLVED: ["OPEN"], DISMISSED: ["OPEN"] };
const VERB: Record<string, string> = { IN_REVIEW: "Start review", RESOLVED: "Resolve", DISMISSED: "Dismiss", OPEN: "Reopen" };

export default function Exceptions() {
  const [sp, setSp] = useSearchParams();
  const type = sp.get("type") ?? "", status = sp.get("status") ?? "OPEN";
  const set = (k: string, v: string) => setSp((p) => { if (v) p.set(k, v); else p.delete(k); return p; }, { replace: true });
  const [open, setOpen] = useState<string | null>(null);
  const counts = useQuery({ queryKey: ["exc-counts"], queryFn: () => get<{ exception_type: string; status: string; n: number }[]>("/analyst/exceptions/counts") });
  const list = useInfiniteQuery({
    queryKey: ["exceptions", type, status],
    queryFn: ({ pageParam }) => get<Page<ExceptionRow>>("/analyst/exceptions", { type, status, cursor: pageParam, limit: 50 }),
    initialPageParam: undefined as string | undefined, getNextPageParam: (l) => l.next_cursor ?? undefined,
  });
  const rows = list.data?.pages.flatMap((p) => p.items) ?? [];
  const n = (t: string) => counts.data?.filter((c) => c.exception_type === t && c.status === status).reduce((a, c) => a + c.n, 0) ?? 0;

  return (
    <>
      <PageHead title="Exceptions" sub="Things the engine would not decide alone. Work them top to bottom." />
      <div className="flex flex-wrap gap-2 mb-3" role="tablist" aria-label="Exception type">
        <button role="tab" aria-selected={!type} className={`btn ${!type ? "btn-solid" : ""}`} onClick={() => set("type", "")}>All</button>
        {TYPES.map((t) => <button key={t} role="tab" aria-selected={type === t} className={`btn ${type === t ? "btn-solid" : ""}`} onClick={() => set("type", t)}>{titleCase(t)} <span className="opacity-70">{n(t)}</span></button>)}
      </div>
      <div className="max-w-xs mb-4"><Field label="Status">{(id) => <select id={id} className="field" value={status} onChange={(e) => set("status", e.target.value)}><option value="">Any</option>{STATUSES.map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}</select>}</Field></div>

      {list.isPending ? <Skeleton rows={8} h={24} /> : list.isError ? <ErrorBox error={list.error} retry={() => list.refetch()} /> : rows.length === 0 ? <Empty title="Queue is clear" hint="No exceptions with these filters." /> : (
        <div className="overflow-x-auto">
          <table className="register min-w-[820px]">
            <thead><tr><th>Case</th><th>Type</th><th>What</th><th>Household</th><th>Status</th><th>Updated</th></tr></thead>
            <tbody>
              {rows.map((x) => (
                <>
                  <tr key={x.exception_id} className="clickable" tabIndex={0} onClick={() => setOpen(open === x.exception_id ? null : x.exception_id)} onKeyDown={(e) => e.key === "Enter" && setOpen(open === x.exception_id ? null : x.exception_id)} aria-expanded={open === x.exception_id}>
                    <td className="font-mono text-xs whitespace-nowrap">{x.exception_id}</td>
                    <td>{titleCase(x.exception_type)}</td>
                    <td><What x={x} />{!x.current && <> <Stamp title="No longer raised by the latest run">Cleared by run</Stamp></>}</td>
                    <td className="font-mono text-xs">{x.user_id}</td>
                    <td><StatusStamp status={x.status} /></td>
                    <td className="text-sm text-muted whitespace-nowrap">{dateTime(x.updated_at)}</td>
                  </tr>
                  {open === x.exception_id && <tr key={`${x.exception_id}-a`}><td colSpan={6} className="bg-blue-soft"><Actions x={x} done={() => setOpen(null)} /></td></tr>}
                </>
              ))}
            </tbody>
          </table>
          <div className="py-4 text-center">{list.hasNextPage ? <button className="btn" disabled={list.isFetchingNextPage} onClick={() => list.fetchNextPage()}>Load more</button> : <span className="text-sm text-muted">End of queue · {rows.length} cases</span>}</div>
        </div>
      )}
    </>
  );
}

function What({ x }: { x: ExceptionRow }) {
  if (x.entity_type === "TXN") return <><Link to={`/trace?txn=${x.entity_id}`} onClick={(e) => e.stopPropagation()}>{x.descriptor ?? x.entity_id}</Link>{x.amount_paise != null && <> · <Money paise={x.amount_paise} sign /></>}</>;
  if (x.entity_type === "BUDGET") return <>Budget <span className="font-mono text-xs">{x.entity_id}</span> · “{String(x.detail?.submitted ?? x.budget_code ?? "")}”</>;
  return <span className="font-mono text-xs">{x.entity_id.split("|").slice(1, 3).join(" · ")}</span>;
}

function Actions({ x, done }: { x: ExceptionRow; done: () => void }) {
  const qc = useQueryClient();
  const catName = useCategoryName();
  const [note, setNote] = useState(""), [cat, setCat] = useState("");
  const m = useMutation({
    mutationFn: (to: string) => post(`/analyst/exceptions/${x.exception_id}/transition`, { to_status: to, note: note.trim() || null, category_code: to === "RESOLVED" && cat ? cat : null }),
    onSuccess: () => { qc.invalidateQueries(); done(); },
    onError: () => qc.invalidateQueries(),     // someone else moved it first (409): show the current state behind the message
  });
  return (
    <div className="py-2 grid md:grid-cols-[1fr_1fr] gap-4">
      <div className="space-y-3">
        <pre className="text-xs bg-sheet border border-rule p-3 overflow-x-auto max-h-40">{JSON.stringify(x.detail, null, 2)}</pre>
        {x.entity_type === "TXN" && x.status !== "RESOLVED" && <Field label="Category to apply when resolving" hint={cat ? `Will be set to ${catName(cat)}` : "Optional"}>{(id) => <CategorySelect id={id} value={cat} onChange={setCat} />}</Field>}
        <Field label="Note">{(id) => <input id={id} className="field" value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} />}</Field>
      </div>
      <div className="flex flex-wrap gap-2 content-start">
        {NEXT[x.status].map((to) => <button key={to} className={`btn ${to === "RESOLVED" ? "btn-solid" : to === "DISMISSED" ? "btn-danger" : ""}`} disabled={m.isPending} onClick={() => m.mutate(to)}>{VERB[to]}</button>)}
        {m.isError && <p role="alert" className="text-red text-sm w-full">{(m.error as ApiError).message}</p>}
      </div>
    </div>
  );
}
