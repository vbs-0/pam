# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Household customer (primary).** Someone in India checking where their money went this month: UPI payments,
  card spends, rent, EMIs, subscriptions, budgets against actual spend, and bills that are due or were missed.
  Either a real person who signed in with Google and enters their own accounts and transactions, or a reviewer
  opening one of the synthetic sample households (read-only).
- **Analyst.** Works the exception queue (uncategorized, unmatched transfers, orphan refunds, unmapped budgets,
  missed recurring payments), manages versioned categorization rules, reads run metrics.
- **Reviewer.** Read-only: checks which labelled anomalies the engine caught, recall per issue type, the audit log,
  and a transaction's full decision trace including ground truth.
- **Admin.** Runs dataset and pipeline jobs, reads validation and reproducibility results, downloads exports,
  manages logins.

## Product Purpose

PAM (Payment Account Manager) categorizes household transactions, maps recurring payments, and compares spending
against monthly budgets, so a household sees true spend (transfers between own accounts, refunds and reversals do not
inflate it) and what needs attention. Built for the YottaFlex Round 2 72-hour challenge (deadline 2026-11-07 12:36
UTC); success is a correct, explainable engine with evidence (validation, evaluation, reproducibility) and a
console people can actually use.

## Positioning

Spend numbers are honest: self-transfers, credit-card bill payments, refunds and reversals are paired and excluded,
so totals match reality where a naive ledger overstates spend by about 112% on the challenge data. Every decision is
traceable to a rule version, link or override.

## Operating Context

- Indian context: INR shown as ₹ with Indian digit grouping (₹1,23,456.78), IST business dates, UPI/IMPS/NEFT/NACH/
  BBPS/card channels, bank narrations like `UPI/DR/612345678901/SWIGGY/...`.
- Money is integer paise end to end. Months are `YYYY-MM`.
- API: FastAPI at `https://pam.is-cool.dev/api/v1` (OpenAPI at `/openapi.json`), JWT bearer tokens; roles come from
  the database. Errors are RFC 9457 problem+json with a request id.
- Desktop-first; customers also use the Flutter Android app, so the web console must also work at phone width.

## Capabilities and Constraints

- Customer: summary, transactions (filters, search, keyset "load more"), transaction detail with override history,
  recategorize, budgets vs actual, recurring payments with event history, insights; real households can add/edit/
  delete accounts, transactions (optional fields, duplicate warning), budgets and profile. Sample households are
  read-only except recategorizing.
- Analyst: exception queue with lifecycle transitions, rules (create, version, retire, dry-run tester), metrics,
  pipeline runs, transaction trace.
- Reviewer: anomaly outcomes, recall summary, audit log, trace with truth.
- Admin: overview, background jobs with status polling, validation results, reproducibility, exports, users.
- Google sign-in needs a Firebase project id (not configured yet); email + password login works today.
- Languages: English only. Light and dark themes following the OS with a manual toggle.

## Brand Commitments

None. Name is PAM (Payment Account Manager); no logo, palette or fonts exist.

## Evidence on Hand

Synthetic dataset (seed 20261022), evaluation and validation reports in `reports/`, edge-case catalogue in
`docs/edge-cases.md`. No real customers, testimonials or usage numbers exist; never fabricate them.

## Product Principles

1. True spend first: never show a number that double-counts transfers or treats refunds as spending.
2. Explain every decision: category, rule, link and override are one click away.
3. Attention over decoration: surface what is over budget, missed or uncategorized before anything else.
4. Honest data states: loading, empty, read-only sample, queued processing and errors are all explicit.

## Accessibility & Inclusion

WCAG 2.2 AA: text contrast ≥ 4.5:1, chart colours ≥ 3:1, visible focus, full keyboard navigation, reduced motion
respected, amounts in tabular figures.
