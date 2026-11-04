import { useState, type FormEvent } from "react";
import { Navigate } from "react-router";
import { Field } from "../components/ui";
import { homeFor } from "../components/Shell";
import { ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";

export default function Login() {
  const { me, login, expired } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (me) return <Navigate to={homeFor(me.role)} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try { await login(email.trim(), password); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Could not sign in."); }
    finally { setBusy(false); }
  }

  return (
    <div className="min-h-screen grid md:grid-cols-[1.1fr_1fr]">
      <section className="hidden md:flex flex-col justify-between p-12 border-r border-rule-strong bg-sheet relative overflow-hidden" aria-hidden>
        <div className="absolute inset-0" style={{ backgroundImage: "linear-gradient(to bottom, transparent 39px, var(--rule) 39px)", backgroundSize: "100% 40px" }} />
        <div className="absolute inset-y-0 left-24 w-px bg-red" />
        <div className="relative pl-28 pt-8">
          <p className="text-5xl font-semibold tracking-tight text-blue leading-[1.15]">Where did<br />the month go?</p>
        </div>
        <div className="relative pl-28 pb-8 space-y-0 text-lg">
          <div className="flex justify-between max-w-md border-b border-rule-strong py-2"><span>Naive ledger spend</span><span className="struck num">₹3,18,420.00</span></div>
          <div className="flex justify-between max-w-md border-b border-rule-strong py-2"><span>Contra, refunds, reversals</span><span className="num text-muted">− ₹1,68,235.50</span></div>
          <div className="flex justify-between max-w-md py-2 font-semibold text-blue"><span>True spend</span><span className="num">₹1,50,184.50</span></div>
          <p className="text-xs text-muted max-w-md pt-3">Illustration of how PAM writes a month. Figures are made up.</p>
        </div>
      </section>
      <section className="flex items-center justify-center p-6">
        <form onSubmit={submit} className="w-full max-w-sm space-y-5" noValidate>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Open your register</h1>
            <p className="text-muted mt-1">Sign in with your email and password.</p>
          </div>
          {expired && <p role="status" className="text-amber border border-amber px-3 py-2 text-sm">Your session ended. Please sign in again.</p>}
          <Field label="Email">{(id) => <input id={id} className="field" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />}</Field>
          <Field label="Password">{(id) => <input id={id} className="field" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />}</Field>
          {error && <p role="alert" className="text-red text-sm border border-red bg-red-soft px-3 py-2">{error}</p>}
          <button className="btn btn-solid w-full" disabled={busy || !email || !password}>{busy ? "Signing in…" : "Sign in"}</button>
          <div className="text-sm text-muted border-t border-rule pt-4 space-y-1">
            <p><b className="text-ink">Looking around?</b> Sample households sign in as <span className="font-mono text-ink">usr-000001@pam.is-cool.dev</span> with password <span className="font-mono text-ink">password123</span>. They are read-only synthetic data.</p>
            <p>Google sign-in is switched off on this server until a Firebase project is connected.</p>
          </div>
        </form>
      </section>
    </div>
  );
}
