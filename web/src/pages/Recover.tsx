import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";
import { Field, Logo } from "../components/ui";
import { api, ApiError } from "../lib/api";

function Page({ title, lead, children }: { title: string; lead: string; children: ReactNode }) {
  return (
    <div className="min-h-screen flex items-center justify-center p-6 relative">
      <div className="absolute inset-y-0 left-6 sm:left-24 w-px bg-red opacity-60" aria-hidden />
      <div className="w-full max-w-sm space-y-5 relative sm:pl-0">
        <p className="flex items-center gap-2 text-sm font-bold tracking-[0.2em] text-blue"><Logo size={32} />PAM</p>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          <p className="text-muted mt-1">{lead}</p>
        </div>
        {children}
      </div>
    </div>
  );
}

const call = (path: string, body: unknown) => api<{ detail: string }>("POST", path, { body, auth: false });
const message = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong. Please try again.");

export function Forgot() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try { setDone((await call("/auth/forgot", { email: email.trim() })).detail); }
    catch (err) { setError(message(err)); }
    finally { setBusy(false); }
  }

  return (
    <Page title="Reset your password" lead="Enter your email and we will send a link that works for 30 minutes.">
      {done ? (
        <p role="status" className="border border-blue px-3 py-2 text-sm">{done} Check your spam folder if it does not arrive in a few minutes.</p>
      ) : (
        <form onSubmit={submit} className="space-y-5" noValidate>
          <Field label="Email">{(id) => <input id={id} className="field" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />}</Field>
          {error && <p role="alert" className="text-red text-sm border border-red bg-red-soft px-3 py-2">{error}</p>}
          <button className="btn btn-solid w-full" disabled={busy || email.length < 5}>{busy ? "Sending…" : "Send reset link"}</button>
        </form>
      )}
      <p className="text-sm"><Link to="/login" className="underline text-blue font-semibold">Back to sign in</Link></p>
    </Page>
  );
}

export function Reset() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mismatch = again.length > 0 && again !== password;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try { await call("/auth/reset", { token, password }); setDone(true); }
    catch (err) { setError(message(err)); }
    finally { setBusy(false); }
  }

  if (!token) return (
    <Page title="Link incomplete" lead="This page needs the link from your reset email.">
      <p className="text-sm"><Link to="/forgot" className="underline text-blue font-semibold">Ask for a new link</Link></p>
    </Page>
  );
  return (
    <Page title="Choose a new password" lead="At least 10 characters. Older reset links stop working once you save.">
      {done ? (
        <>
          <p role="status" className="border border-blue px-3 py-2 text-sm">Password changed.</p>
          <Link to="/login" className="btn btn-solid w-full no-underline">Sign in</Link>
        </>
      ) : (
        <form onSubmit={submit} className="space-y-5" noValidate>
          <Field label="New password">{(id) => <input id={id} className="field" type="password" autoComplete="new-password" required minLength={10} value={password} onChange={(e) => setPassword(e.target.value)} />}</Field>
          <Field label="Type it again" hint={mismatch ? "The two passwords differ" : undefined}>{(id) => <input id={id} className="field" type="password" autoComplete="new-password" required value={again} onChange={(e) => setAgain(e.target.value)} />}</Field>
          {error && <p role="alert" className="text-red text-sm border border-red bg-red-soft px-3 py-2">{error} <Link to="/forgot" className="underline font-semibold">Get a new link</Link></p>}
          <button className="btn btn-solid w-full" disabled={busy || password.length < 10 || password !== again}>{busy ? "Saving…" : "Save password"}</button>
        </form>
      )}
    </Page>
  );
}
