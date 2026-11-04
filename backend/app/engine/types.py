"""Engine value types. The engine is pure: it never reads ground truth and never touches the database."""
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(slots=True, frozen=True)
class Txn:
    txn_id: str
    user_id: str
    account_id: str
    account_type: str
    posted_at: datetime
    amount_paise: int
    channel: str
    descriptor: str
    counterparty_vpa: str | None = None
    reference_no: str | None = None


@dataclass(slots=True, frozen=True)
class Category:
    code: str
    kind: str
    effective_from: date
    effective_to: date | None = None
    replaced_by: str | None = None
    name: str = ""

    def active_in(self, month: str) -> bool:
        start = date(int(month[:4]), int(month[5:7]), 1)
        return self.effective_from <= start and (self.effective_to is None or self.effective_to >= start)


@dataclass(slots=True)
class Enriched:
    txn: Txn
    norm: str
    local_date: date
    local_month: str
    merchant_id: str | None = None
    category_code: str = "UNCATEGORIZED"
    rule_id: str | None = None
    rule_version: int | None = None
    confidence: float = 0.0
    kind: str = "UNKNOWN"
    link_txn_id: str | None = None
    series_key: tuple[str, str, str] | None = None
    decision: str = "NO_RULE"
    locked: bool = False


def kind_for(category_kind: str, amount_paise: int) -> str:
    """Kind from the category's kind and the sign: an expense-category credit is a refund."""
    if category_kind in ("TRANSFER", "INCOME", "UNKNOWN"):
        return category_kind
    return "EXPENSE" if amount_paise < 0 else "REFUND"
