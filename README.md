# PAM: Payment Account Manager

PAM turns a household's bank and UPI transactions into answers to three questions: **what did we really spend, what repeats, and are we inside budget?** It categorizes every transaction, maps recurring payments (salary, rent, EMIs, subscriptions, bills), and compares spending with monthly budgets. Everything it decides is traceable to a rule, a version and a confidence, and every exception goes to a human queue.

Indian context throughout: UPI/IMPS/NEFT/card channels, amounts in integer **paise**, business dates in **IST**, UTC storage.

**Live:** https://pam.is-cool.dev (web console) · https://pam.is-cool.dev/docs (API) · [Android APK](https://pam.is-cool.dev/downloads/pam.apk)
Sign in as `usr-000001@pam.is-cool.dev` / `password123` for a read-only sample household, or create an account to get your own empty household and enter real data.

## What is in the repo

| Path | What |
|---|---|
| `backend/` | FastAPI + Postgres. Data generator, decision engine, jobs, REST API, Alembic migrations, 190+ tests |
| `web/` | React 19 + Vite + Tailwind console for all four roles (customer, analyst, reviewer, admin), light and dark |
| `mobile/` | Small Flutter Android app for customers (folio, entries, recurring, books) |
| `data/starter/` | The starter dataset: 50 households, 25,000 transactions (committed) |
| `reports/` | Validation, evaluation and reproducibility reports for starter and full scale |
| `docs/` | Data dictionary, edge-case register, infrastructure and deploy notes, AI disclosure, prompt history |
| `deploy/` | systemd unit, nginx site, deploy script |

The full dataset (1,000 households, 500,000 transactions, seed `20261022`, ~500 MB) is not committed. `python -m app.cli generate --scale full` recreates it byte for byte; its manifest and reports are in `reports/full/`.

## Run it

Needs Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 20+, Postgres 14+. Flutter is only for the mobile app.

```bash
cd backend
cp .env.example .env            # set DATABASE_URL, JWT_SECRET, DEMO_PASSWORD
uv sync
uv run alembic upgrade head
uv run python -m app.cli all --scale starter     # generate, validate, load, run engine, evaluate, validate outputs
uv run uvicorn app.main:app --port 8000          # API on :8000, docs at /docs
cd ../web && npm install && VITE_API_TARGET=http://localhost:8000 npm run dev
```

Verify key behaviour:

```bash
cd backend && uv run pytest -q                    # 193 tests
uv run python -m app.cli repro --scale starter    # two fresh generations must have identical checksums
cat ../reports/starter/evaluation.md              # metrics against acceptance targets
```

Mobile: `cd mobile && flutter build apk --release` (set `--dart-define=API_BASE=...` to point at another server). Release signing reads a git-ignored `android/key.properties`; without it the build falls back to the debug key.

## How it works

1. **Generate.** A seeded generator (`seed 20261022`) writes master data first (categories, merchants, users, accounts), then dependent records with valid parent ids, then ground-truth labels derived from the same rules rather than random draws.
2. **Decide.** The engine runs in a fixed order: categorize (rules, versioned, with confidence) → apply human overrides → link refunds to original purchases → match transfers between a household's own accounts → detect recurring series and missed payments → budgets, insights and exceptions. Ids are stable (`REC-`, `EXC-`), so a re-run does not duplicate or lose history.
3. **Expose.** Customers see true spend (transfers, contra and reversed rows struck out of the total), budget versus actual, recurring payments and margin notes. Analysts work the exception queue, edit and test rules, and see engine metrics. Reviewers see anomalies and the audit log. Admins run jobs, validation, reproducibility checks, exports and user management.
4. **Persist history.** Overrides, rule versions, exception transitions, account events and audit entries are appended, never overwritten.

## Results

| Metric (full scale, 500,000 txns) | Result | Target |
|---|---|---|
| Category accuracy | 97.99% | ≥ 85% |
| Transfer F1 | 1.000 | ≥ 0.95 |
| Refund link recall | 0.909 | ≥ 0.90 |
| Timezone-boundary month accuracy | 1.000 | = 1.0 |
| Budget/category mismatch handling | 1.000 | = 1.0 |
| Recurring series recall | 0.9995 | ≥ 0.85 |
| Missed-payment precision / recall | 0.96 / 1.00 | ≥ 0.80 |
| Decoy false-alarm rate | 0.000 | ≤ 0.10 |

Per-issue recall: transfer double-count 400/400, TZ boundary 400/400, budget mismatch 200/200, recurring skip 120/120, recurring-not-skip 240/240, refund-as-expense 465/500. Full tables: `reports/full/evaluation.md`. Evaluation excludes real (user-entered) households, which have no ground truth.

## Decisions and trade-offs

- **Paise as integers, IST business dates, UTC storage.** No floats near money; a 23:50 IST payment lands in the right month (the TZ-boundary cases exist to prove it).
- **Rules over a model.** Rules are explainable, versioned and testable by an analyst before release. The cost is coverage: 99.26% of transactions get a category, the rest go to the exception queue instead of a guess.
- **Postgres + in-process jobs.** One 1 GB server, so no Redis or queue. Jobs run in threads, a single-flight advisory lock stops overlapping runs, orphaned jobs are marked failed on restart. Job size is capped (`MAX_JOB_TRANSACTIONS`).
- **Real users are first class.** New sign-ups get their own empty household. Entries they add are categorized instantly by re-running the engine for that household only. Sample households are read-only.
- **Roles are read from the database on every request**, so a demoted admin loses access immediately; tokens only carry identity.

## Edge cases

[`docs/edge-cases.md`](docs/edge-cases.md) lists over 60 scenarios with the expected handling, where it lives, the test that covers it and its status (A = analysis/engine, U = UI, M = mobile). Highlights: refund after the budget month, own-account transfers matched by amount and window, duplicate entries flagged but kept, a skipped salary month versus a month that simply had no salary, login lockout, Google first-sign-in never inheriting someone else's household, path traversal on exports, and a failed run leaving no partial outputs.

## Limitations (honest list)

- **Google sign-in needs a Firebase project.** It is on in the live deployment (web popup and the app's native picker). A fresh install needs `FIREBASE_PROJECT_ID` on the server, the `VITE_FIREBASE_*` values for the web build (`web/.env.example`) and, for the app, a git-ignored `google-services.json` with the release SHA-1 registered. Without them the button is hidden and email sign-in still works.
- **Email is for password reset only.** Sign-up does not verify the address, and no mail is sent on registration. Outbound mail uses any SMTP relay (`SMTP_*` settings); the host's cloud blocks port 25, so a relay on port 587 is required.
- **Refund recall is just over target (0.909 vs 0.90).** Missed links are mostly refunds that arrive after a long gap with a changed descriptor; they surface as exceptions rather than being linked wrongly.
- **Single node.** Fine for the challenge load; a worker queue would be the next step for larger runs.
- The mobile app is a thin customer client: no budgets editor, no staff screens.
- Visual design was checked at desktop and phone widths through DOM and layout checks and the live site; there is no automated visual-regression suite.

## AI use

See [`docs/ai/AI-DISCLOSURE.md`](docs/ai/AI-DISCLOSURE.md) and [`docs/ai/prompt-history.md`](docs/ai/prompt-history.md).
