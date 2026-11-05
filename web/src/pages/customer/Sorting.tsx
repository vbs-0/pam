import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Section } from "../../components/ui";
import { ApiError, del, get, post, put } from "../../lib/api";

interface Rule { rule_id: string; phrase: string; direction: "DR" | "CR"; category_code: string; category_name: string | null }
interface Ai { available: boolean; enabled: boolean; provider: string; what_is_sent: string }

/** "Remember my choice" rules, and the optional AI sorter. Both only touch entries PAM could not sort. */
export default function Sorting({ canWrite }: { canWrite: boolean }) {
  const qc = useQueryClient();
  const rules = useQuery({ queryKey: ["rules"], queryFn: () => get<Rule[]>("/me/sorting-rules") });
  const remove = useMutation({ mutationFn: (id: string) => del(`/me/sorting-rules/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["rules"] }) });
  return (
    <>
      <Section title="Sorting rules you made">
        <p className="text-sm text-muted mb-3 max-w-2xl">When you change an unsorted entry's category and tick “Remember”, PAM files similar narrations the same way from then on. Removing a rule only affects future entries.</p>
        {rules.data?.length ? (
          <ul className="border-t border-rule max-w-2xl">
            {rules.data.map((r) => (
              <li key={r.rule_id} className="py-2.5 border-b border-rule flex items-center gap-3">
                <span className="flex-1 min-w-0 truncate"><b>“{r.phrase}”</b> <span className="text-muted">({r.direction === "DR" ? "money out" : "money in"})</span> goes to <b>{r.category_name ?? r.category_code}</b></span>
                {canWrite && <button className="btn btn-ghost !min-h-[32px]" disabled={remove.isPending} onClick={() => remove.mutate(r.rule_id)}>Remove</button>}
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-muted">None yet.</p>}
      </Section>
      <AiPanel canWrite={canWrite} />
    </>
  );
}

function useAi() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["ai"], queryFn: () => get<Ai>("/me/ai") });
  const toggle = useMutation({ mutationFn: (enabled: boolean) => put("/me/ai", { enabled }), onSuccess: () => qc.invalidateQueries({ queryKey: ["ai"] }) });
  const run = useMutation({ mutationFn: () => post<{ checked: number; sorted: number; left: number }>("/me/ai/sort"), onSuccess: () => qc.invalidateQueries() });
  return { q, toggle, run };
}

function AiPanel({ canWrite }: { canWrite: boolean }) {
  const { q, toggle, run } = useAi();
  const a = q.data;
  return (
    <Section title="AI sorting (optional)">
      <div className="max-w-2xl space-y-3">
        {!a ? <p className="text-sm text-muted">Loading…</p> : !a.available ? (
          <p className="text-sm text-muted">Not set up on this server. The owner can switch it on by adding a Gemini API key.</p>
        ) : (
          <>
            <label className="flex items-start gap-3">
              <input type="checkbox" className="mt-1" checked={a.enabled} disabled={!canWrite || toggle.isPending} onChange={(e) => toggle.mutate(e.target.checked)} />
              <span><b>Let {a.provider} suggest categories for entries PAM could not sort</b><br />
                <span className="text-sm text-muted">{a.what_is_sent} Suggestions only apply when you press the button below, show as “AI” in the entry's history, and you can change any of them.</span></span>
            </label>
            {a.enabled && canWrite && (
              <div className="flex items-center gap-3 flex-wrap">
                <button className="btn btn-solid" disabled={run.isPending} onClick={() => run.mutate()}>{run.isPending ? "Asking…" : "Sort my unsorted entries"}</button>
                {run.isSuccess && <p role="status" className="text-sm text-green">{run.data.sorted} sorted{run.data.left ? `, ${run.data.left} left for you` : ""}.</p>}
                {run.isError && <p role="alert" className="text-sm text-red">{(run.error as ApiError).message}</p>}
              </div>
            )}
          </>
        )}
      </div>
    </Section>
  );
}

/** A one-line shortcut shown above the Unsorted list when AI sorting is on. */
export function AiInline() {
  const { q, run } = useAi();
  if (!q.data?.available || !q.data.enabled) return null;
  return (
    <div className="mb-4 flex items-center gap-3 flex-wrap border border-rule-strong bg-sheet p-3">
      <span className="text-sm flex-1">Let {q.data.provider} suggest categories for these. Sure answers are applied and marked “AI”.</span>
      <button className="btn btn-solid" disabled={run.isPending} onClick={() => run.mutate()}>{run.isPending ? "Asking…" : "Sort with AI"}</button>
      {run.isSuccess && <span role="status" className="text-sm text-green">{run.data.sorted} sorted, {run.data.left} left.</span>}
      {run.isError && <span role="alert" className="text-sm text-red">{(run.error as ApiError).message}</span>}
    </div>
  );
}
