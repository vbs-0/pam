import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Empty, Field, PageHead, QueryState, Stamp } from "../../components/ui";
import { ApiError, del, get, patch, post } from "../../lib/api";
import { dayLabel, rupees, toPaise, todayIso } from "../../lib/format";
import type { Goal, Profile } from "../../lib/types";

/** Savings goals: set a target and a date, add money as you set it aside, watch the bar fill. */
export default function Goals() {
  const qc = useQueryClient();
  const goals = useQuery({ queryKey: ["goals"], queryFn: () => get<Goal[]>("/me/goals") });
  const profile = useQuery({ queryKey: ["profile"], queryFn: () => get<Profile>("/me/profile") });
  const [adding, setAdding] = useState(false);
  const canWrite = profile.data && !profile.data.sample;
  const refresh = () => qc.invalidateQueries({ queryKey: ["goals"] }).then(() => qc.invalidateQueries({ queryKey: ["alerts"] }));
  return (
    <>
      <PageHead title="Goals" sub="Money you are putting aside for something. Add to a goal whenever you set cash aside." right={canWrite && <button className="btn btn-solid" onClick={() => setAdding((v) => !v)}><Plus size={16} aria-hidden /> New goal</button>} />
      {adding && canWrite && <NewGoal onDone={() => { setAdding(false); refresh(); }} />}
      <QueryState q={goals} rows={3}>
        {(rows) => rows.length === 0 && !adding ? (
          <Empty title="No goals yet" hint="A trip, a laptop, an emergency fund. Give it a target and a date and PAM tells you how much to set aside each month." action={canWrite && <button className="btn btn-solid" onClick={() => setAdding(true)}>Start a goal</button>} />
        ) : (
          <div className="grid gap-5 md:grid-cols-2">{rows.map((g) => <GoalCard key={g.goal_id} g={g} canWrite={!!canWrite} onChange={refresh} />)}</div>
        )}
      </QueryState>
    </>
  );
}

function NewGoal({ onDone }: { onDone: () => void }) {
  const [name, setName] = useState(""), [target, setTarget] = useState(""), [saved, setSaved] = useState(""), [deadline, setDeadline] = useState("");
  const m = useMutation({
    mutationFn: () => post("/me/goals", { name, target_paise: toPaise(target), saved_paise: saved ? toPaise(saved) : 0, deadline: deadline || null }),
    onSuccess: onDone,
  });
  const ok = name.trim() && toPaise(target);
  return (
    <form className="border border-rule-strong bg-sheet p-4 mb-6 grid gap-3 sm:grid-cols-2" onSubmit={(e: FormEvent) => { e.preventDefault(); if (ok) m.mutate(); }}>
      <Field label="What for?">{(id) => <input id={id} className="field" value={name} maxLength={60} onChange={(e) => setName(e.target.value)} placeholder="Goa trip, new phone, emergency fund" autoFocus />}</Field>
      <Field label="Target amount (₹)">{(id) => <input id={id} className="field" inputMode="decimal" value={target} onChange={(e) => setTarget(e.target.value)} placeholder="50,000" />}</Field>
      <Field label="Already saved (₹)" hint="Optional">{(id) => <input id={id} className="field" inputMode="decimal" value={saved} onChange={(e) => setSaved(e.target.value)} placeholder="0" />}</Field>
      <Field label="Needed by" hint="Optional">{(id) => <input id={id} type="date" className="field" min={todayIso()} value={deadline} onChange={(e) => setDeadline(e.target.value)} />}</Field>
      <div className="sm:col-span-2 flex items-center gap-3">
        <button className="btn btn-solid" disabled={!ok || m.isPending}>{m.isPending ? "Saving…" : "Create goal"}</button>
        {m.isError && <p role="alert" className="text-red text-sm">{(m.error as ApiError).message}</p>}
      </div>
    </form>
  );
}

function GoalCard({ g, canWrite, onChange }: { g: Goal; canWrite: boolean; onChange: () => void }) {
  const [amt, setAmt] = useState("");
  const add = useMutation({ mutationFn: (sign: 1 | -1) => post(`/me/goals/${g.goal_id}/contribute`, { amount_paise: sign * (toPaise(amt) ?? 0) }), onSuccess: () => { setAmt(""); onChange(); } });
  const remove = useMutation({ mutationFn: () => del(`/me/goals/${g.goal_id}`), onSuccess: onChange });
  const [confirm, setConfirm] = useState(false), [editing, setEditing] = useState(false);
  const pct = Math.round(g.progress * 100);
  return (
    <section className="border border-rule-strong bg-sheet p-4" aria-label={g.name}>
      <div className="flex items-start gap-2">
        <h3 className="font-semibold text-lg flex-1">{g.name}</h3>
        {g.completed && <Stamp tone="green">Reached</Stamp>}
        {canWrite && !confirm && <button className="btn btn-ghost !min-h-[32px]" onClick={() => setEditing((v) => !v)}>{editing ? "Close" : "Edit"}</button>}
        {canWrite && !confirm && <button className="btn btn-ghost !min-h-[32px]" aria-label={`Delete ${g.name}`} onClick={() => setConfirm(true)}><Trash2 size={15} aria-hidden /></button>}
      </div>
      {confirm && <p className="text-sm my-2">Delete this goal? <button className="btn btn-danger !min-h-[32px] ml-2" onClick={() => remove.mutate()}>Yes, delete</button> <button className="btn btn-ghost !min-h-[32px]" onClick={() => setConfirm(false)}>Keep</button></p>}
      {editing && <EditGoal g={g} onDone={() => { setEditing(false); onChange(); }} />}
      <p className="num text-2xl font-semibold mt-1">₹{rupees(g.saved_paise)} <span className="text-base font-normal text-muted">of ₹{rupees(g.target_paise)}</span></p>
      <div className="h-3 bg-[var(--rule)] mt-3" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={`${g.name}: ${pct} percent saved`}>
        <div className={`h-full ${g.completed ? "bg-green" : "bg-blue"} bar-grow`} style={{ width: `${pct}%` }} />
      </div>
      <p className="text-sm text-muted mt-2">
        {g.completed ? "You made it." : <>₹{rupees(g.remaining_paise)} to go{g.deadline && <> · by {dayLabel(g.deadline)} ({g.days_left} day{g.days_left === 1 ? "" : "s"})</>}</>}
      </p>
      {!g.completed && g.monthly_needed_paise !== null && <p className="text-sm mt-1">Set aside about <b>₹{rupees(g.monthly_needed_paise)}</b> a month to get there.</p>}
      {canWrite && (
        <form className="flex gap-2 mt-4" onSubmit={(e) => { e.preventDefault(); if (toPaise(amt)) add.mutate(1); }}>
          <input className="field flex-1" inputMode="decimal" aria-label={`Amount to add to ${g.name}`} placeholder="₹ amount" value={amt} onChange={(e) => setAmt(e.target.value)} />
          <button className="btn btn-solid" disabled={!toPaise(amt) || add.isPending}>Add</button>
          <button type="button" className="btn" disabled={!toPaise(amt) || add.isPending || g.saved_paise === 0} onClick={() => add.mutate(-1)}>Take out</button>
        </form>
      )}
      {(add.isError || remove.isError) && <p role="alert" className="text-red text-sm mt-2">{((add.error ?? remove.error) as ApiError).message}</p>}
    </section>
  );
}


function EditGoal({ g, onDone }: { g: Goal; onDone: () => void }) {
  const [name, setName] = useState(g.name), [target, setTarget] = useState(String(g.target_paise / 100)), [deadline, setDeadline] = useState(g.deadline ?? "");
  const m = useMutation({ mutationFn: () => patch(`/me/goals/${g.goal_id}`, { name, target_paise: toPaise(target), deadline: deadline || null }), onSuccess: onDone });
  return (
    <form className="grid gap-2 my-3" onSubmit={(e) => { e.preventDefault(); if (name.trim() && toPaise(target)) m.mutate(); }}>
      <input className="field" aria-label="Goal name" value={name} maxLength={60} onChange={(e) => setName(e.target.value)} />
      <div className="grid grid-cols-2 gap-2">
        <input className="field" aria-label="Target amount" inputMode="decimal" value={target} onChange={(e) => setTarget(e.target.value)} />
        <input className="field" aria-label="Needed by" type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
      </div>
      <div className="flex items-center gap-3"><button className="btn btn-solid" disabled={m.isPending}>Save changes</button>{m.isError && <p role="alert" className="text-red text-sm">{(m.error as ApiError).message}</p>}</div>
    </form>
  );
}
