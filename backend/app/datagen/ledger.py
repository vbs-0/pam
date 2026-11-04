"""Money movement between a household's own accounts and the values derived from the ledger.

Self transfers, credit-card statements and their bill payments, opening balances that keep savings
accounts solvent, quarterly savings interest and the balance sweep when an account is closed.
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from app.datagen import descriptors as dsc
from app.datagen.catalog import BANK_BY_CODE, CRED_ID, MERCHANT_BY_ID
from app.datagen.events import Ev, Keys
from app.datagen.people import AccountCtx, UserCtx
from app.datagen.rand import Rand
from app.datagen.schedules import Occ, Plan

QUARTERS = [(date(2026, 1, 1), date(2026, 3, 31)), (date(2026, 4, 1), date(2026, 6, 30)),
            (date(2026, 7, 1), date(2026, 9, 30)), (date(2026, 10, 1), date(2026, 12, 31))]
FLOOR = 100_000          # savings balances never dip below Rs 1,000
CRED = MERCHANT_BY_ID[CRED_ID]


def _pair(k1: int, k2: int, user: str, debit_acct: str, credit_acct: str, t1: datetime, t2: datetime, amount: int,
          channel: str, d_desc: str, c_desc: str, ref: str, category: str, tag: str, *, c_channel: str | None = None,
          d_vpa: str | None = None, d_merchant: str | None = None) -> list[Ev]:
    d = Ev(k1, user, debit_acct, t1, -amount, channel, d_desc, d_vpa, ref, d_merchant, category, "TRANSFER",
           link_key=k2, tags={tag})
    c = Ev(k2, user, credit_acct, t2, amount, c_channel or channel, c_desc, None, ref, None, category, "TRANSFER",
           link_key=k1, tags={tag})
    return [d, c]


def self_transfers(u: UserCtx, keys: Keys, seed: int) -> list[Ev]:
    sec = u.secondary
    if sec is None:
        return []
    r, out = Rand(f"{seed}:{u.user_id}:self"), []
    for m in range(1, 13):
        for _ in range(r.randint(1, 3)):
            d = date(2026, m, r.randint(1, 28))
            if not sec.open_on(d):
                continue
            src, dst = (u.primary, sec) if r.chance(.7) else (sec, u.primary)
            amount = r.randint(2, 100) * 50_000                       # Rs 1,000-50,000 in Rs 500 steps
            t1 = datetime.combine(d, time(r.randint(8, 21), r.randint(0, 59), r.randint(0, 59)))
            k1, k2 = keys(), keys()
            ref = dsc.ref_for(k1, seed)
            t2 = t1 + timedelta(minutes=r.randint(0, 20))
            out += _pair(k1, k2, u.user_id, src.account_id, dst.account_id, t1, t2, amount, "IMPS",
                         dsc.imps_self(True, ref, dst.bank_code, dst.last4),
                         dsc.imps_self(False, ref, src.bank_code, src.last4), ref, "SELF_TRANSFER", "self_transfer")
    return out


def card_payments(u: UserCtx, card_events: list[Ev], keys: Keys, seed: int) -> list[Ev]:
    """Statement of IST month m = card spend net of refunds in m; paid on day 3-7 of m+1 (Dec is unpaid, D06).
    Sets the card's opening outstanding (Dec 2025 statement, paid in January, D07)."""
    card = u.card
    if card is None:
        return []
    r = Rand(f"{seed}:{u.user_id}:card")
    stmt = defaultdict(int)
    for e in card_events:
        stmt[e.local_dt.month] -= e.amount
    dues: list[tuple[int, int]] = []          # (month the payment is made, amount)
    if card.opened_on < date(2026, 1, 1):
        positive = [v for v in stmt.values() if v > 0]
        opening = int(sum(positive) / len(positive) * r.uniform(.6, 1.2)) if positive else 0
        card.opening_balance = -opening
        dues.append((1, opening))
    dues += [(m + 1, stmt[m]) for m in range(1, 12)]
    out: list[Ev] = []
    for pay_month, amount in dues:
        if amount <= 0:                        # nothing owed, or only refunds (D05)
            continue
        t1 = datetime(2026, pay_month, r.randint(3, 7), r.randint(10, 19), r.randint(0, 59), r.randint(0, 59))
        if t1.date() < card.opened_on:
            continue
        k1, k2 = keys(), keys()
        ref = dsc.ref_for(k1, seed)
        if r.chance(.6):
            ch, desc, vpa, merchant = "IMPS", dsc.cc_bill(card.bank_code, card.last4, ref), None, None
        else:
            ch, desc, vpa, merchant = "UPI", dsc.upi(True, ref, "CRED", CRED.vpa, "Credit card bill"), CRED.vpa, CRED_ID
        out += _pair(k1, k2, u.user_id, u.primary.account_id, card.account_id, t1,
                     t1 + timedelta(minutes=r.randint(0, 240)), amount, ch, desc, dsc.card_payment_received(ref), ref,
                     "CC_BILL_PAYMENT", "cc_payment", c_channel="INTERNAL", d_vpa=vpa, d_merchant=merchant)
    return out


def interest_quarters(a: AccountCtx) -> list[tuple[date, date]]:
    """No interest for the quarter in which the account closes (D08)."""
    return [q for q in QUARTERS if a.open_on(q[1])]


def planned_rows(users: list[UserCtx]) -> int:
    """Rows settle() will add: one interest credit per savings account per quarter, two per closure sweep."""
    return sum(len(interest_quarters(a)) + (2 if a.closed_on else 0)
               for u in users for a in u.accounts if a.account_type == "SAVINGS")


def _order(e: Ev):
    return e.local_dt, e.key


def settle(users: list[UserCtx], events: list[Ev], keys: Keys, seed: int, plan_no: int) -> list[Plan]:
    """Opening balances, interest and closure sweeps. Appends to ``events``; returns interest truth plans."""
    by_acc: dict[str, list[Ev]] = defaultdict(list)
    for e in events:
        by_acc[e.account_id].append(e)
    plans: list[Plan] = []
    for u in users:
        r = Rand(f"{seed}:{u.user_id}:balance")
        savings = [a for a in u.accounts if a.account_type == "SAVINGS"]
        for a in savings:                                         # D04: derived opening balance
            run = low = 0
            for e in sorted(by_acc[a.account_id], key=_order):
                run += e.amount
                low = min(low, run)
            share = r.uniform(1.5, 4) if a.kind == "PRIMARY" else r.uniform(.3, 1.5)
            opening = -(-int(u.income_paise * share) // 100_000) * 100_000
            a.opening_balance = max(opening, FLOOR - low)
        for a in sorted(savings, key=lambda a: a.closed_on is None):   # closing accounts first: sweeps feed primary
            plan = Plan(u.user_id, a.account_id, "INTEREST", BANK_BY_CODE[a.bank_code][1], "QUARTERLY", "INTEREST",
                        None, "INTERNAL", "interest", {}, ended=a.closed_on is not None, plan_no=plan_no)
            plan_no += 1
            delta: dict[date, int] = defaultdict(int)
            for e in by_acc[a.account_id]:
                delta[e.local_dt.date()] += e.amount
            bal, d = a.opening_balance, date(2026, 1, 1)
            for qs, qe in interest_quarters(a):
                total = 0
                while d <= qe:                                     # sum of end-of-day balances
                    bal += delta.get(d, 0)
                    total += bal
                    d += timedelta(days=1)
                amount = max((total * 3 + 18_250) // 36_500, 100)   # 3% p.a. on daily balance, min Rs 1
                k = keys()
                ev = Ev(k, u.user_id, a.account_id, datetime.combine(qe, time(20)), amount, "INTERNAL",
                        dsc.interest(qs, qe), None, dsc.ref_for(k, seed), None, "INTEREST", "INCOME",
                        series=plan.plan_no, tags={"interest"})
                events.append(ev)
                by_acc[a.account_id].append(ev)
                bal += amount
                plan.occ.append(Occ(qe, amount, time(20)))
            plans.append(plan)
            if a.closed_on:                                        # D03: sweep the balance, close at exactly 0
                balance = a.opening_balance + sum(e.amount for e in by_acc[a.account_id])
                p = u.primary
                t = datetime.combine(a.closed_on, time(10))
                k1, k2 = keys(), keys()
                ref = dsc.ref_for(k1, seed)
                legs = _pair(k1, k2, u.user_id, a.account_id, p.account_id, t, t + timedelta(minutes=1), balance,
                             "IMPS", dsc.imps_self(True, ref, p.bank_code, p.last4),
                             dsc.imps_self(False, ref, a.bank_code, a.last4), ref, "SELF_TRANSFER", "self_transfer")
                for e in legs:
                    e.tags.add("sweep")
                    events.append(e)
                    by_acc[e.account_id].append(e)
    return plans
