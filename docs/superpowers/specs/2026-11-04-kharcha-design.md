# Kharcha — Household Spend Intelligence: Design Spec

Date: 2026-11-04 · Status: approved in chat, pending written review · Owner: vbs-0

Kharcha categorizes bank transactions, maps recurring payments, and compares household
spending against budgets for Indian (INR / UPI) households. It ships as one FastAPI backend,
a desktop web console (4 roles) and a customer Android app, all reading one Postgres database.
All data is synthetic, generated with a fixed seed and labelled ground truth.

---

## 1. Requirement traceability (Problem Statement → design → plan task)

| # | Problem statement requirement | Design element | Plan task |
|---|---|---|---|
| R1 | Categorize transactions | Rule engine §6.2 (merchant → regex → channel → fallback), versioned rules | B10, B13 |
| R2 | Map recurring payments | Recurring detector §6.5, stable `REC-` ids, event history | B12, B15 |
| R3 | Compare household spending vs budgets | Budget resolution + budget-vs-actual §6.6 | B13, B17 |
| R4 | Expose key decisions and exceptions | `txn_enrichment.decision`, exception queue §6.8, trace endpoint | B13, B15, B18 |
| R5 | Preserve traceability | rule id+version per decision, run ids, append-only overrides/events, audit log | B3, B15–B19 |
| R6 | Measurable outputs | Evaluation metrics §8 incl. naive baseline, stored per run | B14, B15 |
| R7 | Actors: customer, analyst, risk reviewer, admin | 4 roles, web console per role, Android for customer §10 | B16–B19, W*, M* |
| R8 | Master data first, then dependent records with valid parent ids | Generator order §7.2 | B5, B6 |
| R9 | Profiles+accounts, signed ledger with merchant descriptors, taxonomy+rules, monthly budgets, salary/rent/subscription series, insights from aggregations | §7, §6.7 | B4–B7, B13 |
| R10 | State changes as records/events, no overwriting | §5.3 lifecycle tables | B3, B15 |
| R11 | Outcomes and labels from documented rules | §7.4 truth = generator intent; §7.5 anomaly rules | B6, B7 |
| R12 | Entities UserProfile, Account, Merchant, Transaction, Category, CategoryRule, Budget, RecurringSeries, Insight with PK/FK, cardinality, optional, effective dates, lifecycle | §5 | B3 |
| R13 | Bridge tables for N:M, event history, validate joins | `account_holder`, `merchant_category`; FK checks §9 | B3, B9 |
| R14 | Anomaly cases keep issue_type/ground_truth label | `gt.anomaly` §7.5 | B7 |
| R15 | ID conventions `USR-000001`, `ACC-<user-id>-01`, `TXN-2026-00000001`, `BUD-<user-id>-2026-01-<cat>`, `REC-000001` | `app/ids.py` §5.1 | B2 |
| R16 | Data dictionary (type, required, allowed, units, uniqueness, validation) | Generated from `app/schema.py` column metadata | B3 |
| R17 | 1,000 profiles, 500,000 txns, 12 months; aliases, refunds, transfers, recurring bills, seasonal, ambiguous; truth category labels | §7.3 | B5–B7 |
| R18 | Fixed seed 20261022; same generator for starter and full | `--scale starter|full`, cross-version-stable RNG §7.1 | B5, B8 |
| R19 | Valid baseline first, then inject labelled edge cases (5 listed) | §7.5 | B7 |
| R20 | Derived values computed from source records | balances, CC payments, interest, statuses §7.2 | B6, B13 |
| R21 | Separate ground_truth files, never leaked into inputs | `ground_truth/` dir, `gt` schema, import-boundary test | B6, B8, B13 |
| R22 | Validation: PK uniqueness, FK integrity, enums, date ordering, arithmetic reconciliation, lifecycle transitions, duplicates | §9 | B9, B15 |
| R23 | Export CSV/JSON/SQL seed + README, data dictionary, generator command, seed, source manifest, validation summary | §11 | B8, B20, D1 |
| R24 | Regenerate twice, compare row counts/checksums | `repro` command §11 | B8 |
| R25 | Acceptance: ledger totals reconcile; categorization metrics calculable; transfers/refunds consistent; recurring detection has labelled evaluation examples | §9 checks 6, §8, §6.3–6.4, `gt.recurring_truth` + decoys | B9, B14 |
| R26 | Lawful provenance | 100% synthetic; brand names used nominatively; `docs/provenance.md` §11 | D1 |
| R27 | Submission: public repo, README, run steps, prompt history, AI disclosure | §12 | D1 |

---

## 2. Actors and features

| Actor | Client | Features |
|---|---|---|
| Customer / account holder | Web + Android | Dashboard (income, spend, savings rate, budget bars), transactions (filter, search, detail, re-categorize), budgets vs actual, recurring payments, insights |
| Operations analyst | Web | Exception queue with state transitions, rule manager (versioned, tester), categorization/recurring metrics, transaction trace |
| Risk/compliance reviewer | Web (read-only) | Anomaly outcomes vs ground truth, audit trail, transaction trace incl. truth label |
| System administrator | Web + CLI | Generate/load dataset, run pipeline/evaluate/validate jobs, reproducibility check, exports, user/role admin |

---

## 3. Architecture

```
 Web (React)  ──┐                                ┌──▶ PostgreSQL (public + gt schemas)
 Android ───────┼─ Google Sign-In ─▶ Firebase ─▶ ID token
 (Flutter)      │                                │
                └── Bearer token ──▶ FastAPI ────┤ verify (Firebase RS256 | local HS256) → app_user → role
                                      │          │
                     routers → services/jobs → engine (pure) / datagen (pure) → COPY in/out
```

* **One backend process type** (uvicorn workers). Long jobs run as background tasks; job state lives in the
  `job` table; a Postgres advisory lock guarantees one pipeline/load at a time across workers.
* **Pure core.** `app/engine` (decisions) and `app/datagen` (synthetic data) have no DB or HTTP code; they take
  and return plain dataclasses. The same functions run in jobs, API handlers, CLI and tests.
* **Single schema source.** `app/schema.py` (SQLAlchemy Core) holds every table with column metadata
  (description, allowed values, unit, validation). Alembic migration, SQL seed DDL, CSV column order,
  enum validation and `docs/data_dictionary.md` are all derived from it.
* **Ground-truth isolation.** Truth lives in `ground_truth/` files and the `gt` schema. `app/engine` must not
  import `gt` tables (enforced by a test). Only evaluation code and reviewer/admin endpoints read `gt`.

Layers: `api` (HTTP, auth deps, pydantic schemas) → `services`/`jobs` (use cases, transactions) →
`engine`/`datagen` (pure) → `repo` (SQL + COPY). Core: `config`, `db`, `security`, `ids`, `timeutil`, `money`.

---

## 4. Conventions

* Money: signed integer **paise** (`BIGINT`). Debit (money out) < 0, credit > 0, never 0. No floats.
* Time: `posted_at` stored UTC (`timestamptz`). Business date/month = date in the user's timezone
  (`Asia/Kolkata`, UTC+05:30, no DST) computed by the pipeline. Months are `YYYY-MM` strings.
* Data period: 2026-01-01 00:00 IST → 2026-12-31 23:59 IST (calendar months; India FY noted in README).
* Enums are `TEXT` + `CHECK` constraints (cheap to evolve), never Postgres enum types.
* CSV: UTF-8, `\n` line endings, header row, rows sorted by primary key.

---

## 5. Domain model

### 5.1 Identifiers

| Entity | Format | Example |
|---|---|---|
| UserProfile | `USR-{n:06d}` | USR-000001 |
| Account | `ACC-{user_id}-{n:02d}` | ACC-USR-000001-01 |
| Transaction | `TXN-{year}-{n:08d}` (global chronological order, IST year) | TXN-2026-00000001 |
| Budget | `BUD-{user_id}-{YYYY-MM}-{submitted_category_code}` (+ `version`) | BUD-USR-000001-2026-01-FOOD_DINING |
| RecurringSeries | `REC-{n:06d}` (stable registry, first-detection order) | REC-000001 |
| Merchant / Rule | `MER-{n:04d}` / `RUL-{n:04d}` (+ `version`) | MER-0012 / RUL-0040 v2 |
| Others | `AEV-` account event, `OVR-` override, `EXC-` exception, `RUN-` pipeline run, `JOB-`, `VAL-`, `ANM-` anomaly, `TRS-` truth series, `INS-{run:04d}-{n:06d}`, `APP-` app user | |

IDs are immutable; referenced ids are byte-identical across files.

### 5.2 Tables, keys and cardinality

Input / master (`public`):

| Table | PK | FKs | Notes |
|---|---|---|---|
| `user_profile` | user_id | — | persona, city, tier, income band, household size, timezone |
| `account` | account_id | user_id → user_profile (owner) | SAVINGS / CREDIT_CARD, opened_on, closed_on (opt), status, opening balance, vpa (opt, unique) |
| `account_holder` (bridge N:M) | (account_id, user_id) | both | PRIMARY / JOINT, since |
| `account_event` | event_id | account_id | OPENED / CLOSED history |
| `account_balance_monthly` | (account_id, month) | account_id | derived opening/credits/debits/closing |
| `category` | category_code | replaced_by → category (opt) | kind INCOME/EXPENSE/TRANSFER/UNKNOWN, group, effective_from/to |
| `category_synonym` | synonym | category_code | for budget remapping |
| `merchant` | merchant_id | default_category_code → category | vpa (opt), online flag |
| `merchant_alias` | alias | merchant_id | 1:N descriptor spellings |
| `merchant_category` (bridge N:M) | (merchant_id, category_code) | both | categories a merchant can legitimately map to |
| `category_rule` | (rule_id, version) | category_code, merchant_id (opt) | priority, conditions, confidence, effective_from, retired_at (opt) |
| `txn` (Transaction) | txn_id | account_id, user_id (= account owner, denormalized, validated) | posted_at UTC, amount_paise, channel, descriptor, counterparty_vpa (opt), reference_no (opt) |
| `budget` | (budget_id, version) | user_id | month, **submitted** category_code (deliberately no FK, validated by pipeline), amount_paise, submitted_at |

Pipeline outputs (`public`, every row stamped with `run_id`):

| Table | PK | FKs |
|---|---|---|
| `pipeline_run` | run_id | — |
| `txn_enrichment` | (run_id, txn_id) | txn, merchant (opt), category, link_txn_id → txn (opt), series_id → recurring_series (opt) |
| `category_override` | override_id | txn_id, category_code |
| `recurring_series` (registry) | series_id | user_id; UNIQUE(user_id, counterparty_key, direction) |
| `recurring_series_state` | (run_id, series_id) | run, series, account, merchant (opt), category |
| `recurring_series_event` | (run_id, series_id, seq) | run, series |
| `budget_resolution` | (run_id, budget_id, version) | budget, resolved_category_code (opt) |
| `insight` | insight_id | run, user, category (opt) |
| `exception_case` | exception_id | first/last run; UNIQUE(exception_type, entity_id) |
| `exception_event` | (exception_id, seq) | exception |
| `evaluation_run` | run_id | run |
| `anomaly_outcome` | (run_id, anomaly_id) | run, gt.anomaly |
| `validation_run`, `job`, `dataset_load` | own ids | — |
| `app_user` | app_user_id | profile_user_id → user_profile (opt) |
| `audit_event` | id (bigserial) | — |

Ground truth (`gt` schema; files under `ground_truth/`):

| Table | PK | FKs |
|---|---|---|
| `gt.txn_label` | txn_id | txn; true_merchant_id (opt); true_category_code; true_link_txn_id (opt); true_series_id → gt.recurring_truth (opt) |
| `gt.recurring_truth` | truth_series_id | user, account |
| `gt.anomaly` | anomaly_id | entity ids (validated per entity_type) |

Cardinality summary: UserProfile 1:N Account (owner); UserProfile N:M Account via `account_holder`;
Account 1:N Transaction; Account 1:N AccountEvent; Merchant 1:N MerchantAlias; Merchant N:M Category via
`merchant_category`; Category 1:N CategoryRule; Category 0..1:1 Category (`replaced_by`); UserProfile 1:N
Budget; Budget 1:N versions; UserProfile 1:N RecurringSeries; RecurringSeries 1:N Transaction (per run, via
`txn_enrichment.series_id`); Transaction 0..1:1 Transaction (transfer counterpart / refund original);
PipelineRun 1:N Insight; UserProfile 1:N Insight; ExceptionCase 1:N ExceptionEvent; UserProfile 0..1:N AppUser.

### 5.3 Lifecycles (state + append-only history)

| Entity | States | History record |
|---|---|---|
| Account | ACTIVE → CLOSED (terminal; no txns after `closed_on`, closing balance 0) | `account_event` |
| Budget | version n current until version n+1 exists (derived; rows never updated) | `budget` versions |
| CategoryRule | active → retired (`retired_at` set once; content never edited; edits = new version) | rule versions |
| Category | active within [effective_from, effective_to]; retired codes carry `replaced_by` | category row |
| RecurringSeries | ACTIVE ⇄ MISSED → ENDED | `recurring_series_event` (DETECTED, AMOUNT_CHANGED, MISSED, RESUMED, ENDED) |
| ExceptionCase | OPEN → IN_REVIEW → RESOLVED/DISMISSED; RESOLVED/DISMISSED → OPEN (reopen) | `exception_event` |
| Category of a txn | pipeline decision per run; user/analyst override wins | `txn_enrichment` per run + `category_override` |
| PipelineRun / Job | RUNNING → SUCCEEDED/FAILED (jobs start QUEUED) | own row + `audit_event` |

`txn`, `category_override`, `*_event`, `txn_enrichment`, `insight` are never updated or deleted.
A dataset re-load is an explicit admin reset (recorded in `dataset_load`).

---

## 6. Business rules (the pipeline)

Order: local date → merchant resolution → own-VPA rule → categorization rules → overrides (lock) → kind →
transfer pairing → reversals/refunds → recurring detection (+ rent inference) → budget resolution →
budget-vs-actual → insights → exceptions. Overridden ("locked") txns are never changed by later steps.

### 6.1 Local date (timezone)
`local_date = posted_at.astimezone(user.timezone).date()`; `local_month = YYYY-MM`. 00:15 IST on 1 Feb is
18:45 UTC on 31 Jan; it belongs to **February**.

### 6.2 Categorization
* Normalize descriptor: lowercase; strip card masks, IFSC codes, reference numbers (≥6 digits), punctuation.
* Merchant resolution: exact `counterparty_vpa` → merchant; else longest alias match on normalized text.
* System rule `SYS-OWNVPA`: counterparty VPA belongs to one of the user's own accounts → SELF_TRANSFER (0.99).
* Rules sorted by (priority, rule_id); first rule whose every non-null condition matches wins. Conditions:
  `merchant_id`, `pattern` (regex on normalized descriptor), `channel`, `direction` (DR/CR/ANY),
  `account_type`. No match → `UNCATEGORIZED` (confidence 0).
* Results are cached per (normalized descriptor, vpa, channel, direction, account type) — the main speed trick.
* Ambiguous merchants are handled by refinement rules with lower priority numbers (e.g. Amazon + `fresh` →
  GROCERIES before Amazon → SHOPPING; Amazon + `prime` → SUBSCRIPTIONS).

### 6.3 Kind and transfers
* Kind from category kind and sign: TRANSFER→TRANSFER; INCOME→INCOME; EXPENSE: debit→EXPENSE,
  credit→REFUND; UNKNOWN→UNKNOWN. Later steps may set REVERSAL.
* Pairing: within one user, debit and credit on **different** accounts, equal absolute amount,
  credit between 1 day before and 3 days after the debit. Eligible debits: category kind TRANSFER or
  UNCATEGORIZED. Eligible credits: kind TRANSFER, UNCATEGORIZED or OTHER_INCOME. Greedy by smallest time gap,
  each leg used once. Paired legs → kind TRANSFER, category CC_BILL_PAYMENT if either leg is on a credit
  card account else SELF_TRANSFER, `link_txn_id` = counterpart, decision `TRANSFER_PAIR`.
* Transfers never count as spending or income. Unpaired TRANSFER-kind txns raise `UNMATCHED_TRANSFER`.

### 6.4 Reversals and refunds
* UPI reversal: credit on the **same account** with the same `reference_no` and equal amount as an earlier
  debit → both legs kind REVERSAL (excluded from spend), credit takes the debit's category.
* Refund: a credit with a resolved merchant whose category kind is EXPENSE, or whose descriptor contains
  refund/rfnd/reversal/rvsl/rev. Link to the most recent earlier debit by the same user at the same merchant
  within 90 days whose unrefunded remainder ≥ the credit (supports partial and multiple refunds).
  Linked → kind REFUND, category = original's category, decision `REFUND_LINKED`.
  No original → kind REFUND, rule category (UNCATEGORIZED if that category is not EXPENSE),
  decision `REFUND_ORPHAN`, exception `ORPHAN_REFUND`.
* Refunds reduce spend of the original's category **in the month the refund posts** (cash basis).

### 6.5 Recurring detection
* Candidates: kinds EXPENSE, INCOME, UNKNOWN. Group key: (user, counterparty key, direction) where
  counterparty key = `M:<merchant_id>` | `V:<vpa>` | `D:<normalized descriptor without digits/months/years>`.
* Need ≥3 occurrences. Median gap g: 25–35 days → MONTHLY; 80–100 → QUARTERLY; else not recurring.
* Regularity: every gap ≥ 0.5·g, and ≥70% of gaps in [0.6·g, 1.4·g].
* Amount stability: ≥80% of consecutive pairs within tolerance (15%; 60% for UTILITIES) of the previous
  amount — a single step change (salary hike, rent increase, price change) is allowed.
* Events: DETECTED (first), AMOUNT_CHANGED (consecutive change > 5%, non-utility), MISSED at prev+g for each
  missing cycle when a gap ≥ 1.6·g, RESUMED at the next occurrence. Tail: days since last > 2.5·g → ENDED;
  > 1.6·g → MISSED; else ACTIVE. `next_expected = last + g` unless ENDED.
* Weekend/holiday shifts, month-end clamping (31st→28 Feb) and payment retries of a few days never reach
  1.6·g, so they are not skips (labelled decoys verify this).
* Series type from category: SALARY, RENT, SUBSCRIPTIONS→SUBSCRIPTION, EMI_LOANS→EMI, UTILITIES→UTILITY,
  INTEREST; an UNCATEGORIZED monthly P2P debit ≥ ₹5,000 is inferred RENT (members re-categorized RENT,
  confidence 0.7, decision `RECUR_RENT`); otherwise OTHER.
* Stable ids: registry `recurring_series` keyed by (user, counterparty key, direction); ids assigned on first
  detection and reused by later runs.

### 6.6 Budgets
* Effective budget per (budget_id): highest version.
* Category resolution for the submitted code in its month:
  active EXPENSE code → VALID; retired code with `replaced_by` → REMAPPED_RETIRED;
  case-folded active code → REMAPPED_CASE; in `category_synonym` → REMAPPED_SYNONYM; else UNMAPPED
  (excluded from comparison, exception `BUDGET_CATEGORY_UNMAPPED`, insight `UNMAPPED_BUDGET`).
  Several budgets resolving to one category in one month are summed.
* Spend (positive paise) per (user, month, category) = −Σ amount over kinds EXPENSE, REFUND and UNKNOWN
  debits. Status: no budget → NO_BUDGET; ratio > 1.0 → OVER; ≥ 0.8 → NEAR; else UNDER (budget 0 → OVER if any spend).
* Joint accounts count toward the **owner's** household budget; joint holders can view the account.
* Budget-vs-actual is computed on read by the same engine function from the latest run + latest overrides,
  so a re-categorization is reflected immediately.

### 6.7 Insights (per user, month)
OVER_BUDGET (ALERT), NEAR_BUDGET (WARN), SPEND_SPIKE (WARN: spend ≥ 1.5× trailing-3-month mean and
≥ ₹2,000 above it), RECURRING_MISSED (ALERT), RECURRING_PRICE_CHANGE (INFO), NEW_RECURRING (INFO, first seen
after the first data month), LOW_SAVINGS (WARN: (income − spend)/income < 10%), UNMAPPED_BUDGET (WARN).
Each carries metric, baseline, message (₹ with Indian digit grouping) and evidence ids.

### 6.8 Exceptions
Types: UNCATEGORIZED, UNMATCHED_TRANSFER, ORPHAN_REFUND, BUDGET_CATEGORY_UNMAPPED, RECURRING_MISSED.
Natural key (type, entity_id) → stable `EXC-` id; reruns update `last_run_id` only and never reopen
resolved cases. Analyst transitions are validated; resolving a txn exception with a category creates an override.

### 6.9 Ledger partition (reconciliation identity)
Every txn is in exactly one bucket: spend (EXPENSE, REFUND, UNKNOWN debit), income (INCOME, UNKNOWN credit),
TRANSFER, REVERSAL. Σ all amounts = income − spend + Σ transfer amounts + Σ reversal amounts.

---

## 7. Synthetic data generation

### 7.1 Determinism
* Seed default **20261022**. Each user draws from its own stream `Rand(f"{seed}:{user_id}")`; global steps use
  `Rand(f"{seed}:global:{step}")`. Adding users never changes earlier users' profiles.
* `Rand` wraps `random.Random(str_seed)` and uses **only** `random()` (the one method Python guarantees stable
  across versions); choice, weighted choice, randint, lognormal (Box–Muller), sample are implemented on top.
  Checksums therefore match across Python 3.12+ and OSes.
* Output files are sorted by PK, ints only, fixed ISO timestamps → byte-identical reruns.

### 7.2 Generation order (parents first, derived values last)
1. `user_profile` → `account` → `account_holder` → `account_event`.
2. Schedules (truth series): salary/pension, rent, subscriptions, EMI, utilities, with planned skips,
   retry/holiday decoys, cancellations, price changes.
3. Discretionary purchases (persona × seasonality × merchant popularity), long-tail merchants, ATM,
   refunds (3% of online purchases; 30% partial; can cross months), UPI reversals (0.3% of UPI debits).
4. Self transfers (users with 2 savings accounts); credit-card bill payments = previous IST month's card
   statement (derived); account closure sweeps.
5. Anomaly injection (§7.5), count-neutral conversions.
6. Exact-count adjustment: add/remove standalone savings UPI debits so total = target.
7. Opening-balance fix: raise savings opening balances so no running balance goes negative (derived).
8. Quarterly savings interest = average daily balance × 3.0% × days/365 (derived), posted 20:00 IST on quarter end.
9. Sort by (posted_at, account_id, seq) → assign `TXN-2026-…` ids → write labels.
10. `account_balance_monthly` (derived) → budgets (derived from expected spend) → budget anomalies.

### 7.3 Distributions (realism)
* Users: personas SALARIED 80% / SELF_EMPLOYED 15% (irregular income, no salary series) / RETIRED 5% (pension);
  20 cities in tiers 1–3; income bands LOW ₹18k–35k, MID ₹35k–90k, HIGH ₹90k–2.5L, AFFLUENT ₹2.5L–8L per month
  (30/45/20/5%); household size 1–6.
* Accounts: primary savings 100%; second savings 40% (5% of these joint with another user in the same city);
  credit card 45% (10% opened during 2026); 3% of second savings accounts closed Jun–Oct.
* Rails & descriptors: UPI (≈70% of debits), card POS/e-com, NEFT salary, NACH EMI, BBPS bills, IMPS
  transfers, ATM. Examples:
  `UPI/DR/612345678901/SWIGGY/YESB/swiggy-mrch@ybl/Payment`,
  `NEFT CR-HDFC0000123-ACME TECHNOLOGIES PVT LTD-SALARY JAN 2026`, `ACH D- BAJAJ FINANCE LTD-EMI 61234567`,
  `BBPS/BESCOM/ELECTRICITY/612345678901`, `POS 412345XXXXXX1234 DMART AVENUE BENGALURU`,
  `IMPS/P2A/612345678901/SELF/HDFC XX4321`, `ATM WDL SBI ATM KORAMANGALA 612345`,
  `INT.PD:01-01-2026 TO 31-03-2026`.
* Merchant aliases: 2–4 spellings per merchant (`AMAZON PAY`, `AMZN MKTP IN`, `AMAZON.IN`), typos (`SWIGY`).
* Ambiguity: multi-category merchants (Amazon, Swiggy/Instamart, Reliance, Tata), P2P rent without note,
  long-tail merchants (`SRI LAKSHMI PROVISION STORES`, `NEW RAJ ENTERPRISES` — "enterprises/traders" have
  mixed true categories).
* Seasonality multipliers (category frequency): shopping 1.6–1.7× Oct–Nov (Diwali), travel peaks May/Dec,
  electricity 1.4–1.5× Apr–Jun, education fees Apr/Jun, food/dining Dec bump, health Jul–Sep monsoon.
* Time of day: category profiles in IST, incl. late-night food orders that naturally cross the UTC date.
* Salary: last working day (SALARIED, Sundays, 2nd/4th Saturdays and national holidays shift it earlier);
  pension on the 1st; ~15% get a hike mid-year. Rent day 1–7, ~15% increase on lease renewal.
  Subscriptions monthly on signup day; mobile recharge every 28 days; 10% cancel (ending by September);
  10% price change.

### 7.4 Ground truth (truth = generator intent, never random relabelling)
`gt.txn_label` for every txn: true merchant (null for long tail), true category (the category of the purchase
the generator created; transfers SELF_TRANSFER/CC_BILL_PAYMENT; refunds and reversals = original's category),
true kind, true link (transfer counterpart / refund original / reversal original), true series, true local month.

### 7.5 Edge cases (labelled in `gt.anomaly`; counts per 1,000 users, min 1 each)

| issue_type | How injected | Expected decision | Count |
|---|---|---|---|
| TRANSFER_DOUBLE_COUNT | Normal self-transfer converted to UPI to own VPA with generic note "Payment", credit leg delayed 1–3 days (may cross month); or CC bill paid via CRED with card credit 2 days later | Both legs TRANSFER, excluded from spend | 400 |
| REFUND_AS_EXPENSE | Refund descriptor rewritten without any refund keyword (looks like a merchant payment, but credit) | kind REFUND, linked to original, nets category | 500 |
| RECURRING_SKIP | One mid-series occurrence of rent/subscription/EMI omitted | MISSED event within ±7 days of expected date | 120 |
| RECURRING_NOT_SKIP (decoy) | Occurrence delayed 2–4 days (retry) | No MISSED event | 240 |
| TZ_BOUNDARY | Txn moved to 1st of month 00:00–05:29 IST (UTC date is previous month) | local_month = IST month | 400 |
| BUDGET_CATEGORY_MISMATCH | Budget code replaced by retired (`DINING_OUT`, `MOBILE_RECHARGE`), lowercase (`groceries`) or synonym (`FOOD_AND_DINING`, `GROCERY`, `BILLS`) → REMAP; or extra budget with unknown code (`GYM_FITNESS`, `PETS`, `MISC_SPEND`) → EXCEPTION | `REMAP_TO:<code>` or `EXCEPTION` | 150 + 50 |

Normal/boundary coverage also present: partial refunds, refunds crossing months, orphan refunds (purchase in
Dec 2025), UPI reversals, joint accounts, closed accounts, accounts opened mid-year, users without budgets (5%),
budget revisions (8%), salary hikes, price changes, cancellations, 28-day cycles, 31st→Feb clamp.

### 7.6 Scale
`--scale full` = 1,000 users / 500,000 txns; `--scale starter` = 50 users / 25,000 txns; or `--users/--transactions`.
Total txn count is exact.

---

## 8. Evaluation metrics (stored per run in `evaluation_run`, written to `reports/`)
* Categorization: accuracy, macro-F1, per-category precision/recall/F1, confusion matrix, coverage.
* Kind accuracy (EXPENSE/INCOME/TRANSFER/REFUND/REVERSAL/UNKNOWN).
* Transfer pairs P/R/F1; refund links P/R/F1; reversal pairs P/R.
* Recurring: series-level P/R (match = same user and ≥50% member overlap), member-level P/R, MISSED-event P/R
  (±7 days), decoy false-alarm rate.
* Timezone: month accuracy on all txns and on TZ_BOUNDARY; naive-UTC baseline accuracy.
* Budgets: spend MAE per user-month-category vs truth spend; status agreement; mismatch handling accuracy.
* Anomaly outcome per `gt.anomaly` (CAUGHT/MISSED) and recall per issue_type.
* **Naive baseline**: spend = Σ|debits and non-income credits| bucketed by UTC month — reports how much a naive
  ledger overstates spend (double-counted transfers, refunds as expenses, wrong months).

Acceptance thresholds on the starter dataset (integration test): category accuracy ≥ 0.85, transfer F1 ≥ 0.95,
refund-link recall ≥ 0.90, TZ_BOUNDARY month accuracy = 1.0, budget mismatch handling = 1.0,
recurring series recall ≥ 0.85, MISSED precision ≥ 0.80 and recall ≥ 0.80, decoy false-alarm rate ≤ 0.10.

---

## 9. Validation (dataset and outputs; `reports/*/validation_*.json|md`)
1. PK uniqueness for every table.
2. FK integrity for every relationship (incl. `gt` → inputs, `account_id` embeds owner user id).
3. Allowed enum values (from schema metadata); ID format regexes.
4. Date ordering: opened_on ≤ txn local date ≤ closed_on; refund/reversal after original; budget versions'
   submitted_at increasing; category effective_from ≤ effective_to.
5. Arithmetic: monthly balances (opening + credits + debits = closing; closing[m] = opening[m+1]); savings never
   negative; CC payment in m+1 = −(card statement of m); transfer pairs sum to 0; ledger partition identity §6.9;
   Σ budget-line actuals = total spend.
6. Lifecycle: account events OPENED → CLOSED only, nothing after CLOSED; exception event chains valid;
   recurring events ordered by date.
7. Duplicates: natural key (account_id, reference_no, amount, posted_at) unique; budget (user, month, code, version) unique.
8. Taxonomy conformance: budget codes outside the active taxonomy == exactly the labelled
   BUDGET_CATEGORY_MISMATCH set (every violation is a labelled anomaly, none silent).
9. Ground-truth isolation: input files contain no `true_*` columns; engine imports no `gt` table.
10. Sign/descriptor consistency: `UPI/DR`, `ATM`, `ACH D-` ⇒ negative; `UPI/CR`, `UPI/REV`, `NEFT CR` ⇒ positive.

---

## 10. Clients
* **Web** (desktop-first): React 19 + TypeScript + Vite, Tailwind + shadcn/ui, TanStack Query/Table, React Router,
  Recharts, Firebase Web SDK, types generated from FastAPI OpenAPI. Served by nginx (SPA + `/api` proxy).
  Pages per role as in §2.
* **Android** (customer only): Flutter, Firebase Auth + Google Sign-In, Riverpod, Dio, go_router, fl_chart.
  Screens: Login, Home, Transactions (+detail, re-categorize), Recurring, Insights.
* **Auth**: Firebase proves identity; the backend owns roles. First Google login creates a CUSTOMER `app_user`
  linked to a synthetic profile (deterministic by uid); `ADMIN_EMAILS` get ADMIN. Local JWT login (seeded demo
  users, password from env) works with no Firebase project, so reviewers can run everything offline.

---

## 11. Exports, reproducibility, provenance
* `data/<scale>/inputs/*.csv`, `data/<scale>/ground_truth/*.csv`, `json/*.json`, `seed.sql`
  (DDL + `COPY … FROM stdin` blocks, loads with `psql -f`), `manifest.json` (params, seed, generator version,
  per-file rows + SHA-256; no timestamps so it is itself reproducible).
* `repro`: generate twice into temp dirs, compare manifests → `reports/<scale>/repro.json`.
* Starter data and all reports are committed; full data is regenerated by one command (its manifest committed).
* Provenance: no external datasets. Merchant brand names, bank codes, city names and holiday dates are public
  reference facts used descriptively; all people, accounts, VPAs and amounts are synthetic.

## 12. Performance techniques
Postgres `COPY` for bulk load/outputs (no ORM row inserts); categorization cache keyed on normalized descriptor;
per-user grouping for matching (no cross-user O(n²)); keyset pagination; indexes on (run_id, user_id, local_month)
and (txn_id, created_at); orjson responses + GZip; pooled sync SQLAlchemy with pre-ping; advisory lock single-flight;
generated web types; nginx immutable caching for hashed assets. Targets on a laptop at full scale: generate ≤ 60 s,
load ≤ 30 s, pipeline ≤ 90 s, p95 API ≤ 150 ms.

## 13. Assumptions and limitations
* Calendar-year months (ID format requires `-2026-01`); India FY (Apr–Mar) not modelled.
* Rules were written knowing the generator's merchant catalogue; long-tail names and ambiguity keep metrics honest,
  but real-world accuracy would be lower. No ML model (deliberate: explainable rules, rule ids in every decision).
* A cancelled subscription is indistinguishable from one missed payment until 2.5 cycles pass.
* Analyst regexes are trusted input (length-capped at 200; no timeout).
* Production deployment runbook (Linux host, TLS, backups) is a later, separate plan.
