import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { CategorySelect, Drawer, Empty, Field, PageHead, QueryState, Section, Stamp, useCategoryName } from "../../components/ui";
import { ApiError, get, post } from "../../lib/api";
import { titleCase } from "../../lib/format";
import type { Rule } from "../../lib/types";

const CHANNELS = ["UPI", "IMPS", "NEFT", "RTGS", "NACH", "CARD_POS", "CARD_ECOM", "ATM", "BBPS", "INTERNAL"];
type Form = { priority: string; category_code: string; merchant_id: string; pattern: string; channel: string; direction: string; account_type: string; confidence: string; note: string };
const blank: Form = { priority: "50", category_code: "", merchant_id: "", pattern: "", channel: "", direction: "ANY", account_type: "", confidence: "0.8", note: "" };

export default function Rules() {
  const [retired, setRetired] = useState(false);
  const q = useQuery({ queryKey: ["rules", retired], queryFn: () => get<Rule[]>("/analyst/rules", { include_retired: retired }) });
  const catName = useCategoryName();
  const qc = useQueryClient();
  const [edit, setEdit] = useState<{ rule?: Rule } | null>(null);
  const retire = useMutation({ mutationFn: (id: string) => post(`/analyst/rules/${id}/retire`), onSuccess: () => qc.invalidateQueries({ queryKey: ["rules"] }) });
  return (
    <>
      <PageHead title="Rules" sub="Lower priority numbers run first. Changes apply at the next pipeline run." right={<>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={retired} onChange={(e) => setRetired(e.target.checked)} /> Show retired</label>
        <button className="btn btn-solid" onClick={() => setEdit({})}><Plus size={16} aria-hidden /> New rule</button></>} />
      <Tester />
      <Section title="Active rules">
        <QueryState q={q} rows={8}>{(rows) => rows.length === 0 ? <Empty title="No rules" /> : (
          <div className="overflow-x-auto"><table className="register min-w-[860px]">
            <thead><tr><th>Rule</th><th className="num">Priority</th><th>Category</th><th>When</th><th className="num">Confidence</th><th><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.rule_id} className={r.retired_at ? "opacity-60" : ""}>
                <td><span className="font-mono text-xs">{r.rule_id}</span> <span className="text-muted text-xs">v{r.version}</span>{r.retired_at && <> <Stamp>Retired</Stamp></>}</td>
                <td className="num">{r.priority}</td>
                <td>{catName(r.category_code)}</td>
                <td className="text-sm">{[r.pattern && <code key="p" className="bg-blue-soft px-1">{r.pattern}</code>, r.merchant_id, r.channel && titleCase(r.channel), r.direction !== "ANY" && (r.direction === "DR" ? "debit" : "credit"), r.account_type && titleCase(r.account_type)].filter(Boolean).map((x, i) => <span key={i} className="mr-2">{x}</span>)}</td>
                <td className="num">{Math.round(r.confidence * 100)}%</td>
                <td className="whitespace-nowrap">{!r.retired_at && <><button className="btn btn-ghost !min-h-[32px]" onClick={() => setEdit({ rule: r })}>New version</button><button className="btn btn-ghost !min-h-[32px] text-red" disabled={retire.isPending} onClick={() => retire.mutate(r.rule_id)}>Retire</button></>}</td>
              </tr>))}</tbody>
          </table></div>
        )}</QueryState>
      </Section>
      {edit && <RuleDrawer rule={edit.rule} onClose={() => setEdit(null)} />}
    </>
  );
}

function RuleDrawer({ rule, onClose }: { rule?: Rule; onClose: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState<Form>(rule ? { priority: String(rule.priority), category_code: rule.category_code, merchant_id: rule.merchant_id ?? "", pattern: rule.pattern ?? "", channel: rule.channel ?? "", direction: rule.direction, account_type: rule.account_type ?? "", confidence: String(rule.confidence), note: "" } : blank);
  const up = (k: keyof Form) => (v: string) => setF((s) => ({ ...s, [k]: v }));
  const m = useMutation({
    mutationFn: () => post(rule ? `/analyst/rules/${rule.rule_id}/versions` : "/analyst/rules", {
      priority: Number(f.priority), category_code: f.category_code, merchant_id: f.merchant_id || null, pattern: f.pattern || null,
      channel: f.channel || null, direction: f.direction, account_type: f.account_type || null, confidence: Number(f.confidence), note: f.note || null,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["rules"] }); onClose(); },
  });
  const err = (n: string) => (m.error as ApiError | null)?.fields?.find((x) => x.field.endsWith(n))?.message;
  return (
    <Drawer title={rule ? `${rule.rule_id}: new version` : "New rule"} onClose={onClose}>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
        <Field label="Category">{(id) => <CategorySelect id={id} value={f.category_code} onChange={up("category_code")} />}</Field>
        <Field label="Narration pattern (regular expression)" hint="Matched against the lower-cased narration with numbers and bank codes removed. Max 200 characters." error={err("pattern")}>{(id) => <input id={id} className="field font-mono" value={f.pattern} onChange={(e) => up("pattern")(e.target.value)} placeholder="\bclinic\b" maxLength={200} />}</Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Merchant id" error={err("merchant_id")}>{(id) => <input id={id} className="field" value={f.merchant_id} onChange={(e) => up("merchant_id")(e.target.value)} placeholder="MER-0012" />}</Field>
          <Field label="Channel">{(id) => <select id={id} className="field" value={f.channel} onChange={(e) => up("channel")(e.target.value)}><option value="">Any</option>{CHANNELS.map((c) => <option key={c}>{c}</option>)}</select>}</Field>
          <Field label="Direction">{(id) => <select id={id} className="field" value={f.direction} onChange={(e) => up("direction")(e.target.value)}><option value="ANY">Any</option><option value="DR">Money out</option><option value="CR">Money in</option></select>}</Field>
          <Field label="Account type">{(id) => <select id={id} className="field" value={f.account_type} onChange={(e) => up("account_type")(e.target.value)}><option value="">Any</option><option value="SAVINGS">Savings</option><option value="CREDIT_CARD">Credit card</option></select>}</Field>
          <Field label="Priority" hint="1 runs first">{(id) => <input id={id} className="field" inputMode="numeric" maxLength={3} value={f.priority} onChange={(e) => up("priority")(e.target.value.replace(/\D/g, "").slice(0, 3))} />}</Field>
          <Field label="Confidence (0–1)" error={err("confidence")}>{(id) => <input id={id} className="field" inputMode="decimal" maxLength={4} value={f.confidence} onChange={(e) => up("confidence")(e.target.value.replace(/[^\d.]/g, "").slice(0, 4))} />}</Field>
        </div>
        <Field label="Why">{(id) => <input id={id} className="field" value={f.note} onChange={(e) => up("note")(e.target.value)} maxLength={300} />}</Field>
        {m.isError && !(m.error as ApiError).fields?.length && <p role="alert" className="text-red text-sm border border-red bg-red-soft p-3">{(m.error as ApiError).message}</p>}
        {(m.error as ApiError | null)?.fields?.map((x) => <p key={x.field} role="alert" className="text-red text-sm">{x.field}: {x.message}</p>)}
        <button className="btn btn-solid w-full" disabled={!f.category_code || m.isPending}>{m.isPending ? "Saving…" : rule ? "Save as new version" : "Create rule"}</button>
      </form>
    </Drawer>
  );
}

function Tester() {
  const [f, setF] = useState({ descriptor: "UPI/DR/612345678901/CITY CLINIC/SBIN/q@ybl/x", channel: "UPI", amount: "500", account_type: "SAVINGS", vpa: "" });
  const catName = useCategoryName();
  const m = useMutation({ mutationFn: () => post<{ normalized: string; merchant_id: string | null; rule_id: string | null; rule_version: number | null; category_code: string; confidence: number }>("/analyst/rules/test", { descriptor: f.descriptor, channel: f.channel, amount_paise: -Math.round(Number(f.amount || 0) * 100), account_type: f.account_type, counterparty_vpa: f.vpa || null }) });
  return (
    <Section title="Try a narration">
      <form className="grid md:grid-cols-[3fr_1fr_1fr_auto] gap-3 items-end" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
        <Field label="Bank narration">{(id) => <input id={id} className="field font-mono text-sm" value={f.descriptor} onChange={(e) => setF({ ...f, descriptor: e.target.value })} maxLength={160} />}</Field>
        <Field label="Channel">{(id) => <select id={id} className="field" value={f.channel} onChange={(e) => setF({ ...f, channel: e.target.value })}>{CHANNELS.map((c) => <option key={c}>{c}</option>)}</select>}</Field>
        <Field label="Account">{(id) => <select id={id} className="field" value={f.account_type} onChange={(e) => setF({ ...f, account_type: e.target.value })}><option value="SAVINGS">Savings</option><option value="CREDIT_CARD">Credit card</option></select>}</Field>
        <button className="btn btn-solid" disabled={!f.descriptor || m.isPending}>Test</button>
      </form>
      {m.data && (
        <dl className="mt-4 grid grid-cols-[150px_1fr] gap-y-1 text-sm border-t border-rule pt-3" aria-live="polite">
          <dt className="text-muted">Cleaned narration</dt><dd className="font-mono">{m.data.normalized}</dd>
          <dt className="text-muted">Merchant</dt><dd>{m.data.merchant_id ?? "none recognised"}</dd>
          <dt className="text-muted">Category</dt><dd><b>{catName(m.data.category_code)}</b> {m.data.rule_id ? <>by {m.data.rule_id} v{m.data.rule_version} · {Math.round(m.data.confidence * 100)}%</> : <Stamp tone="red">No rule matched</Stamp>}</dd>
        </dl>
      )}
      {m.isError && <p role="alert" className="text-red mt-3 text-sm">{(m.error as ApiError).message}</p>}
    </Section>
  );
}
