"""Link failed-payment reversals and merchant refunds to the purchase they undo."""
import re
from collections import defaultdict
from datetime import timedelta

from app.engine.types import Category, Enriched

REFUND_HINT = re.compile(r"\b(refund|rfnd|reversal|rvsl|rev)\b")


def link_refunds(items: list[Enriched], categories: dict[str, Category], window_days: int = 90) -> dict:
    out = {"reversals": 0, "linked": 0, "orphans": 0}
    # 1) UPI reversals (E10): same account, same RRN, equal amount, credit after the debit
    debit_by_ref = {(e.txn.account_id, e.txn.reference_no): e for e in items
                    if e.txn.amount_paise < 0 and e.txn.reference_no and not e.locked and e.kind != "TRANSFER"}
    for c in items:
        if c.locked or c.kind == "TRANSFER" or c.txn.amount_paise <= 0 or not c.txn.reference_no:
            continue
        d = debit_by_ref.get((c.txn.account_id, c.txn.reference_no))
        if d is None or d.txn.amount_paise != -c.txn.amount_paise or d.txn.posted_at > c.txn.posted_at:
            continue
        c.category_code, c.merchant_id = d.category_code, c.merchant_id or d.merchant_id
        for x, other in ((d, c.txn.txn_id), (c, d.txn.txn_id)):
            x.kind, x.link_txn_id, x.decision = "REVERSAL", other, "UPI_REVERSAL"
        out["reversals"] += 1

    # 2) Refunds: a merchant credit (or one worded as a refund) undoes an earlier purchase at that merchant.
    #    Prefer the purchase whose unrefunded remainder equals the credit on the same account, then the latest
    #    purchase with enough remainder left (partial refunds, E11 over-refunds become orphans).
    window = timedelta(days=window_days)
    purchases: dict[tuple[str, str], list[Enriched]] = defaultdict(list)
    for e in items:
        if e.txn.amount_paise < 0 and e.kind == "EXPENSE" and e.merchant_id:
            purchases[(e.txn.user_id, e.merchant_id)].append(e)
    remaining = {p.txn.txn_id: -p.txn.amount_paise for lst in purchases.values() for p in lst}
    credits = [e for e in items if not e.locked and e.txn.amount_paise > 0 and e.kind not in ("TRANSFER", "REVERSAL")
               and ((e.merchant_id and categories[e.category_code].kind == "EXPENSE") or REFUND_HINT.search(e.norm))]
    credits.sort(key=lambda x: (x.txn.posted_at, x.txn.txn_id))
    for c in credits:
        amount, best, best_key = c.txn.amount_paise, None, None
        for p in purchases.get((c.txn.user_id, c.merchant_id), ()):
            gap = c.txn.posted_at - p.txn.posted_at
            if gap <= timedelta(0) or gap > window or remaining[p.txn.txn_id] < amount:
                continue
            key = (remaining[p.txn.txn_id] != amount, p.txn.account_id != c.txn.account_id, gap, p.txn.txn_id)
            if best_key is None or key < best_key:
                best, best_key = p, key
        c.kind = "REFUND"
        if best:
            remaining[best.txn.txn_id] -= amount
            c.category_code, c.link_txn_id, c.decision = best.category_code, best.txn.txn_id, "REFUND_LINKED"
            out["linked"] += 1
        else:
            if categories[c.category_code].kind != "EXPENSE":    # E12: no expense bucket to net against
                c.category_code = "UNCATEGORIZED"
            c.decision = "REFUND_ORPHAN"
            out["orphans"] += 1
    return out
