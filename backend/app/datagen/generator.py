"""Synthetic dataset assembly: households → plans → events → exact volume → balances → ids, labels, budgets.

``generate`` is pure and deterministic for a given ``GenParams``; the writer (``writer.py``) turns the
returned rows into CSV/JSON/SQL files.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from app import ids
from app.datagen.anomalies import Draft, inject_budgets, inject_ledger, plan_series_anomalies
from app.datagen.budgets import make_budgets
from app.datagen.catalog import CATEGORIES, MERCHANTS, SYNONYMS, seed_rules
from app.datagen.events import Ev, Keys
from app.datagen.ledger import card_payments, planned_rows, self_transfers, settle
from app.datagen.people import UserCtx, make_users, master_rows
from app.datagen.rand import Rand
from app.datagen.schedules import Plan, make_plans, materialize
from app.datagen.spending import ADD_CATS, Spender, split, user_weight
from app.timeutil import ist_to_utc, month_key

SCALES = {"starter": (50, 25_000), "full": (1_000, 500_000)}
RULES_FROM = datetime(2025, 12, 1, tzinfo=UTC)
FOLLOWUP_RATE = 0.016    # refunds + reversals + same-day duplicates per purchase (measured), corrected exactly later


@dataclass(frozen=True)
class GenParams:
    users: int
    transactions: int
    seed: int = 20261022
    year: int = 2026

    @classmethod
    def for_scale(cls, name: str, seed: int = 20261022) -> "GenParams":
        users, txns = SCALES[name]
        return cls(users, txns, seed)


@dataclass
class Dataset:
    tables: dict[str, list[tuple]]
    truth: dict[str, list[tuple]]
    params: GenParams


def _card_rows_estimate(u: UserCtx) -> int:
    c = u.card
    if c is None:
        return 0
    months = sum(1 for m in range(1, 12) if c.opened_on <= date(2026, m, 28))
    return 2 * (months + (c.opened_on < date(2026, 1, 1)))


def _adjust(events: list[Ev], target: int, users: list[UserCtx], spenders: dict[str, Spender], keys: Keys,
            seed: int) -> list[Ev]:
    """Hit the exact volume (D09) by removing or adding standalone savings UPI purchases only."""
    r = Rand(f"{seed}:global:adjust")
    diff = target - len(events)
    if diff < 0:
        cands = sorted((e for e in events if "adjustable" in e.tags), key=lambda e: e.key)
        if len(cands) < -diff:
            raise ValueError("not enough adjustable purchases to reach the exact volume")
        drop = {e.key for e in r.sample(cands, -diff)}
        events = [e for e in events if e.key not in drop]
    for _ in range(max(diff, 0)):
        u = r.choice(users)
        events += spenders[u.user_id].purchase(r, r.randint(1, 12), keys, cat=r.choice(ADD_CATS), force_upi=True,
                                               followups=False)
    return events


def _catalog_tables() -> dict[str, list[tuple]]:
    return {
        "category": sorted((c.code, c.name, c.group, c.kind, c.effective_from, c.effective_to, c.replaced_by)
                           for c in CATEGORIES),
        "category_synonym": sorted(SYNONYMS.items()),
        "merchant": sorted((m.merchant_id, m.name, m.category, m.vpa, m.online) for m in MERCHANTS),
        "merchant_alias": sorted((a, m.merchant_id) for m in MERCHANTS for a in m.aliases),
        "merchant_category": sorted((m.merchant_id, c) for m in MERCHANTS for c in (m.category, *m.extra_categories)),
        "category_rule": [(x["rule_id"], x["version"], x["priority"], x["category_code"], x["merchant_id"],
                           x["pattern"], x["channel"], x["direction"], x["account_type"], Decimal(str(x["confidence"])),
                           RULES_FROM, None, "system", x["note"]) for x in seed_rules()],
    }


def generate(p: GenParams) -> Dataset:
    if p.year != 2026:
        raise ValueError("the holiday calendar and seasonality cover 2026 only")
    seed, users = p.seed, make_users(p.users, p.seed)
    keys = Keys()
    plans: list[Plan] = [pl for u in users for pl in make_plans(u, seed)]
    for i, pl in enumerate(plans, 1):
        pl.plan_no = i
    drafts: list[Draft] = plan_series_anomalies(plans, seed, p.users)
    events = materialize(plans, keys, seed)
    spenders = {u.user_id: Spender(u, seed) for u in users}
    for u in users:
        events += spenders[u.user_id].extras(keys)
        events += self_transfers(u, keys, seed)

    fixed_tail = planned_rows(users)
    room = p.transactions - len(events) - fixed_tail - sum(_card_rows_estimate(u) for u in users)
    n_purchases = round(room / (1 + FOLLOWUP_RATE))
    if n_purchases < 12 * p.users:
        raise ValueError(f"{p.transactions} transactions is too few for {p.users} households")
    if p.users >= 500_000:
        raise ValueError("synthetic households must stay below USR-500001 (real households start there)")
    for u, q in zip(users, split(n_purchases, [user_weight(u, seed) for u in users]), strict=True):
        sp = spenders[u.user_id]
        for m, n in enumerate(split(q, sp.month_weights()), 1):
            events += sp.month(m, n, keys)

    on_card: dict[str, list[Ev]] = defaultdict(list)
    cards = {u.card.account_id for u in users if u.card}
    for e in events:
        if e.account_id in cards:
            on_card[e.account_id].append(e)
    for u in users:
        if u.card:
            events += card_payments(u, on_card[u.card.account_id], keys, seed)

    drafts += inject_ledger(events, users, seed, p.users)
    events = _adjust(events, p.transactions - fixed_tail, users, spenders, keys, seed)
    plans += settle(users, events, keys, seed, plan_no=len(plans) + 1)
    if len(events) != p.transactions:
        raise AssertionError(f"volume {len(events)} != {p.transactions}")

    # ids: chronological (IST and UTC order agree: fixed offset), ties by account then generation order
    events.sort(key=lambda e: (e.local_dt, e.account_id, e.key))
    txn_of = {e.key: ids.txn_id(e.local_dt.year, i) for i, e in enumerate(events, 1)}
    truth_plans = sorted((pl for pl in plans if len(pl.live()) >= 3),
                         key=lambda pl: (pl.user_id, pl.account_id, pl.series_type, pl.counterparty, pl.plan_no))
    trs = {pl.plan_no: ids.seq("TRS", i) for i, pl in enumerate(truth_plans, 1)}

    txn_rows, labels = [], []
    flows: dict[tuple[str, int], list[int]] = defaultdict(lambda: [0, 0])
    spend: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for e in events:
        tid = txn_of[e.key]
        txn_rows.append((tid, e.account_id, e.user_id, ist_to_utc(e.local_dt), e.amount, "INR", e.channel,
                         e.descriptor, e.vpa, e.ref))
        labels.append((tid, e.true_merchant, e.true_category, e.true_kind,
                       txn_of[e.link_key] if e.link_key is not None else None, trs.get(e.series),
                       month_key(e.local_dt)))
        flows[(e.account_id, e.local_dt.month)][e.amount < 0] += e.amount
        if e.true_kind in ("EXPENSE", "REFUND"):
            spend[e.user_id][e.true_category] -= e.amount
    del events

    balances = []
    for u in users:
        for a in u.accounts:
            first = 1 if a.opened_on < date(2026, 1, 1) else a.opened_on.month
            bal = a.opening_balance
            for m in range(first, (a.closed_on.month if a.closed_on else 12) + 1):
                cr, dr = flows.get((a.account_id, m), (0, 0))
                balances.append((a.account_id, f"2026-{m:02d}", bal, cr, dr, bal + cr + dr))
                bal += cr + dr

    budget_rows = [row for u in users for row in make_budgets(u, spend[u.user_id], seed)]
    budget_rows, budget_drafts = inject_budgets(budget_rows, users, seed, p.users)
    drafts += budget_drafts

    def resolve(d: Draft) -> tuple:
        if d.entity_type == "TXN":
            ent, rel = txn_of[d.entity], txn_of[d.related] if d.related is not None else None
        elif d.entity_type == "SERIES":
            ent, rel = trs[d.entity], None
        else:
            ent, rel = d.entity, None
        return d.issue_type, d.entity_type, ent, rel, d.expected, d.expected_date, d.note

    anomalies = sorted((resolve(d) for d in drafts), key=lambda a: (a[0], a[2]))
    recurring = []
    for pl in truth_plans:
        live = pl.live()
        recurring.append((trs[pl.plan_no], pl.user_id, pl.account_id, pl.series_type, pl.counterparty, pl.cadence,
                          live[0].when, live[-1].when if pl.ended else None, "ENDED" if pl.ended else "ACTIVE"))

    tables = {**_catalog_tables(), **master_rows(users)}
    tables["account_balance_monthly"] = sorted(balances)
    tables["txn"] = txn_rows
    tables["budget"] = sorted(budget_rows, key=lambda b: (b[0], b[1]))
    truth = {"recurring_truth": recurring, "txn_label": labels,
             "anomaly": [(ids.seq("ANM", i), *a) for i, a in enumerate(anomalies, 1)]}
    return Dataset(tables, truth, p)
