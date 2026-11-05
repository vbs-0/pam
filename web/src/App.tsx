import { lazy, Suspense, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import Shell, { homeFor } from "./components/Shell";
import { Splash, TopBar } from "./components/ui";
import { useAuth } from "./lib/auth";
import type { Role } from "./lib/types";
import Login from "./pages/Login";
import { Forgot, Reset } from "./pages/Recover";
import Folio from "./pages/customer/Folio";

const Entries = lazy(() => import("./pages/customer/Entries"));
const Budgets = lazy(() => import("./pages/customer/Budgets"));
const Recurring = lazy(() => import("./pages/customer/Recurring"));
const Insights = lazy(() => import("./pages/customer/Insights"));
const Books = lazy(() => import("./pages/customer/Books"));
const Exceptions = lazy(() => import("./pages/staff/Exceptions"));
const Rules = lazy(() => import("./pages/staff/Rules"));
const Metrics = lazy(() => import("./pages/staff/Metrics"));
const Anomalies = lazy(() => import("./pages/staff/Review").then((m) => ({ default: m.Anomalies })));
const AuditLog = lazy(() => import("./pages/staff/Review").then((m) => ({ default: m.AuditLog })));
const Trace = lazy(() => import("./pages/staff/Review").then((m) => ({ default: m.Trace })));
const AdminOverview = lazy(() => import("./pages/admin/Admin").then((m) => ({ default: m.AdminOverview })));
const Jobs = lazy(() => import("./pages/admin/Admin").then((m) => ({ default: m.Jobs })));
const Users = lazy(() => import("./pages/admin/Admin").then((m) => ({ default: m.Users })));
const Exports = lazy(() => import("./pages/admin/Admin").then((m) => ({ default: m.Exports })));
const Households = lazy(() => import("./pages/admin/Admin").then((m) => ({ default: m.Households })));

function Guard({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { me } = useAuth();
  if (!me) return <Navigate to="/login" replace />;
  if (!roles.includes(me.role)) return <Navigate to={homeFor(me.role)} replace />;
  return <>{children}</>;
}
/** Customer pages: customers always, admins in the support view (they pick a household first). */
const customer = (el: ReactNode) => <Guard roles={["CUSTOMER", "ADMIN"]}>{el}</Guard>;
const staff = (roles: Role[], el: ReactNode) => <Guard roles={roles}>{el}</Guard>;

function Gate() {
  const { me, loading } = useAuth();
  if (loading) return <Splash />;
  if (!me) return <Navigate to="/login" replace />;
  return <Shell />;
}

export default function App() {
  return (
    <BrowserRouter>
      <TopBar />
      <Suspense fallback={<Splash />}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/forgot" element={<Forgot />} />
          <Route path="/reset" element={<Reset />} />
          <Route element={<Gate />}>
            <Route path="/" element={<Home />} />
            <Route path="/entries" element={customer(<Entries />)} />
            <Route path="/budgets" element={customer(<Budgets />)} />
            <Route path="/recurring" element={customer(<Recurring />)} />
            <Route path="/insights" element={customer(<Insights />)} />
            <Route path="/books" element={customer(<Books />)} />
            <Route path="/exceptions" element={staff(["ANALYST", "ADMIN"], <Exceptions />)} />
            <Route path="/rules" element={staff(["ANALYST", "ADMIN"], <Rules />)} />
            <Route path="/metrics" element={staff(["ANALYST", "ADMIN"], <Metrics />)} />
            <Route path="/trace" element={staff(["ANALYST", "REVIEWER", "ADMIN"], <Trace />)} />
            <Route path="/anomalies" element={staff(["REVIEWER", "ADMIN"], <Anomalies />)} />
            <Route path="/audit" element={staff(["REVIEWER", "ADMIN"], <AuditLog />)} />
            <Route path="/admin" element={staff(["ADMIN"], <AdminOverview />)} />
            <Route path="/admin/jobs" element={staff(["ADMIN"], <Jobs />)} />
            <Route path="/admin/users" element={staff(["ADMIN"], <Users />)} />
            <Route path="/admin/exports" element={staff(["ADMIN"], <Exports />)} />
            <Route path="/admin/households" element={staff(["ADMIN"], <Households />)} />
          </Route>
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}

/** "/" is the folio for customers and for admins who opened a household; everyone else goes to their own home. */
function Home() {
  const { me } = useAuth();
  if (!me) return null;
  if (me.role === "CUSTOMER" || (me.role === "ADMIN" && sessionStorage.getItem("pam.household"))) return <Folio />;
  return <Navigate to={homeFor(me.role)} replace />;
}

function NotFound() {
  return (
    <div className="min-h-screen grid place-items-center p-6 text-center">
      <div><p className="stamp text-red">404</p><h1 className="text-2xl font-semibold mt-3">That page is not in the register</h1><a className="btn mt-5 no-underline" href="/">Back to the folio</a></div>
    </div>
  );
}
