"""Master data: household profiles, accounts, holders and account lifecycle events.

Each profile draws from its own RNG stream so adding households never changes existing ones. Population-level
flags (account closures, joint holders, cards opened in 2026) use global streams with a guaranteed minimum of
one occurrence so even tiny datasets cover those edge cases.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta

from app import ids
from app.datagen.catalog import BANKS, CITIES, FIRST_NAMES, LAST_NAMES
from app.datagen.rand import Rand

BAND_RANGES = {"LOW": (18_000, 35_000), "MID": (35_000, 90_000), "HIGH": (90_000, 250_000),
               "AFFLUENT": (250_000, 800_000)}
BANDS = list(BAND_RANGES)
PERIOD_START, PERIOD_END = date(2026, 1, 1), date(2026, 12, 31)


@dataclass
class AccountCtx:
    account_id: str
    user_id: str
    kind: str              # PRIMARY | SECONDARY | CARD
    account_type: str      # SAVINGS | CREDIT_CARD
    bank_code: str
    vpa: str | None
    opened_on: date
    last4: int
    credit_limit: int | None = None
    closed_on: date | None = None
    opening_balance: int = 0

    def open_on(self, d: date) -> bool:
        """Can ordinary activity happen on day d? The closure day itself only carries the balance sweep."""
        return self.opened_on <= d and (self.closed_on is None or d < self.closed_on)


@dataclass
class UserCtx:
    user_id: str
    n: int
    display_name: str
    persona: str
    income_band: str
    income_paise: int
    city: str
    state: str
    tier: int
    household: int
    renter: bool
    created_on: date
    accounts: list[AccountCtx] = field(default_factory=list)
    joint: list[tuple[str, date]] = field(default_factory=list)  # (account_id, since) held jointly

    def account(self, kind: str) -> AccountCtx | None:
        return next((a for a in self.accounts if a.kind == kind), None)

    @property
    def primary(self) -> AccountCtx:
        return self.accounts[0]

    @property
    def card(self) -> AccountCtx | None:
        return self.account("CARD")

    @property
    def secondary(self) -> AccountCtx | None:
        return self.account("SECONDARY")


def _bank(r: Rand) -> str:
    return r.weighted([b[0] for b in BANKS], [.25, .25, .20, .06, .06, .06, .06, .06])


def _date_between(r: Rand, start: date, end: date) -> date:
    return start + timedelta(days=r.randint(0, (end - start).days))


def make_user(n: int, seed: int) -> UserCtx:
    uid = ids.user_id(n)
    r = Rand(f"{seed}:{uid}")
    persona = r.weighted(["SALARIED", "SELF_EMPLOYED", "RETIRED"], [.80, .15, .05])
    city, state, tier = r.choice(CITIES)
    band = r.weighted(BANDS, [.25, .45, .25, .05] if tier == 1 else [.30, .45, .20, .05])
    lo, hi = BAND_RANGES[band]
    rupees = round(r.uniform(lo, hi) / 100) * 100
    if persona == "RETIRED":
        rupees = round(rupees * 0.7 / 100) * 100
    household = r.weighted([1, 2, 3, 4, 5, 6], [.15, .25, .25, .20, .10, .05])
    renter = r.chance(.3) if persona == "RETIRED" else r.chance(.75 if tier == 1 else .6)
    name = f"{r.choice(FIRST_NAMES)} {r.choice(LAST_NAMES)}"
    created = _date_between(r, date(2018, 1, 1), date(2025, 12, 31))
    u = UserCtx(uid, n, name, persona, band, rupees * 100, city, state, tier, household, renter, created)

    def add(kind: str, account_type: str, bank: str, opened: date, limit: int | None = None):
        k = len(u.accounts) + 1
        handle = dict((b[0], b[2]) for b in BANKS)[bank]
        vpa = f"usr{n:06d}.{k:02d}@{handle}" if account_type == "SAVINGS" else None
        u.accounts.append(AccountCtx(ids.account_id(uid, k), uid, kind, account_type, bank, vpa, opened,
                                     r.randint(1000, 9999), limit))

    primary_bank = _bank(r)
    add("PRIMARY", "SAVINGS", primary_bank, _date_between(r, date(2012, 1, 1), date(2025, 6, 30)))
    if r.chance(.40):
        add("SECONDARY", "SAVINGS", _bank(r), _date_between(r, date(2014, 1, 1), date(2025, 9, 30)))
    if r.chance(.75 if band in ("HIGH", "AFFLUENT") else .45):
        bank = primary_bank if r.chance(.6) else _bank(r)
        limit = max(5_000_000, round(u.income_paise * 3 / 100_000) * 100_000)
        add("CARD", "CREDIT_CARD", bank, _date_between(r, date(2016, 1, 1), date(2025, 10, 31)), limit)
    return u


def make_users(n_users: int, seed: int) -> list[UserCtx]:
    users = [make_user(i, seed) for i in range(1, n_users + 1)]
    _population_flags(users, seed)
    return users


def _population_flags(users: list[UserCtx], seed: int) -> None:
    secondaries = sorted((a for u in users for a in u.accounts if a.kind == "SECONDARY"), key=lambda a: a.account_id)
    if secondaries:
        r = Rand(f"{seed}:global:closures")
        for a in r.sample(secondaries, max(1, round(.03 * len(secondaries)))):
            a.closed_on = _date_between(r, date(2026, 6, 1), date(2026, 10, 31))
    cards = sorted((a for u in users for a in u.accounts if a.kind == "CARD"), key=lambda a: a.account_id)
    if cards:
        r = Rand(f"{seed}:global:new_cards")
        for a in r.sample(cards, max(1, round(.10 * len(cards)))):
            a.opened_on = _date_between(r, date(2026, 2, 1), date(2026, 8, 31))
    open_secondaries = [a for a in secondaries if a.closed_on is None]
    if open_secondaries and len(users) > 1:
        r = Rand(f"{seed}:global:joint")
        by_id = {u.user_id: u for u in users}
        for a in r.sample(open_secondaries, max(1, round(.05 * len(open_secondaries)))):
            owner = by_id[a.user_id]
            pool = [u for u in users if u.user_id != owner.user_id and u.city == owner.city] or \
                   [u for u in users if u.user_id != owner.user_id]
            holder = r.choice(sorted(pool, key=lambda u: u.user_id))
            holder.joint.append((a.account_id, max(a.opened_on, holder.created_on)))


def master_rows(users: list[UserCtx]) -> dict[str, list[tuple]]:
    """Rows in schema column order, sorted by primary key."""
    profiles, accounts, holders, events = [], [], [], []
    for u in users:
        profiles.append((u.user_id, u.display_name, u.city, u.state, u.tier, u.persona, u.income_band,
                         u.income_paise, u.household, "Asia/Kolkata", u.created_on))
        for a in u.accounts:
            masked = f"XXXXXXXX{a.last4}" if a.account_type == "SAVINGS" else f"XXXX-XXXX-XXXX-{a.last4}"
            accounts.append((a.account_id, u.user_id, a.account_type, a.bank_code, masked, a.vpa, "INR",
                             a.opened_on, a.closed_on, "CLOSED" if a.closed_on else "ACTIVE", a.opening_balance,
                             a.credit_limit))
            holders.append((a.account_id, u.user_id, "PRIMARY", a.opened_on))
            events.append((a.account_id, a.opened_on, 0, "OPENED", None))
            if a.closed_on:
                events.append((a.account_id, a.closed_on, 1, "CLOSED", "balance swept to primary account"))
        for account_id, since in u.joint:
            holders.append((account_id, u.user_id, "JOINT", since))
    events.sort()
    return {
        "user_profile": sorted(profiles),
        "account": sorted(accounts),
        "account_holder": sorted(holders),
        "account_event": [(ids.seq("AEV", i), acc, typ, d, detail)
                          for i, (acc, d, _o, typ, detail) in enumerate(events, 1)],
    }
