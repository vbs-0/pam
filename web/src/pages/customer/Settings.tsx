import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";
import { Field, PageHead, QueryState, Section, Stamp } from "../../components/ui";
import { ApiError, del, download, get, post, put, tokenStore } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { dateTime, todayIso } from "../../lib/format";
import type { HouseholdInfo, NotifyPrefs, Profile } from "../../lib/types";

/** Account, alerts, sharing and your data, in one place. */
export default function Settings() {
  const { me } = useAuth();
  const profile = useQuery({ queryKey: ["profile"], queryFn: () => get<Profile>("/me/profile") });
  const real = profile.data && !profile.data.sample;
  return (
    <>
      <PageHead title="Settings" sub={me ? <>Signed in as <b>{me.email}</b></> : undefined} />
      <Notifications />
      {real ? <Household /> : <Section title="Share your register"><p className="text-sm text-muted">Sharing, backups and security settings are for your own register. This is a sample household, which is read-only.</p></Section>}
      <DataSection real={!!real} />
      {real && <Security />}
    </>
  );
}

function Msg({ m }: { m: { isError: boolean; error: unknown; isSuccess: boolean }; ok?: string }) {
  if (m.isError) return <p role="alert" className="text-red text-sm">{(m.error as ApiError).message}</p>;
  return null;
}

/* ---------- alerts ---------- */
function Notifications() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["notify"], queryFn: () => get<NotifyPrefs>("/me/notifications") });
  const save = useMutation({ mutationFn: (p: Partial<NotifyPrefs>) => put<NotifyPrefs>("/me/notifications", { ...q.data, ...p }), onSuccess: (d) => qc.setQueryData(["notify"], d) });
  return (
    <Section title="Daily email">
      <QueryState q={q} rows={3}>
        {(p) => (
          <div className="space-y-3 max-w-xl">
            <label className="flex items-start gap-3"><input type="checkbox" className="mt-1" checked={p.email_digest} disabled={save.isPending} onChange={(e) => save.mutate({ email_digest: e.target.checked })} />
              <span><b>Email me when something needs a look</b><br /><span className="text-sm text-muted">One short email a day, around 8 in the morning, to {p.email}. Nothing is sent on days with nothing to say.</span></span></label>
            {p.email_digest && (
              <fieldset className="pl-7 space-y-1"><legend className="sr-only">What to include</legend>
                {([["bills", "Bills and income due"], ["budgets", "Budgets near or over their limit"], ["cards", "Credit card due dates and limits"]] as const).map(([k, label]) => (
                  <label key={k} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={p[k]} onChange={(e) => save.mutate({ [k]: e.target.checked })} /> {label}</label>
                ))}
              </fieldset>
            )}
            {!p.mail_configured && p.email_digest && <p className="text-sm text-amber">This server has no outgoing email set up yet, so nothing will arrive until the owner configures it.</p>}
            <Msg m={save} />
          </div>
        )}
      </QueryState>
    </Section>
  );
}

/* ---------- household sharing ---------- */
function Household() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["household"], queryFn: () => get<HouseholdInfo>("/me/household/members") });
  const [code, setCode] = useState("");
  const refresh = () => qc.invalidateQueries();
  const invite = useMutation({ mutationFn: () => post("/me/household/invite"), onSuccess: () => qc.invalidateQueries({ queryKey: ["household"] }) });
  const join = useMutation({ mutationFn: () => post("/me/household/join", { code }), onSuccess: () => { setCode(""); refresh(); } });
  const leave = useMutation({ mutationFn: () => post("/me/household/leave"), onSuccess: refresh });
  const remove = useMutation({ mutationFn: (id: string) => del(`/me/household/members/${id}`), onSuccess: refresh });
  return (
    <Section title="Share your register">
      <QueryState q={q} rows={3}>
        {(h) => (
          <div className="space-y-5 max-w-2xl">
            <p className="text-sm text-muted">Invite a partner or family member so you both see the same accounts and entries, each with your own login.</p>
            <ul className="border-t border-rule">{h.members.map((m) => (
              <li key={m.app_user_id} className="py-2.5 border-b border-rule flex items-center gap-3"><span className="flex-1 truncate">{m.email}</span>{m.you && <Stamp tone="blue">You</Stamp>}{m.is_owner && <Stamp>Owner</Stamp>}{h.you === h.owner && !m.you && <button className="btn btn-ghost !min-h-[32px]" disabled={remove.isPending} onClick={() => confirm(`Remove ${m.email} from this household? They keep their login and get an empty register.`) && remove.mutate(m.app_user_id)}>Remove</button>}</li>
            ))}</ul>
            {h.invites.length > 0 && (
              <div><p className="text-sm font-semibold mb-1">Unused invite codes</p>
                <ul>{h.invites.map((i) => <li key={i.code} className="text-sm"><code className="font-mono text-lg tracking-widest">{i.code}</code> <span className="text-muted">expires {dateTime(i.expires_at)}</span></li>)}</ul>
                <p className="text-xs text-muted mt-1">Give the code to them. They sign in to their own account, open Settings, and enter it under “Join a household”. It works once.</p></div>
            )}
            <div className="flex flex-wrap gap-2">
              <button className="btn btn-solid" disabled={invite.isPending} onClick={() => invite.mutate()}>{invite.isPending ? "Creating…" : "Create an invite code"}</button>
              {h.members.length > 1 && <button className="btn btn-danger" disabled={leave.isPending} onClick={() => confirm("Leave this household? You will get an empty register of your own.") && leave.mutate()}>Leave this household</button>}
            </div>
            <Msg m={invite} /><Msg m={leave} />
            <form className="border-t border-rule pt-4" onSubmit={(e: FormEvent) => { e.preventDefault(); if (code.trim().length >= 6) join.mutate(); }}>
              <Field label="Join a household" hint="Enter a code someone gave you. Your own register must be empty.">{(id) => <input id={id} className="field max-w-xs font-mono uppercase tracking-widest" maxLength={12} value={code} onChange={(e) => setCode(e.target.value)} placeholder="ABCD2345" />}</Field>
              <button className="btn mt-2" disabled={code.trim().length < 6 || join.isPending}>Join</button> <Msg m={join} />
            </form>
          </div>
        )}
      </QueryState>
    </Section>
  );
}

/* ---------- data: export, backup, restore ---------- */
function DataSection({ real }: { real: boolean }) {
  const qc = useQueryClient();
  const [from, setFrom] = useState(""), [to, setTo] = useState("");
  const [err, setErr] = useState<string | null>(null), [done, setDone] = useState<string | null>(null);
  const run = async (fn: () => Promise<unknown>, ok?: string) => { setErr(null); setDone(null); try { await fn(); if (ok) setDone(ok); } catch (e) { setErr((e as Error).message); } };
  const restore = async (file: File) => {
    const text = await file.text();
    let backup: unknown;
    try { backup = JSON.parse(text); } catch { throw new Error("That file is not a PAM backup."); }
    const r = await post<{ accounts: number; transactions: number }>("/me/restore", { backup });
    await qc.invalidateQueries();
    return r;
  };
  return (
    <Section title="Your data">
      <div className="space-y-5 max-w-2xl">
        <div>
          <p className="font-semibold">Export entries</p>
          <p className="text-sm text-muted mb-2">A spreadsheet (CSV) of your register, opens in Excel or Google Sheets.</p>
          <div className="flex flex-wrap gap-2 items-end">
            <label className="text-sm">From<input type="date" className="field block" max={todayIso()} value={from} onChange={(e) => setFrom(e.target.value)} /></label>
            <label className="text-sm">To<input type="date" className="field block" max={todayIso()} value={to} onChange={(e) => setTo(e.target.value)} /></label>
            <button className="btn btn-solid" onClick={() => run(() => download("/me/export.csv", { date_from: from, date_to: to }, `pam-register-${todayIso()}.csv`), "Downloaded.")}>Download CSV</button>
          </div>
        </div>
        {real && (
          <div className="border-t border-rule pt-4">
            <p className="font-semibold">Backup and restore</p>
            <p className="text-sm text-muted mb-2">A complete copy of everything you entered: accounts, entries, notes, budgets and goals. Restore it into an empty register, for example after starting over.</p>
            <div className="flex flex-wrap gap-2">
              <button className="btn" onClick={() => run(() => download("/me/backup.json", {}, `pam-backup-${todayIso()}.json`), "Backup downloaded.")}>Download backup</button>
              <label className="btn cursor-pointer">Restore from a backup
                <input type="file" accept="application/json,.json" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) run(async () => { const r = await restore(f); setDone(`Restored ${r.accounts} accounts and ${r.transactions} entries.`); }); }} />
              </label>
            </div>
          </div>
        )}
        {err && <p role="alert" className="text-red text-sm">{err}</p>}
        {done && <p role="status" className="text-green text-sm">{done}</p>}
      </div>
    </Section>
  );
}

/* ---------- security ---------- */
function Security() {
  const { logout } = useAuth();
  const [open, setOpen] = useState<"pw" | "email" | "delete" | null>(null);
  return (
    <Section title="Account and security">
      <div className="space-y-3 max-w-xl">
        <Row title="Change password" sub="Signs you out everywhere else." active={open === "pw"} onToggle={() => setOpen(open === "pw" ? null : "pw")}><ChangePassword onDone={() => setOpen(null)} /></Row>
        <Row title="Change email" sub="Needs your password. We email the old address." active={open === "email"} onToggle={() => setOpen(open === "email" ? null : "email")}><ChangeEmail onDone={() => setOpen(null)} /></Row>
        <Row title="Delete my account" sub="Removes your login and, if nobody else shares it, every entry. This cannot be undone." danger active={open === "delete"} onToggle={() => setOpen(open === "delete" ? null : "delete")}><DeleteAccount onDone={logout} /></Row>
      </div>
    </Section>
  );
}

function Row({ title, sub, active, onToggle, danger, children }: { title: string; sub: string; active: boolean; onToggle: () => void; danger?: boolean; children: ReactNode }) {
  return (
    <div className="border border-rule-strong bg-sheet">
      <button type="button" className="w-full flex items-center gap-3 p-4 text-left" aria-expanded={active} onClick={onToggle}>
        <span className="flex-1"><span className={`block font-semibold ${danger ? "text-red" : ""}`}>{title}</span><span className="block text-sm text-muted">{sub}</span></span>
        <span aria-hidden className="text-muted">{active ? "−" : "+"}</span>
      </button>
      {active && <div className="px-4 pb-4 border-t border-rule pt-4">{children}</div>}
    </div>
  );
}

function ChangePassword({ onDone }: { onDone: () => void }) {
  const [cur, setCur] = useState(""), [pw, setPw] = useState(""), [again, setAgain] = useState("");
  const m = useMutation({ mutationFn: () => post<{ access_token: string }>("/auth/change-password", { current_password: cur, new_password: pw }), onSuccess: (d) => { tokenStore.set(d.access_token); setCur(""); setPw(""); setAgain(""); onDone(); } });
  const bad = pw.length < 10 ? "At least 10 characters" : pw !== again ? "The two new passwords differ" : "";
  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (!bad && cur) m.mutate(); }}>
      <Field label="Current password">{(id) => <input id={id} type="password" autoComplete="current-password" className="field" value={cur} onChange={(e) => setCur(e.target.value)} />}</Field>
      <Field label="New password" hint="At least 10 characters">{(id) => <input id={id} type="password" autoComplete="new-password" className="field" value={pw} onChange={(e) => setPw(e.target.value)} />}</Field>
      <Field label="New password again" error={again && bad ? bad : undefined}>{(id) => <input id={id} type="password" autoComplete="new-password" className="field" value={again} onChange={(e) => setAgain(e.target.value)} />}</Field>
      <button className="btn btn-solid" disabled={!!bad || !cur || m.isPending}>{m.isPending ? "Saving…" : "Change password"}</button> <Msg m={m} />
      {m.isSuccess && <p role="status" className="text-green text-sm">Password changed. Other devices were signed out.</p>}
    </form>
  );
}

function ChangeEmail({ onDone }: { onDone: () => void }) {
  const { refresh } = useAuth() as unknown as { refresh?: () => void };
  const [pw, setPw] = useState(""), [email, setEmail] = useState("");
  const m = useMutation({ mutationFn: () => post<{ access_token: string }>("/auth/change-email", { password: pw, new_email: email }), onSuccess: (d) => { tokenStore.set(d.access_token); onDone(); refresh?.(); location.reload(); } });
  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
      <Field label="New email">{(id) => <input id={id} type="email" autoComplete="email" className="field" value={email} onChange={(e) => setEmail(e.target.value)} />}</Field>
      <Field label="Your password">{(id) => <input id={id} type="password" autoComplete="current-password" className="field" value={pw} onChange={(e) => setPw(e.target.value)} />}</Field>
      <button className="btn btn-solid" disabled={!email.includes("@") || !pw || m.isPending}>{m.isPending ? "Saving…" : "Change email"}</button> <Msg m={m} />
    </form>
  );
}

function DeleteAccount({ onDone }: { onDone: () => void }) {
  const { me } = useAuth();
  const [email, setEmail] = useState(""), [pw, setPw] = useState("");
  const m = useMutation({ mutationFn: () => post("/auth/delete-account", { confirm_email: email, password: pw || null }), onSuccess: onDone });
  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
      <p className="text-sm">Type your email, <b>{me?.email}</b>, to confirm. If you sign in with a password, enter it as well.</p>
      <Field label="Your email">{(id) => <input id={id} className="field" autoComplete="off" value={email} onChange={(e) => setEmail(e.target.value)} />}</Field>
      <Field label="Password" hint="Leave empty if you only use Google">{(id) => <input id={id} type="password" autoComplete="current-password" className="field" value={pw} onChange={(e) => setPw(e.target.value)} />}</Field>
      <button className="btn btn-danger" disabled={email.trim().toLowerCase() !== me?.email.toLowerCase() || m.isPending}>{m.isPending ? "Deleting…" : "Delete my account for good"}</button> <Msg m={m} />
    </form>
  );
}

