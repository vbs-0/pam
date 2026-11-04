"""Render docs/data_dictionary.md from the schema metadata (never edited by hand)."""
from sqlalchemy.dialects import postgresql

from app import schema

HEADER = "| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |"

CARDINALITY = """\
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
"""


def _unique(t, c) -> str:
    if c.primary_key:
        return "PK" if len(t.primary_key.columns) == 1 else "PK (composite)"
    return "yes" if c.unique else ""


def _validation(c) -> str:
    parts = [c.info.get("rule") or ""]
    parts += [f"FK → `{fk.column.table.fullname}.{fk.column.name}`" for fk in c.foreign_keys]
    return "; ".join(p for p in parts if p).replace("|", "\\|")


def render_data_dictionary() -> str:
    out = ["# Data Dictionary", "",
           "Generated from `backend/app/schema.py` by `python -m app.cli docs` — do not edit by hand.", "",
           "Conventions: money is signed integer **paise** (₹1 = 100 paise; debit < 0, credit > 0). "
           "Timestamps are UTC (`timestamptz`); business dates and months are in the household timezone "
           "(Asia/Kolkata). Enumerations are TEXT columns with CHECK constraints.", "",
           "## Cardinality", "", CARDINALITY]
    groups = [("Inputs and master data", schema.INPUT_TABLES), ("Ground truth (`gt` schema)", schema.GT_TABLES),
              ("Pipeline outputs", schema.OUTPUT_TABLES), ("Operational", schema.OPERATIONAL_TABLES)]
    for title, tables in groups:
        out += [f"## {title}", ""]
        for t in tables:
            out += [f"### `{t.fullname}`", "", t.comment or "", "", HEADER, "|" + "---|" * 8]
            for c in t.columns:
                typ = c.type.compile(dialect=postgresql.dialect())
                allowed = ", ".join(map(str, c.info.get("allowed") or []))
                out.append(f"| `{c.name}` | {typ} | {'no' if c.nullable else 'yes'} | {allowed} | "
                           f"{c.info.get('unit') or ''} | {_unique(t, c)} | {_validation(c)} | {c.info['desc']} |")
            out.append("")
    out += ["## Foreign keys", ""]
    for t in schema.metadata.sorted_tables:
        for fk in sorted(t.foreign_keys, key=lambda f: f.parent.name):
            out.append(f"- `{t.fullname}.{fk.parent.name}` → `{fk.column.table.fullname}.{fk.column.name}`"
                       f" ({'optional' if fk.parent.nullable else 'required'})")
    return "\n".join(out) + "\n"
