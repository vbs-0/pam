"""Recurring payment plans (salary, pension, rent, subscriptions, EMIs, utilities) — the truth series.

A plan lists nominal occurrence dates and amounts. Anomaly injection may skip one occurrence (a true skip)
or delay one (a decoy) before the plan is turned into ledger events.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from app.datagen import descriptors as dsc
from app.datagen.calendar import clamp_day, last_working_day, next_working_day
from app.datagen.catalog import (
    BROADBAND,
    DEFAULT_UTILITY,
    DTH,
    EMPLOYERS,
    FIRST_NAMES,
    LAST_NAMES,
    LENDERS,
    MERCHANT_BY_ID,
    MOBILE,
    SEASONALITY,
    SUBSCRIPTIONS,
    UTILITY_BY_STATE,
)
from app.datagen.events import Ev, Keys
from app.datagen.people import PERIOD_END, UserCtx
from app.datagen.rand import Rand


@dataclass
class Occ:
    nominal: date
    amount: int
    at: time
    actual: date | None = None   # set when a decoy delays this occurrence
    skipped: bool = False

    @property
    def when(self) -> date:
        return self.actual or self.nominal


@dataclass
class Plan:
    user_id: str
    account_id: str
    series_type: str            # SALARY | RENT | SUBSCRIPTION | EMI | UTILITY | (INTEREST added later)
    counterparty: str
    cadence: str
    category: str
    merchant_id: str | None
    channel: str
    style: str                  # how occurrences are rendered into narrations
    params: dict
    occ: list[Occ] = field(default_factory=list)
    ended: bool = False
    plan_no: int = 0

    def live(self) -> list[Occ]:
        return [o for o in self.occ if not o.skipped]


def _t(r: Rand, h0: int, h1: int) -> time:
    return time(r.randint(h0, h1), r.randint(0, 59), r.randint(0, 59))


def _rupees_to_paise(x: float, step: int = 1) -> int:
    return int(round(x / step)) * step * 100


def make_plans(u: UserCtx, seed: int) -> list[Plan]:
    r = Rand(f"{seed}:{u.user_id}:sched")
    acct = u.primary.account_id
    plans: list[Plan] = []
    income_rupees = u.income_paise // 100

    if u.persona == "SALARIED":
        employer = r.choice(EMPLOYERS)
        code = dsc.ifsc(r.choice(["HDFC", "ICIC", "UTIB", "SBIN"]), r.randint(1, 9999))
        hike_month = r.randint(4, 9) if r.chance(.15) else 13
        hike = r.uniform(.05, .15)
        p = Plan(u.user_id, acct, "SALARY", employer, "MONTHLY", "SALARY", None, "NEFT", "salary",
                 {"payer": employer, "ifsc": code})
        for m in range(1, 13):
            amt = u.income_paise if m < hike_month else _rupees_to_paise(income_rupees * (1 + hike))
            p.occ.append(Occ(last_working_day(2026, m), amt, _t(r, 9, 11)))
        plans.append(p)
    elif u.persona == "RETIRED":
        code = dsc.ifsc("SBIN", r.randint(1, 9999))
        p = Plan(u.user_id, acct, "SALARY", "PENSION", "MONTHLY", "SALARY", None, "NEFT", "pension",
                 {"payer": "PENSION DISBURSEMENT", "ifsc": code})
        for m in range(1, 13):
            p.occ.append(Occ(next_working_day(date(2026, m, 1)), u.income_paise, _t(r, 8, 10)))
        plans.append(p)

    if u.renter:
        name = f"{r.choice(FIRST_NAMES)} {r.choice(LAST_NAMES)}".upper()
        vpa = f"landlord.{u.n:06d}@okaxis"
        note = "rent" if r.chance(.6) else "Payment"     # 40% pay rent with no hint at all
        day = r.randint(1, 7)
        base = max(6000, round(income_rupees * r.uniform(.18, .35) / 500) * 500)
        bump_month = r.randint(4, 10) if r.chance(.15) else 13
        bumped = round(base * r.uniform(1.05, 1.10) / 500) * 500
        p = Plan(u.user_id, acct, "RENT", name, "MONTHLY", "RENT", None, "UPI", "rent",
                 {"name": name, "vpa": vpa, "note": note})
        for m in range(1, 13):
            p.occ.append(Occ(date(2026, m, day), (base if m < bump_month else bumped) * 100, _t(r, 7, 22)))
        plans.append(p)

    k = r.weighted([0, 1, 2, 3, 4], [.25, .30, .25, .12, .08])
    if u.income_band in ("HIGH", "AFFLUENT"):
        k = min(4, k + 1)
    card = u.card if u.card and u.card.opened_on < date(2026, 1, 1) else None
    for merchant_id, price in r.sample(SUBSCRIPTIONS, k):
        m = MERCHANT_BY_ID[merchant_id]
        alias = "amazon prime" if merchant_id == "MER-0013" else m.aliases[0]
        day = r.randint(1, 31)                                   # 29-31 clamp to month end (D14)
        start = 1 if r.chance(.8) else r.randint(2, 6)
        last = 12
        if r.chance(.10):
            last = r.randint(3, 9)
            if last < start + 2:
                last = 12
        change_month = r.randint(4, 9) if r.chance(.10) else 13
        new_price = round(price * r.uniform(1.15, 1.30) / 100) * 100
        on_card = card is not None and r.chance(.5)
        p = Plan(u.user_id, card.account_id if on_card else acct, "SUBSCRIPTION", m.name, "MONTHLY",
                 "SUBSCRIPTIONS", merchant_id, "CARD_ECOM" if on_card else "UPI",
                 "sub_card" if on_card else "sub_upi",
                 {"name": alias.upper(), "vpa": m.vpa, "city": dsc.hq(merchant_id)}, ended=last < 12)
        for mo in range(start, last + 1):
            p.occ.append(Occ(clamp_day(2026, mo, day), price if mo < change_month else new_price, _t(r, 2, 7)))
        plans.append(p)

    if r.chance(.30):
        lender = MERCHANT_BY_ID[r.choice(LENDERS)]
        amount = round(min(25000, max(2000, income_rupees * r.uniform(.08, .25))) / 100) * 100
        last = r.randint(4, 9) if r.chance(.25) else 12
        p = Plan(u.user_id, acct, "EMI", lender.name, "MONTHLY", "EMI_LOANS", lender.merchant_id, "NACH", "emi",
                 {"name": lender.aliases[0].upper() + " LTD"}, ended=last < 12)
        for m in range(1, last + 1):
            p.occ.append(Occ(next_working_day(date(2026, m, 5)), amount * 100, _t(r, 6, 9)))
        plans.append(p)

    elec = MERCHANT_BY_ID[UTILITY_BY_STATE.get(u.state, DEFAULT_UTILITY)]
    day = r.randint(10, 20)
    p = Plan(u.user_id, acct, "UTILITY", elec.name, "MONTHLY", "UTILITIES", elec.merchant_id, "BBPS", "bbps",
             {"biller": elec.aliases[0].upper(), "service": "ELECTRICITY"})
    for m in range(1, 13):
        rupees = (400 + 350 * u.household) * SEASONALITY["UTILITIES"][m - 1] * r.lognormal(0, .15)
        p.occ.append(Occ(date(2026, m, day), _rupees_to_paise(rupees), _t(r, 8, 22)))
    plans.append(p)

    if r.chance(.5):
        bb = MERCHANT_BY_ID[r.choice(BROADBAND)]
        price, day = r.choice([599, 799, 999, 1179]) * 100, r.randint(1, 28)
        p = Plan(u.user_id, acct, "UTILITY", bb.name, "MONTHLY", "UTILITIES", bb.merchant_id, "BBPS", "bbps",
                 {"biller": bb.aliases[0].upper(), "service": "BROADBAND"})
        p.occ = [Occ(date(2026, m, day), price, _t(r, 8, 22)) for m in range(1, 13)]
        plans.append(p)

    mob_id, mob_price = r.choice(MOBILE)
    mob = MERCHANT_BY_ID[mob_id]
    d = date(2026, 1, r.randint(1, 28))
    p = Plan(u.user_id, acct, "UTILITY", mob.name, "MONTHLY", "UTILITIES", mob_id, "UPI", "mobile",
             {"name": (mob.aliases[-1] if "prepaid" in mob.aliases[-1] else mob.aliases[0]).upper(), "vpa": mob.vpa})
    while d <= PERIOD_END:                                       # 28-day packs: 13 per year (D15)
        p.occ.append(Occ(d, mob_price, _t(r, 8, 22)))
        d += timedelta(days=28)
    plans.append(p)

    if r.chance(.30):
        dth = MERCHANT_BY_ID[DTH]
        price, day = r.choice([299, 349, 449]) * 100, r.randint(1, 28)
        p = Plan(u.user_id, acct, "UTILITY", dth.name, "MONTHLY", "UTILITIES", DTH, "BBPS", "bbps",
                 {"biller": dth.aliases[0].upper(), "service": "DTH"})
        p.occ = [Occ(date(2026, m, day), price, _t(r, 8, 22)) for m in range(1, 13)]
        plans.append(p)
    return plans


def materialize(plans: list[Plan], keys: Keys, seed: int) -> list[Ev]:
    out = []
    for p in plans:
        for o in p.live():
            k = keys()
            ref = dsc.ref_for(k, seed)
            prm, when = p.params, datetime.combine(o.when, o.at)
            vpa = None
            if p.style in ("salary", "pension"):
                note = f"{'SALARY' if p.style == 'salary' else 'PENSION'} {dsc.MON[o.nominal.month - 1]} 2026"
                desc, amount = dsc.neft_cr(prm["ifsc"], prm["payer"], note), o.amount
            elif p.style == "rent":
                desc, amount, vpa = dsc.upi(True, ref, prm["name"], prm["vpa"], prm["note"]), -o.amount, prm["vpa"]
            elif p.style == "sub_upi":
                desc, amount, vpa = dsc.upi(True, ref, prm["name"], prm["vpa"], "AutoPay"), -o.amount, prm["vpa"]
            elif p.style == "sub_card":
                desc, amount = dsc.ecom(prm["name"], prm["city"], recurring=True), -o.amount
            elif p.style == "emi":
                desc, amount = dsc.nach(prm["name"], ref), -o.amount
            elif p.style == "bbps":
                desc, amount = dsc.bbps(prm["biller"], prm["service"], ref), -o.amount
            elif p.style == "mobile":
                desc, amount, vpa = dsc.upi(True, ref, prm["name"], prm["vpa"], "Recharge"), -o.amount, prm["vpa"]
            else:  # pragma: no cover - guarded by make_plans
                raise ValueError(p.style)
            kind = "INCOME" if amount > 0 else "EXPENSE"
            out.append(Ev(k, p.user_id, p.account_id, when, amount, p.channel, desc, vpa, ref, p.merchant_id,
                          p.category, kind, series=p.plan_no, tags={"series"}))
    return out
