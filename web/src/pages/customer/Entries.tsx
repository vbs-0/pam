import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Search } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";
import { CategorySelect, Drawer, Empty, ErrorBox, Field, Money, MonthBar, PageHead, Skeleton, Stamp, StatusStamp, useCategoryName } from "../../components/ui";
import { ApiError, del, get, patch, post } from "../../lib/api";
import { currentMonth, dateTime, dayLabel, monthName, titleCase, todayIso, toPaise } from "../../lib/format";
import type { Account, Profile, Txn, TxnPage } from "../../lib/types";

const KINDS = ["EXPENSE", "INCOME", "TRANSFER", "REFUND", "REVERSAL", "UNKNOWN"];
const CHANNELS = ["UPI", "IMPS", "NEFT", "RTGS", "NACH", "CARD_POS", "CARD_ECOM", "ATM", "BBPS", "INTERNAL"];

export default function Entries() {
  const [sp, setSp] = useSearchParams();
  const month = sp.get("month") ?? currentMonth();
  const allTime = sp.get("month") === "all";
  const category = sp.get("category") ?? "", account = sp.get("account") ?? "", kind = sp.get("kind") ?? "", q = sp.get("q") ?? "";
  const [search, setSearch] = useState(q);
  const [open, setOpen] = useState<string | null>(null);
  const adding = sp.get("add") === "1";
  const catName = useCategoryName();
  const set = (k: string, v: string) => setSp((p) => { if (v) p.set(k, v); else p.delete(k); return p; }, { replace: true });

  useEffect(() => { const t = setTimeout(() => search !== q && set("q", search.trim()), 300); return () => clearTimeout(t); }, [search]); // eslint-disable-line

  const profile = useQuery({ queryKey: ["profile"], queryFn: () => get<Profile>("/me/profile") });
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: () => get<Account[]>("/me/accounts") });
  const list = useInfiniteQuery({
    queryKey: ["entries", { month: allTime ? null : month, category, account, kind, q }],
    queryFn: ({ pageParam }) => get<TxnPage>("/me/transactions", { month: allTime ? undefined : month, category, account_id: account, kind, q, cursor: pageParam, limit: 50 }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (l) => l.next_cursor ?? undefined,
  });
  const rows = list.data?.pages.flatMap((p) => p.items) ?? [];
  const canWrite = profile.data && !profile.data.sample;

  return (
    <>
      <PageHead
        title={`Entries${allTime ? "" : ` · ${monthName(month)}`}`}
        sub="Every payment in and out, in the order it was written."
        right={<>
          {!allTime && <MonthBar month={month} onChange={(m) => set("month", m)} />}
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={allTime} onChange={(e) => set("month", e.target.checked ? "all" : currentMonth())} /> All months</label>
          {canWrite && <button className="btn btn-solid" onClick={() => set("add", "1")}><Plus size={16} aria-hidden /> Add entry</button>}
        </>}
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[2fr_1.3fr_1.3fr_1fr] mb-4" role="search">
        <Field label="Search narration">{(id) => (
          <div className="relative"><Search size={16} className="absolute left-3 top-3 text-muted" aria-hidden />
            <input id={id} className="field field-icon" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="swiggy, rent, 4821…" maxLength={60} /></div>
        )}</Field>
        <Field label="Category">{(id) => <CategorySelect id={id} value={category} onChange={(v) => set("category", v)} includeBlank="All categories" />}</Field>
        <Field label="Account">{(id) => (
          <select id={id} className="field" value={account} onChange={(e) => set("account", e.target.value)}>
            <option value="">All accounts</option>
            {accounts.data?.map((a) => <option key={a.account_id} value={a.account_id}>{a.display_name}</option>)}
          </select>
        )}</Field>
        <Field label="Kind">{(id) => (
          <select id={id} className="field" value={kind} onChange={(e) => set("kind", e.target.value)}>
            <option value="">Any</option>{KINDS.map((k) => <option key={k} value={k}>{k === "TRANSFER" ? "Contra" : k === "UNKNOWN" ? "Unsorted" : titleCase(k)}</option>)}
          </select>
        )}</Field>
      </div>

      {list.isPending ? <Skeleton rows={8} h={22} /> : list.isError ? <ErrorBox error={list.error} retry={() => list.refetch()} /> : rows.length === 0 ? (
        <Empty
          title={q || category || account || kind ? "No entries match these filters" : "No entries for this period"}
          hint={q || category || account || kind ? "Clear a filter or widen the month." : canWrite ? "Add your first entry to start the register." : undefined}
          action={(q || category || account || kind) && <button className="btn" onClick={() => setSp(new URLSearchParams(allTime ? { month: "all" } : { month }), { replace: true })}>Clear filters</button>}
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="register min-w-[760px]">
            <thead><tr><th className="w-[84px]">Date</th><th>Narration</th><th>Category</th><th className="num">Money out</th><th className="num">Money in</th></tr></thead>
            <tbody>
              {rows.map((t) => {
                const struck = t.kind === "TRANSFER" || t.kind === "REVERSAL";
                return (
                  <tr key={t.txn_id} className="clickable" onClick={() => setOpen(t.txn_id)} onKeyDown={(e) => e.key === "Enter" && setOpen(t.txn_id)} tabIndex={0} aria-label={`${t.descriptor}, open details`}>
                    <td className="margin-rule font-semibold text-blue pl-3">{dayLabel(t.local_date)}</td>
                    <td>
                      <div className={struck ? "struck" : ""}>{t.merchant_name ?? t.descriptor}</div>
                      <div className="text-xs text-muted truncate max-w-[420px]" title={t.descriptor}>{t.merchant_name ? t.descriptor : ""}{" "}<span className="opacity-80">{titleCase(t.channel)}</span></div>
                    </td>
                    <td>
                      <div className="flex gap-2 items-start flex-wrap">
                        <span>{catName(t.category_code)}</span>
                        {t.kind === "UNKNOWN" ? <StatusStamp status="UNKNOWN" /> : ["TRANSFER", "REFUND", "REVERSAL"].includes(t.kind) && <StatusStamp status={t.kind} />}
                        {t.overridden && <Stamp tone="blue" title="Changed by a person">Set by hand</Stamp>}
                      </div>
                    </td>
                    <td className="num">{t.amount_paise < 0 && <Money paise={t.amount_paise} struck={struck} />}</td>
                    <td className="num">{t.amount_paise > 0 && <Money paise={t.amount_paise} struck={struck} tone={struck ? undefined : "blue"} />}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="py-4 text-center">
            {list.hasNextPage
              ? <button className="btn" disabled={list.isFetchingNextPage} onClick={() => list.fetchNextPage()}>{list.isFetchingNextPage ? "Loading…" : "Load more entries"}</button>
              : <p className="text-muted text-sm">End of the register · {rows.length} entries</p>}
          </div>
        </div>
      )}

      {open && <TxnDrawer id={open} canWrite={!!canWrite} accounts={accounts.data ?? []} onClose={() => setOpen(null)} />}
      {adding && canWrite && <AddEntry accounts={accounts.data ?? []} onClose={() => set("add", "")} />}
    </>
  );
}

function useRefreshAll() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries();
}

function TxnDrawer({ id, canWrite, accounts, onClose }: { id: string; canWrite: boolean; accounts: Account[]; onClose: () => void }) {
  const catName = useCategoryName();
  const refresh = useRefreshAll();
  const q = useQuery({ queryKey: ["txn", id], queryFn: () => get<Txn>(`/me/transactions/${id}`) });
  const [cat, setCat] = useState(""), [reason, setReason] = useState(""), [edit, setEdit] = useState(false), [confirm, setConfirm] = useState(false);
  const recat = useMutation({
    mutationFn: () => post(`/me/transactions/${id}/category`, { category_code: cat, reason: reason.trim() || null }),
    onSuccess: () => { setCat(""); setReason(""); refresh(); },
  });
  const remove = useMutation({ mutationFn: () => del(`/me/transactions/${id}`), onSuccess: () => { refresh(); onClose(); } });
  const t = q.data;
  const acct = accounts.find((a) => a.account_id === t?.account_id);
  return (
    <Drawer title="Entry" onClose={onClose} wide>
      {q.isPending ? <Skeleton rows={6} /> : q.isError ? <ErrorBox error={q.error} retry={() => q.refetch()} /> : t && (
        <div className="space-y-6">
          <div>
            <p className="text-sm text-muted">{dayLabel(t.local_date)} · {dateTime(t.posted_at)} IST</p>
            <p className="text-3xl font-semibold mt-1"><Money paise={t.amount_paise} sign tone={t.amount_paise > 0 ? "blue" : undefined} /></p>
            <p className="mt-2 font-medium">{t.merchant_name ?? t.descriptor}</p>
            {t.merchant_name && <p className="text-sm text-muted break-words">{t.descriptor}</p>}
          </div>
          <dl className="grid grid-cols-[130px_1fr] gap-y-1.5 text-sm border-y border-rule py-3">
            <dt className="text-muted">Category</dt><dd>{catName(t.category_code)} {t.kind !== "EXPENSE" && <StatusStamp status={t.kind} />}</dd>
            <dt className="text-muted">Account</dt><dd>{acct ? acct.display_name : t.account_id}</dd>
            <dt className="text-muted">Channel</dt><dd>{titleCase(t.channel)}{t.counterparty_vpa && <> · {t.counterparty_vpa}</>}</dd>
            {t.reference_no && <><dt className="text-muted">Reference</dt><dd className="font-mono text-xs">{t.reference_no}</dd></>}
            <dt className="text-muted">Why this category</dt>
            <dd>{t.overridden ? "Set by hand." : t.decision === "NO_RULE" ? "No rule matched." : t.rule_id ? `Rule ${t.rule_id} v${t.rule_version}${t.confidence ? ` · ${Math.round(t.confidence * 100)}% sure` : ""}.` : titleCase(t.decision)}</dd>
            {t.link_txn_id && <><dt className="text-muted">Paired with</dt><dd className="font-mono text-xs">{t.link_txn_id}</dd></>}
            {t.series_id && <><dt className="text-muted">Recurring</dt><dd>Part of series {t.series_id}</dd></>}
          </dl>

          <section aria-labelledby="recat">
            <h3 id="recat" className="font-semibold mb-2">Change category</h3>
            <div className="space-y-3">
              <CategorySelect value={cat} onChange={setCat} />
              <input className="field" placeholder="Why? (optional)" maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} aria-label="Reason" />
              <button className="btn btn-solid" disabled={!cat || recat.isPending} onClick={() => recat.mutate()}>{recat.isPending ? "Saving…" : "Save category"}</button>
              {recat.isError && <p role="alert" className="text-red text-sm">{(recat.error as ApiError).message}</p>}
              {recat.isSuccess && <p role="status" className="text-green text-sm">Saved. Budgets and totals are already updated.</p>}
            </div>
          </section>

          {!!t.overrides?.length && (
            <section>
              <h3 className="font-semibold mb-2">History</h3>
              <ul className="text-sm border-t border-rule">{t.overrides.map((o) => (
                <li key={o.override_id} className="py-1.5 border-b border-rule">{catName(o.category_code)} · {o.actor} · {dateTime(o.created_at)}{o.reason && <span className="text-muted"> — {o.reason}</span>}</li>
              ))}</ul>
            </section>
          )}

          {canWrite && (
            <section className="border-t border-rule-strong pt-4 flex flex-wrap gap-2">
              <button className="btn" onClick={() => setEdit((v) => !v)}>{edit ? "Close editor" : "Edit entry"}</button>
              {!confirm ? <button className="btn btn-danger" onClick={() => setConfirm(true)}>Delete entry</button> : (
                <>
                  <span className="self-center text-sm">Delete permanently?</span>
                  <button className="btn btn-danger" disabled={remove.isPending} onClick={() => remove.mutate()}>Yes, delete</button>
                  <button className="btn btn-ghost" onClick={() => setConfirm(false)}>Keep</button>
                </>
              )}
              {remove.isError && <p role="alert" className="text-red text-sm w-full">{(remove.error as ApiError).message}</p>}
              {edit && <EditForm t={t} onDone={() => { setEdit(false); refresh(); }} />}
            </section>
          )}
        </div>
      )}
    </Drawer>
  );
}

function EditForm({ t, onDone }: { t: Txn; onDone: () => void }) {
  const [desc, setDesc] = useState(t.descriptor);
  const [amount, setAmount] = useState(String(Math.abs(t.amount_paise) / 100));
  const [date, setDate] = useState(t.local_date);
  const [dir, setDir] = useState<"DR" | "CR">(t.amount_paise < 0 ? "DR" : "CR");
  const m = useMutation({
    mutationFn: () => patch(`/me/transactions/${t.txn_id}`, { description: desc, amount_paise: toPaise(amount), date, direction: dir }),
    onSuccess: onDone,
  });
  const paise = toPaise(amount);
  return (
    <form className="w-full space-y-3 mt-2 border border-rule-strong p-4" onSubmit={(e) => { e.preventDefault(); if (paise) m.mutate(); }}>
      <Field label="Narration">{(id) => <input id={id} className="field" value={desc} onChange={(e) => setDesc(e.target.value)} maxLength={160} required />}</Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Amount (₹)" error={paise ? undefined : "Enter an amount like 1,250.50"}>{(id) => <input id={id} className="field" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />}</Field>
        <Field label="Date">{(id) => <input id={id} type="date" className="field" max={todayIso()} value={date} onChange={(e) => setDate(e.target.value)} />}</Field>
      </div>
      <Direction value={dir} onChange={setDir} />
      {m.isError && <p role="alert" className="text-red text-sm">{(m.error as ApiError).message}</p>}
      <button className="btn btn-solid" disabled={!paise || m.isPending}>{m.isPending ? "Saving…" : "Save changes"}</button>
    </form>
  );
}

function Direction({ value, onChange }: { value: "DR" | "CR"; onChange: (v: "DR" | "CR") => void }) {
  return (
    <fieldset>
      <legend className="text-sm font-semibold mb-1">Direction</legend>
      <div className="flex border border-rule-strong rounded-sm w-fit">
        {(["DR", "CR"] as const).map((d) => (
          <label key={d} className={`px-4 py-2 cursor-pointer text-sm font-semibold ${value === d ? "bg-blue text-paper" : "hover:bg-blue-soft"}`}>
            <input type="radio" className="sr-only" name="dir" checked={value === d} onChange={() => onChange(d)} />{d === "DR" ? "Money out" : "Money in"}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function AddEntry({ accounts, onClose }: { accounts: Account[]; onClose: () => void }) {
  const refresh = useRefreshAll();
  const open = accounts.filter((a) => a.status === "ACTIVE");
  const [f, setF] = useState({ account_id: open[0]?.account_id ?? "", date: todayIso(), time: "", amount: "", dir: "DR" as "DR" | "CR", description: "", channel: "UPI", vpa: "", ref: "", category: "" });
  const [more, setMore] = useState(false);
  const [saved, setSaved] = useState<{ txn_id: string; processed: boolean; possible_duplicate_of: string | null; transaction: Txn | null } | null>(null);
  const catName = useCategoryName();
  const paise = toPaise(f.amount);
  const up = (k: keyof typeof f) => (v: string) => setF((s) => ({ ...s, [k]: v }));
  const m = useMutation({
    mutationFn: () => post<NonNullable<typeof saved>>("/me/transactions", {
      account_id: f.account_id, date: f.date, time: f.time || null, amount_paise: paise, direction: f.dir, description: f.description,
      channel: f.channel, counterparty_vpa: f.vpa || null, reference_no: f.ref || null, category_code: f.category || null,
    }),
    onSuccess: (r) => { setSaved(r); refresh(); },
  });
  const dupDelete = useMutation({ mutationFn: (id: string) => del(`/me/transactions/${id}`), onSuccess: () => { refresh(); onClose(); } });
  const fieldErr = (name: string) => (m.error as ApiError | null)?.fields?.find((x) => x.field.endsWith(name))?.message;

  function submit(e: FormEvent) { e.preventDefault(); if (paise && f.account_id && f.description.trim()) m.mutate(); }

  if (open.length === 0) return (
    <Drawer title="Add entry" onClose={onClose}>
      <Empty title="Add an account first" hint="Entries live inside an account (a savings account or a credit card)." action={<a className="btn btn-solid no-underline" href="/books">Go to Books</a>} />
    </Drawer>
  );
  if (saved) return (
    <Drawer title="Entry written" onClose={onClose}>
      <div className="space-y-4">
        <p className="text-green font-semibold" role="status">Saved{saved.processed ? " and sorted." : "; it will be sorted in the next run."}</p>
        {saved.transaction && <p>Filed under <b>{catName(saved.transaction.category_code)}</b>{saved.transaction.kind === "TRANSFER" && <> <StatusStamp status="TRANSFER" /> — paired with your other account, not counted as spend.</>}</p>}
        {saved.possible_duplicate_of && (
          <div className="border border-amber p-3 text-sm">
            <p className="text-amber font-semibold">This looks like a duplicate of {saved.possible_duplicate_of}.</p>
            <p className="text-muted mt-1">Same account, day, amount and narration. Two identical payments in a day do happen, so it was kept.</p>
            <button className="btn btn-danger mt-3" disabled={dupDelete.isPending} onClick={() => dupDelete.mutate(saved.txn_id)}>Remove the new one</button>
          </div>
        )}
        <div className="flex gap-2"><button className="btn btn-solid" onClick={() => { setSaved(null); setF((s) => ({ ...s, amount: "", description: "", vpa: "", ref: "" })); m.reset(); }}>Add another</button><button className="btn" onClick={onClose}>Done</button></div>
      </div>
    </Drawer>
  );
  return (
    <Drawer title="Add entry" onClose={onClose}>
      <form onSubmit={submit} className="space-y-4" noValidate>
        <Direction value={f.dir} onChange={(v) => setF((s) => ({ ...s, dir: v }))} />
        <Field label="Amount (₹)" error={f.amount && !paise ? "Enter an amount like 1,250.50" : undefined}>{(id) => <input id={id} className="field text-xl" inputMode="decimal" autoFocus value={f.amount} onChange={(e) => up("amount")(e.target.value)} placeholder="0.00" />}</Field>
        <Field label="What was it for?" hint="Copy the bank narration or write your own, e.g. Swiggy dinner" error={fieldErr("description")}>{(id) => <input id={id} className="field" value={f.description} onChange={(e) => up("description")(e.target.value)} maxLength={160} />}</Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Date" error={fieldErr("date")}>{(id) => <input id={id} type="date" className="field" max={todayIso()} value={f.date} onChange={(e) => up("date")(e.target.value)} />}</Field>
          <Field label="Account">{(id) => (
            <select id={id} className="field" value={f.account_id} onChange={(e) => up("account_id")(e.target.value)}>
              {open.map((a) => <option key={a.account_id} value={a.account_id}>{a.display_name}</option>)}
            </select>
          )}</Field>
        </div>
        <Field label="Category" hint="Optional. Leave blank and PAM sorts it from the narration.">{(id) => <CategorySelect id={id} value={f.category} onChange={up("category")} includeBlank="Let PAM decide" />}</Field>
        <button type="button" className="text-sm underline text-blue" onClick={() => setMore((v) => !v)} aria-expanded={more}>{more ? "Hide" : "Show"} optional details</button>
        {more && (
          <div className="space-y-3 border-l border-rule-strong pl-4">
            <Field label="Time (IST)" hint="Noon if left blank">{(id) => <input id={id} type="time" className="field" value={f.time} onChange={(e) => up("time")(e.target.value)} />}</Field>
            <Field label="Channel">{(id) => <select id={id} className="field" value={f.channel} onChange={(e) => up("channel")(e.target.value)}>{CHANNELS.map((c) => <option key={c} value={c}>{titleCase(c)}</option>)}</select>}</Field>
            <Field label="Other party's UPI ID" hint="For payments between your own accounts, use the other account's UPI ID" error={fieldErr("counterparty_vpa")}>{(id) => <input id={id} className="field" value={f.vpa} onChange={(e) => up("vpa")(e.target.value)} placeholder="name@bank" />}</Field>
            <Field label="Reference number">{(id) => <input id={id} className="field" value={f.ref} onChange={(e) => up("ref")(e.target.value)} maxLength={24} />}</Field>
          </div>
        )}
        {m.isError && !(m.error as ApiError).fields?.length && <p role="alert" className="text-red text-sm border border-red bg-red-soft p-3">{(m.error as ApiError).message}</p>}
        <button className="btn btn-solid w-full" disabled={!paise || !f.description.trim() || m.isPending}>{m.isPending ? "Writing…" : "Write entry"}</button>
      </form>
    </Drawer>
  );
}
