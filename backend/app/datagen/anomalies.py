"""Labelled edge cases from the brief, injected into otherwise clean data.

Every injection is count-neutral (it rewrites, moves or deletes a planned occurrence) and is recorded as a
draft that the generator turns into a ``gt.anomaly`` row with the decision a correct pipeline must make.
Selections use one global stream per issue type over key-sorted candidates, so they are reproducible.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app import ids
from app.datagen import descriptors as dsc
from app.datagen.budgets import submitted
from app.datagen.catalog import CRED_ID, MERCHANT_BY_ID, REMAP_VARIANTS, UNKNOWN_BUDGET_CODES
from app.datagen.events import Ev
from app.datagen.people import PERIOD_END, UserCtx
from app.datagen.rand import Rand
from app.datagen.schedules import Plan

RATES = {"TRANSFER_DOUBLE_COUNT": .4, "REFUND_AS_EXPENSE": .5, "RECURRING_SKIP": .12, "RECURRING_NOT_SKIP": .24,
         "TZ_BOUNDARY": .4, "BUDGET_REMAP": .15, "BUDGET_UNKNOWN": .05}
SKIPPABLE = ("RENT", "SUBSCRIPTION", "EMI")
REFUND_WORDS = ("refund", "rev", "rfnd")
CRED = MERCHANT_BY_ID[CRED_ID]


@dataclass
class Draft:
    issue_type: str
    entity_type: str          # TXN | SERIES | BUDGET
    entity: object            # event key | plan number | budget id
    related: object | None    # event key
    expected: str
    expected_date: date | None
    note: str


def count(issue: str, n_users: int) -> int:
    return max(1, round(RATES[issue] * n_users))


def _rnd(seed: int, issue: str) -> Rand:
    return Rand(f"{seed}:global:anomaly:{issue}")


def plan_series_anomalies(plans: list[Plan], seed: int, n_users: int) -> list[Draft]:
    """True skips and late-but-present decoys, applied to plans before they become ledger events."""
    eligible = sorted((p for p in plans if p.series_type in SKIPPABLE and len(p.occ) >= 8), key=lambda p: p.plan_no)
    r = _rnd(seed, "RECURRING_SKIP")
    skips = r.sample(eligible, min(count("RECURRING_SKIP", n_users), len(eligible)))
    drafts = []
    for p in sorted(skips, key=lambda p: p.plan_no):
        o = p.occ[r.randint(3, len(p.occ) - 4)]          # never the first or last three: still clearly a series
        o.skipped = True
        drafts.append(Draft("RECURRING_SKIP", "SERIES", p.plan_no, None, "MISSED_EVENT", o.nominal,
                            f"{p.series_type.lower()} payment for {o.nominal:%b %Y} never happened"))
    taken = {p.plan_no for p in skips}
    rest = [p for p in eligible if p.plan_no not in taken]
    r = _rnd(seed, "RECURRING_NOT_SKIP")
    for p in sorted(r.sample(rest, min(count("RECURRING_NOT_SKIP", n_users), len(rest))), key=lambda p: p.plan_no):
        o = p.occ[r.randint(3, len(p.occ) - 4)]
        o.actual = o.nominal + timedelta(days=r.randint(2, 4))
        drafts.append(Draft("RECURRING_NOT_SKIP", "SERIES", p.plan_no, None, "NO_MISSED_EVENT", o.nominal,
                            f"{p.series_type.lower()} payment retried {(o.actual - o.nominal).days} days late"))
    return drafts


def inject_ledger(events: list[Ev], users: list[UserCtx], seed: int, n_users: int) -> list[Draft]:
    by_key = {e.key: e for e in events}
    accounts = {a.account_id: a for u in users for a in u.accounts}
    names = {u.user_id: u.display_name.upper() for u in users}
    drafts: list[Draft] = []

    def mark(*evs: Ev) -> None:
        for e in evs:
            e.tags.discard("adjustable")
            e.tags.add("anomaly")

    # ★A1 transfer counted as spending twice: own-account move that looks like a UPI payment, credit 1-3 days late
    want = count("TRANSFER_DOUBLE_COUNT", n_users)
    r = _rnd(seed, "TRANSFER_DOUBLE_COUNT")
    selfs = sorted((e for e in events if "self_transfer" in e.tags and e.amount < 0), key=lambda e: e.key)
    ccs = sorted((e for e in events if "cc_payment" in e.tags and e.amount < 0), key=lambda e: e.key)
    want_cc = min(len(ccs), round(.2 * want))
    for d in r.sample(selfs, len(selfs)):
        if want - want_cc <= 0:
            break
        c = by_key[d.link_key]
        src, dst = accounts[d.account_id], accounts[c.account_id]
        t = c.local_dt + timedelta(seconds=int(r.uniform(1.0, 2.9) * 86_400))
        if t.date() > PERIOD_END or not dst.open_on(t.date()):
            continue
        name = names[d.user_id]
        d.descriptor, d.channel, d.vpa = dsc.upi(True, d.ref, name, dst.vpa, "Payment"), "UPI", dst.vpa
        c.descriptor, c.channel, c.vpa = dsc.upi(False, d.ref, name, src.vpa, "Payment"), "UPI", src.vpa
        c.local_dt = t
        mark(d, c)
        want -= 1
        drafts.append(Draft("TRANSFER_DOUBLE_COUNT", "TXN", d.key, c.key, "EXCLUDE_BOTH_LEGS", None,
                            "own-account UPI with note 'Payment'; credit posted later"))
    for d in r.sample(ccs, len(ccs))[:want]:
        c = by_key[d.link_key]
        d.descriptor, d.channel, d.vpa = dsc.upi(True, d.ref, "CRED", CRED.vpa, "Payment"), "UPI", CRED.vpa
        d.true_merchant = CRED_ID
        c.local_dt += timedelta(days=2)
        mark(d, c)
        drafts.append(Draft("TRANSFER_DOUBLE_COUNT", "TXN", d.key, c.key, "EXCLUDE_BOTH_LEGS", None,
                            "card bill paid via CRED; card credit posted 2 days later"))

    # ★A2 refund treated as a new expense: the credit carries no refund wording
    r = _rnd(seed, "REFUND_AS_EXPENSE")
    refunds = sorted((e for e in events if "refund" in e.tags and e.link_key is not None and "anomaly" not in e.tags),
                     key=lambda e: e.key)
    picked = 0
    for e in r.sample(refunds, len(refunds)):
        if picked == count("REFUND_AS_EXPENSE", n_users):
            break
        desc = (e.descriptor.rsplit("/", 1)[0] + "/Payment" if e.channel == "UPI"
                else e.descriptor.replace("ECOM REFUND ", "ECOM ", 1))
        if any(w in desc.lower() for w in REFUND_WORDS):
            continue
        e.descriptor = desc
        mark(e)
        picked += 1
        drafts.append(Draft("REFUND_AS_EXPENSE", "TXN", e.key, e.link_key, f"NET_AGAINST:{e.true_category}", None,
                            "merchant credit without refund wording"))

    # ★A4 date crosses the timezone boundary: 00:00-05:29 IST on the 1st is the previous month in UTC
    r = _rnd(seed, "TZ_BOUNDARY")
    cands = sorted((e for e in events if "discretionary" in e.tags and e.link_key is None and e.series is None
                    and not e.tags & {"has_dep", "anomaly", "duplicate"}), key=lambda e: e.key)
    picked = 0
    for e in r.sample(cands, len(cands)):
        if picked == count("TZ_BOUNDARY", n_users):
            break
        first = e.local_dt.date().replace(day=1)
        if not accounts[e.account_id].open_on(first):
            continue
        e.local_dt = datetime.combine(first, datetime.min.time()) + timedelta(minutes=r.randint(0, 329),
                                                                               seconds=r.randint(0, 59))
        mark(e)
        picked += 1
        drafts.append(Draft("TZ_BOUNDARY", "TXN", e.key, None, f"MONTH:{first:%Y-%m}", None,
                            "posted 00:00-05:29 IST on the 1st; the UTC date is in the previous month"))
    return drafts


def inject_budgets(rows: list[tuple], users: list[UserCtx], seed: int, n_users: int) -> tuple[list[tuple], list[Draft]]:
    """★A5 budget categories that do not match the taxonomy: retired/synonym/case variants and unknown codes."""
    drafts: list[Draft] = []
    r = _rnd(seed, "BUDGET_CATEGORY_MISMATCH")
    keys = sorted({(b[0], b[4]) for b in rows if b[4] in REMAP_VARIANTS})
    remap: dict[str, tuple[str, str]] = {}
    for bid, code in r.sample(keys, min(count("BUDGET_REMAP", n_users), len(keys))):
        variant = r.choice(REMAP_VARIANTS[code])
        remap[bid] = (variant, bid[: -len(code)] + variant)
        drafts.append(Draft("BUDGET_CATEGORY_MISMATCH", "BUDGET", remap[bid][1], None, f"REMAP_TO:{code}", None,
                            f"submitted as '{variant}'"))
    rows = [(remap[b[0]][1], b[1], b[2], b[3], remap[b[0]][0], b[5], b[6]) if b[0] in remap else b for b in rows]
    taken = {b[0] for b in rows}
    budget_users = sorted({b[2] for b in rows}) or [u.user_id for u in users]
    added = 0
    while added < count("BUDGET_UNKNOWN", n_users):
        user, m, code = r.choice(budget_users), r.randint(1, 12), r.choice(UNKNOWN_BUDGET_CODES)
        month = f"2026-{m:02d}"
        bid = ids.budget_id(user, month, code)
        if bid in taken:
            continue
        taken.add(bid)
        rows.append((bid, 1, user, month, code, r.randint(2, 10) * 50_000, submitted(m)))
        drafts.append(Draft("BUDGET_CATEGORY_MISMATCH", "BUDGET", bid, None, "EXCEPTION", None,
                            f"'{code}' is not in the taxonomy"))
        added += 1
    return rows, drafts
