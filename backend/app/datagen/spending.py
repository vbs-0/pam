"""Discretionary spending and other non-series activity.

Purchases (named merchants via their aliases, local shops that are not in the merchant master, ATM cash),
their refunds and failed-payment reversals, same-day identical purchases, self-employed client income,
annual insurance premiums and orphan refunds for purchases made before the data window.
"""
import calendar as _cal
import re
from datetime import date, datetime, time, timedelta

from app.datagen import descriptors as dsc
from app.datagen.calendar import is_bank_working_day
from app.datagen.catalog import (
    BANK_BY_CODE,
    CLIENTS,
    LONG_TAIL,
    LONG_TAIL_PREFIXES,
    MERCHANT_BY_ID,
    MERCHANTS,
    PERSONA_WEIGHTS,
    SEASONALITY,
)
from app.datagen.events import Ev, Keys
from app.datagen.people import PERIOD_END, AccountCtx, UserCtx
from app.datagen.rand import Rand

INCOME_MULT = {"LOW": .6, "MID": 1.0, "HIGH": 1.6, "AFFLUENT": 2.5}
BAND_WEIGHT = {"LOW": .7, "MID": 1.0, "HIGH": 1.3, "AFFLUENT": 1.6}
LONG_TAIL_MEAN = {"GROCERIES": 450, "FOOD_DINING": 250, "HEALTH": 400, "FUEL": 1200, "PERSONAL_CARE": 400,
                  "SHOPPING": 900}
ATM_RUPEES = [500, 1000, 2000, 3000, 5000, 10000]
UPI_NOTES = ["UPI", "Payment from Ph", "Paid via GPay", "NA"]
HOURS = list(range(24))
FOOD_HOURS = [3, 2, 1, 0, 0, 0, 0, 1, 4, 5, 4, 3, 8, 10, 8, 4, 3, 4, 6, 9, 10, 8, 6, 4]  # lunch/dinner + late tail
DAY_HOURS = [0] * 9 + [1] * 13 + [0] * 2                                                 # 09:00-21:59
ONES = [1.0] * 12
ADD_CATS = ["GROCERIES", "FOOD_DINING", "TRANSPORT", "LONG_TAIL"]   # used to top up the exact volume
INSURERS = ["MER-0045", "MER-0046"]
ORPHAN_MERCHANTS = ["MER-0013", "MER-0014", "MER-0015", "MER-0016"]

# Days of each 2026 month with weekend weighting (Sat/Sun x1.3).
DAYS = {m: [date(2026, m, d) for d in range(1, _cal.monthrange(2026, m)[1] + 1)] for m in range(1, 13)}
DAY_W = {m: [1.3 if d.weekday() >= 5 else 1.0 for d in DAYS[m]] for m in range(1, 13)}


def _aliases(m, cat: str) -> tuple[list[str], bool]:
    """(aliases to draw from, refined?) — refined aliases name the sub-business (e.g. 'swiggy instamart')."""
    if cat != m.category:
        refined = [a for a in m.aliases for rx, c in m.refinements if c == cat and re.search(rx, a)]
        return (refined, True) if refined else ([m.aliases[0]], False)
    return [a for a in m.aliases if not any(re.search(rx, a) for rx, _ in m.refinements)], False


def _pool(cat: str):
    ms = [m for m in MERCHANTS if m.category == cat] + [m for m in MERCHANTS if cat in m.extra_categories]
    return ms, [1 / (i + 1) for i in range(len(ms))], {m.merchant_id: _aliases(m, cat) for m in ms}  # Zipf


POOLS = {c: _pool(c) for c in PERSONA_WEIGHTS["SALARIED"] if c not in ("CASH_WITHDRAWAL", "LONG_TAIL")}


def user_weight(u: UserCtx, seed: int) -> float:
    w = Rand(f"{seed}:{u.user_id}:weight").lognormal(0, .35) * BAND_WEIGHT[u.income_band]
    return w * (.6 if u.persona == "RETIRED" else 1.0)


def split(total: int, weights: list[float]) -> list[int]:
    """Integer split proportional to weights (largest remainder, ties by position)."""
    s = sum(weights)
    raw = [total * w / s for w in weights]
    out = [int(x) for x in raw]
    for i in sorted(range(len(raw)), key=lambda i: (out[i] - raw[i], i))[:total - sum(out)]:
        out[i] += 1
    return out


class Spender:
    def __init__(self, u: UserCtx, seed: int):
        self.u, self.seed = u, seed
        self.r = Rand(f"{seed}:{u.user_id}:spend")
        self.mult = INCOME_MULT[u.income_band]
        w = PERSONA_WEIGHTS[u.persona]
        self.cats, self.cat_w = list(w), [w[c] for c in w]
        s = Rand(f"{seed}:{u.user_id}:shops")
        self.shops = []                      # the household's regular local shops: (name, true category, QR VPA)
        for _ in range(8):
            suffix, cats = s.choice(LONG_TAIL)
            self.shops.append((f"{s.choice(LONG_TAIL_PREFIXES)} {suffix}", s.choice(cats),
                               f"q{s.randint(10**8, 10**9 - 1)}@ybl"))
        self.dup_left = 1 if s.chance(.05) else 0   # one same-day identical purchase (D21)

    def month_weights(self) -> list[float]:
        return [sum(w * SEASONALITY.get(c, ONES)[m] for c, w in zip(self.cats, self.cat_w, strict=True))
                * (1 + self.r.uniform(-.1, .1)) for m in range(12)]

    def month(self, month: int, n: int, keys: Keys) -> list[Ev]:
        out: list[Ev] = []
        for _ in range(n):
            out.extend(self.purchase(self.r, month, keys))
        return out

    def _savings(self, r: Rand, d: date) -> AccountCtx:
        sec = self.u.secondary
        return sec if sec and sec.open_on(d) and r.chance(.15) else self.u.primary

    def purchase(self, r: Rand, month: int, keys: Keys, cat: str | None = None, force_upi: bool = False,
                 followups: bool = True) -> list[Ev]:
        u = self.u
        if cat is None:
            cat = r.weighted(self.cats, [w * SEASONALITY.get(c, ONES)[month - 1]
                                         for c, w in zip(self.cats, self.cat_w, strict=True)])
        d = r.weighted(DAYS[month], DAY_W[month])
        when = datetime.combine(d, time(r.weighted(HOURS, FOOD_HOURS if cat == "FOOD_DINING" else DAY_HOURS),
                                        r.randint(0, 59), r.randint(0, 59)))
        k = keys()
        ref = dsc.ref_for(k, self.seed)
        if cat == "CASH_WITHDRAWAL":
            acct = u.primary
            return [Ev(k, u.user_id, acct.account_id, when, -r.choice(ATM_RUPEES) * 100, "ATM",
                       dsc.atm(BANK_BY_CODE[acct.bank_code][1], u.city, ref), None, ref, None, "CASH_WITHDRAWAL",
                       "EXPENSE", tags={"discretionary"})]
        if cat == "LONG_TAIL":
            name, true_cat, vpa = r.choice(self.shops)
            m, online, mean, sigma = None, False, LONG_TAIL_MEAN[true_cat], .5
        else:
            ms, ws, aliases = POOLS[cat]
            m = r.weighted(ms, ws)
            names, refined = aliases[m.merchant_id]
            if refined:   # sub-business named 70% of the time, otherwise only the generic brand shows
                name = (r.choice(names) if r.chance(.7) else m.aliases[0]).upper()
            else:
                name = (names[0] if r.chance(.6) else r.choice(names)).upper()
            true_cat, vpa, online, mean, sigma = cat, m.vpa, m.online, m.mean_rupees, m.sigma
        rupees = max(10.0, mean * self.mult * r.lognormal(0, sigma))
        card = u.card if u.card and u.card.open_on(d) else None
        if online and not force_upi and card and r.chance(.45):
            acct, channel, desc, cp = card, "CARD_ECOM", dsc.ecom(name, dsc.hq(m.merchant_id)), None
        elif online or force_upi or r.chance(.75):
            acct, channel, cp = self._savings(r, d), "UPI", vpa
            desc = dsc.upi(True, ref, name, vpa, r.choice(UPI_NOTES))
        else:
            acct = card or self._savings(r, d)
            channel, desc, cp = "CARD_POS", dsc.pos(acct.last4, name, u.city), None
        paise = int(round(rupees)) * 100 if channel == "UPI" and r.chance(.7) else int(round(rupees * 100))
        tags = {"discretionary"}
        if online:
            tags.add("online")
        if channel == "UPI" and acct.account_type == "SAVINGS":
            tags.add("adjustable")
        ev = Ev(k, u.user_id, acct.account_id, when, -paise, channel, desc, cp, ref,
                m.merchant_id if m else None, true_cat, "EXPENSE", tags=tags)
        out = [ev]
        if not followups:
            return out
        if online and r.chance(.03):
            out.extend(self._refunds(r, ev, acct, name, m.merchant_id, keys))
        elif channel == "UPI" and r.chance(.003):
            out.extend(self._reversal(r, ev, acct, name, keys))
        elif not online and self.dup_left and when.hour < 23:
            self.dup_left = 0
            k2 = keys()
            ref2 = dsc.ref_for(k2, self.seed)
            desc2 = dsc.upi(True, ref2, name, vpa, desc.rsplit("/", 1)[1]) if channel == "UPI" else desc
            ev.tags.discard("adjustable")
            ev.tags.add("duplicate")
            out.append(Ev(k2, u.user_id, acct.account_id, when + timedelta(minutes=r.randint(2, 15)), -paise,
                          channel, desc2, cp, ref2, ev.true_merchant, true_cat, "EXPENSE", tags={"duplicate"}))
        return out

    def _refunds(self, r: Rand, ev: Ev, acct: AccountCtx, name: str, merchant_id: str, keys: Keys) -> list[Ev]:
        amount = -ev.amount
        if r.chance(.7):
            parts = [amount]
        elif r.chance(.3):        # two partial refunds of one order, total <= original (D17)
            parts = [int(amount * r.uniform(.2, .4)), int(amount * r.uniform(.2, .4))]
        else:
            parts = [int(amount * r.uniform(.3, .8))]
        out, day = [], ev.local_dt.date()
        for p in parts:
            day += timedelta(days=r.randint(2, 20) if not out else r.randint(1, 5))
            if p <= 0 or day > PERIOD_END or not acct.open_on(day):   # outside window / account closed (D16)
                break
            k = keys()
            ref = dsc.ref_for(k, self.seed)
            if ev.channel == "UPI":
                desc = dsc.upi(False, ref, name, ev.vpa, "Refund")
            else:
                desc = dsc.ecom(name, dsc.hq(merchant_id), refund=True)
            out.append(Ev(k, ev.user_id, ev.account_id, datetime.combine(day, time(r.randint(8, 21),
                          r.randint(0, 59), r.randint(0, 59))), p, ev.channel, desc, ev.vpa, ref, ev.true_merchant,
                          ev.true_category, "REFUND", link_key=ev.key, tags={"refund"}))
        if out:
            ev.tags.discard("adjustable")
            ev.tags.add("has_dep")
        return out

    def _reversal(self, r: Rand, ev: Ev, acct: AccountCtx, name: str, keys: Keys) -> list[Ev]:
        when = ev.local_dt + timedelta(minutes=r.randint(60, 30 * 60))
        if when.date() > PERIOD_END or not acct.open_on(when.date()):
            return []
        k = keys()
        rev = Ev(k, ev.user_id, ev.account_id, when, -ev.amount, "UPI", dsc.upi_reversal(ev.ref, name, ev.vpa),
                 ev.vpa, ev.ref, ev.true_merchant, ev.true_category, "REVERSAL", link_key=ev.key, tags={"reversal"})
        ev.true_kind, ev.link_key = "REVERSAL", k
        ev.tags.discard("adjustable")
        ev.tags.add("has_dep")
        return [rev]

    def extras(self, keys: Keys) -> list[Ev]:
        """Self-employed client income, annual insurance premium, orphan January refund."""
        u, r, out = self.u, Rand(f"{self.seed}:{self.u.user_id}:extras"), []
        acct = u.primary
        if u.persona == "SELF_EMPLOYED":          # irregular income, deliberately not a series (D24)
            for m in range(1, 13):
                n = r.randint(2, 5)
                total = u.income_paise * r.uniform(.6, 1.4)
                for share in split(int(total / 10_000), [r.uniform(.5, 1.5) for _ in range(n)]):
                    if share <= 0:
                        continue
                    d = r.choice([d for d in DAYS[m] if is_bank_working_day(d)])
                    k = keys()
                    ref = dsc.ref_for(k, self.seed)
                    client = r.choice(CLIENTS)
                    if r.chance(.6):
                        desc, ch = dsc.neft_cr(dsc.ifsc(r.choice(["HDFC", "ICIC", "SBIN"]), r.randint(1, 9999)),
                                               client, f"INV{r.randint(100, 999)}"), "NEFT"
                    else:
                        desc, ch = dsc.imps_cr(ref, client), "IMPS"
                    out.append(Ev(k, u.user_id, acct.account_id, datetime.combine(d, time(r.randint(10, 18),
                                  r.randint(0, 59))), share * 10_000, ch, desc, None, ref, None, "OTHER_INCOME",
                                  "INCOME", tags={"income"}))
        if r.chance(.35):
            m = MERCHANT_BY_ID[r.choice(INSURERS)]
            d = date(2026, r.randint(1, 12), r.randint(1, 28))
            k = keys()
            ref = dsc.ref_for(k, self.seed)
            paise = int(round(m.mean_rupees * self.mult * r.lognormal(0, m.sigma))) * 100
            out.append(Ev(k, u.user_id, acct.account_id, datetime.combine(d, time(r.randint(9, 20), r.randint(0, 59))),
                          -paise, "BBPS", dsc.bbps(m.aliases[0].upper(), "INSURANCE", ref), None, ref, m.merchant_id,
                          m.category, "EXPENSE", tags={"insurance"}))
        if r.chance(.2):                          # refund of a December 2025 order (D18)
            m = MERCHANT_BY_ID[r.choice(ORPHAN_MERCHANTS)]
            d = date(2026, 1, r.randint(1, 15))
            k = keys()
            ref = dsc.ref_for(k, self.seed)
            paise = int(round(m.mean_rupees * self.mult * r.lognormal(0, m.sigma))) * 100
            out.append(Ev(k, u.user_id, acct.account_id, datetime.combine(d, time(r.randint(9, 20), r.randint(0, 59))),
                          paise, "UPI", dsc.upi(False, ref, m.aliases[0].upper(), m.vpa, "Refund"), m.vpa, ref,
                          m.merchant_id, m.category, "REFUND", tags={"refund", "orphan"}))
        return out
