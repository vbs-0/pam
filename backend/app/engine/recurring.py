"""Recurring series detection: group by counterparty, test cadence and amount stability, emit lifecycle events.

A group is one (user, counterparty key, direction). The key includes the account, category and channel, so one
merchant can run two independent series (Airtel broadband via BBPS and Airtel prepaid via UPI, D30/E32) and an
Amazon Prime subscription does not merge with ordinary Amazon shopping.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median

from app.engine.normalize import strip_variable
from app.engine.types import Enriched

SERIES_TYPE = {"SALARY": "SALARY", "RENT": "RENT", "SUBSCRIPTIONS": "SUBSCRIPTION", "EMI_LOANS": "EMI",
               "UTILITIES": "UTILITY", "INTEREST": "INTEREST"}
VARIABLE_TOL = {"UTILITIES": 0.6, "INTEREST": float("inf")}  # bills vary; interest follows the balance (E17)
CANDIDATE_KINDS = {"EXPENSE", "INCOME", "UNKNOWN"}


@dataclass(slots=True)
class DetectedSeries:
    key: tuple[str, str, str]
    account_id: str
    merchant_id: str | None
    category_code: str
    series_type: str
    cadence: str
    median_gap_days: int
    typical_amount_paise: int
    first_seen: date
    last_seen: date
    next_expected: date | None
    status: str
    member_txn_ids: list[str]
    events: list[tuple[str, date, dict]] = field(default_factory=list)


def counterparty_key(e: Enriched) -> str:
    if e.merchant_id:
        who = f"M:{e.merchant_id}"
    elif e.txn.counterparty_vpa:
        who = f"V:{e.txn.counterparty_vpa.lower()}"
    else:
        who = "D:" + strip_variable(e.norm)[:60]
    return f"{e.txn.account_id}|{who}|{e.category_code}|{e.txn.channel}"


def detect_recurring(items: list[Enriched], data_end: date, rent_min_paise: int = 500_000,
                     closed: dict[str, date] | None = None) -> list[DetectedSeries]:
    groups: dict[tuple[str, str, str], list[Enriched]] = defaultdict(list)
    for e in items:
        if e.kind in CANDIDATE_KINDS:
            groups[(e.txn.user_id, counterparty_key(e), "DR" if e.txn.amount_paise < 0 else "CR")].append(e)
    found = []
    for key in sorted(groups):
        g = sorted(groups[key], key=lambda x: (x.local_date, x.txn.txn_id))
        s = _analyse(key, g, data_end, rent_min_paise, (closed or {}).get(g[0].txn.account_id))
        if s:
            found.append(s)
    return found


def _analyse(key, g, data_end: date, rent_min: int, closed_on: date | None) -> DetectedSeries | None:
    if len(g) < 3:                                              # E21: two payments are not a pattern yet
        return None
    gaps = [(b.local_date - a.local_date).days for a, b in zip(g, g[1:], strict=False)]
    med = median(gaps)
    cadence = "MONTHLY" if 25 <= med <= 35 else "QUARTERLY" if 80 <= med <= 100 else None
    if cadence is None or min(gaps) < 0.5 * med:               # E18: frequent merchants are not series
        return None
    if sum(0.6 * med <= x <= 1.4 * med for x in gaps) < 0.7 * len(gaps):
        return None
    amounts = [abs(e.txn.amount_paise) for e in g]
    cat = Counter(e.category_code for e in g).most_common(1)[0][0]
    tol = VARIABLE_TOL.get(cat, 0.15)
    pairs = list(zip(amounts, amounts[1:], strict=False))
    if sum(abs(b - a) <= tol * a for a, b in pairs) < 0.8 * len(pairs):
        return None
    gap = timedelta(days=round(med))
    events: list[tuple[str, date, dict]] = [("DETECTED", g[0].local_date, {})]
    for (a, b), (pa, pb) in zip(zip(g, g[1:], strict=False), pairs, strict=True):
        if cat not in VARIABLE_TOL and abs(pb - pa) > 0.05 * pa:              # E16: one-step price change
            events.append(("AMOUNT_CHANGED", b.local_date, {"from_paise": pa, "to_paise": pb}))
        d = (b.local_date - a.local_date).days
        if d >= 1.6 * med:                                                    # ★A3 / E15: one MISSED per gap
            for k in range(1, max(1, round(d / med) - 1) + 1):
                events.append(("MISSED", a.local_date + gap * k, {}))
            events.append(("RESUMED", b.local_date, {}))
    since = (data_end - g[-1].local_date).days
    nxt: date | None = g[-1].local_date + gap
    if closed_on is not None:                                  # E31: the account itself closed
        status, nxt = "ENDED", None
        events.append(("ENDED", closed_on, {"reason": "account closed"}))
    elif since > 2.5 * med:
        status, nxt = "ENDED", None
        events.append(("ENDED", g[-1].local_date + gap, {}))
    elif since > 1.6 * med:                                    # E20: late, not yet given up on
        status = "MISSED"
        events.append(("MISSED", g[-1].local_date + gap, {}))
    else:
        status = "ACTIVE"
    events.sort(key=lambda ev: ev[1])
    stype = SERIES_TYPE.get(cat)
    if stype is None:
        rentlike = (cat == "UNCATEGORIZED" and key[2] == "DR" and cadence == "MONTHLY"
                    and median(amounts) >= rent_min and not any(e.locked for e in g))
        if rentlike:                                           # E19: monthly P2P to the same person is rent
            stype, cat = "RENT", "RENT"
            for e in g:
                e.category_code, e.kind, e.confidence, e.decision = "RENT", "EXPENSE", 0.7, "RECUR_RENT"
                e.rule_id, e.rule_version = "SYS-RECUR-RENT", None
        else:
            stype = "OTHER"
    for e in g:
        e.series_key = key
    return DetectedSeries(key, g[-1].txn.account_id, g[-1].merchant_id, cat, stype, cadence, round(med),
                          int(median(amounts[-3:])), g[0].local_date, g[-1].local_date, nxt, status,
                          [e.txn.txn_id for e in g], events)
