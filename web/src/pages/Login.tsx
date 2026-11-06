import { useState, type FormEvent } from "react";
import { Link, Navigate } from "react-router";
import { Field, Logo, Spinner } from "../components/ui";
import { homeFor } from "../components/Shell";
import { ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { googleEnabled } from "../lib/firebase";

export default function Login() {
  const { me, login, register, google, expired } = useAuth();
  const [mode, setMode] = useState<"in" | "up">("in");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (me) return <Navigate to={homeFor(me.role)} replace />;

  async function withGoogle() {
    setBusy(true); setError(null);
    try { await google(); }
    catch (err) { setError(err instanceof ApiError || err instanceof Error ? err.message : "Could not sign in with Google."); }
    finally { setBusy(false); }
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (mode === "up" && password.length < 6) { setError("Your password needs at least 6 characters."); return; }
    setBusy(true); setError(null);
    try { await (mode === "in" ? login(email.trim(), password) : register(email.trim(), password, name.trim())); }
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
            <div className="mb-4"><Logo size={56} /></div>
            <h1 className="text-2xl font-semibold tracking-tight">{mode === "in" ? "Open your register" : "Start your register"}</h1>
            <p className="text-muted mt-1">{mode === "in" ? "Sign in with your email and password." : "Create an account. You get a household of your own, empty and ready for your entries."}</p>
          </div>
          {expired && <p role="status" className="text-amber border border-amber px-3 py-2 text-sm">Your session ended. Please sign in again.</p>}
          {mode === "up" && <Field label="Your name" hint="Optional">{(id) => <input id={id} className="field" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} maxLength={80} />}</Field>}
          <Field label="Email">{(id) => <input id={id} className="field" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />}</Field>
          <Field label="Password" hint={mode === "up" ? "At least 6 characters" : undefined}>{(id) => <input id={id} className="field" type="password" autoComplete={mode === "in" ? "current-password" : "new-password"} required minLength={mode === "up" ? 10 : undefined} value={password} onChange={(e) => setPassword(e.target.value)} />}</Field>
          {mode === "in" && <p className="text-sm -mt-2"><Link to="/forgot" className="underline text-blue">Forgot your password?</Link></p>}
          {error && <p role="alert" className="text-red text-sm border border-red bg-red-soft px-3 py-2">{error}</p>}
          <button className="btn btn-solid w-full" disabled={busy || !email || !password}>{busy ? <><Spinner />One moment…</> : mode === "in" ? "Sign in" : "Create account"}</button>
          {googleEnabled && <button type="button" className="btn w-full" disabled={busy} onClick={withGoogle}>Continue with Google</button>}
          <p className="text-sm text-center">{mode === "in" ? "New here? " : "Already have an account? "}<button type="button" className="underline text-blue font-semibold" onClick={() => { setMode(mode === "in" ? "up" : "in"); setError(null); }}>{mode === "in" ? "Create an account" : "Sign in"}</button></p>
          <div className="text-sm text-muted border-t border-rule pt-4 space-y-1">
            <p><b className="text-ink">Looking around?</b> Sample households sign in as <span className="font-mono text-ink">usr-000001@pam.is-cool.dev</span> with password <span className="font-mono text-ink">password123</span>. They are read-only synthetic data.</p>
          </div>
          <a href="https://github.com/vbs-0/pam" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 text-sm text-muted hover:text-ink transition-colors" aria-label="PAM source code on GitHub">
            <svg viewBox="0 0 16 16" width="20" height="20" fill="currentColor" aria-hidden="true"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg>
            View the source on GitHub
          </a>
        </form>
      </section>
    </div>
  );
}
