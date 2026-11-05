import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { CategorySelect, Drawer, Field } from "../../components/ui";
import { ApiError, post, put } from "../../lib/api";
import { rupees, todayIso, toPaise } from "../../lib/format";
import type { Account, ImportPreview, ImportResult, Txn } from "../../lib/types";

const err = (m: { isError: boolean; error: unknown }) => m.isError && <p role="alert" className="text-red text-sm">{(m.error as ApiError).message}</p>;
const useRefresh = () => { const qc = useQueryClient(); return () => qc.invalidateQueries(); };

/** Private note and #tags on one entry. */
export function NoteEditor({ t }: { t: Txn }) {
  const refresh = useRefresh();
  const [note, setNote] = useState(t.note ?? "");
  const [tags, setTags] = useState((t.tags ?? []).join(", "));
  const m = useMutation({
    mutationFn: () => put(`/me/transactions/${t.txn_id}/note`, { note: note.trim(), tags: tags.split(/[,\s]+/).map((x) => x.replace(/^#/, "").trim()).filter(Boolean).slice(0, 8) }),
    onSuccess: refresh,
  });
  return (
    <section aria-labelledby="note-h">
      <h3 id="note-h" className="font-semibold mb-2">Note and tags</h3>
      <div className="space-y-2">
        <textarea className="field" rows={2} maxLength={300} placeholder="Private note, e.g. shared with Riya" aria-label="Note" value={note} onChange={(e) => setNote(e.target.value)} />
        <input className="field" placeholder="Tags: trip, tax, reimbursable" aria-label="Tags" value={tags} onChange={(e) => setTags(e.target.value)} />
        <button className="btn" disabled={m.isPending} onClick={() => m.mutate()}>{m.isPending ? "Saving…" : "Save note"}</button>
        {m.isSuccess && <span role="status" className="text-green text-sm ml-3">Saved</span>}
        {err(m)}
      </div>
    </section>
  );
}

/** Split one payment across several categories. The parts must add up to the original. */
export function SplitForm({ t, onDone }: { t: Txn; onDone: () => void }) {
  const refresh = useRefresh();
  const total = Math.abs(t.amount_paise);
  const [parts, setParts] = useState([{ amount: "", category: "" }, { amount: "", category: "" }]);
  const sum = parts.reduce((s, p) => s + (toPaise(p.amount) ?? 0), 0);
  const left = total - sum;
  const m = useMutation({
    mutationFn: () => post(`/me/transactions/${t.txn_id}/split`, { parts: parts.map((p) => ({ amount_paise: toPaise(p.amount), category_code: p.category || null })) }),
    onSuccess: () => { refresh(); onDone(); },
  });
  const set = (i: number, k: "amount" | "category", v: string) => setParts((ps) => ps.map((p, j) => (j === i ? { ...p, [k]: v } : p)));
  return (
    <form className="w-full space-y-3 border border-rule-strong p-4" onSubmit={(e) => { e.preventDefault(); if (left === 0 && parts.every((p) => toPaise(p.amount))) m.mutate(); }}>
      <p className="text-sm">Split ₹{rupees(total)} across categories. Each part becomes its own entry.</p>
      {parts.map((p, i) => (
        <div key={i} className="grid grid-cols-[110px_1fr_auto] gap-2 items-start">
          <input className="field" inputMode="decimal" aria-label={`Part ${i + 1} amount`} placeholder="₹" value={p.amount} onChange={(e) => set(i, "amount", e.target.value)} />
          <CategorySelect value={p.category} onChange={(v) => set(i, "category", v)} includeBlank="Let PAM decide" />
          {parts.length > 2 && <button type="button" className="btn btn-ghost" aria-label={`Remove part ${i + 1}`} onClick={() => setParts((ps) => ps.filter((_, j) => j !== i))}>×</button>}
        </div>
      ))}
      <div className="flex items-center gap-3 flex-wrap">
        {parts.length < 10 && <button type="button" className="btn btn-ghost" onClick={() => setParts((ps) => [...ps, { amount: "", category: "" }])}>+ Add part</button>}
        <p className={`text-sm ${left === 0 ? "text-green" : "text-amber"}`} role="status">{left === 0 ? "Adds up." : left > 0 ? `₹${rupees(left)} still to place` : `₹${rupees(left)} too much`}</p>
      </div>
      {err(m)}
      <button className="btn btn-solid" disabled={left !== 0 || m.isPending || !parts.every((p) => toPaise(p.amount))}>{m.isPending ? "Splitting…" : "Split entry"}</button>
    </form>
  );
}

export function DuplicateButton({ t, onDone }: { t: Txn; onDone: () => void }) {
  const refresh = useRefresh();
  const [date, setDate] = useState(todayIso());
  const [open, setOpen] = useState(false);
  const m = useMutation({ mutationFn: () => post(`/me/transactions/${t.txn_id}/duplicate`, { date }), onSuccess: () => { refresh(); onDone(); } });
  return open ? (
    <span className="inline-flex gap-2 items-center flex-wrap">
      <input type="date" className="field !w-auto" max={todayIso()} aria-label="Date for the copy" value={date} onChange={(e) => setDate(e.target.value)} />
      <button className="btn btn-solid" disabled={m.isPending} onClick={() => m.mutate()}>{m.isPending ? "Copying…" : "Make copy"}</button>
      <button className="btn btn-ghost" onClick={() => setOpen(false)}>Cancel</button>
      {err(m)}
    </span>
  ) : <button className="btn" onClick={() => setOpen(true)}>Duplicate</button>;
}

/** Move money between two of your own accounts. Written as a pair that is never counted as spending. */
export function TransferDrawer({ accounts, onClose }: { accounts: Account[]; onClose: () => void }) {
  const refresh = useRefresh();
  const open = accounts.filter((a) => a.status === "ACTIVE");
  const [from, setFrom] = useState(open[0]?.account_id ?? ""), [to, setTo] = useState(open[1]?.account_id ?? "");
  const [amount, setAmount] = useState(""), [date, setDate] = useState(todayIso());
  const paise = toPaise(amount);
  const m = useMutation({ mutationFn: () => post("/me/transfers", { from_account_id: from, to_account_id: to, amount_paise: paise, date }), onSuccess: refresh });
  const sel = (v: string, set: (s: string) => void, label: string) => (
    <Field label={label}>{(id) => <select id={id} className="field" value={v} onChange={(e) => set(e.target.value)}>{open.map((a) => <option key={a.account_id} value={a.account_id}>{a.display_name}</option>)}</select>}</Field>
  );
  return (
    <Drawer title="Move money between accounts" onClose={onClose}>
      {open.length < 2 ? <p className="text-sm text-muted">You need two active accounts to move money between them. Add one in Books.</p> : m.isSuccess ? (
        <div className="space-y-4"><p role="status" className="text-green font-semibold">Done. Both sides are written and it is not counted as spending.</p><button className="btn btn-solid" onClick={onClose}>Close</button></div>
      ) : (
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); if (paise && from !== to) m.mutate(); }}>
          {sel(from, setFrom, "From")}
          {sel(to, setTo, "To")}
          {from === to && <p className="text-red text-sm" role="alert">Pick two different accounts.</p>}
          <Field label="Amount (₹)">{(id) => <input id={id} className="field text-xl" inputMode="decimal" autoFocus value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" />}</Field>
          <Field label="Date">{(id) => <input id={id} type="date" className="field" max={todayIso()} value={date} onChange={(e) => setDate(e.target.value)} />}</Field>
          {err(m)}
          <button className="btn btn-solid w-full" disabled={!paise || from === to || m.isPending}>{m.isPending ? "Moving…" : "Move money"}</button>
        </form>
      )}
    </Drawer>
  );
}

const FIELDS: [string, string][] = [["date", "Date"], ["description", "Narration"], ["amount", "Amount (one column)"], ["debit", "Debit (money out)"], ["credit", "Credit (money in)"]];

/** Bring in a bank statement CSV: pick the file, check the column mapping, see a dry run, then import. */
export function ImportDrawer({ accounts, onClose }: { accounts: Account[]; onClose: () => void }) {
  const refresh = useRefresh();
  const open = accounts.filter((a) => a.status === "ACTIVE");
  const [text, setText] = useState(""), [name, setName] = useState(""), [fileErr, setFileErr] = useState<string | null>(null);
  const [account, setAccount] = useState(open[0]?.account_id ?? "");
  const [map, setMap] = useState<Record<string, string>>({});
  const [prev, setPrev] = useState<ImportPreview | null>(null);
  const [dry, setDry] = useState<ImportResult | null>(null);
  const preview = useMutation({ mutationFn: (csv: string) => post<ImportPreview>("/me/import/preview", { csv_text: csv }), onSuccess: (p) => { setPrev(p); setMap(p.suggested_mapping); setDry(null); } });
  const run = useMutation({
    mutationFn: (dry_run: boolean) => post<ImportResult>("/me/import", { account_id: account, csv_text: text, mapping: map, dry_run }),
    onSuccess: (r) => { setDry(r); if (!r.dry_run) refresh(); },
  });
  async function pick(f: File | undefined) {
    setFileErr(null); setPrev(null); setDry(null);
    if (!f) return;
    if (f.size > 2_000_000) return setFileErr("That file is over 2 MB. Split it by year and import each part.");
    setName(f.name);
    const t = await f.text();
    setText(t);
    preview.mutate(t);
  }
  const done = dry && !dry.dry_run;
  return (
    <Drawer title="Import a bank statement" onClose={onClose} wide>
      {open.length === 0 ? <p className="text-sm text-muted">Add an account in Books first.</p> : done ? (
        <div className="space-y-4">
          <p role="status" className="text-green font-semibold">Imported {dry.imported} entr{dry.imported === 1 ? "y" : "ies"}{dry.skipped_duplicates ? `; ${dry.skipped_duplicates} already in your register were skipped` : ""}.</p>
          <button className="btn btn-solid" onClick={onClose}>Done</button>
        </div>
      ) : (
        <div className="space-y-5">
          <p className="text-sm text-muted">Download the statement as CSV from your bank’s app or site, then choose it here. Nothing is saved until you confirm. Rows you already have are skipped, so importing twice is safe.</p>
          <Field label="Into which account?">{(id) => <select id={id} className="field" value={account} onChange={(e) => { setAccount(e.target.value); setDry(null); }}>{open.map((a) => <option key={a.account_id} value={a.account_id}>{a.display_name}</option>)}</select>}</Field>
          <Field label="CSV file" hint={name || "Up to 5,000 rows"} error={fileErr ?? undefined}>{(id) => <input id={id} type="file" accept=".csv,text/csv" className="field" onChange={(e) => pick(e.target.files?.[0])} />}</Field>
          {preview.isPending && <p className="text-sm text-muted">Reading the file…</p>}
          {err(preview)}
          {prev && (
            <>
              <p className="text-sm">Found <b>{prev.rows_total}</b> rows. Check that each column is matched correctly.</p>
              <div className="grid sm:grid-cols-2 gap-3">
                {FIELDS.map(([k, label]) => (
                  <Field key={k} label={label}>{(id) => (
                    <select id={id} className="field" value={map[k] ?? ""} onChange={(e) => { setMap((m) => ({ ...m, [k]: e.target.value })); setDry(null); }}>
                      <option value="">— none —</option>{prev.headers.map((h) => <option key={h} value={h}>{h}</option>)}
                    </select>
                  )}</Field>
                ))}
              </div>
              <div className="overflow-x-auto"><table className="register min-w-[480px] text-xs"><thead><tr>{prev.headers.map((h) => <th key={h}>{h}</th>)}</tr></thead><tbody>{prev.sample.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody></table></div>
              <button className="btn" disabled={run.isPending || !account} onClick={() => run.mutate(true)}>{run.isPending ? "Checking…" : "Check before importing"}</button>
            </>
          )}
          {err(run)}
          {dry?.dry_run && (
            <div className="border border-rule-strong p-4 space-y-3" role="status">
              <p><b>{dry.to_import}</b> will be imported · {dry.skipped_duplicates} duplicates skipped · {dry.error_count} rows with problems</p>
              {dry.errors.length > 0 && <ul className="text-sm text-red list-disc pl-5">{dry.errors.slice(0, 8).map((e) => <li key={e.row}>Row {e.row}: {e.message}</li>)}</ul>}
              {dry.sample.length > 0 && <ul className="text-sm">{dry.sample.map((s, i) => <li key={i}>{s.date} · {s.description} · {s.amount_paise < 0 ? "−" : "+"}₹{rupees(s.amount_paise)}</li>)}</ul>}
              <button className="btn btn-solid" disabled={run.isPending || dry.to_import === 0} onClick={() => run.mutate(false)}>{run.isPending ? "Importing…" : `Import ${dry.to_import} entries`}</button>
            </div>
          )}
        </div>
      )}
    </Drawer>
  );
}
