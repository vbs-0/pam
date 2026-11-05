# Data Dictionary

Generated from `backend/app/schema.py` by `python -m app.cli docs` — do not edit by hand.

Conventions: money is signed integer **paise** (₹1 = 100 paise; debit < 0, credit > 0). Timestamps are UTC (`timestamptz`); business dates and months are in the household timezone (Asia/Kolkata). Enumerations are TEXT columns with CHECK constraints.

## Cardinality

| Relationship | Cardinality | Optional | Via |
|---|---|---|---|
| UserProfile → Account (owner) | 1:N | no | `account.user_id` |
| UserProfile ↔ Account (holders) | N:M | joint holder optional | bridge `account_holder` |
| Account → AccountEvent | 1:N | no | `account_event.account_id` |
| Account → Transaction | 1:N | no | `txn.account_id` |
| Merchant → MerchantAlias | 1:N | no | `merchant_alias.merchant_id` |
| Merchant ↔ Category | N:M | no | bridge `merchant_category` |
| Category → CategoryRule | 1:N | no | `category_rule.category_code` |
| Category → Category (successor) | 0..1:1 | yes | `category.replaced_by` |
| UserProfile → Budget (versions) | 1:N | 5% of households have none | `budget.user_id` |
| Budget → BudgetResolution (per run) | 1:N | no | `budget_resolution(budget_id, version)` |
| UserProfile → RecurringSeries | 1:N | yes | `recurring_series.user_id` |
| RecurringSeries → Transaction (per run) | 1:N | yes | `txn_enrichment.series_id` |
| Transaction → Transaction (transfer counterpart / refund original) | 0..1:1 | yes | `txn_enrichment.link_txn_id` |
| PipelineRun → TxnEnrichment / Insight / SeriesState | 1:N | no | `run_id` |
| ExceptionCase → ExceptionEvent | 1:N | no | `exception_event.exception_id` |
| UserProfile → AppUser | 0..1:N | yes (soft reference) | `app_user.profile_user_id` |

## Inputs and master data

### `user_profile`

UserProfile: one household. Budgets and insights are per profile.

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `user_id` | VARCHAR(32) | yes |  |  | PK | ^USR-\d{6}$ | Household profile id |
| `display_name` | VARCHAR(80) | yes |  |  |  |  | Synthetic display name (no real person) |
| `city` | VARCHAR(40) | yes |  |  |  |  | City of residence |
| `state` | VARCHAR(2) | yes |  |  |  |  | Indian state/UT code |
| `city_tier` | SMALLINT | yes | 1, 2, 3 |  |  |  | City tier |
| `persona` | VARCHAR(16) | yes | SALARIED, SELF_EMPLOYED, RETIRED |  |  |  | Income persona |
| `income_band` | VARCHAR(10) | yes | LOW, MID, HIGH, AFFLUENT |  |  |  | Monthly net income band |
| `monthly_income_paise` | BIGINT | yes |  | paise |  | >= 0 | Declared monthly net income |
| `household_size` | SMALLINT | yes |  |  |  | 1..8 | People in household |
| `timezone` | VARCHAR(40) | yes | Asia/Kolkata |  |  |  | IANA timezone for business dates |
| `created_on` | DATE | yes |  |  |  |  | Profile creation date |

### `category`

Category taxonomy (two levels: group -> category). Retired codes keep a successor.

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `category_code` | VARCHAR(40) | yes |  |  | PK | ^[A-Z_]+$ | Taxonomy code |
| `name` | VARCHAR(60) | yes |  |  |  |  | Display name |
| `group_code` | VARCHAR(12) | yes | INCOME, ESSENTIALS, LIFESTYLE, OTHER, FINANCIAL |  |  |  | Taxonomy group (level 1) |
| `kind` | VARCHAR(10) | yes | INCOME, EXPENSE, TRANSFER, UNKNOWN |  |  |  | Accounting kind |
| `effective_from` | DATE | yes |  |  |  |  | First day the code is valid |
| `effective_to` | DATE | no |  |  |  | >= effective_from | Last day the code is valid (retired codes) |
| `replaced_by` | VARCHAR(40) | no |  |  |  | FK → `category.category_code` | Successor code for retired categories |

### `category_synonym`

Alternative spellings accepted when resolving user-submitted budget categories.

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `synonym` | VARCHAR(40) | yes |  |  | PK |  | Upper-case alternative spelling |
| `category_code` | VARCHAR(40) | yes |  |  |  | FK → `category.category_code` | Canonical code |

### `merchant`

Merchant master. Local long-tail shops are deliberately absent.

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `merchant_id` | VARCHAR(32) | yes |  |  | PK | ^MER-\d{4}$ | Merchant id |
| `name` | VARCHAR(80) | yes |  |  |  |  | Canonical merchant name |
| `default_category_code` | VARCHAR(40) | yes |  |  |  | FK → `category.category_code` | Most likely category |
| `vpa` | VARCHAR(64) | no |  |  | yes |  | Merchant UPI id (synthetic) |
| `is_online` | BOOLEAN | yes |  |  |  |  | Sells online (refund-capable) |

### `merchant_alias`

Merchant 1:N aliases (spellings, legal names, typos).

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `alias` | VARCHAR(60) | yes |  |  | PK |  | Normalized descriptor spelling |
| `merchant_id` | VARCHAR(32) | yes |  |  |  | FK → `merchant.merchant_id` | Merchant |

### `merchant_category`

Bridge: Merchant N:M Category (ambiguous merchants such as Amazon).

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `merchant_id` | VARCHAR(32) | yes |  |  | PK (composite) | FK → `merchant.merchant_id` | Merchant |
| `category_code` | VARCHAR(40) | yes |  |  | PK (composite) | FK → `category.category_code` | Category the merchant can map to |

### `category_rule`

CategoryRule: versioned, conditional mapping rules. Never edited in place.

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `rule_id` | VARCHAR(32) | yes |  |  | PK (composite) | ^RUL-\d{4}$ | Rule id |
| `version` | SMALLINT | yes |  |  | PK (composite) | >= 1 | Rule version (edits create a new version) |
| `priority` | SMALLINT | yes |  |  |  |  | Lower runs first |
| `category_code` | VARCHAR(40) | yes |  |  |  | FK → `category.category_code` | Category assigned |
| `merchant_id` | VARCHAR(32) | no |  |  |  | FK → `merchant.merchant_id` | Condition: resolved merchant |
| `pattern` | VARCHAR(200) | no |  |  |  |  | Condition: regex on normalized descriptor |
| `channel` | VARCHAR(10) | no | UPI, IMPS, NEFT, RTGS, NACH, CARD_POS, CARD_ECOM, ATM, BBPS, INTERNAL |  |  |  | Condition: channel |
| `direction` | VARCHAR(3) | yes | DR, CR, ANY |  |  |  | Condition: DR/CR/ANY |
| `account_type` | VARCHAR(12) | no | SAVINGS, CREDIT_CARD |  |  |  | Condition: account type |
| `confidence` | NUMERIC(3, 2) | yes |  |  |  | 0..1 | Confidence when matched |
| `effective_from` | TIMESTAMP WITH TIME ZONE | yes |  |  |  |  | Version effective from |
| `retired_at` | TIMESTAMP WITH TIME ZONE | no |  |  |  |  | Set once when superseded or retired |
| `created_by` | VARCHAR(120) | yes |  |  |  |  | Author |
| `note` | TEXT | no |  |  |  |  | Why the rule exists |

### `account`

Account: savings, credit card or UPI app. Owner is the household whose budget it affects.

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `account_id` | VARCHAR(32) | yes |  |  | PK | ^ACC-USR-\d{6}-\d{2}$ | Account id; embeds owner user id |
| `user_id` | VARCHAR(32) | yes |  |  |  | = user id embedded in account_id; FK → `user_profile.user_id` | Owner profile |
| `account_type` | VARCHAR(12) | yes | SAVINGS, CREDIT_CARD, UPI |  |  |  | Account type (UPI: a UPI app or wallet; real households only) |
| `bank_code` | VARCHAR(4) | yes | SBIN, HDFC, ICIC, UTIB, KKBK, BARB, PUNB, CNRB, OTHR, PTYM, PHPE, GPAY, BHIM, AMZN |  |  |  | Bank IFSC prefix, UPI app code, or OTHR for a name the user typed |
| `masked_number` | VARCHAR(20) | yes |  |  |  |  | Masked account/card number |
| `vpa` | VARCHAR(64) | no |  |  | yes |  | UPI id of this account (savings and UPI accounts) |
| `currency` | VARCHAR(3) | yes | INR |  |  |  | ISO 4217 |
| `opened_on` | DATE | yes |  |  |  |  | Open date |
| `closed_on` | DATE | no |  |  |  | >= opened_on | Close date |
| `status` | VARCHAR(8) | yes | ACTIVE, CLOSED |  |  |  | Lifecycle state |
| `opening_balance_paise` | BIGINT | yes |  | paise |  |  | Balance at max(2026-01-01, opened_on); for cards a negative value is the outstanding amount |
| `credit_limit_paise` | BIGINT | no |  | paise |  |  | Card limit |

### `account_holder`

Bridge: UserProfile N:M Account (joint accounts).

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `account_id` | VARCHAR(32) | yes |  |  | PK (composite) | FK → `account.account_id` | Account |
| `user_id` | VARCHAR(32) | yes |  |  | PK (composite) | FK → `user_profile.user_id` | Holder |
| `holder_role` | VARCHAR(8) | yes | PRIMARY, JOINT |  |  |  | Role |
| `since` | DATE | yes |  |  |  |  | Holder since |

### `account_event`

Account lifecycle history (append-only).

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `event_id` | VARCHAR(32) | yes |  |  | PK | ^AEV-\d{6}$ | Event id |
| `account_id` | VARCHAR(32) | yes |  |  |  | FK → `account.account_id` | Account |
| `event_type` | VARCHAR(8) | yes | OPENED, CLOSED |  |  |  | Lifecycle event |
| `event_date` | DATE | yes |  |  |  |  | Event date |
| `detail` | TEXT | no |  |  |  |  | Free text |

### `account_balance_monthly`

Derived from txn; recomputed by validation.

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `account_id` | VARCHAR(32) | yes |  |  | PK (composite) | FK → `account.account_id` | Account |
| `month` | VARCHAR(7) | yes |  |  | PK (composite) | ^\d{4}-\d{2}$ | IST month |
| `opening_paise` | BIGINT | yes |  | paise |  |  | Balance at month start |
| `credits_paise` | BIGINT | yes |  | paise |  | >= 0 | Sum of credits |
| `debits_paise` | BIGINT | yes |  | paise |  | <= 0 | Sum of debits |
| `closing_paise` | BIGINT | yes |  | paise |  |  | Balance at month end |

### `txn`

Transaction ledger (append-only).

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `txn_id` | VARCHAR(32) | yes |  |  | PK | ^TXN-\d{4}-\d{8}$ | Transaction id (chronological) |
| `account_id` | VARCHAR(32) | yes |  |  |  | FK → `account.account_id` | Account |
| `user_id` | VARCHAR(32) | yes |  |  |  | = account.user_id; FK → `user_profile.user_id` | Account owner (denormalized for indexing) |
| `posted_at` | TIMESTAMP WITH TIME ZONE | yes |  |  |  |  | Posting instant, UTC |
| `amount_paise` | BIGINT | yes |  | paise |  | <> 0 | Signed: debit < 0, credit > 0 |
| `currency` | VARCHAR(3) | yes | INR |  |  |  | ISO 4217 |
| `channel` | VARCHAR(10) | yes | UPI, IMPS, NEFT, RTGS, NACH, CARD_POS, CARD_ECOM, ATM, BBPS, INTERNAL |  |  |  | Payment rail |
| `descriptor` | VARCHAR(160) | yes |  |  |  |  | Raw bank narration |
| `counterparty_vpa` | VARCHAR(64) | no |  |  |  |  | Counterparty UPI id |
| `reference_no` | VARCHAR(24) | no |  |  |  |  | RRN/UTR (shared by transfer legs and reversals) |

### `budget`

Budget: monthly household budget per category; revisions are new versions.

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `budget_id` | VARCHAR(64) | yes |  |  | PK (composite) | ^BUD-USR-\d{6}-\d{4}-\d{2}-[A-Za-z_]+$ | BUD-<user>-<YYYY-MM>-<submitted code> |
| `version` | SMALLINT | yes |  |  | PK (composite) | >= 1 | Revision number; highest is effective |
| `user_id` | VARCHAR(32) | yes |  |  |  | FK → `user_profile.user_id` | Profile |
| `month` | VARCHAR(7) | yes |  |  |  | ^\d{4}-\d{2}$ | Budget month (IST) |
| `category_code` | VARCHAR(40) | yes |  |  |  |  | Category AS SUBMITTED; deliberately no FK, resolved by the pipeline |
| `amount_paise` | BIGINT | yes |  | paise |  | > 0 | Budget amount |
| `submitted_at` | TIMESTAMP WITH TIME ZONE | yes |  |  |  |  | Submission instant (effective from) |

## Ground truth (`gt` schema)

### `gt.recurring_truth`

Recurring series the generator actually created.

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `truth_series_id` | VARCHAR(32) | yes |  |  | PK | ^TRS-\d{6}$ | Truth series id |
| `user_id` | VARCHAR(32) | yes |  |  |  | FK → `user_profile.user_id` | Profile |
| `account_id` | VARCHAR(32) | yes |  |  |  | FK → `account.account_id` | Account |
| `series_type` | VARCHAR(12) | yes | SALARY, RENT, SUBSCRIPTION, EMI, UTILITY, INTEREST |  |  |  | Series type |
| `counterparty` | VARCHAR(80) | yes |  |  |  |  | Payee/payer |
| `cadence` | VARCHAR(10) | yes | MONTHLY, QUARTERLY |  |  |  | Cadence |
| `start_date` | DATE | yes |  |  |  |  | First occurrence |
| `end_date` | DATE | no |  |  |  |  | Last occurrence if ended |
| `status_at_end` | VARCHAR(8) | yes | ACTIVE, ENDED |  |  |  | Status at data end |

### `gt.txn_label`

Ground-truth label for every transaction.

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `txn_id` | VARCHAR(32) | yes |  |  | PK | FK → `txn.txn_id` | Transaction |
| `true_merchant_id` | VARCHAR(32) | no |  |  |  | FK → `merchant.merchant_id` | True merchant (null = long tail) |
| `true_category_code` | VARCHAR(40) | yes |  |  |  | FK → `category.category_code` | True category |
| `true_kind` | VARCHAR(10) | yes | EXPENSE, INCOME, TRANSFER, REFUND, REVERSAL |  |  |  | True kind |
| `true_link_txn_id` | VARCHAR(32) | no |  |  |  | FK → `txn.txn_id` | Transfer counterpart / refund or reversal original |
| `true_series_id` | VARCHAR(32) | no |  |  |  | FK → `gt.recurring_truth.truth_series_id` | True recurring series |
| `true_local_month` | VARCHAR(7) | yes |  |  |  |  | IST month |

### `gt.anomaly`

Deliberately injected edge cases with the expected decision.

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `anomaly_id` | VARCHAR(32) | yes |  |  | PK | ^ANM-\d{6}$ | Anomaly id |
| `issue_type` | VARCHAR(28) | yes | TRANSFER_DOUBLE_COUNT, REFUND_AS_EXPENSE, RECURRING_SKIP, RECURRING_NOT_SKIP, TZ_BOUNDARY, BUDGET_CATEGORY_MISMATCH |  |  |  | Injected issue |
| `entity_type` | VARCHAR(8) | yes | TXN, SERIES, BUDGET |  |  |  | Entity kind |
| `entity_id` | VARCHAR(64) | yes |  |  |  |  | Primary entity id |
| `related_ids` | TEXT | no |  |  |  |  | Pipe-separated related ids |
| `expected_decision` | VARCHAR(60) | yes |  |  |  |  | What a correct system does |
| `expected_date` | DATE | no |  |  |  |  | Expected date (skips/decoys) |
| `note` | TEXT | yes |  |  |  |  | Human explanation |

## Pipeline outputs

### `pipeline_run`

Every pipeline execution. Readers use the latest SUCCEEDED run.

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `run_id` | VARCHAR(32) | yes |  |  | PK | ^RUN-\d{6}$ | Run id |
| `status` | VARCHAR(10) | yes | RUNNING, SUCCEEDED, FAILED |  |  |  | Run state |
| `started_at` | TIMESTAMP WITH TIME ZONE | yes |  |  |  |  | Start |
| `finished_at` | TIMESTAMP WITH TIME ZONE | no |  |  |  |  | End |
| `ruleset_hash` | VARCHAR(64) | no |  |  |  |  | SHA-256 of active rules |
| `stats` | JSONB | no |  |  |  |  | Counters |
| `error` | TEXT | no |  |  |  |  | Failure reason |

### `recurring_series`

RecurringSeries registry: ids are assigned once and never change across runs.

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `series_id` | VARCHAR(32) | yes |  |  | PK | ^REC-\d{6}$ | Stable series id |
| `user_id` | VARCHAR(32) | yes |  |  |  | FK → `user_profile.user_id` | Profile |
| `counterparty_key` | VARCHAR(120) | yes |  |  |  |  | M:<merchant> | V:<vpa> | D:<descriptor> |
| `direction` | VARCHAR(2) | yes | DR, CR |  |  |  | DR/CR |
| `first_run_id` | VARCHAR(32) | yes |  |  |  | FK → `pipeline_run.run_id` | Run that first detected it |

### `txn_enrichment`

Per-run decision for every transaction (traceable to rule id + version).

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `run_id` | VARCHAR(32) | yes |  |  | PK (composite) | FK → `pipeline_run.run_id` | Run |
| `txn_id` | VARCHAR(32) | yes |  |  | PK (composite) | FK → `txn.txn_id` | Transaction |
| `user_id` | VARCHAR(32) | yes |  |  |  | FK → `user_profile.user_id` | Owner (denormalized) |
| `local_date` | DATE | yes |  |  |  |  | Business date in the household timezone |
| `local_month` | VARCHAR(7) | yes |  |  |  |  | Business month |
| `merchant_id` | VARCHAR(32) | no |  |  |  | FK → `merchant.merchant_id` | Resolved merchant |
| `category_code` | VARCHAR(40) | yes |  |  |  | FK → `category.category_code` | Decided category |
| `rule_id` | VARCHAR(32) | no |  |  |  |  | Deciding rule (RUL-… or SYS-…) |
| `rule_version` | SMALLINT | no |  |  |  |  | Rule version |
| `confidence` | NUMERIC(3, 2) | yes |  |  |  | 0..1 | Decision confidence |
| `kind` | VARCHAR(10) | yes | EXPENSE, INCOME, TRANSFER, REFUND, REVERSAL, UNKNOWN |  |  |  | Decided kind |
| `link_txn_id` | VARCHAR(32) | no |  |  |  | FK → `txn.txn_id` | Transfer counterpart / refund or reversal original |
| `series_id` | VARCHAR(32) | no |  |  |  | FK → `recurring_series.series_id` | Recurring series |
| `decision` | VARCHAR(40) | yes |  |  |  |  | Decision code (RULE, OWN_VPA, TRANSFER_PAIR, REFUND_LINKED, ...) |

### `category_override`

Human category decisions (append-only; latest wins and locks the txn).

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `override_id` | VARCHAR(32) | yes |  |  | PK | ^OVR-\d{6}$ | Override id |
| `txn_id` | VARCHAR(32) | yes |  |  |  | FK → `txn.txn_id` | Transaction |
| `category_code` | VARCHAR(40) | yes |  |  |  | FK → `category.category_code` | Chosen category |
| `actor` | VARCHAR(120) | yes |  |  |  |  | Who (email) |
| `reason` | TEXT | no |  |  |  |  | Why |
| `created_at` | TIMESTAMP WITH TIME ZONE | yes |  |  |  |  | When |

### `recurring_series_state`

Recurring series state as of a run.

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `run_id` | VARCHAR(32) | yes |  |  | PK (composite) | FK → `pipeline_run.run_id` | Run |
| `series_id` | VARCHAR(32) | yes |  |  | PK (composite) | FK → `recurring_series.series_id` | Series |
| `account_id` | VARCHAR(32) | yes |  |  |  | FK → `account.account_id` | Account of latest member |
| `merchant_id` | VARCHAR(32) | no |  |  |  | FK → `merchant.merchant_id` | Merchant |
| `category_code` | VARCHAR(40) | yes |  |  |  | FK → `category.category_code` | Category |
| `series_type` | VARCHAR(12) | yes | SALARY, RENT, SUBSCRIPTION, EMI, UTILITY, INTEREST, OTHER |  |  |  | Type |
| `cadence` | VARCHAR(10) | yes | MONTHLY, QUARTERLY |  |  |  | Cadence |
| `median_gap_days` | SMALLINT | yes |  | days |  |  | Median gap |
| `typical_amount_paise` | BIGINT | yes |  | paise |  |  | Median of the last 3 amounts |
| `first_seen` | DATE | yes |  |  |  |  | First occurrence |
| `last_seen` | DATE | yes |  |  |  |  | Last occurrence |
| `next_expected` | DATE | no |  |  |  |  | Next expected date |
| `status` | VARCHAR(8) | yes | ACTIVE, MISSED, ENDED |  |  |  | Lifecycle |
| `occurrences` | INTEGER | yes |  |  |  |  | Member count |

### `recurring_series_event`

Recurring series history: detected, amount changed, missed, resumed, ended.

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `run_id` | VARCHAR(32) | yes |  |  | PK (composite) | FK → `recurring_series_state.run_id` | Run |
| `series_id` | VARCHAR(32) | yes |  |  | PK (composite) | FK → `recurring_series_state.series_id` | Series |
| `seq` | SMALLINT | yes |  |  | PK (composite) |  | Order within the series |
| `event_type` | VARCHAR(16) | yes | DETECTED, AMOUNT_CHANGED, MISSED, RESUMED, ENDED |  |  |  | Event |
| `event_date` | DATE | yes |  |  |  |  | When |
| `detail` | JSONB | no |  |  |  |  | Event data |

### `budget_resolution`

How each effective budget maps onto the taxonomy in a run.

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `run_id` | VARCHAR(32) | yes |  |  | PK (composite) | FK → `pipeline_run.run_id` | Run |
| `budget_id` | VARCHAR(64) | yes |  |  | PK (composite) | FK → `budget.budget_id` | Budget |
| `version` | SMALLINT | yes |  |  | PK (composite) | FK → `budget.version` | Effective version |
| `resolved_category_code` | VARCHAR(40) | no |  |  |  | FK → `category.category_code` | Taxonomy code used |
| `resolution` | VARCHAR(18) | yes | VALID, REMAPPED_RETIRED, REMAPPED_CASE, REMAPPED_SYNONYM, UNMAPPED |  |  |  | How the submitted code was resolved |

### `insight`

Insight: derived from aggregations, always with evidence ids.

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `insight_id` | VARCHAR(32) | yes |  |  | PK | ^INS-\d{4}-\d{6}$ | INS-<run>-<n> |
| `run_id` | VARCHAR(32) | yes |  |  |  | FK → `pipeline_run.run_id` | Run |
| `user_id` | VARCHAR(32) | yes |  |  |  | FK → `user_profile.user_id` | Profile |
| `month` | VARCHAR(7) | yes |  |  |  |  | Month |
| `insight_type` | VARCHAR(24) | yes | OVER_BUDGET, NEAR_BUDGET, SPEND_SPIKE, RECURRING_MISSED, RECURRING_PRICE_CHANGE, NEW_RECURRING, LOW_SAVINGS, UNMAPPED_BUDGET |  |  |  | Type |
| `severity` | VARCHAR(5) | yes | INFO, WARN, ALERT |  |  |  | Severity |
| `category_code` | VARCHAR(40) | no |  |  |  | FK → `category.category_code` | Category |
| `metric_paise` | BIGINT | no |  | paise |  |  | Observed value |
| `baseline_paise` | BIGINT | no |  | paise |  |  | Comparison value |
| `message` | TEXT | yes |  |  |  |  | Human message |
| `evidence` | JSONB | yes |  |  |  |  | Ids backing the insight |

### `exception_case`

Exception queue for analysts (current state; history in exception_event).

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `exception_id` | VARCHAR(32) | yes |  |  | PK | ^EXC-\d{6}$ | Exception id |
| `exception_type` | VARCHAR(28) | yes | UNCATEGORIZED, UNMATCHED_TRANSFER, ORPHAN_REFUND, BUDGET_CATEGORY_UNMAPPED, RECURRING_MISSED |  |  |  | Type |
| `entity_type` | VARCHAR(8) | yes | TXN, BUDGET, SERIES |  |  |  | Entity kind |
| `entity_id` | VARCHAR(64) | yes |  |  |  |  | Entity id |
| `user_id` | VARCHAR(32) | no |  |  |  | FK → `user_profile.user_id` | Profile |
| `status` | VARCHAR(10) | yes | OPEN, IN_REVIEW, RESOLVED, DISMISSED |  |  |  | Lifecycle |
| `first_run_id` | VARCHAR(32) | yes |  |  |  | FK → `pipeline_run.run_id` | First seen |
| `last_run_id` | VARCHAR(32) | yes |  |  |  | FK → `pipeline_run.run_id` | Last seen |
| `detail` | JSONB | no |  |  |  |  | Context |
| `created_at` | TIMESTAMP WITH TIME ZONE | yes |  |  |  |  | Created |
| `updated_at` | TIMESTAMP WITH TIME ZONE | yes |  |  |  |  | Last transition |

### `exception_event`

Exception state transitions (append-only).

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `exception_id` | VARCHAR(32) | yes |  |  | PK (composite) | FK → `exception_case.exception_id` | Exception |
| `seq` | SMALLINT | yes |  |  | PK (composite) |  | Order |
| `from_status` | VARCHAR(10) | no |  |  |  |  | Before |
| `to_status` | VARCHAR(10) | yes | OPEN, IN_REVIEW, RESOLVED, DISMISSED |  |  |  | After |
| `actor` | VARCHAR(120) | yes |  |  |  |  | Who |
| `note` | TEXT | no |  |  |  |  | Note |
| `at` | TIMESTAMP WITH TIME ZONE | yes |  |  |  |  | When |

### `evaluation_run`

Metrics of a pipeline run against ground truth.

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `run_id` | VARCHAR(32) | yes |  |  | PK | FK → `pipeline_run.run_id` | Evaluated run |
| `created_at` | TIMESTAMP WITH TIME ZONE | yes |  |  |  |  | When |
| `metrics` | JSONB | yes |  |  |  |  | All metrics |

### `anomaly_outcome`

Whether each injected anomaly was handled correctly in a run.

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `run_id` | VARCHAR(32) | yes |  |  | PK (composite) | FK → `pipeline_run.run_id` | Run |
| `anomaly_id` | VARCHAR(32) | yes |  |  | PK (composite) | FK → `gt.anomaly.anomaly_id` | Anomaly |
| `outcome` | VARCHAR(8) | yes | CAUGHT, MISSED |  |  |  | Result |
| `observed` | TEXT | yes |  |  |  |  | What the system did |

## Operational

### `validation_run`

Validation runs over the dataset or pipeline outputs.

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `validation_id` | VARCHAR(32) | yes |  |  | PK | ^VAL-\d{6}$ | Id |
| `scope` | VARCHAR(8) | yes | DATASET, OUTPUTS |  |  |  | Scope |
| `created_at` | TIMESTAMP WITH TIME ZONE | yes |  |  |  |  | When |
| `passed` | BOOLEAN | yes |  |  |  |  | All checks passed |
| `results` | JSONB | yes |  |  |  |  | Per-check results |

### `job`

Admin-triggered background jobs.

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `job_id` | VARCHAR(32) | yes |  |  | PK | ^JOB-\d{6}$ | Job id |
| `job_type` | VARCHAR(16) | yes | GENERATE_LOAD, PIPELINE, EVALUATE, VALIDATE, EXPORT, REPRO |  |  |  | Type |
| `params` | JSONB | yes |  |  |  |  | Parameters |
| `status` | VARCHAR(10) | yes | QUEUED, RUNNING, SUCCEEDED, FAILED |  |  |  | State |
| `created_by` | VARCHAR(120) | yes |  |  |  |  | Requester |
| `created_at` | TIMESTAMP WITH TIME ZONE | yes |  |  |  |  | Queued at |
| `started_at` | TIMESTAMP WITH TIME ZONE | no |  |  |  |  | Start |
| `finished_at` | TIMESTAMP WITH TIME ZONE | no |  |  |  |  | End |
| `result` | JSONB | no |  |  |  |  | Result |
| `error` | TEXT | no |  |  |  |  | Error |

### `dataset_load`

Dataset (re)loads — each one is an explicit reset.

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `load_id` | VARCHAR(32) | yes |  |  | PK | ^DSL-\d{6}$ | Load id |
| `loaded_at` | TIMESTAMP WITH TIME ZONE | yes |  |  |  |  | When |
| `scale` | VARCHAR(16) | yes |  |  |  |  | Scale label |
| `seed` | BIGINT | yes |  |  |  |  | Generator seed |
| `manifest_sha256` | VARCHAR(64) | yes |  |  |  |  | Manifest hash |
| `rows` | JSONB | yes |  |  |  |  | Row counts per table |

### `app_user`

People who can sign in. Roles live here, never in tokens.

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `app_user_id` | VARCHAR(32) | yes |  |  | PK | ^APP-\d{6}$ | Login id |
| `email` | VARCHAR(120) | yes |  |  | yes |  | Email (lower-case) |
| `role` | VARCHAR(10) | yes | CUSTOMER, ANALYST, REVIEWER, ADMIN |  |  |  | Role |
| `profile_user_id` | VARCHAR(32) | no |  |  |  |  | Linked profile (soft reference so logins survive dataset resets) |
| `password_hash` | VARCHAR(200) | no |  |  |  |  | argon2 hash for local login |
| `firebase_uid` | VARCHAR(128) | no |  |  | yes |  | Firebase uid |
| `disabled` | BOOLEAN | yes |  |  |  |  | Login disabled |
| `created_at` | TIMESTAMP WITH TIME ZONE | yes |  |  |  |  | Created |

### `audit_event`

Append-only audit log of every human or job action.

| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |
|---|---|---|---|---|---|---|---|
| `id` | BIGINT | yes |  |  | PK |  | Sequence |
| `at` | TIMESTAMP WITH TIME ZONE | yes |  |  |  |  | When |
| `actor` | VARCHAR(120) | yes |  |  |  |  | Who |
| `action` | VARCHAR(60) | yes |  |  |  |  | What |
| `entity_type` | VARCHAR(30) | yes |  |  |  |  | Entity kind |
| `entity_id` | VARCHAR(64) | yes |  |  |  |  | Entity id |
| `request_id` | VARCHAR(64) | no |  |  |  |  | Request id |
| `detail` | JSONB | no |  |  |  |  | Before/after |

## Foreign keys

- `category.replaced_by` → `category.category_code` (optional)
- `account.user_id` → `user_profile.user_id` (required)
- `anomaly_outcome.anomaly_id` → `gt.anomaly.anomaly_id` (required)
- `anomaly_outcome.run_id` → `pipeline_run.run_id` (required)
- `budget.user_id` → `user_profile.user_id` (required)
- `category_synonym.category_code` → `category.category_code` (required)
- `evaluation_run.run_id` → `pipeline_run.run_id` (required)
- `exception_case.first_run_id` → `pipeline_run.run_id` (required)
- `exception_case.last_run_id` → `pipeline_run.run_id` (required)
- `exception_case.user_id` → `user_profile.user_id` (optional)
- `insight.category_code` → `category.category_code` (optional)
- `insight.run_id` → `pipeline_run.run_id` (required)
- `insight.user_id` → `user_profile.user_id` (required)
- `merchant.default_category_code` → `category.category_code` (required)
- `recurring_series.first_run_id` → `pipeline_run.run_id` (required)
- `recurring_series.user_id` → `user_profile.user_id` (required)
- `account_balance_monthly.account_id` → `account.account_id` (required)
- `account_event.account_id` → `account.account_id` (required)
- `account_holder.account_id` → `account.account_id` (required)
- `account_holder.user_id` → `user_profile.user_id` (required)
- `budget_resolution.budget_id` → `budget.budget_id` (required)
- `budget_resolution.resolved_category_code` → `category.category_code` (optional)
- `budget_resolution.run_id` → `pipeline_run.run_id` (required)
- `budget_resolution.version` → `budget.version` (required)
- `category_rule.category_code` → `category.category_code` (required)
- `category_rule.merchant_id` → `merchant.merchant_id` (optional)
- `exception_event.exception_id` → `exception_case.exception_id` (required)
- `gt.recurring_truth.account_id` → `account.account_id` (required)
- `gt.recurring_truth.user_id` → `user_profile.user_id` (required)
- `merchant_alias.merchant_id` → `merchant.merchant_id` (required)
- `merchant_category.category_code` → `category.category_code` (required)
- `merchant_category.merchant_id` → `merchant.merchant_id` (required)
- `recurring_series_state.account_id` → `account.account_id` (required)
- `recurring_series_state.category_code` → `category.category_code` (required)
- `recurring_series_state.merchant_id` → `merchant.merchant_id` (optional)
- `recurring_series_state.run_id` → `pipeline_run.run_id` (required)
- `recurring_series_state.series_id` → `recurring_series.series_id` (required)
- `txn.account_id` → `account.account_id` (required)
- `txn.user_id` → `user_profile.user_id` (required)
- `category_override.category_code` → `category.category_code` (required)
- `category_override.txn_id` → `txn.txn_id` (required)
- `gt.txn_label.true_category_code` → `category.category_code` (required)
- `gt.txn_label.true_link_txn_id` → `txn.txn_id` (optional)
- `gt.txn_label.true_merchant_id` → `merchant.merchant_id` (optional)
- `gt.txn_label.true_series_id` → `gt.recurring_truth.truth_series_id` (optional)
- `gt.txn_label.txn_id` → `txn.txn_id` (required)
- `recurring_series_event.run_id` → `recurring_series_state.run_id` (required)
- `recurring_series_event.series_id` → `recurring_series_state.series_id` (required)
- `txn_enrichment.category_code` → `category.category_code` (required)
- `txn_enrichment.link_txn_id` → `txn.txn_id` (optional)
- `txn_enrichment.merchant_id` → `merchant.merchant_id` (optional)
- `txn_enrichment.run_id` → `pipeline_run.run_id` (required)
- `txn_enrichment.series_id` → `recurring_series.series_id` (optional)
- `txn_enrichment.txn_id` → `txn.txn_id` (required)
- `txn_enrichment.user_id` → `user_profile.user_id` (required)
