import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Empty, Field, Money, PageHead, QueryState, Section, Stamp, StatusStamp } from "../../components/ui";
import { ApiError, get, patch, post } from "../../lib/api";
import { dayLabel, todayIso, toPaise } from "../../lib/format";
import type { Account, Profile } from "../../lib/types";

const BANKS: Record<string, string> = { SBIN: "State Bank of India", HDFC: "HDFC Bank", ICIC: "ICICI Bank", UTIB: "Axis Bank", KKBK: "Kotak Mahindra Bank", BARB: "Bank of Baroda", PUNB: "Punjab National Bank", CNRB: "Canara Bank", OTHR: "Other bank" };
const UPI_APPS: Record<string, string> = { PHPE: "PhonePe", GPAY: "Google Pay", PTYM: "Paytm", BHIM: "BHIM", AMZN: "Amazon Pay", OTHR: "Other (type a name)" };
const ALL_NAMES: Record<string, string> = { ...BANKS, ...UPI_APPS, OTHR: "Other" };

export default function Books() {
  const qc = useQueryClient();
  const profile = useQuery({ queryKey: ["profile"], queryFn: () => get<Profile>("/me/profile") });
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: () => get<Account[]>("/me/accounts") });
  const sample = profile.data?.sample;
  const close = useMutation({ mutationFn: (id: string) => post(`/me/accounts/${id}/close`, {}), onSuccess: () => qc.invalidateQueries() });
  const [confirm, setConfirm] = useState<string | null>(null);

  return (
    <>
      <PageHead title="Books" sub="Your accounts and household details." />
      <Section title="Accounts">
        <QueryState q={accounts}>
          {(rows) => rows.length === 0 ? <Empty title="No accounts yet" hint="Add a savings account, credit card or UPI app to start writing entries." /> : (
            <div className="overflow-x-auto"><table className="register min-w-[640px]">
              <thead><tr><th>Account</th><th>Provider</th><th>UPI ID</th><th className="num">Balance</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>
                {rows.map((a) => (
                  <tr key={a.account_id}>
                    <td><div>{a.display_name}</div><div className="text-xs text-muted">Opened {dayLabel(a.opened_on)} {a.opened_on.slice(0, 4)}{a.holder_role === "JOINT" && <> · <Stamp>Joint</Stamp></>}</div></td>
                    <td>{a.label && a.account_type !== "UPI" ? `${a.label} (${ALL_NAMES[a.bank_code] ?? a.bank_code})` : ALL_NAMES[a.bank_code] ?? a.bank_code}</td>
                    <td className="font-mono text-xs">{a.vpa ?? "—"}</td>
                    <td className="num"><Money paise={a.balance_paise} tone={a.balance_paise < 0 ? "red" : undefined} />{a.credit_limit_paise && <div className="text-xs text-muted">limit <Money paise={a.credit_limit_paise} /></div>}</td>
                    <td><StatusStamp status={a.status} /></td>
                    <td>{!sample && a.status === "ACTIVE" && !a.shared_from_other_household && (confirm === a.account_id
                      ? <span className="flex gap-1"><button className="btn btn-danger !min-h-[32px]" disabled={close.isPending} onClick={() => close.mutate(a.account_id)}>Close it</button><button className="btn btn-ghost !min-h-[32px]" onClick={() => setConfirm(null)}>Keep</button></span>
                      : <button className="btn btn-ghost !min-h-[32px]" onClick={() => setConfirm(a.account_id)}>Close</button>)}</td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          )}
        </QueryState>
        {close.isError && <p role="alert" className="text-red mt-2">{(close.error as ApiError).message}</p>}
        {profile.data && !sample && <AddAccount />}
      </Section>

      <Section title="Household">
        <QueryState q={profile} rows={3}>{(p) => <ProfileForm p={p} />}</QueryState>
      </Section>
    </>
  );
}

function AddAccount() {
  const qc = useQueryClient();
  const [f, setF] = useState({ type: "SAVINGS", bank: "HDFC", label: "", last4: "", vpa: "", opening: "", opened: todayIso(), limit: "" });
  const up = (k: keyof typeof f) => (v: string) => setF((s) => ({ ...s, [k]: v }));
  const m = useMutation({
    mutationFn: () => post("/me/accounts", {
      account_type: f.type, bank_code: f.bank, label: f.label.trim() || null, last4: f.type === "UPI" ? null : f.last4 || null, vpa: f.vpa || null, opened_on: f.opened,
      opening_balance_paise: f.opening ? toPaise(f.opening) ?? 0 : 0, credit_limit_paise: f.type === "CREDIT_CARD" && f.limit ? toPaise(f.limit) : null,
    }),
    onSuccess: () => { qc.invalidateQueries(); setF((s) => ({ ...s, label: "", last4: "", vpa: "", opening: "", limit: "" })); },
  });
  const isUpi = f.type === "UPI";
  const setType = (type: string) => setF((s) => ({ ...s, type, bank: type === "UPI" ? "PHPE" : s.bank in BANKS ? s.bank : "HDFC", label: "" }));
  const needsName = isUpi && f.bank === "OTHR";
  const err = (n: string) => (m.error as ApiError | null)?.fields?.find((x) => x.field.endsWith(n))?.message;
  return (
    <form className="mt-8 border border-rule-strong p-5 bg-sheet" onSubmit={(e: FormEvent) => { e.preventDefault(); m.mutate(); }}>
      <h3 className="font-semibold mb-3">Add an account</h3>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <Field label="Type">{(id) => <select id={id} className="field" value={f.type} onChange={(e) => setType(e.target.value)}><option value="SAVINGS">Savings account</option><option value="CREDIT_CARD">Credit card</option><option value="UPI">UPI app (PhonePe, Paytm…)</option></select>}</Field>
        <Field label={isUpi ? "UPI app" : "Bank"}>{(id) => <select id={id} className="field" value={f.bank} onChange={(e) => up("bank")(e.target.value)}>{Object.entries(isUpi ? UPI_APPS : BANKS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>}</Field>
        {(needsName || (!isUpi && f.bank === "OTHR")) && <Field label={isUpi ? "App name" : "Bank name"} hint={isUpi ? undefined : "Optional"} error={err("label")}>{(id) => <input id={id} className="field" maxLength={40} required={needsName} value={f.label} onChange={(e) => up("label")(e.target.value)} placeholder={isUpi ? "e.g. Slice, Cred, Navi" : "e.g. Federal Bank"} />}</Field>}
        {!isUpi && <Field label="Last 4 digits" hint="Optional" error={err("last4")}>{(id) => <input id={id} className="field" inputMode="numeric" maxLength={4} value={f.last4} onChange={(e) => up("last4")(e.target.value.replace(/\D/g, ""))} />}</Field>}
        {f.type !== "CREDIT_CARD" && <Field label="Your UPI ID" hint="Optional. Lets PAM recognise payments between your own accounts." error={err("vpa")}>{(id) => <input id={id} className="field" value={f.vpa} onChange={(e) => up("vpa")(e.target.value)} placeholder={isUpi ? "name@ybl" : "name@okhdfcbank"} />}</Field>}
        <Field label={f.type === "CREDIT_CARD" ? "Amount owed today (₹)" : isUpi ? "Wallet balance today (₹)" : "Balance when you start (₹)"} hint="Optional. Leave blank for zero.">{(id) => <input id={id} className="field" inputMode="decimal" value={f.opening} onChange={(e) => up("opening")(e.target.value)} />}</Field>
        {f.type === "CREDIT_CARD" && <Field label="Credit limit (₹)" hint="Optional">{(id) => <input id={id} className="field" inputMode="decimal" value={f.limit} onChange={(e) => up("limit")(e.target.value)} />}</Field>}
        <Field label="Opened on" error={err("opened_on")}>{(id) => <input id={id} type="date" className="field" max={todayIso()} value={f.opened} onChange={(e) => up("opened")(e.target.value)} />}</Field>
      </div>
      {m.isError && !(m.error as ApiError).fields?.length && <p role="alert" className="text-red mt-3 text-sm">{(m.error as ApiError).message}</p>}
      <button className="btn btn-solid mt-4" disabled={m.isPending}>{m.isPending ? "Adding…" : "Add account"}</button>
    </form>
  );
}

function ProfileForm({ p }: { p: Profile }) {
  const qc = useQueryClient();
  const [f, setF] = useState({ name: p.display_name, city: p.city === "Not set" ? "" : p.city, state: p.state === "NA" ? "" : p.state, income: p.monthly_income_paise ? String(p.monthly_income_paise / 100) : "", size: String(p.household_size), persona: p.persona });
  const m = useMutation({
    mutationFn: () => patch("/me/profile", { display_name: f.name, city: f.city || undefined, state: f.state || undefined, monthly_income_paise: f.income ? toPaise(f.income) : undefined, household_size: Number(f.size), persona: f.persona }),
    onSuccess: () => qc.invalidateQueries(),
  });
  const up = (k: keyof typeof f) => (v: string) => setF((s) => ({ ...s, [k]: v }));
  const ro = p.sample;
  return (
    <form className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 max-w-4xl" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
      <Field label="Household name">{(id) => <input id={id} className="field" disabled={ro} value={f.name} onChange={(e) => up("name")(e.target.value)} maxLength={80} />}</Field>
      <Field label="City">{(id) => <input id={id} className="field" disabled={ro} value={f.city} onChange={(e) => up("city")(e.target.value)} maxLength={40} />}</Field>
      <Field label="State code" hint="Two letters, e.g. MH">{(id) => <input id={id} className="field uppercase" disabled={ro} value={f.state} onChange={(e) => up("state")(e.target.value.toUpperCase().slice(0, 2))} maxLength={2} />}</Field>
      <Field label="Monthly income (₹)" hint="Optional. Used for the savings rate.">{(id) => <input id={id} className="field" disabled={ro} inputMode="decimal" value={f.income} onChange={(e) => up("income")(e.target.value)} />}</Field>
      <Field label="People in the household">{(id) => <input id={id} className="field" type="number" min={1} max={20} disabled={ro} value={f.size} onChange={(e) => up("size")(e.target.value)} />}</Field>
      <Field label="Income type">{(id) => <select id={id} className="field" disabled={ro} value={f.persona} onChange={(e) => up("persona")(e.target.value)}><option value="SALARIED">Salaried</option><option value="SELF_EMPLOYED">Self-employed</option><option value="RETIRED">Retired</option></select>}</Field>
      {!ro && <div className="sm:col-span-2 lg:col-span-3 flex items-center gap-3"><button className="btn btn-solid" disabled={m.isPending}>{m.isPending ? "Saving…" : "Save details"}</button>
        {m.isSuccess && <span role="status" className="text-green text-sm">Saved</span>}{m.isError && <span role="alert" className="text-red text-sm">{(m.error as ApiError).message}</span>}</div>}
      {ro && <p className="text-muted text-sm sm:col-span-3">This is a sample household, so its details are read-only.</p>}
    </form>
  );
}
