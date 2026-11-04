# Kharcha Web Console, Android App and Submission Docs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A desktop-first React console for all four roles, a smooth Flutter Android app for customers (Google
sign-in via Firebase), and the submission documentation (README, AI disclosure, prompt history).

**Architecture:** Both clients are thin views over the backend `/api/v1` (plan `2026-11-04-backend.md`, tasks
B16–B19). Web types are generated from the backend OpenAPI schema so the client cannot drift. Firebase only proves
identity; the backend decides roles. Every client also supports the backend's local demo login so reviewers can run
without a Firebase project.

**Tech Stack:** Web — Node ≥20 (dev box: 24), React 19, TypeScript, Vite, Tailwind v4 + shadcn/ui, TanStack Query v5 +
Table v8, React Router v7, Recharts, Firebase JS SDK v11, openapi-fetch + openapi-typescript, Vitest; nginx for serving.
Android — Flutter stable (dev box: `C:\flutter\bin`), firebase_core, firebase_auth, google_sign_in ^6.2, flutter_riverpod,
dio, go_router, fl_chart, flutter_secure_storage, intl.

**Spec:** `docs/superpowers/specs/2026-11-04-kharcha-design.md` (§2 features, §10 clients, §12 performance).

## Global Constraints

- Prerequisite: backend tasks B1–B19 complete and `uv run uvicorn app.main:app --port 8000` serving a loaded dataset.
- Money arrives as integer paise; format only at the edge with `en-IN` INR (₹1,23,456.78). Never do float math on paise except for display.
- Months are `YYYY-MM` strings; the selected month lives in the URL (`?month=`) on web and in a Riverpod provider on mobile.
- No secrets in git: `web/.env.local`, `mobile/android/app/google-services.json` are ignored; `.env.example` files document keys.
- Demo passwords are typed by the user, never hardcoded in client code.
- Every list endpoint is paginated by keyset cursor; clients use "load more"/infinite scroll, never page numbers.
- Every screen has loading (skeleton), empty and error (with retry) states.
- Commit messages end with exactly `Authored-By: vbs-0`; no AI attribution trailers. No `git push` without the user's explicit go-ahead in that message.

**UI quality bar (the frontend is a first-class deliverable, judged as hard as the backend):**
- One design system shared by web and mobile: `design/tokens.json` (brand, semantic colors, category palette, light + dark) is the only place colors are defined; web reads it into CSS variables, mobile into `ThemeExtension`.
- Typography: Inter (self-hosted, no CDN) on web and mobile; `font-variant-numeric: tabular-nums` / `FontFeature.tabularFigures()` for every amount so columns align.
- Light and dark themes on both clients, following the OS setting with a manual toggle on web.
- Accessibility: text contrast ≥ 4.5:1, chart/category colors ≥ 3:1 against the surface (enforced by a test), visible focus rings, every icon-only button labelled, full keyboard navigation on web, Flutter `Semantics` on custom widgets, layouts survive 130% text scale.
- Motion: 150–200 ms ease-out transitions only where they explain a change (drawer/sheet open, month switch, list insert); disabled under `prefers-reduced-motion` / `MediaQuery.disableAnimations`.
- No layout shift: skeletons match final layout; numbers never reflow when loaded.
- Charts follow the `dataviz` skill (load it before writing chart code): direct labels over legends where possible, no 3D/pies for comparisons, consistent category colors across every view.
- Design execution uses the `impeccable` skill: direction before W1 (Task W0) and a critique/audit/polish pass at the end (Task W6). Lighthouse on the dashboard: Accessibility ≥ 95, Performance ≥ 90, Best Practices ≥ 95.

## File Map

```
design/tokens.json                      (single source of colors/radii/motion for web + mobile)
web/
  package.json vite.config.ts tsconfig*.json index.html components.json .env.example Dockerfile nginx.conf security-headers.conf
  src/styles/tokens.css  src/lib/tokens.ts  src/lib/contrast.ts  src/pages/dev/Styleguide.tsx
  src/main.tsx App.tsx index.css
  src/lib/{api.ts,schema.d.ts,money.ts,firebase.ts,auth.tsx,nav.ts,month.ts,utils.ts}
  src/components/ui/* (shadcn)  src/components/{AppShell,MonthPicker,DataTable,StatCard,StatusBadge,QueryState,CategorySelect}.tsx
  src/pages/Login.tsx
  src/pages/customer/{Dashboard,Transactions,TxnDrawer,Budgets,Recurring,Insights}.tsx
  src/pages/analyst/{Exceptions,Rules,Metrics}.tsx  src/pages/review/{Anomalies,Audit}.tsx
  src/pages/ops/TxnTrace.tsx  src/pages/admin/{Jobs,Validation,Exports,Users}.tsx
  src/**/*.test.ts(x)
mobile/
  pubspec.yaml  android/app/src/main/AndroidManifest.xml  android/app/src/main/res/xml/network_security_config.xml
  lib/{main.dart,config.dart,router.dart,theme.dart}
  lib/api/{client.dart,models.dart}  lib/auth/auth_controller.dart  lib/state/providers.dart
  lib/ui/{money.dart,month_bar.dart,async_view.dart,tokens.dart,skeleton.dart}  assets/fonts/Inter-*.ttf  assets/tokens.json (copied from design/)
  lib/screens/{login_screen,shell,home_screen,transactions_screen,txn_detail_sheet,recurring_screen,insights_screen}.dart
  test/{money_test.dart,models_test.dart}
README.md  docs/{ai-usage.md,decisions.md,provenance.md,verification.md}  prompts/
```

---

### Task W0: Visual direction and shared design tokens

**Files:**
- Create: `design/tokens.json`, `design/DESIGN.md` (direction: audience, tone, layout principles, do/don't with reasons), `web/src/lib/contrast.ts`
- Test: `web/src/lib/contrast.test.ts`

**Interfaces:**
- Produces: `design/tokens.json` with keys `brand`, `radius` (`sm 6, md 10, lg 14` px), `motion` (`fast 150, base 200` ms, `easing "cubic-bezier(0.2, 0, 0, 1)"`), `light` and `dark` objects (`bg, surface, surfaceRaised, text, muted, border, focus, success, warning, danger, info`), `category.light` and `category.dark` (one color per active EXPENSE/INCOME category code + `UNCATEGORIZED`), `status` mapping (`UNDER→success, NEAR→warning, OVER→danger, NO_BUDGET→muted, MISSED→danger, ACTIVE→success, ENDED→muted, ALERT→danger, WARN→warning, INFO→info`);
  `contrast.ts`: `luminance(hex) -> number`, `contrastRatio(a, b) -> number` (WCAG 2.x formula).

- [ ] **Step 1: Set direction** — invoke the `impeccable` skill (shape/direction mode) with this brief: "Desktop-first finance operations console for Indian households and back-office roles; calm, trustworthy, data-dense but readable; numbers are the hero; INR with Indian grouping; four roles with different jobs; light and dark." Record the chosen direction, type scale, spacing scale (4 px base), table density and component inventory in `design/DESIGN.md`. Load the `dataviz` skill and produce the category palette with its validator; put the result in `tokens.json`.
- [ ] **Step 2: Failing test** — `web/src/lib/contrast.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import tokens from "../../../design/tokens.json";
import { contrastRatio } from "./contrast";

const themes = ["light", "dark"] as const;

describe("design tokens", () => {
  it("computes WCAG contrast", () => {
    expect(contrastRatio("#000000", "#FFFFFF")).toBeCloseTo(21, 1);
    expect(contrastRatio("#777777", "#FFFFFF")).toBeCloseTo(4.48, 1);
  });
  for (const t of themes) {
    it(`${t}: text and semantic colors meet AA on surface`, () => {
      const c = tokens[t];
      for (const key of ["text", "muted", "success", "warning", "danger", "info"] as const) {
        expect(contrastRatio(c[key], c.surface), `${t}.${key}`).toBeGreaterThanOrEqual(4.5);
      }
    });
    it(`${t}: every category color is >= 3:1 on surface`, () => {
      for (const [code, hex] of Object.entries(tokens.category[t])) {
        expect(contrastRatio(hex as string, tokens[t].surface), `${t}.${code}`).toBeGreaterThanOrEqual(3);
      }
    });
  }
});
```
- [ ] **Step 3: Implement** `contrast.ts`:
```ts
const channel = (v: number) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
export function luminance(hex: string): number {
  const n = parseInt(hex.replace("#", ""), 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((x) => channel(x / 255));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
export function contrastRatio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
```
  (Run this task's test after W1 Step 1 creates `web/`; until then keep the files staged.)
- [ ] **Step 4: Run, expect PASS** — adjust token values (never the thresholds) until it passes.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(design): shared design tokens with enforced contrast and visual direction" -m "Authored-By: vbs-0"`

---

### Task W1: Web scaffold, typed API client, auth, role navigation

**Files:**
- Create: everything under `web/` listed for W1 (`package.json`, `vite.config.ts`, `src/main.tsx`, `src/App.tsx`, `src/lib/*`, `src/components/AppShell.tsx`, `src/components/QueryState.tsx`, `src/pages/Login.tsx`)
- Test: `web/src/lib/money.test.ts`, `web/src/lib/nav.test.ts`

**Interfaces:**
- Consumes: backend `POST /api/v1/auth/login`, `GET /api/v1/auth/me`, `/openapi.json`.
- Produces: `api` (openapi-fetch client with auth middleware), `formatINR(paise)`, `useAuth() -> {me, status, loginLocal(email, pw), loginGoogle(), logout()}`, `NAV: NavItem[]`, `navFor(role)`, `homeFor(role)`, `useMonth() -> [month, setMonth]`, `<QueryState query>` wrapper, `<AppShell>` layout with sidebar filtered by role and a month picker in the top bar.

- [ ] **Step 1: Scaffold**

```bash
cd /c/Users/chbha/Desktop/YottaFlex/kharcha && npm create vite@latest web -- --template react-ts
cd web && npm i @tanstack/react-query @tanstack/react-table react-router recharts firebase openapi-fetch clsx tailwind-merge lucide-react sonner @fontsource-variable/inter
npm i -D tailwindcss @tailwindcss/vite openapi-typescript vitest jsdom @testing-library/react @testing-library/jest-dom vitest-axe
npx shadcn@latest init -d
npx shadcn@latest add button card table badge dialog sheet select input tabs dropdown-menu skeleton sonner separator label textarea tooltip
```
`web/vite.config.ts`:
```ts
import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: { proxy: { "/api": "http://localhost:8000" } },
  build: { sourcemap: false, chunkSizeWarningLimit: 900 },
  test: { environment: "jsdom" },
});
```
`package.json` scripts: `"gen:api": "openapi-typescript http://localhost:8000/openapi.json -o src/lib/schema.d.ts"`, `"test": "vitest run"`, `"build": "tsc -b && vite build"`.
`web/.env.example`: `VITE_FIREBASE_API_KEY= VITE_FIREBASE_AUTH_DOMAIN= VITE_FIREBASE_PROJECT_ID= VITE_FIREBASE_APP_ID=` (one per line).

- [ ] **Step 2: Failing tests**

`web/src/lib/money.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { formatINR, pct } from "./money";

describe("formatINR", () => {
  it("uses Indian digit grouping", () => {
    expect(formatINR(12345678)).toBe("₹1,23,456.78");
    expect(formatINR(100000000)).toBe("₹10,00,000.00");
    expect(formatINR(-50000)).toBe("-₹500.00");
  });
  it("formats ratios", () => {
    expect(pct(0.8234)).toBe("82%");
    expect(pct(null)).toBe("—");
  });
});
```
`web/src/lib/nav.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { homeFor, navFor } from "./nav";

describe("navFor", () => {
  it("shows each role only its pages", () => {
    expect(navFor("CUSTOMER").map((n) => n.path)).toEqual(["/dashboard", "/transactions", "/budgets", "/recurring", "/insights"]);
    expect(navFor("REVIEWER").every((n) => n.path.startsWith("/review"))).toBe(true);
    expect(navFor("ADMIN").some((n) => n.path === "/admin/jobs")).toBe(true);
    expect(navFor("ADMIN").some((n) => n.path === "/dashboard")).toBe(false);
  });
  it("routes each role home", () => {
    expect(homeFor("ANALYST")).toBe("/analyst/exceptions");
    expect(homeFor("ADMIN")).toBe("/admin/jobs");
  });
});
```
Run `npm test` → FAIL (modules missing).

- [ ] **Step 3: Implement libs**

`web/src/lib/money.ts`:
```ts
const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", minimumFractionDigits: 2 });
export const formatINR = (paise: number) => inr.format(paise / 100);
export const pct = (r: number | null | undefined) => (r == null ? "—" : `${Math.round(r * 100)}%`);
```
`web/src/lib/nav.ts`:
```ts
export type Role = "CUSTOMER" | "ANALYST" | "REVIEWER" | "ADMIN";
export type NavItem = { path: string; label: string; roles: Role[] };
export const NAV: NavItem[] = [
  { path: "/dashboard", label: "Dashboard", roles: ["CUSTOMER"] },
  { path: "/transactions", label: "Transactions", roles: ["CUSTOMER"] },
  { path: "/budgets", label: "Budgets", roles: ["CUSTOMER"] },
  { path: "/recurring", label: "Recurring", roles: ["CUSTOMER"] },
  { path: "/insights", label: "Insights", roles: ["CUSTOMER"] },
  { path: "/analyst/exceptions", label: "Exceptions", roles: ["ANALYST", "ADMIN"] },
  { path: "/analyst/rules", label: "Rules", roles: ["ANALYST", "ADMIN"] },
  { path: "/analyst/metrics", label: "Metrics", roles: ["ANALYST", "ADMIN"] },
  { path: "/review/anomalies", label: "Anomalies", roles: ["REVIEWER", "ADMIN"] },
  { path: "/review/audit", label: "Audit trail", roles: ["REVIEWER", "ADMIN"] },
  { path: "/admin/jobs", label: "Jobs", roles: ["ADMIN"] },
  { path: "/admin/validation", label: "Validation", roles: ["ADMIN"] },
  { path: "/admin/exports", label: "Exports", roles: ["ADMIN"] },
  { path: "/admin/users", label: "Users", roles: ["ADMIN"] },
];
export const navFor = (role: Role) => NAV.filter((n) => n.roles.includes(role));
const HOME: Record<Role, string> = {
  CUSTOMER: "/dashboard", ANALYST: "/analyst/exceptions", REVIEWER: "/review/anomalies", ADMIN: "/admin/jobs",
};
export const homeFor = (role: Role) => HOME[role] ?? "/login";
```
`web/src/lib/firebase.ts`:
```ts
import { initializeApp } from "firebase/app";
import { GoogleAuthProvider, getAuth, signInWithPopup } from "firebase/auth";

const cfg = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};
export const firebaseEnabled = Boolean(cfg.apiKey && cfg.projectId);
export const fbAuth = firebaseEnabled ? getAuth(initializeApp(cfg)) : null;
export const googleSignIn = async () => {
  if (!fbAuth) throw new Error("Google sign-in is not configured");
  await signInWithPopup(fbAuth, new GoogleAuthProvider());
};
```
`web/src/lib/api.ts`:
```ts
import createClient, { type Middleware } from "openapi-fetch";
import { fbAuth } from "./firebase";
import type { paths } from "./schema";

const KEY = "kharcha.token";
export const tokenStore = {
  get: () => sessionStorage.getItem(KEY),
  set: (t: string) => sessionStorage.setItem(KEY, t),
  clear: () => sessionStorage.removeItem(KEY),
};
let onUnauthorized = () => {};
export const setUnauthorizedHandler = (fn: () => void) => { onUnauthorized = fn; };

const auth: Middleware = {
  async onRequest({ request }) {
    const local = tokenStore.get();
    const token = local ?? (fbAuth?.currentUser ? await fbAuth.currentUser.getIdToken() : null);
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    return request;
  },
  async onResponse({ response }) {
    if (response.status === 401) onUnauthorized();
    return response;
  },
};
export const api = createClient<paths>({ baseUrl: "" });
api.use(auth);

export async function unwrap<T>(p: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await p;
  if (error || data === undefined) {
    const detail = (error as { detail?: string })?.detail ?? response.statusText;
    throw new Error(`${response.status}: ${detail}`);
  }
  return data;
}
```
`web/src/lib/auth.tsx` — `AuthProvider` (React context): on mount, if `tokenStore.get()` → `GET /auth/me`; else subscribe `onIdTokenChanged(fbAuth, …)` → `GET /auth/me`; exposes `loginLocal` (POST login → `tokenStore.set` → me), `loginGoogle` (`googleSignIn` then me), `logout` (clear token, `fbAuth.signOut()`, `queryClient.clear()`); `setUnauthorizedHandler(logout)`. `RequireRole({roles, children})` redirects to `/login` or the role home.
`web/src/lib/month.ts` — `useMonth()` reads/writes `?month=` with React Router `useSearchParams`, default = latest month with data (`"2026-12"`), validated by `/^\d{4}-(0[1-9]|1[0-2])$/`.
`web/src/main.tsx` — `QueryClient` with `{queries: {staleTime: 30_000, retry: 1, refetchOnWindowFocus: false}}`, `BrowserRouter`, `AuthProvider`, `Toaster`.
`web/src/App.tsx` — routes from the File Map, each wrapped in `RequireRole` with the `NAV` roles (`/ops/transactions/:id` → ANALYST, REVIEWER, ADMIN); `/` → `homeFor(me.role)`; pages lazy-loaded with `React.lazy` + `Suspense` (code-splitting per role).
`web/src/components/AppShell.tsx` — left sidebar (`navFor(me.role)`, active link highlight, lucide icons), top bar with `MonthPicker` (prev/next buttons + select of 2026-01..2026-12), user menu (email, role badge, logout). Min width 1024px layout; sidebar collapses under 1280px.
`web/src/components/QueryState.tsx` — renders `Skeleton` while loading, an error card with "Retry" (`query.refetch()`), an empty message when data is an empty array, else children.
`web/src/pages/Login.tsx` — "Continue with Google" button (hidden when `!firebaseEnabled`) and an email/password form for demo accounts with a hint listing the 4 demo emails (no passwords). Split layout: brand panel with product one-liner and three proof points (categorize, recurring, budgets) left, form right; form errors inline under the field, submit button shows a spinner and stays the same width.

Design system wiring (from Task W0):
- `web/src/styles/tokens.css`: `:root` = `tokens.light`, `[data-theme="dark"]` and `@media (prefers-color-scheme: dark) :root:not([data-theme="light"])` = `tokens.dark`, as CSS variables (`--bg`, `--surface`, `--text`, `--muted`, `--border`, `--focus`, `--success`, …, `--radius-md`, `--motion-base`, `--ease`); a `@media (prefers-reduced-motion: reduce)` block sets `--motion-*: 0ms`. Map shadcn's variables (`--background`, `--foreground`, `--primary`, `--ring`, …) onto these so shadcn components inherit the system. Generate this file from `design/tokens.json` with `scripts/tokens.mjs` (`npm run tokens`, also run in `prebuild`) so the JSON stays the single source.
- `web/src/lib/tokens.ts`: `categoryColor(code, theme)`, `statusTone(status)` read from the JSON (used by badges and charts so a category has the same color everywhere).
- `index.css`: `@import "@fontsource-variable/inter";` `body { font-family: "Inter Variable", system-ui, sans-serif; }` `.num { font-variant-numeric: tabular-nums; }`; global `:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }`.
- Theme toggle (light / dark / system) in the user menu, persisted in `localStorage` (wrapped in `try/catch`), applied as `data-theme` on `<html>` before first paint via an inline script in `index.html` (no flash).
- `web/src/pages/dev/Styleguide.tsx` at `/styleguide` (only when `import.meta.env.DEV`): every component, badge, status, category chip, chart sample and empty/error/loading state in both themes, used for visual review and screenshots.

- [ ] **Step 4: Generate types and verify** — with the API running: `npm run gen:api && npm test && npm run build`. Expected: tests pass; build succeeds; `npm run dev` → log in as `customer@kharcha.test` lands on `/dashboard` (empty page shell).
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(web): scaffold console with typed API client, Firebase/demo auth and role navigation" -m "Authored-By: vbs-0"`

---

### Task W2: Customer pages

**Files:**
- Create: `web/src/pages/customer/{Dashboard,Transactions,TxnDrawer,Budgets,Recurring,Insights}.tsx`, `web/src/components/{DataTable,StatCard,StatusBadge,CategorySelect}.tsx`
- Test: `web/src/components/StatusBadge.test.tsx`

**Interfaces:**
- Consumes: `/me/summary`, `/me/budgets`, `/me/transactions` (+ detail, POST category), `/me/recurring`, `/me/insights`, `/categories`, `/me/accounts`.
- Produces: `<StatusBadge status>` (UNDER green, NEAR amber, OVER red, NO_BUDGET grey, ACTIVE/MISSED/ENDED, INFO/WARN/ALERT); `<DataTable columns rows onLoadMore hasMore>`; `<CategorySelect value onChange kinds?>` (active, non-UNKNOWN categories, grouped by `group`).

Page behaviour:
- **Dashboard**: 4 `StatCard`s (income, spend, savings rate, over-budget count) from `/me/summary`; horizontal bar chart (Recharts `BarChart`, budget vs actual per category, actual bar colored by status) from `/me/budgets`; top-5 categories list; latest 5 insights. Queries keyed `["summary", month]`, `["budgets", month]`.
- **Transactions**: filters (category, account, kind, search with 300 ms debounce) in the URL; `useInfiniteQuery` keyed by filters with `getNextPageParam = last.next_cursor`; table columns date, description (merchant name bold + raw descriptor muted), category badge (with "edited" dot if overridden), amount (red debit / green credit, right-aligned, tabular numbers); row click opens `TxnDrawer` (shadcn `Sheet`): descriptor, merchant, category, confidence, decision code, linked transaction, recurring series, override history, and "Change category" (`CategorySelect` + reason) → `POST` → toast → `invalidateQueries(["transactions"])`, `["budgets"]`, `["summary"]`.
- **Budgets**: table of lines (category, budget, actual, variance, ratio progress bar, status) + totals; "Unmapped budgets" callout listing submitted codes that were not in the taxonomy.
- **Recurring**: cards grouped by status (MISSED first), each with type icon, counterparty/merchant, typical amount, cadence, next expected date, and a compact event timeline (DETECTED, AMOUNT_CHANGED, MISSED, RESUMED, ENDED).
- **Insights**: list sorted ALERT → WARN → INFO with severity badge, message, and a link to the relevant page (category → Transactions filtered, series → Recurring).

- [ ] **Step 1: Failing test** — `web/src/components/StatusBadge.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("labels and colors statuses", () => {
    render(<StatusBadge status="OVER" />);
    const el = screen.getByText("Over budget");
    expect(el.className).toMatch(/red/);
  });
  it("falls back to raw text", () => {
    render(<StatusBadge status="SOMETHING" />);
    expect(screen.getByText("SOMETHING")).toBeTruthy();
  });
});
```
- [ ] **Step 2: Run, expect FAIL.**  - [ ] **Step 3: Implement components and pages.**
- [ ] **Step 4: Verify** — `npm test && npm run build`; manual run as customer: change one transaction's category and watch the Budgets actual move by that amount; scroll Transactions past 3 pages; switch months via the top bar. Take screenshots `docs/screenshots/web-dashboard.png`, `web-transactions.png`.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(web): customer dashboard, transactions with re-categorize, budgets, recurring and insights" -m "Authored-By: vbs-0"`

---

### Task W3: Analyst, reviewer and trace pages

**Files:**
- Create: `web/src/pages/analyst/{Exceptions,Rules,Metrics}.tsx`, `web/src/pages/review/{Anomalies,Audit}.tsx`, `web/src/pages/ops/TxnTrace.tsx`
- Test: `web/src/pages/analyst/transitions.test.ts`

**Interfaces:**
- Consumes: `/analyst/exceptions` (+ transition), `/analyst/rules` (+ create, versions, retire, test), `/analyst/metrics`, `/analyst/runs`, `/review/anomalies`, `/review/summary`, `/review/audit`, `/ops/transactions/{id}`.
- Produces: `allowedTransitions(status) -> Status[]` in `web/src/pages/analyst/transitions.ts` (mirror of backend `ALLOWED`, used to render only valid action buttons).

Page behaviour:
- **Exceptions**: tabs by status (OPEN, IN_REVIEW, RESOLVED, DISMISSED), type filter, infinite table (id, type, entity, user, first/last run, age); row actions = `allowedTransitions(status)` buttons; RESOLVE on a TXN exception opens a dialog with `CategorySelect` + note; 409 → toast "Changed by someone else — refreshed" and refetch. Entity link → `/ops/transactions/:id`.
- **Rules**: table of latest versions (id, v, priority, conditions summary, category, confidence, retired); "New rule" and "New version" dialogs (priority, category, merchant, regex pattern with live compile check in the browser via `new RegExp`, channel, direction, account type, confidence, note); **Rule tester** panel: descriptor + channel + amount + account type → shows normalized text, matched rule, category, confidence.
- **Metrics**: headline stat cards (category accuracy, macro-F1, transfer F1, refund recall, recurring series recall, missed precision/recall, TZ accuracy, naive overstatement vs engine error); per-category precision/recall/F1 table sorted by F1 ascending; confusion matrix heatmap (CSS grid, cell opacity ∝ count, diagonal highlighted); run selector from `/analyst/runs`.
- **Anomalies**: recall per issue type (bar chart) + table (issue type, entity, expected decision, outcome CAUGHT/MISSED, what the system did), filters by issue type and outcome; entity link to trace.
- **Audit**: infinite table of audit events (time, actor, action, entity, request id) with entity/actor filters; expandable row shows `detail` JSON.
- **TxnTrace**: header (txn, account, amount, posted UTC + IST local), timeline of enrichments per run (category, rule id/version, decision, kind, link, series), overrides, exceptions with event history, and — if present — the truth label card (reviewer/admin only) with mismatches highlighted.

- [ ] **Step 1: Failing test** — `web/src/pages/analyst/transitions.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { allowedTransitions } from "./transitions";

describe("allowedTransitions", () => {
  it("matches the backend state machine", () => {
    expect(allowedTransitions("OPEN")).toEqual(["IN_REVIEW", "RESOLVED", "DISMISSED"]);
    expect(allowedTransitions("IN_REVIEW")).toEqual(["RESOLVED", "DISMISSED", "OPEN"]);
    expect(allowedTransitions("RESOLVED")).toEqual(["OPEN"]);
  });
});
```
- [ ] **Step 2: Run, expect FAIL.**  - [ ] **Step 3: Implement.**
- [ ] **Step 4: Verify** — `npm test && npm run build`; manual: as analyst resolve an UNCATEGORIZED exception with a category and confirm the trace shows the override and the OPEN→IN_REVIEW→RESOLVED chain; create a rule and see it in the tester; as reviewer confirm no write buttons exist anywhere. Screenshots `web-exceptions.png`, `web-metrics.png`, `web-anomalies.png`.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(web): analyst exception/rule/metrics consoles, reviewer anomalies, audit and transaction trace" -m "Authored-By: vbs-0"`

---

### Task W4: Admin pages

**Files:**
- Create: `web/src/pages/admin/{Jobs,Validation,Exports,Users}.tsx`

**Interfaces:**
- Consumes: `/admin/jobs` (+ POST, detail), `/admin/validation`, `/admin/reproducibility`, `/admin/exports/{scale}` (+ files), `/admin/users` (+ PATCH).

Page behaviour:
- **Jobs**: action buttons (Generate & load starter / full, Run pipeline, Evaluate, Validate dataset / outputs, Export, Reproducibility check) with a confirm dialog for GENERATE_LOAD ("replaces all data"); jobs table polls with `refetchInterval: (q) => q.state.data?.some(j => j.status === "RUNNING" || j.status === "QUEUED") ? 2000 : false`; 409 → toast "Another dataset job is running".
- **Validation**: scope tabs; one row per check (name, PASS/FAIL/WARN badge, violations, labelled, examples expandable).
- **Exports**: scale select; manifest table (file, rows, sha256 short) with download links (`/api/v1/admin/exports/{scale}/files/{path}` using a fetch + blob so the bearer token is sent); reproducibility result card (match ✓/✗, both manifest hashes).
- **Users**: table (email, role select, linked profile input, disabled toggle) → PATCH with optimistic update and rollback on error; own row's role/disabled controls disabled.

- [ ] **Step 1: Verify by hand** (no new pure logic): run each job from the UI on the starter scale; confirm statuses move QUEUED→RUNNING→SUCCEEDED and Validation/Exports pages update. `npm run build` passes.
- [ ] **Step 2: Commit** — `git add -A && git commit -m "feat(web): admin jobs, validation, exports and user management" -m "Authored-By: vbs-0"`

---

### Task W6: UI critique, accessibility audit and polish

**Files:**
- Modify: any `web/src/**` file flagged by the audit
- Test: `web/src/a11y.test.tsx`

- [ ] **Step 1: Failing a11y test** — `web/src/a11y.test.tsx` renders `StatusBadge`, `DataTable` (3 sample rows), `MonthPicker`, `CategorySelect`, the Login form and the TxnDrawer content with mocked data inside the providers, and asserts `expect(await axe(container)).toHaveNoViolations()` (`vitest-axe`). Run → fix every violation (labels, roles, contrast, button names).
- [ ] **Step 2: Critique and polish** — invoke the `impeccable` skill in critique → audit → polish mode on the running app (`npm run dev`, every role's pages, light and dark, 1280 px and 1920 px widths). Fix, in priority order: hierarchy (one primary action per view, numbers dominant), alignment and spacing to the 4 px scale, tabular numerals everywhere amounts appear, consistent category colors across table/chart/badge, empty/error/loading states on every query, truncation with tooltip for long descriptors, keyboard flow (Tab order, Esc closes drawers/dialogs, Enter submits), focus return after a drawer closes, toasts that say what changed ("Moved ₹499.00 to Subscriptions").
- [ ] **Step 3: Measure** — `npm run build && npx vite preview --port 4173`, then `npx lighthouse http://localhost:4173/login --only-categories=performance,accessibility,best-practices --output=json --output-path=../reports/lighthouse-login.json` and the same for `/dashboard` with an authenticated session (Lighthouse `--extra-headers` is not enough for SPA auth — instead run it from Chrome DevTools on the logged-in page and save the report). Targets: Accessibility ≥ 95, Performance ≥ 90, Best Practices ≥ 95. Record scores in `docs/verification.md`.
- [ ] **Step 4: Screenshots** — light and dark of Dashboard, Transactions + drawer, Budgets, Exceptions, Metrics, Anomalies, Jobs into `docs/screenshots/` for the README.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "fix(web): accessibility and visual polish from UI audit" -m "Authored-By: vbs-0"`

---

### Task W5: Web container and compose service

**Files:**
- Create: `web/Dockerfile`, `web/nginx.conf`, `web/security-headers.conf`
- Modify: `docker-compose.yml` (add `web`)

- [ ] **Step 1: Files**

`web/Dockerfile`:
```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
ARG VITE_FIREBASE_API_KEY VITE_FIREBASE_AUTH_DOMAIN VITE_FIREBASE_PROJECT_ID VITE_FIREBASE_APP_ID
RUN npm run build

FROM nginx:1.27-alpine
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY web/security-headers.conf /etc/nginx/security-headers.conf
COPY --from=build /app/dist /usr/share/nginx/html
```
`web/security-headers.conf` (included in every location because `add_header` in a location drops server-level headers):
```nginx
add_header X-Content-Type-Options nosniff always;
add_header X-Frame-Options DENY always;
add_header Referrer-Policy strict-origin-when-cross-origin always;
```
`web/nginx.conf`:
```nginx
server {
  listen 8080;
  root /usr/share/nginx/html;
  gzip on;
  gzip_types text/css application/javascript application/json image/svg+xml;
  client_max_body_size 1m;
  location /assets/ { include /etc/nginx/security-headers.conf; add_header Cache-Control "public, max-age=31536000, immutable"; }
  location /api/ {
    proxy_pass http://api:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 120s;
  }
  location / { include /etc/nginx/security-headers.conf; add_header Cache-Control "no-cache"; try_files $uri /index.html; }
}
```
`docker-compose.yml` add:
```yaml
  web:
    build: {context: ., dockerfile: web/Dockerfile}
    depends_on: [api]
    ports: ["8080:8080"]
```
- [ ] **Step 2: Verify** — on a machine with Docker (Linux host later): `docker compose up -d --build` → `http://localhost:8080` loads, `/api/v1/categories` proxies (401 without token). On this Windows box (no Docker) verify `npm run build && npx vite preview --port 8080` instead and note it in `docs/verification.md`.
- [ ] **Step 3: Commit** — `git add -A && git commit -m "build(web): nginx image with SPA fallback, API proxy, caching and security headers" -m "Authored-By: vbs-0"`

---

### Task M1: Flutter app scaffold, API client, auth

**Files:**
- Create: `mobile/` via `flutter create`, then `mobile/lib/{main,config,router,theme}.dart`, `mobile/lib/api/{client,models}.dart`, `mobile/lib/auth/auth_controller.dart`, `mobile/lib/state/providers.dart`, `mobile/lib/ui/{money,async_view}.dart`, `mobile/lib/screens/login_screen.dart`, `mobile/android/app/src/main/res/xml/network_security_config.xml`
- Modify: `mobile/android/app/src/main/AndroidManifest.xml`, `mobile/android/app/build.gradle(.kts)` (Firebase plugin applied only when `google-services.json` exists)
- Test: `mobile/test/money_test.dart`, `mobile/test/models_test.dart`

**Interfaces:**
- Consumes: `/auth/login`, `/auth/me`, all `/me/*`, `/categories`.
- Produces: `apiBaseUrl`, `demoLoginEnabled` (dart-define); `ApiClient` (`getMe, getSummary(month), getBudgets(month), getTransactions({month, category, q, cursor, limit}), getTxn(id), setCategory(id, code, reason), getRecurring(), getInsights(month), getCategories()`); models `Me, Summary, BudgetLine, BudgetsView, Txn, TxnPage, TxnDetail, Series, Insight, CategoryItem` with `fromJson`; `formatInr(int paise)`; `AuthController` (Riverpod `AsyncNotifier<Me?>`: `signInWithGoogle()`, `signInDemo(email, password)`, `signOut()`, `token()`); `AsyncView<T>` widget (loading shimmer, error + retry, data).

- [ ] **Step 1: Create project and dependencies**

```bash
cd /c/Users/chbha/Desktop/YottaFlex/kharcha && /c/flutter/bin/flutter create --org in.kharcha --platforms android mobile
cd mobile && /c/flutter/bin/flutter pub add firebase_core firebase_auth google_sign_in:^6.2.1 flutter_riverpod dio go_router fl_chart flutter_secure_storage intl
/c/flutter/bin/flutter doctor
```
If `flutter doctor` reports a missing Android SDK, stop and tell the user (installing Android Studio/SDK is their call).

`mobile/lib/config.dart`:
```dart
const apiBaseUrl = String.fromEnvironment('API_BASE_URL', defaultValue: 'http://10.0.2.2:8000');
const demoLoginEnabled = bool.fromEnvironment('DEMO_LOGIN', defaultValue: true);
```
`network_security_config.xml` allows cleartext only for `10.0.2.2` and `localhost` (debug/demo); manifest sets `android:networkSecurityConfig="@xml/network_security_config"` and `INTERNET` permission.

- [ ] **Step 2: Failing tests**

`mobile/test/money_test.dart`:
```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:kharcha/ui/money.dart';

void main() {
  test('Indian grouping', () {
    expect(formatInr(12345678), '₹1,23,456.78');
    expect(formatInr(-50000), '-₹500.00');
  });
}
```
`mobile/test/models_test.dart`:
```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:kharcha/api/models.dart';

void main() {
  test('TxnPage parses items and cursor', () {
    final p = TxnPage.fromJson({
      'items': [
        {'txn_id': 'TXN-2026-00000001', 'local_date': '2026-03-01', 'posted_at': '2026-02-28T18:45:00Z',
         'account_id': 'ACC-USR-000001-01', 'amount_paise': -49900, 'channel': 'UPI',
         'descriptor': 'UPI/DR/1/NETFLIX/x', 'merchant_id': 'MER-0051', 'merchant_name': 'Netflix',
         'category_code': 'SUBSCRIPTIONS', 'kind': 'EXPENSE', 'confidence': 0.95, 'decision': 'RULE',
         'overridden': false}
      ],
      'next_cursor': 'abc'
    });
    expect(p.items.single.amountPaise, -49900);
    expect(p.items.single.isDebit, true);
    expect(p.nextCursor, 'abc');
  });
}
```
Run `/c/flutter/bin/flutter test` → FAIL.

- [ ] **Step 3: Implement**

`mobile/lib/ui/money.dart`:
```dart
import 'package:intl/intl.dart';

final _inr = NumberFormat.currency(locale: 'en_IN', symbol: '₹', decimalDigits: 2);
String formatInr(int paise) => _inr.format(paise / 100);
```
`mobile/lib/api/client.dart`:
```dart
import 'package:dio/dio.dart';
import '../config.dart';
import 'models.dart';

typedef TokenProvider = Future<String?> Function();

class ApiClient {
  ApiClient(this._token, {void Function()? onUnauthorized})
      : dio = Dio(BaseOptions(
          baseUrl: '$apiBaseUrl/api/v1',
          connectTimeout: const Duration(seconds: 10),
          receiveTimeout: const Duration(seconds: 20),
        )) {
    dio.interceptors.add(InterceptorsWrapper(
      onRequest: (o, h) async {
        final t = await _token();
        if (t != null) o.headers['Authorization'] = 'Bearer $t';
        h.next(o);
      },
      onError: (e, h) {
        if (e.response?.statusCode == 401) onUnauthorized?.call();
        h.next(e);
      },
    ));
  }

  final TokenProvider _token;
  final Dio dio;

  Future<TxnPage> getTransactions({String? month, String? category, String? q, String? cursor, int limit = 30}) async {
    final r = await dio.get('/me/transactions', queryParameters: {
      if (month != null) 'month': month, if (category != null) 'category': category,
      if (q != null && q.isNotEmpty) 'q': q, if (cursor != null) 'cursor': cursor, 'limit': limit,
    });
    return TxnPage.fromJson(r.data as Map<String, dynamic>);
  }
  // getMe, getSummary, getBudgets, getTxn, setCategory, getRecurring, getInsights, getCategories follow the same shape
}
```
Implement the remaining methods explicitly (one `dio.get`/`dio.post` each, mapping to the models). `AuthController`: on build, try `Firebase.initializeApp()` inside `try/catch` (absent `google-services.json` → Firebase disabled, Google button hidden); restore a stored demo token from `FlutterSecureStorage`; `signInWithGoogle` = `GoogleSignIn().signIn()` → `GoogleAuthProvider.credential(idToken, accessToken)` → `FirebaseAuth.instance.signInWithCredential` → `getMe()`; `token()` returns the demo token or `FirebaseAuth.instance.currentUser?.getIdToken()` (SDK refreshes automatically); a non-CUSTOMER role shows "This app is for customers — use the web console" and signs out. `router.dart`: go_router with `redirect` to `/login` when signed out; shell route with bottom `NavigationBar` (Home, Transactions, Recurring, Insights). `theme.dart`: Material 3 light + dark built from `assets/tokens.json` (copied from `design/tokens.json` by a `tool/sync_tokens.dart` script; never hand-edited): `ColorScheme.fromSeed(seedColor: brand)` with `surface`/`error`/semantic colors overridden from the tokens, a `KharchaColors` `ThemeExtension` exposing `success, warning, danger, info, muted, categoryColor(code)`, Inter bundled under `assets/fonts/` (no runtime download), `TextTheme` with `FontFeature.tabularFigures()` on the numeric styles, `ThemeMode.system`.

- [ ] **Step 4: Run tests, expect PASS** — `/c/flutter/bin/flutter test && /c/flutter/bin/flutter analyze`.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(mobile): Flutter app scaffold with Firebase Google sign-in, demo login and typed API client" -m "Authored-By: vbs-0"`

---

### Task M2: Home, transactions, recurring, insights screens

**Files:**
- Create: `mobile/lib/screens/{shell,home_screen,transactions_screen,txn_detail_sheet,recurring_screen,insights_screen}.dart`, `mobile/lib/ui/month_bar.dart`
- Modify: `mobile/lib/state/providers.dart`

**Interfaces:**
- Produces providers: `monthProvider` (`StateProvider<String>`, default `'2026-12'`), `summaryProvider` / `budgetsProvider` / `insightsProvider` (`FutureProvider.family<…, String>`), `recurringProvider`, `categoriesProvider` (keepAlive), `txnListProvider` (`AsyncNotifier` holding items + cursor + filters with `loadMore()` and `refresh()`).

Screen behaviour (smoothness rules: `const` widgets where possible, `ListView.builder`, no work in `build`, images none, providers cached per month so switching back is instant):
- **Home**: `MonthBar` (◀ month ▶), summary card (income, spend, savings rate), budget list with `LinearProgressIndicator` colored by status and "₹x of ₹y", top insight banner; pull-to-refresh invalidates the month's providers.
- **Transactions**: search field (300 ms debounce), category filter chip opening a bottom sheet, infinite list (`loadMore` when within 5 items of the end), sticky date headers, amount colored by sign; tap → `TxnDetailSheet` (descriptor, merchant, category, confidence, decision, "Change category" dropdown → `setCategory` → snackbar → invalidate budgets/summary and patch the item in place).
- **Recurring**: sections MISSED / ACTIVE / ENDED with amount, cadence, next expected date.
- **Insights**: cards by severity with icon and color.

Feel and polish (part of done, not optional):
- Skeleton placeholders (`lib/ui/skeleton.dart`, a single shimmer `AnimationController` shared via `InheritedWidget`) shaped like the final rows/cards; no spinners on full screens.
- Month switch uses `AnimatedSwitcher` (200 ms fade + 8 px slide) on the content; budget bars animate width with `TweenAnimationBuilder`; all durations read from tokens and drop to zero when `MediaQuery.disableAnimationsOf(context)` is true.
- Transaction row → detail uses a `Hero` on the amount; category change gives `HapticFeedback.selectionClick()` and a snackbar naming the move ("₹499.00 moved to Subscriptions") with Undo (re-posts the previous category).
- Empty states with an icon and one-line guidance; offline/error state with Retry; pull-to-refresh on every list.
- Accessibility: `Semantics(label: …)` on amount/status widgets ("Debit ₹499.00, Subscriptions, 5 March"), tap targets ≥ 48 dp, verified at 130% text scale (no overflow stripes) in light and dark.
- Widget test `mobile/test/home_golden_test.dart`: pump `HomeScreen` with a fake `ApiClient` (override providers) in light and dark at 130% text scale and assert no overflow (`tester.takeException()` is null) and that the budget row exposes its semantics label.

- [ ] **Step 1: Implement screens.**
- [ ] **Step 2: Verify on emulator** — `cd mobile && /c/flutter/bin/flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000` (backend on host port 8000): demo login as `customer@kharcha.test`, scroll 100+ transactions without jank (`flutter run --profile` → DevTools frame chart has no red frames during scroll), change a category and see the Home budget bar update, switch months back and forth instantly. Save screenshots to `docs/screenshots/mobile-*.png`.
- [ ] **Step 3: Commit** — `git add -A && git commit -m "feat(mobile): home budgets, infinite transactions with re-categorize, recurring and insights" -m "Authored-By: vbs-0"`

---

### Task M3: Release APK and Firebase setup notes

**Files:**
- Create: `mobile/README.md`

- [ ] **Step 1: Build** — `/c/flutter/bin/flutter build apk --release --dart-define=API_BASE_URL=http://10.0.2.2:8000` (debug signing config for the demo; note in README that a real release needs an upload keystore kept out of git). Record APK size.
- [ ] **Step 2: Document Firebase setup** in `mobile/README.md`: create a Firebase project → add Android app `in.kharcha.kharcha` → add the debug SHA-1 (`cd android && ./gradlew signingReport`) → enable Google provider → download `google-services.json` into `android/app/` (git-ignored) → set backend `FIREBASE_PROJECT_ID` → first Google login becomes a CUSTOMER linked to a synthetic profile; admins listed in `ADMIN_EMAILS`.
- [ ] **Step 3: Commit** — `git add -A && git commit -m "docs(mobile): release build and Firebase configuration guide" -m "Authored-By: vbs-0"`

---

### Task D1: Submission documentation and prompt history

**Files:**
- Create/Modify: `README.md`, `docs/ai-usage.md`, `docs/decisions.md` (append), `docs/provenance.md` (from B20), `docs/verification.md`, `prompts/README.md`, `prompts/claude-code-session.md`

- [ ] **Step 1: README.md** with sections, in this order: one-paragraph problem statement and what Kharcha does; architecture diagram (from spec §3) and component list; quick start on Windows (native Postgres) and on Linux (Docker Compose) with exact commands: create DB → `uv sync` → `alembic upgrade head` → `python -m app.cli all --scale starter` → `uvicorn` → `npm run dev` → `flutter run`; demo accounts (emails only; password from your `.env`); generator command, seed `20261022`, scales, output layout, how to regenerate full data and verify checksums against `reports/full/manifest.json`; data model summary + link to `docs/data_dictionary.md`; business rules summary (link to spec §6); edge cases table (spec §7.5) with the measured outcome per issue type from `reports/full/metrics.md`; evaluation results (headline table: engine vs naive baseline); validation summary (link `reports/*/validation_*.md`); reproducibility result; performance numbers; assumptions; limitations; requirement traceability (link spec §1); AI usage summary (link `docs/ai-usage.md`); next steps (Linux deployment runbook, TLS, backups, ML categorizer experiment).
- [ ] **Step 2: docs/ai-usage.md** — tools used (Claude Code in the desktop app; list any other tool actually used), where AI accelerated (scaffolding, catalogue data, test authoring, docs), where it was relied on heavily, and what was personally reviewed/changed/validated (rules thresholds, edge-case semantics, metric definitions, every failing threshold investigation in `docs/decisions.md`). Written in the owner's voice; only facts that are true.
- [ ] **Step 3: docs/verification.md** — the exact commands run and their outputs (pytest summary lines for backend/web/mobile, `cli all` timings, repro match, validation pass counts, manual UI checks with screenshots).
- [ ] **Step 4: Prompt history** — export this Claude Code session transcript to `prompts/claude-code-session.md` (desktop app export, or `mcp__ccd_session_mgmt__export_transcript`), redact nothing but secrets (there should be none), and list every AI tool + session in `prompts/README.md` with dates; if a tool cannot export, say so there (FAQ #6).
- [ ] **Step 5: Final checks** — `git status` clean except intended files; `grep -rIl "PRIVATE KEY\|JWT_SECRET=.\{8,\}\|AIza" --exclude-dir=node_modules .` returns nothing outside `.env.example`; `uv run pytest -q`, `npm test`, `flutter test` all pass.
- [ ] **Step 6: Commit** — `git add -A && git commit -m "docs: README, AI usage disclosure, verification log and prompt history" -m "Authored-By: vbs-0"`

### Task D2: Publish (only with the user's explicit go-ahead)

- [ ] **Step 1:** Ask the user for the repository name and explicit permission to create a **new public** GitHub repository and push (their global rules allow pushing only to the emplinx repos unless they say otherwise in that message).
- [ ] **Step 2 (after "yes"):** `gh repo create vbs-0/<name> --public --source . --remote origin --push`; verify the repo page renders the README and that `data/full/` and secrets are absent.
- [ ] **Step 3:** Keep the repo editable until the deadline (Sat 7 Nov 2026 12:36 UTC); the user submits the URL themselves on the YottaFlex portal.

---

## Self-review

- Execution order: W0 → W1 → W2 → W3 → W4 → W6 → W5 → M1 → M2 → M3 → D1 → D2 (polish W6 before containerizing so the image ships the polished build).
- UI quality bar → W0 (tokens, direction, contrast test), W1 (theme, font, focus, styleguide), W2/W3 (states, consistent colors), W6 (axe, impeccable audit, Lighthouse, screenshots), M1/M2 (shared tokens, motion, semantics, text-scale test).
- Spec §2 features: customer (W2, M2), analyst (W3), reviewer (W3), admin (W4) — covered. §10 Firebase + demo login (W1, M1, M3). §12 performance (keyset infinite lists, query caching, code-splitting, nginx caching) — W1/W2/W5/M2.
- Submission requirements (README, run steps, prompt history, AI disclosure, verification, lawful provenance, public repo) — D1, D2.
- Names consistent with backend plan routes: `/api/v1/auth/*`, `/me/*`, `/analyst/*`, `/review/*`, `/ops/transactions/{id}`, `/admin/*`, `/categories`.
