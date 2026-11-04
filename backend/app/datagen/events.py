"""Internal event record used while generating the ledger (becomes a txn row + a truth label)."""
import itertools
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class Ev:
    key: int
    user_id: str
    account_id: str
    local_dt: datetime          # naive IST wall-clock time
    amount: int                 # signed paise
    channel: str
    descriptor: str
    vpa: str | None
    ref: str | None
    true_merchant: str | None
    true_category: str
    true_kind: str
    link_key: int | None = None
    series: int | None = None   # plan number of the truth series
    tags: set[str] = field(default_factory=set)


class Keys:
    """Monotonic event keys; generation order is deterministic so keys (and refs derived from them) are too."""

    def __init__(self) -> None:
        self._c = itertools.count(1)

    def __call__(self) -> int:
        return next(self._c)
