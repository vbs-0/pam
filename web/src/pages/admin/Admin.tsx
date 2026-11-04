import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Play } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router";
import { Empty, ErrorBox, Field, PageHead, QueryState, Section, Skeleton, Stamp, StatusStamp } from "../../components/ui";
import { ApiError, BASE, get, household, patch, post, tokenStore } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { dateTime, titleCase } from "../../lib/format";
import type { Job, Page } from "../../lib/types";

interface Overview {
  dataset: { scale: string; loaded_at: string; seed: number } | null; latest_run_id: string | null;
  evaluation: { run_id: string; all_pass: boolean } | null; counts: Record<string, number>; running_jobs: { job_id: string; job_type: string; status: string }[];
}

export function AdminOverview() {
  const q = useQuery({ queryKey: ["overview"], queryFn: () => get<Overview>("/admin/overview"), refetchInterval: 10_000 });
  const val = useQuery({ queryKey: ["validation", "OUTPUTS"], queryFn: () => get<any>("/admin/validation", { scope: "OUTPUTS" }), retry: false });
  const repro = useQuery({ queryKey: ["repro"], queryFn: () => get<any>("/admin/reproducibility", { scale: "starter" }), retry: false });
  return (
    <>
      <PageHead title="Overview" sub="State of the dataset, the pipeline and the evidence." />
      <QueryState q={q} rows={4}>{(o) => (
        <>
          <dl className="grid grid-cols-2 md:grid-cols-5 border-y border-rule-strong mb-8">
            {[["Households", o.counts.households], ["Real households", o.counts.real_households], ["Transactions", o.counts.transactions], ["Open exceptions", o.counts.open_exceptions], ["Logins", o.counts.logins]].map(([k, v]) => (
              <div key={String(k)} className="p-4 border-r border-rule last:border-r-0"><dt className="text-xs font-bold uppercase tracking-wider text-muted">{k}</dt><dd className="text-2xl font-semibold mt-1 num !text-left">{Number(v).toLocaleString("en-IN")}</dd></div>
            ))}
          </dl>
          <div className="grid md:grid-cols-2 gap-x-10">
            <Section title="Dataset"><p>{o.dataset ? <>Scale <b>{o.dataset.scale}</b>, seed {o.dataset.seed}, loaded {dateTime(o.dataset.loaded_at)}.</> : "Nothing loaded."}</p></Section>
            <Section title="Latest run"><p>{o.latest_run_id ?? "No run yet"} {o.evaluation && <> · evaluation <StatusStamp status={o.evaluation.all_pass ? "PASS" : "FAIL"} /></>}</p></Section>
            <Section title="Output validation">
              {val.isPending ? <Skeleton rows={2} /> : val.isError ? <p className="text-muted">None yet. Start a Validate job.</p> : <><p><StatusStamp status={val.data.passed ? "PASS" : "FAIL"} /> {dateTime(val.data.created_at)}</p>
                <ul className="mt-2 text-sm">{val.data.results.checks.map((c: any) => <li key={c.name} className="flex justify-between py-1 border-b border-rule"><span>{titleCase(c.name)}</span><StatusStamp status={c.status} /></li>)}</ul></>}
            </Section>
            <Section title="Reproducibility">
              {repro.isPending ? <Skeleton rows={2} /> : repro.isError ? <p className="text-muted">No check yet. Start a Repro job.</p> : <p><StatusStamp status={repro.data.match ? "PASS" : "FAIL"} /> two fresh interpreters produced {repro.data.match ? "identical" : "different"} checksums ({repro.data.source}).</p>}
            </Section>
          </div>
        </>
      )}</QueryState>
    </>
  );
}

const JOBS: [string, string, Record<string, unknown>, string][] = [
  ["GENERATE_LOAD", "Generate + load starter", { scale: "starter" }, "Rebuilds the sample households and runs the pipeline. Real households are kept."],
  ["PIPELINE", "Run pipeline", {}, "Re-decide every transaction with the current rules."],
  ["EVALUATE", "Evaluate", {}, "Score the latest run against ground truth."],
  ["VALIDATE", "Validate outputs", { scope: "OUTPUTS" }, "Check the latest run's outputs for consistency."],
  ["VALIDATE", "Validate dataset", { scope: "DATASET" }, "Check keys, joins, dates and arithmetic of the loaded files."],
  ["EXPORT", "Export starter", { scale: "starter" }, "Write JSON and SQL next to the CSVs."],
  ["REPRO", "Reproducibility check", { scale: "starter" }, "Generate twice in fresh interpreters and compare checksums."],
];

export function Jobs() {
  const qc = useQueryClient();
  const q = useInfiniteQuery({
    queryKey: ["jobs"], queryFn: ({ pageParam }) => get<Page<Job>>("/admin/jobs", { cursor: pageParam, limit: 20 }),
    initialPageParam: undefined as string | undefined, getNextPageParam: (l) => l.next_cursor ?? undefined,
    refetchInterval: (query) => (query.state.data?.pages[0]?.items.some((j) => j.status === "QUEUED" || j.status === "RUNNING") ? 2000 : false),
  });
  const start = useMutation({ mutationFn: (j: (typeof JOBS)[number]) => post("/admin/jobs", { job_type: j[0], params: j[2] }), onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }) });
  const rows = q.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <>
      <PageHead title="Jobs" sub="Long tasks run in the background, one dataset job at a time." />
      <Section title="Start a job">
        <ul className="grid md:grid-cols-2 gap-x-10">
          {JOBS.map((j) => (
            <li key={j[1]} className="flex items-center justify-between gap-3 py-2.5 border-b border-rule">
              <div><div className="font-semibold">{j[1]}</div><div className="text-sm text-muted">{j[3]}</div></div>
              <button className="btn" disabled={start.isPending} onClick={() => start.mutate(j)}><Play size={14} aria-hidden /> Run</button>
            </li>
          ))}
        </ul>
        {start.isError && <p role="alert" className="text-red mt-3">{(start.error as ApiError).message}</p>}
      </Section>
      <Section title="History">
        {q.isPending ? <Skeleton rows={5} /> : q.isError ? <ErrorBox error={q.error} retry={() => q.refetch()} /> : rows.length === 0 ? <Empty title="No jobs yet" /> : (
          <div className="overflow-x-auto"><table className="register min-w-[720px]">
            <thead><tr><th>Job</th><th>Type</th><th>Status</th><th>By</th><th>Started</th><th>Result</th></tr></thead>
            <tbody>{rows.map((j) => (
              <tr key={j.job_id}><td className="font-mono text-xs">{j.job_id}</td><td>{titleCase(j.job_type)}</td><td><StatusStamp status={j.status} /></td><td className="text-sm">{j.created_by}</td><td className="text-sm">{dateTime(j.created_at)}</td>
                <td className="text-xs max-w-[320px]">{j.error ? <span className="text-red">{j.error}</span> : j.result ? <span className="text-muted break-all">{JSON.stringify(j.result).slice(0, 140)}</span> : ""}</td></tr>
            ))}</tbody>
          </table>{q.hasNextPage && <div className="py-3 text-center"><button className="btn" onClick={() => q.fetchNextPage()}>Older jobs</button></div>}</div>
        )}
      </Section>
    </>
  );
}

interface User { app_user_id: string; email: string; role: string; profile_user_id: string | null; disabled: boolean; google: boolean; password: boolean }
export function Users() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const list = useInfiniteQuery({
    queryKey: ["users", search], queryFn: ({ pageParam }) => get<Page<User>>("/admin/users", { q: search, cursor: pageParam, limit: 50 }),
    initialPageParam: undefined as string | undefined, getNextPageParam: (l) => l.next_cursor ?? undefined,
  });
  const upd = useMutation({ mutationFn: (v: { id: string; body: Record<string, unknown> }) => patch(`/admin/users/${v.id}`, v.body), onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }) });
  const rows = list.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <>
      <PageHead title="Logins" sub="Roles are stored here, never in tokens. Changes apply on the person's next request." />
      <div className="max-w-sm mb-4"><Field label="Search email">{(id) => <input id={id} className="field" value={search} onChange={(e) => setSearch(e.target.value)} />}</Field></div>
      {upd.isError && <p role="alert" className="text-red mb-3 border border-red bg-red-soft p-3">{(upd.error as ApiError).message}</p>}
      {list.isPending ? <Skeleton rows={6} /> : list.isError ? <ErrorBox error={list.error} retry={() => list.refetch()} /> : rows.length === 0 ? <Empty title="No logins match" /> : (
        <div className="overflow-x-auto"><table className="register min-w-[760px]">
          <thead><tr><th>Email</th><th>Role</th><th>Household</th><th>Sign-in</th><th>Status</th></tr></thead>
          <tbody>{rows.map((u) => (
            <tr key={u.app_user_id}>
              <td>{u.email}{u.app_user_id === me?.app_user_id && <> <Stamp tone="blue">You</Stamp></>}<div className="font-mono text-xs text-muted">{u.app_user_id}</div></td>
              <td><select aria-label={`Role for ${u.email}`} className="field !w-36" value={u.role} disabled={upd.isPending || u.app_user_id === me?.app_user_id} onChange={(e) => upd.mutate({ id: u.app_user_id, body: { role: e.target.value } })}>
                {["CUSTOMER", "ANALYST", "REVIEWER", "ADMIN"].map((r) => <option key={r}>{r}</option>)}</select></td>
              <td className="font-mono text-xs">{u.profile_user_id ?? "—"}</td>
              <td className="text-sm">{[u.password && "Password", u.google && "Google"].filter(Boolean).join(" + ") || "—"}</td>
              <td><button className={`btn !min-h-[32px] ${u.disabled ? "" : "btn-danger"}`} disabled={upd.isPending || u.app_user_id === me?.app_user_id} onClick={() => upd.mutate({ id: u.app_user_id, body: { disabled: !u.disabled } })}>{u.disabled ? "Enable" : "Disable"}</button> {u.disabled && <Stamp tone="red">Disabled</Stamp>}</td>
            </tr>))}</tbody>
        </table>{list.hasNextPage && <div className="py-3 text-center"><button className="btn" onClick={() => list.fetchNextPage()}>Load more</button></div>}</div>
      )}
    </>
  );
}

export function Exports() {
  const [scale, setScale] = useState("starter");
  const q = useQuery({ queryKey: ["exports", scale], queryFn: () => get<{ downloads: string[]; files: Record<string, { rows?: number; sha256: string }> }>(`/admin/exports/${scale}`), retry: false });
  const [err, setErr] = useState<string | null>(null);
  async function download(path: string) {
    setErr(null);
    const res = await fetch(`${BASE}/admin/exports/${scale}/files/${path}`, { headers: { Authorization: `Bearer ${tokenStore.get()}` } });
    if (!res.ok) { setErr("Could not download that file."); return; }
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a"); a.href = url; a.download = path.split("/").pop() ?? "file"; a.click(); URL.revokeObjectURL(url);
  }
  return (
    <>
      <PageHead title="Exports" sub="Dataset files exactly as listed in the manifest, plus the JSON and SQL exports." />
      <div className="max-w-xs mb-4"><Field label="Scale">{(id) => <select id={id} className="field" value={scale} onChange={(e) => setScale(e.target.value)}><option value="starter">Starter</option><option value="full">Full</option></select>}</Field></div>
      {err && <p role="alert" className="text-red mb-3">{err}</p>}
      {q.isPending ? <Skeleton rows={6} /> : q.isError ? <Empty title={(q.error as ApiError).status === 404 ? `No ${scale} dataset on this server` : "Could not load"} hint={scale === "full" ? "The full-scale dataset is generated offline with the command line and published in the repository." : "Run Generate + load from Jobs."} /> : (
        <table className="register"><thead><tr><th>File</th><th className="num">Rows</th><th>SHA-256</th><th /></tr></thead>
          <tbody>{q.data.downloads.map((p) => (
            <tr key={p}><td className="font-mono text-xs">{p}</td><td className="num">{q.data.files[p]?.rows?.toLocaleString("en-IN") ?? ""}</td><td className="font-mono text-xs text-muted">{q.data.files[p]?.sha256?.slice(0, 12) ?? ""}</td>
              <td><button className="btn btn-ghost !min-h-[32px]" onClick={() => download(p)} aria-label={`Download ${p}`}><Download size={15} /></button></td></tr>
          ))}</tbody></table>
      )}
    </>
  );
}

export function Households() {
  const nav = useNavigate();
  const [id, setId] = useState(household.get() ?? "USR-000001");
  const valid = /^USR-\d{6}$/.test(id);
  return (
    <>
      <PageHead title="Households" sub="Open any household's folio as an admin (support view)." />
      <form className="flex gap-2 max-w-md" onSubmit={(e) => { e.preventDefault(); if (valid) { household.set(id); nav("/"); } }}>
        <input aria-label="Household id" className="field font-mono" value={id} onChange={(e) => setId(e.target.value.toUpperCase())} placeholder="USR-000001" />
        <button className="btn btn-solid" disabled={!valid}>Open folio</button>
      </form>
      <p className="text-sm text-muted mt-3">Sample households are USR-000001 and up; real households start at USR-500001.</p>
    </>
  );
}
