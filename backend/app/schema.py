"""Single source of truth for every table.

Column.info carries the data dictionary (description, allowed values, unit, validation rule). The Alembic
migration, the SQL seed DDL, CSV column order, enum validation and docs/data_dictionary.md are all derived
from this module.
"""
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(naming_convention={
    "ix": "ix_%(table_name)s_%(column_0_N_name)s", "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s", "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s"})

CHANNELS = ["UPI", "IMPS", "NEFT", "RTGS", "NACH", "CARD_POS", "CARD_ECOM", "ATM", "BBPS", "INTERNAL"]
KINDS = ["EXPENSE", "INCOME", "TRANSFER", "REFUND", "REVERSAL", "UNKNOWN"]
TRUE_KINDS = KINDS[:-1]
BANKS = ["SBIN", "HDFC", "ICIC", "UTIB", "KKBK", "BARB", "PUNB", "CNRB"]
ISSUE_TYPES = ["TRANSFER_DOUBLE_COUNT", "REFUND_AS_EXPENSE", "RECURRING_SKIP", "RECURRING_NOT_SKIP",
               "TZ_BOUNDARY", "BUDGET_CATEGORY_MISMATCH"]
EXCEPTION_TYPES = ["UNCATEGORIZED", "UNMATCHED_TRANSFER", "ORPHAN_REFUND", "BUDGET_CATEGORY_UNMAPPED",
                   "RECURRING_MISSED"]
EXCEPTION_STATUSES = ["OPEN", "IN_REVIEW", "RESOLVED", "DISMISSED"]
INSIGHT_TYPES = ["OVER_BUDGET", "NEAR_BUDGET", "SPEND_SPIKE", "RECURRING_MISSED", "RECURRING_PRICE_CHANGE",
                 "NEW_RECURRING", "LOW_SAVINGS", "UNMAPPED_BUDGET"]
SERIES_TYPES = ["SALARY", "RENT", "SUBSCRIPTION", "EMI", "UTILITY", "INTEREST", "OTHER"]
SERIES_EVENTS = ["DETECTED", "AMOUNT_CHANGED", "MISSED", "RESUMED", "ENDED"]
RESOLUTIONS = ["VALID", "REMAPPED_RETIRED", "REMAPPED_CASE", "REMAPPED_SYNONYM", "UNMAPPED"]
ROLES = ["CUSTOMER", "ANALYST", "REVIEWER", "ADMIN"]
JOB_TYPES = ["GENERATE_LOAD", "PIPELINE", "EVALUATE", "VALIDATE", "EXPORT", "REPRO"]
ID, LONG_ID, CODE, MONTH = String(32), String(64), String(40), String(7)
TS = DateTime(timezone=True)


def col(name, type_, desc, *extra, fk=None, pk=False, null=False, allowed=None, unit=None, unique=False,
        rule=None, **kw) -> Column:
    args = [fk] if isinstance(fk, ForeignKey) else ([ForeignKey(fk)] if fk else [])
    return Column(name, type_, *args, *extra, primary_key=pk, nullable=null and not pk, unique=unique,
                  info={"desc": desc, "allowed": allowed, "unit": unit, "rule": rule}, **kw)


def table(name, *items, schema=None, comment="") -> Table:
    checks = [CheckConstraint(f"{c.name} IN ({', '.join(repr(v) for v in c.info['allowed'])})",
                              name=f"{c.name}_allowed")
              for c in items if isinstance(c, Column) and c.info.get("allowed")]
    return Table(name, metadata, *items, *checks, schema=schema, comment=comment)


# ---------------------------------------------------------------- inputs / master data
user_profile = table(
    "user_profile",
    col("user_id", ID, "Household profile id", pk=True, rule=r"^USR-\d{6}$"),
    col("display_name", String(80), "Synthetic display name (no real person)"),
    col("city", String(40), "City of residence"),
    col("state", String(2), "Indian state/UT code"),
    col("city_tier", SmallInteger, "City tier", allowed=[1, 2, 3]),
    col("persona", String(16), "Income persona", allowed=["SALARIED", "SELF_EMPLOYED", "RETIRED"]),
    col("income_band", String(10), "Monthly net income band", allowed=["LOW", "MID", "HIGH", "AFFLUENT"]),
    col("monthly_income_paise", BigInteger, "Declared monthly net income", unit="paise", rule=">= 0"),
    col("household_size", SmallInteger, "People in household", rule="1..8"),
    col("timezone", String(40), "IANA timezone for business dates", allowed=["Asia/Kolkata"]),
    col("created_on", Date, "Profile creation date"),
    CheckConstraint("monthly_income_paise >= 0", name="income_nonneg"),
    CheckConstraint("household_size BETWEEN 1 AND 8", name="household_range"),
    comment="UserProfile: one household. Budgets and insights are per profile.")

category = table(
    "category",
    col("category_code", CODE, "Taxonomy code", pk=True, rule=r"^[A-Z_]+$"),
    col("name", String(60), "Display name"),
    col("group_code", String(12), "Taxonomy group (level 1)",
        allowed=["INCOME", "ESSENTIALS", "LIFESTYLE", "OTHER", "FINANCIAL"]),
    col("kind", String(10), "Accounting kind", allowed=["INCOME", "EXPENSE", "TRANSFER", "UNKNOWN"]),
    col("effective_from", Date, "First day the code is valid"),
    col("effective_to", Date, "Last day the code is valid (retired codes)", null=True, rule=">= effective_from"),
    col("replaced_by", CODE, "Successor code for retired categories", null=True, fk="category.category_code"),
    CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="dates"),
    comment="Category taxonomy (two levels: group -> category). Retired codes keep a successor.")

category_synonym = table(
    "category_synonym",
    col("synonym", CODE, "Upper-case alternative spelling", pk=True),
    col("category_code", CODE, "Canonical code", fk="category.category_code"),
    comment="Alternative spellings accepted when resolving user-submitted budget categories.")

merchant = table(
    "merchant",
    col("merchant_id", ID, "Merchant id", pk=True, rule=r"^MER-\d{4}$"),
    col("name", String(80), "Canonical merchant name"),
    col("default_category_code", CODE, "Most likely category", fk="category.category_code"),
    col("vpa", String(64), "Merchant UPI id (synthetic)", null=True, unique=True),
    col("is_online", Boolean, "Sells online (refund-capable)"),
    comment="Merchant master. Local long-tail shops are deliberately absent.")

merchant_alias = table(
    "merchant_alias",
    col("alias", String(60), "Normalized descriptor spelling", pk=True),
    col("merchant_id", ID, "Merchant", fk="merchant.merchant_id"),
    comment="Merchant 1:N aliases (spellings, legal names, typos).")

merchant_category = table(
    "merchant_category",
    col("merchant_id", ID, "Merchant", fk="merchant.merchant_id", pk=True),
    col("category_code", CODE, "Category the merchant can map to", fk="category.category_code", pk=True),
    comment="Bridge: Merchant N:M Category (ambiguous merchants such as Amazon).")

category_rule = table(
    "category_rule",
    col("rule_id", ID, "Rule id", pk=True, rule=r"^RUL-\d{4}$"),
    col("version", SmallInteger, "Rule version (edits create a new version)", pk=True, rule=">= 1"),
    col("priority", SmallInteger, "Lower runs first"),
    col("category_code", CODE, "Category assigned", fk="category.category_code"),
    col("merchant_id", ID, "Condition: resolved merchant", null=True, fk="merchant.merchant_id"),
    col("pattern", String(200), "Condition: regex on normalized descriptor", null=True),
    col("channel", String(10), "Condition: channel", null=True, allowed=CHANNELS),
    col("direction", String(3), "Condition: DR/CR/ANY", allowed=["DR", "CR", "ANY"]),
    col("account_type", String(12), "Condition: account type", null=True, allowed=["SAVINGS", "CREDIT_CARD"]),
    col("confidence", Numeric(3, 2), "Confidence when matched", rule="0..1"),
    col("effective_from", TS, "Version effective from"),
    col("retired_at", TS, "Set once when superseded or retired", null=True),
    col("created_by", String(120), "Author"),
    col("note", Text, "Why the rule exists", null=True),
    CheckConstraint("merchant_id IS NOT NULL OR pattern IS NOT NULL OR channel IS NOT NULL "
                    "OR account_type IS NOT NULL", name="has_condition"),
    CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence_range"),
    comment="CategoryRule: versioned, conditional mapping rules. Never edited in place.")

account = table(
    "account",
    col("account_id", ID, "Account id; embeds owner user id", pk=True, rule=r"^ACC-USR-\d{6}-\d{2}$"),
    col("user_id", ID, "Owner profile", fk="user_profile.user_id", rule="= user id embedded in account_id"),
    col("account_type", String(12), "Account type", allowed=["SAVINGS", "CREDIT_CARD"]),
    col("bank_code", String(4), "Bank IFSC prefix", allowed=BANKS),
    col("masked_number", String(20), "Masked account/card number"),
    col("vpa", String(64), "UPI id of this account (savings only)", null=True, unique=True),
    col("currency", String(3), "ISO 4217", allowed=["INR"]),
    col("opened_on", Date, "Open date"),
    col("closed_on", Date, "Close date", null=True, rule=">= opened_on"),
    col("status", String(8), "Lifecycle state", allowed=["ACTIVE", "CLOSED"]),
    col("opening_balance_paise", BigInteger,
        "Balance at max(2026-01-01, opened_on); for cards a negative value is the outstanding amount",
        unit="paise"),
    col("credit_limit_paise", BigInteger, "Card limit", null=True, unit="paise"),
    CheckConstraint("closed_on IS NULL OR closed_on >= opened_on", name="close_after_open"),
    CheckConstraint("(status = 'CLOSED') = (closed_on IS NOT NULL)", name="status_matches_close"),
    comment="Account: savings or credit card. Owner is the household whose budget it affects.")

account_holder = table(
    "account_holder",
    col("account_id", ID, "Account", fk="account.account_id", pk=True),
    col("user_id", ID, "Holder", fk="user_profile.user_id", pk=True),
    col("holder_role", String(8), "Role", allowed=["PRIMARY", "JOINT"]),
    col("since", Date, "Holder since"),
    comment="Bridge: UserProfile N:M Account (joint accounts).")

account_event = table(
    "account_event",
    col("event_id", ID, "Event id", pk=True, rule=r"^AEV-\d{6}$"),
    col("account_id", ID, "Account", fk="account.account_id"),
    col("event_type", String(8), "Lifecycle event", allowed=["OPENED", "CLOSED"]),
    col("event_date", Date, "Event date"),
    col("detail", Text, "Free text", null=True),
    comment="Account lifecycle history (append-only).")

account_balance_monthly = table(
    "account_balance_monthly",
    col("account_id", ID, "Account", fk="account.account_id", pk=True),
    col("month", MONTH, "IST month", pk=True, rule=r"^\d{4}-\d{2}$"),
    col("opening_paise", BigInteger, "Balance at month start", unit="paise"),
    col("credits_paise", BigInteger, "Sum of credits", unit="paise", rule=">= 0"),
    col("debits_paise", BigInteger, "Sum of debits", unit="paise", rule="<= 0"),
    col("closing_paise", BigInteger, "Balance at month end", unit="paise"),
    CheckConstraint("opening_paise + credits_paise + debits_paise = closing_paise", name="reconciles"),
    CheckConstraint("credits_paise >= 0 AND debits_paise <= 0", name="signs"),
    comment="Derived from txn; recomputed by validation.")

txn = table(
    "txn",
    col("txn_id", ID, "Transaction id (chronological)", pk=True, rule=r"^TXN-\d{4}-\d{8}$"),
    col("account_id", ID, "Account", fk="account.account_id"),
    col("user_id", ID, "Account owner (denormalized for indexing)", fk="user_profile.user_id",
        rule="= account.user_id"),
    col("posted_at", TS, "Posting instant, UTC"),
    col("amount_paise", BigInteger, "Signed: debit < 0, credit > 0", unit="paise", rule="<> 0"),
    col("currency", String(3), "ISO 4217", allowed=["INR"]),
    col("channel", String(10), "Payment rail", allowed=CHANNELS),
    col("descriptor", String(160), "Raw bank narration"),
    col("counterparty_vpa", String(64), "Counterparty UPI id", null=True),
    col("reference_no", String(24), "RRN/UTR (shared by transfer legs and reversals)", null=True),
    CheckConstraint("amount_paise <> 0", name="nonzero"),
    Index("ix_txn_user_posted", "user_id", "posted_at"),
    Index("ix_txn_account_posted", "account_id", "posted_at"),
    comment="Transaction ledger (append-only).")

budget = table(
    "budget",
    col("budget_id", LONG_ID, "BUD-<user>-<YYYY-MM>-<submitted code>", pk=True,
        rule=r"^BUD-USR-\d{6}-\d{4}-\d{2}-[A-Za-z_]+$"),
    col("version", SmallInteger, "Revision number; highest is effective", pk=True, rule=">= 1"),
    col("user_id", ID, "Profile", fk="user_profile.user_id"),
    col("month", MONTH, "Budget month (IST)", rule=r"^\d{4}-\d{2}$"),
    col("category_code", CODE, "Category AS SUBMITTED; deliberately no FK, resolved by the pipeline"),
    col("amount_paise", BigInteger, "Budget amount", unit="paise", rule="> 0"),
    col("submitted_at", TS, "Submission instant (effective from)"),
    CheckConstraint("amount_paise > 0", name="positive"),
    comment="Budget: monthly household budget per category; revisions are new versions.")

# ---------------------------------------------------------------- ground truth (never read by app.engine)
gt_recurring_truth = table(
    "recurring_truth",
    col("truth_series_id", ID, "Truth series id", pk=True, rule=r"^TRS-\d{6}$"),
    col("user_id", ID, "Profile", fk="user_profile.user_id"),
    col("account_id", ID, "Account", fk="account.account_id"),
    col("series_type", String(12), "Series type", allowed=SERIES_TYPES[:-1]),
    col("counterparty", String(80), "Payee/payer"),
    col("cadence", String(10), "Cadence", allowed=["MONTHLY", "QUARTERLY"]),
    col("start_date", Date, "First occurrence"),
    col("end_date", Date, "Last occurrence if ended", null=True),
    col("status_at_end", String(8), "Status at data end", allowed=["ACTIVE", "ENDED"]),
    schema="gt", comment="Recurring series the generator actually created.")

gt_txn_label = table(
    "txn_label",
    col("txn_id", ID, "Transaction", pk=True, fk="txn.txn_id"),
    col("true_merchant_id", ID, "True merchant (null = long tail)", null=True, fk="merchant.merchant_id"),
    col("true_category_code", CODE, "True category", fk="category.category_code"),
    col("true_kind", String(10), "True kind", allowed=TRUE_KINDS),
    col("true_link_txn_id", ID, "Transfer counterpart / refund or reversal original", null=True,
        fk="txn.txn_id"),
    col("true_series_id", ID, "True recurring series", null=True, fk="gt.recurring_truth.truth_series_id"),
    col("true_local_month", MONTH, "IST month"),
    schema="gt", comment="Ground-truth label for every transaction.")

gt_anomaly = table(
    "anomaly",
    col("anomaly_id", ID, "Anomaly id", pk=True, rule=r"^ANM-\d{6}$"),
    col("issue_type", String(28), "Injected issue", allowed=ISSUE_TYPES),
    col("entity_type", String(8), "Entity kind", allowed=["TXN", "SERIES", "BUDGET"]),
    col("entity_id", LONG_ID, "Primary entity id"),
    col("related_ids", Text, "Pipe-separated related ids", null=True),
    col("expected_decision", String(60), "What a correct system does"),
    col("expected_date", Date, "Expected date (skips/decoys)", null=True),
    col("note", Text, "Human explanation"),
    schema="gt", comment="Deliberately injected edge cases with the expected decision.")

# ---------------------------------------------------------------- pipeline outputs
pipeline_run = table(
    "pipeline_run",
    col("run_id", ID, "Run id", pk=True, rule=r"^RUN-\d{6}$"),
    col("status", String(10), "Run state", allowed=["RUNNING", "SUCCEEDED", "FAILED"]),
    col("started_at", TS, "Start"),
    col("finished_at", TS, "End", null=True),
    col("ruleset_hash", String(64), "SHA-256 of active rules", null=True),
    col("stats", JSONB, "Counters", null=True),
    col("error", Text, "Failure reason", null=True),
    comment="Every pipeline execution. Readers use the latest SUCCEEDED run.")

recurring_series = table(
    "recurring_series",
    col("series_id", ID, "Stable series id", pk=True, rule=r"^REC-\d{6}$"),
    col("user_id", ID, "Profile", fk="user_profile.user_id"),
    col("counterparty_key", String(120), "M:<merchant> | V:<vpa> | D:<descriptor>"),
    col("direction", String(2), "DR/CR", allowed=["DR", "CR"]),
    col("first_run_id", ID, "Run that first detected it", fk="pipeline_run.run_id"),
    UniqueConstraint("user_id", "counterparty_key", "direction"),
    comment="RecurringSeries registry: ids are assigned once and never change across runs.")

txn_enrichment = table(
    "txn_enrichment",
    col("run_id", ID, "Run", fk="pipeline_run.run_id", pk=True),
    col("txn_id", ID, "Transaction", fk="txn.txn_id", pk=True),
    col("user_id", ID, "Owner (denormalized)", fk="user_profile.user_id"),
    col("local_date", Date, "Business date in the household timezone"),
    col("local_month", MONTH, "Business month"),
    col("merchant_id", ID, "Resolved merchant", null=True, fk="merchant.merchant_id"),
    col("category_code", CODE, "Decided category", fk="category.category_code"),
    col("rule_id", ID, "Deciding rule (RUL-… or SYS-…)", null=True),
    col("rule_version", SmallInteger, "Rule version", null=True),
    col("confidence", Numeric(3, 2), "Decision confidence", rule="0..1"),
    col("kind", String(10), "Decided kind", allowed=KINDS),
    col("link_txn_id", ID, "Transfer counterpart / refund or reversal original", null=True, fk="txn.txn_id"),
    col("series_id", ID, "Recurring series", null=True, fk="recurring_series.series_id"),
    col("decision", String(40), "Decision code (RULE, OWN_VPA, TRANSFER_PAIR, REFUND_LINKED, ...)"),
    Index("ix_enr_run_user_month", "run_id", "user_id", "local_month"),
    comment="Per-run decision for every transaction (traceable to rule id + version).")

category_override = table(
    "category_override",
    col("override_id", ID, "Override id", pk=True, rule=r"^OVR-\d{6}$"),
    col("txn_id", ID, "Transaction", fk="txn.txn_id"),
    col("category_code", CODE, "Chosen category", fk="category.category_code"),
    col("actor", String(120), "Who (email)"),
    col("reason", Text, "Why", null=True),
    col("created_at", TS, "When"),
    Index("ix_override_txn_created", "txn_id", "created_at"),
    comment="Human category decisions (append-only; latest wins and locks the txn).")

recurring_series_state = table(
    "recurring_series_state",
    col("run_id", ID, "Run", fk="pipeline_run.run_id", pk=True),
    col("series_id", ID, "Series", fk="recurring_series.series_id", pk=True),
    col("account_id", ID, "Account of latest member", fk="account.account_id"),
    col("merchant_id", ID, "Merchant", null=True, fk="merchant.merchant_id"),
    col("category_code", CODE, "Category", fk="category.category_code"),
    col("series_type", String(12), "Type", allowed=SERIES_TYPES),
    col("cadence", String(10), "Cadence", allowed=["MONTHLY", "QUARTERLY"]),
    col("median_gap_days", SmallInteger, "Median gap", unit="days"),
    col("typical_amount_paise", BigInteger, "Median of the last 3 amounts", unit="paise"),
    col("first_seen", Date, "First occurrence"),
    col("last_seen", Date, "Last occurrence"),
    col("next_expected", Date, "Next expected date", null=True),
    col("status", String(8), "Lifecycle", allowed=["ACTIVE", "MISSED", "ENDED"]),
    col("occurrences", Integer, "Member count"),
    comment="Recurring series state as of a run.")

recurring_series_event = table(
    "recurring_series_event",
    col("run_id", ID, "Run", pk=True),
    col("series_id", ID, "Series", pk=True),
    col("seq", SmallInteger, "Order within the series", pk=True),
    col("event_type", String(16), "Event", allowed=SERIES_EVENTS),
    col("event_date", Date, "When"),
    col("detail", JSONB, "Event data", null=True),
    ForeignKeyConstraint(["run_id", "series_id"],
                         ["recurring_series_state.run_id", "recurring_series_state.series_id"]),
    comment="Recurring series history: detected, amount changed, missed, resumed, ended.")

budget_resolution = table(
    "budget_resolution",
    col("run_id", ID, "Run", fk="pipeline_run.run_id", pk=True),
    col("budget_id", LONG_ID, "Budget", pk=True),
    col("version", SmallInteger, "Effective version", pk=True),
    col("resolved_category_code", CODE, "Taxonomy code used", null=True, fk="category.category_code"),
    col("resolution", String(18), "How the submitted code was resolved", allowed=RESOLUTIONS),
    ForeignKeyConstraint(["budget_id", "version"], ["budget.budget_id", "budget.version"]),
    comment="How each effective budget maps onto the taxonomy in a run.")

insight = table(
    "insight",
    col("insight_id", ID, "INS-<run>-<n>", pk=True, rule=r"^INS-\d{4}-\d{6}$"),
    col("run_id", ID, "Run", fk="pipeline_run.run_id"),
    col("user_id", ID, "Profile", fk="user_profile.user_id"),
    col("month", MONTH, "Month"),
    col("insight_type", String(24), "Type", allowed=INSIGHT_TYPES),
    col("severity", String(5), "Severity", allowed=["INFO", "WARN", "ALERT"]),
    col("category_code", CODE, "Category", null=True, fk="category.category_code"),
    col("metric_paise", BigInteger, "Observed value", null=True, unit="paise"),
    col("baseline_paise", BigInteger, "Comparison value", null=True, unit="paise"),
    col("message", Text, "Human message"),
    col("evidence", JSONB, "Ids backing the insight"),
    Index("ix_insight_run_user_month", "run_id", "user_id", "month"),
    comment="Insight: derived from aggregations, always with evidence ids.")

exception_case = table(
    "exception_case",
    col("exception_id", ID, "Exception id", pk=True, rule=r"^EXC-\d{6}$"),
    col("exception_type", String(28), "Type", allowed=EXCEPTION_TYPES),
    col("entity_type", String(8), "Entity kind", allowed=["TXN", "BUDGET", "SERIES"]),
    col("entity_id", LONG_ID, "Entity id"),
    col("user_id", ID, "Profile", null=True, fk="user_profile.user_id"),
    col("status", String(10), "Lifecycle", allowed=EXCEPTION_STATUSES),
    col("first_run_id", ID, "First seen", fk="pipeline_run.run_id"),
    col("last_run_id", ID, "Last seen", fk="pipeline_run.run_id"),
    col("detail", JSONB, "Context", null=True),
    col("created_at", TS, "Created"),
    col("updated_at", TS, "Last transition"),
    UniqueConstraint("exception_type", "entity_id"),
    Index("ix_exception_status_type", "status", "exception_type"),
    comment="Exception queue for analysts (current state; history in exception_event).")

exception_event = table(
    "exception_event",
    col("exception_id", ID, "Exception", fk="exception_case.exception_id", pk=True),
    col("seq", SmallInteger, "Order", pk=True),
    col("from_status", String(10), "Before", null=True),
    col("to_status", String(10), "After", allowed=EXCEPTION_STATUSES),
    col("actor", String(120), "Who"),
    col("note", Text, "Note", null=True),
    col("at", TS, "When"),
    comment="Exception state transitions (append-only).")

evaluation_run = table(
    "evaluation_run",
    col("run_id", ID, "Evaluated run", fk="pipeline_run.run_id", pk=True),
    col("created_at", TS, "When"),
    col("metrics", JSONB, "All metrics"),
    comment="Metrics of a pipeline run against ground truth.")

anomaly_outcome = table(
    "anomaly_outcome",
    col("run_id", ID, "Run", fk="pipeline_run.run_id", pk=True),
    col("anomaly_id", ID, "Anomaly", fk="gt.anomaly.anomaly_id", pk=True),
    col("outcome", String(8), "Result", allowed=["CAUGHT", "MISSED"]),
    col("observed", Text, "What the system did"),
    comment="Whether each injected anomaly was handled correctly in a run.")

validation_run = table(
    "validation_run",
    col("validation_id", ID, "Id", pk=True, rule=r"^VAL-\d{6}$"),
    col("scope", String(8), "Scope", allowed=["DATASET", "OUTPUTS"]),
    col("created_at", TS, "When"),
    col("passed", Boolean, "All checks passed"),
    col("results", JSONB, "Per-check results"),
    comment="Validation runs over the dataset or pipeline outputs.")

job = table(
    "job",
    col("job_id", ID, "Job id", pk=True, rule=r"^JOB-\d{6}$"),
    col("job_type", String(16), "Type", allowed=JOB_TYPES),
    col("params", JSONB, "Parameters"),
    col("status", String(10), "State", allowed=["QUEUED", "RUNNING", "SUCCEEDED", "FAILED"]),
    col("created_by", String(120), "Requester"),
    col("created_at", TS, "Queued at"),
    col("started_at", TS, "Start", null=True),
    col("finished_at", TS, "End", null=True),
    col("result", JSONB, "Result", null=True),
    col("error", Text, "Error", null=True),
    comment="Admin-triggered background jobs.")

dataset_load = table(
    "dataset_load",
    col("load_id", ID, "Load id", pk=True, rule=r"^DSL-\d{6}$"),
    col("loaded_at", TS, "When"),
    col("scale", String(16), "Scale label"),
    col("seed", BigInteger, "Generator seed"),
    col("manifest_sha256", String(64), "Manifest hash"),
    col("rows", JSONB, "Row counts per table"),
    comment="Dataset (re)loads — each one is an explicit reset.")

app_user = table(
    "app_user",
    col("app_user_id", ID, "Login id", pk=True, rule=r"^APP-\d{6}$"),
    col("email", String(120), "Email (lower-case)", unique=True),
    col("role", String(10), "Role", allowed=ROLES),
    col("profile_user_id", ID, "Linked profile (soft reference so logins survive dataset resets)", null=True),
    col("password_hash", String(200), "argon2 hash for local login", null=True),
    col("firebase_uid", String(128), "Firebase uid", null=True, unique=True),
    col("disabled", Boolean, "Login disabled"),
    col("created_at", TS, "Created"),
    comment="People who can sign in. Roles live here, never in tokens.")

audit_event = table(
    "audit_event",
    col("id", BigInteger, "Sequence", Identity(), pk=True),
    col("at", TS, "When"),
    col("actor", String(120), "Who"),
    col("action", String(60), "What"),
    col("entity_type", String(30), "Entity kind"),
    col("entity_id", LONG_ID, "Entity id"),
    col("request_id", String(64), "Request id", null=True),
    col("detail", JSONB, "Before/after", null=True),
    comment="Append-only audit log of every human or job action.")

INPUT_TABLES = [user_profile, category, category_synonym, merchant, merchant_alias, merchant_category,
                category_rule, account, account_holder, account_event, account_balance_monthly, txn, budget]
GT_TABLES = [gt_recurring_truth, gt_txn_label, gt_anomaly]
OUTPUT_TABLES = [pipeline_run, recurring_series, txn_enrichment, category_override, recurring_series_state,
                 recurring_series_event, budget_resolution, insight, exception_case, exception_event,
                 evaluation_run, anomaly_outcome]
OPERATIONAL_TABLES = [validation_run, job, dataset_load, app_user, audit_event]
TABLES = {t.name: t for t in INPUT_TABLES + GT_TABLES + OUTPUT_TABLES + OPERATIONAL_TABLES}


def columns(t: Table) -> list[str]:
    return [c.name for c in t.columns]
