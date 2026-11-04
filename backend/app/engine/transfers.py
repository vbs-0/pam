"""Pair the two legs of money moving between a household's own accounts (self transfers, card bill payments)."""
from collections import defaultdict
from datetime import timedelta

from app.engine.types import Category, Enriched

CREDIT_OK = {"UNCATEGORIZED", "OTHER_INCOME"}


def match_transfers(items: list[Enriched], categories: dict[str, Category], window_days: int = 3,
                    early_days: int = 1) -> int:
    """Pair debit/credit legs between different accounts of the same user: equal |amount|, credit within
    [-early, +window] days of the debit (E08: banks sometimes post the credit first). Greedy by smallest gap so
    two identical transfers pair one-to-one (E07); each leg is used once. Returns the number of pairs."""
    window, early = timedelta(days=window_days), timedelta(days=early_days)
    debits: dict[str, list[Enriched]] = defaultdict(list)
    credits: dict[str, dict[int, list[Enriched]]] = defaultdict(lambda: defaultdict(list))
    for e in items:
        if e.locked or e.kind in ("REVERSAL", "REFUND"):
            continue
        ckind = categories[e.category_code].kind
        if e.txn.amount_paise < 0 and (ckind == "TRANSFER" or e.category_code == "UNCATEGORIZED"):
            debits[e.txn.user_id].append(e)
        elif e.txn.amount_paise > 0 and (ckind == "TRANSFER" or e.category_code in CREDIT_OK):
            credits[e.txn.user_id][e.txn.amount_paise].append(e)
    pairs = 0
    for user, ds in debits.items():
        edges = []
        for d in ds:
            for c in credits[user].get(-d.txn.amount_paise, ()):
                if c.txn.account_id == d.txn.account_id:          # E06: one account cannot transfer to itself
                    continue
                gap = c.txn.posted_at - d.txn.posted_at
                if -early <= gap <= window:
                    edges.append((abs(gap), d.txn.txn_id, c.txn.txn_id, d, c))
        edges.sort(key=lambda x: x[:3])
        used: set[str] = set()
        for _, did, cid, d, c in edges:
            if did in used or cid in used:
                continue
            used.update((did, cid))
            card = "CREDIT_CARD" in (d.txn.account_type, c.txn.account_type)
            for x, other in ((d, cid), (c, did)):
                x.category_code = "CC_BILL_PAYMENT" if card else "SELF_TRANSFER"
                x.kind, x.link_txn_id, x.decision = "TRANSFER", other, "TRANSFER_PAIR"
                x.rule_id, x.rule_version, x.confidence = "SYS-PAIR", None, max(x.confidence, 0.95)
            pairs += 1
    return pairs
