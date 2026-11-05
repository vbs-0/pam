import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Trash2 } from "lucide-react";
import { useState } from "react";
import { CategorySelect, Empty, Field, LimitBar, Money, MonthBar, PageHead, QueryState, Section, Stamp, StatusStamp, useCategoryName, useMonth } from "../../components/ui";
import { ApiError, del, get, put } from "../../lib/api";
import { monthName, toPaise } from "../../lib/format";
import type { BudgetLine, Budgets as B, Profile } from "../../lib/types";

export default function Budgets() {
  const [month, setMonth] = useMonth();
  const catName = useCategoryName();
  const qc = useQueryClient();
  const profile = useQuery({ queryKey: ["profile"], queryFn: () => get<Profile>("/me/profile") });
  const q = useQuery({ queryKey: ["budgets", month], queryFn: () => get<B>("/me/budgets", { month }) });
  const canWrite = profile.data && !profile.data.sample;
  const [editing, setEditing] = useState<{ code: string; amount: string } | null>(null);
  const [newCat, setNewCat] = useState(""), [newAmt, setNewAmt] = useState("");
  const save = useMutation({
    mutationFn: (v: { code: string; amount: string }) => put("/me/budgets", { month, category_code: v.code, amount_paise: toPaise(v.amount) }),
    onSuccess: () => { qc.invalidateQueries(); setEditing(null); setNewCat(""); setNewAmt(""); },
  });
  const carry = useMutation({ mutationFn: (v: { code: string; on: boolean }) => put("/me/budgets/carry", { category_code: v.code, enabled: v.on }), onSuccess: () => qc.invalidateQueries() });
  const remove = useMutation({ mutationFn: (code: string) => del(`/me/budgets/${month}/${code}`), onSuccess: () => qc.invalidateQueries() });

  return (
    <>
      <PageHead title={`Budgets · ${monthName(month)}`} sub="Spend written against each limit. The red tick is the limit." right={<MonthBar month={month} onChange={setMonth} />} />
      <QueryState q={q}>
        {(b) => (
          <>
            <div className="flex flex-wrap gap-x-10 gap-y-1 mb-6 border-b border-rule pb-4">
              <p>Budgeted <b className="text-lg"><Money paise={b.total_budget_paise} /></b></p>
              <p>Spent <b className="text-lg"><Money paise={b.total_actual_paise} /></b></p>
            </div>

            {b.lines.length === 0 ? <Empty title="No budgets or spending for this month" hint={canWrite ? "Set a limit below to start tracking a category." : undefined} /> : (
              <div className="overflow-x-auto"><table className="register min-w-[640px]">
                <thead><tr><th>Category</th><th className="num">Spent</th><th className="num">Limit</th><th className="w-[26%]"><span className="sr-only">Progress</span></th><th>Status</th>{canWrite && <th><span className="sr-only">Actions</span></th>}</tr></thead>
                <tbody>
                  {b.lines.map((l) => <Row key={l.category_code} l={l} name={l.category_name ?? catName(l.category_code)} canWrite={!!canWrite}
                    editing={editing?.code === l.category_code ? editing : null} setEditing={setEditing}
                    save={() => editing && save.mutate(editing)} saving={save.isPending} remove={() => remove.mutate(l.category_code)}
                    carryOn={!!b.carry_enabled?.includes(l.category_code)} toggleCarry={(on) => carry.mutate({ code: l.category_code, on })} />)}
                </tbody>
              </table></div>
            )}
            {save.isError && <p role="alert" className="text-red mt-3">{(save.error as ApiError).message}</p>}
            {remove.isError && <p role="alert" className="text-red mt-3">{(remove.error as ApiError).message}</p>}
            {canWrite && b.lines.some((l) => l.budget_paise !== null) && <p className="text-xs text-muted mt-3">Tick “Roll over” on a category to add whatever you did not spend last month to this month’s limit.</p>}

            {canWrite && (
              <Section title="Set a limit">
                <form className="grid sm:grid-cols-[2fr_1fr_auto] gap-3 items-end" onSubmit={(e) => { e.preventDefault(); if (newCat && toPaise(newAmt) !== null) save.mutate({ code: newCat, amount: newAmt }); }}>
                  <Field label="Category">{(id) => <CategorySelect id={id} value={newCat} onChange={setNewCat} kinds={["EXPENSE"]} />}</Field>
                  <Field label="Monthly limit (₹)">{(id) => <input id={id} className="field" inputMode="decimal" value={newAmt} onChange={(e) => setNewAmt(e.target.value)} placeholder="5,000" />}</Field>
                  <button className="btn btn-solid" disabled={!newCat || toPaise(newAmt) === null || save.isPending}>Save limit</button>
                </form>
                <p className="text-xs text-muted mt-2">A limit of ₹0 means you plan to spend nothing there. Setting one again replaces it and keeps the old version in history.</p>
              </Section>
            )}

            {b.remapped.length > 0 && (
              <Section title="Renamed categories">
                <ul className="text-sm">{b.remapped.map((r) => <li key={r.budget_id} className="py-1.5 border-b border-rule">
                  Budget for <b>{catName(r.submitted_code)}</b> now counts under <b>{catName(r.resolved_code)}</b> <Stamp>{r.resolution.toLowerCase().replace(/_/g, " ")}</Stamp></li>)}</ul>
              </Section>
            )}
            {b.unmapped.length > 0 && (
              <Section title="Budgets PAM could not place">
                <ul className="text-sm">{b.unmapped.map((u) => <li key={u.budget_id} className="py-1.5 border-b border-rule text-red">
                  “{u.submitted_code}” is not a category PAM knows (<Money paise={u.amount_paise} />). An analyst has been asked to map it.</li>)}</ul>
              </Section>
            )}
          </>
        )}
      </QueryState>
    </>
  );
}

function Row({ l, name, canWrite, editing, setEditing, save, saving, remove, carryOn, toggleCarry }: {
  carryOn: boolean; toggleCarry: (on: boolean) => void;
  l: BudgetLine; name: string; canWrite: boolean; editing: { code: string; amount: string } | null;
  setEditing: (v: { code: string; amount: string } | null) => void; save: () => void; saving: boolean; remove: () => void;
}) {
  return (
    <tr>
      <td>{name}</td>
      <td className="num"><Money paise={l.actual_paise} tone={l.status === "OVER" ? "red" : undefined} /></td>
      <td className="num">
        {editing ? (
          <form onSubmit={(e) => { e.preventDefault(); save(); }} className="flex gap-1 justify-end">
            <input aria-label={`Limit for ${name}`} className="field !w-28 !min-h-[32px]" autoFocus inputMode="decimal" value={editing.amount} onChange={(e) => setEditing({ code: l.category_code, amount: e.target.value })} />
            <button className="btn btn-solid !min-h-[32px]" disabled={saving || toPaise(editing.amount) === null}>Save</button>
            <button type="button" className="btn btn-ghost !min-h-[32px]" onClick={() => setEditing(null)}>Cancel</button>
          </form>
        ) : l.budget_paise === null ? <span className="text-muted">—</span> : <Money paise={l.budget_paise} tone="muted" />}
        {!!l.carried_paise && !editing && <div className="text-xs text-blue">incl. ₹{(l.carried_paise / 100).toLocaleString("en-IN")} rolled over</div>}
      </td>
      <td className="align-middle"><LimitBar actual={l.actual_paise} budget={l.budget_paise} status={l.status} /></td>
      <td><StatusStamp status={l.status} />{l.ratio !== null && <span className="ml-2 text-xs text-muted num">{Math.round(l.ratio * 100)}%</span>}</td>
      {canWrite && (
        <td className="whitespace-nowrap">
          {l.budget_paise !== null && !editing && <label className="inline-flex items-center gap-1 text-xs mr-2"><input type="checkbox" checked={carryOn} onChange={(e) => toggleCarry(e.target.checked)} /> Roll over</label>}
          {!editing && <button className="btn btn-ghost !min-h-[32px]" aria-label={`Edit limit for ${name}`} onClick={() => setEditing({ code: l.category_code, amount: l.budget_paise === null ? "" : String(l.budget_paise / 100) })}><Pencil size={15} /></button>}
          {l.budget_paise !== null && !editing && <button className="btn btn-ghost !min-h-[32px] text-red" aria-label={`Remove limit for ${name}`} onClick={remove}><Trash2 size={15} /></button>}
        </td>
      )}
    </tr>
  );
}
