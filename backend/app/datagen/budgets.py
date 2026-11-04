"""Household monthly budgets, sized from each household's own true spend so over/under outcomes are realistic."""
import calendar as _cal
from datetime import datetime

from app import ids
from app.datagen.people import UserCtx
from app.datagen.rand import Rand
from app.timeutil import ist_to_utc

BASE = ["FOOD_DINING", "GROCERIES", "SHOPPING", "TRANSPORT", "UTILITIES", "ENTERTAINMENT"]
OPTIONAL = [("FUEL", .5), ("HEALTH", .3), ("PERSONAL_CARE", .2)]
STEP = 50_000            # budgets are whole Rs 500 amounts


def round_step(paise: float) -> int:
    return max(STEP, int(round(paise / STEP)) * STEP)


def submitted(month: int, day: int | None = None) -> datetime:
    """v1 lands at 21:00 IST on the last day of the previous month; revisions at 21:00 IST on ``day``."""
    if day is None:
        y, m = (2025, 12) if month == 1 else (2026, month - 1)
        local = datetime(y, m, _cal.monthrange(y, m)[1], 21)
    else:
        local = datetime(2026, month, day, 21)
    return ist_to_utc(local)


def make_budgets(u: UserCtx, annual_spend: dict[str, int], seed: int) -> list[tuple]:
    """Rows in schema order: (budget_id, version, user_id, month, category_code, amount_paise, submitted_at)."""
    r = Rand(f"{seed}:{u.user_id}:budget")
    if not r.chance(.95):                       # ~5% of households keep no budget at all (D22)
        return []
    cats = BASE + (["RENT"] if u.renter else []) + [c for c, p in OPTIONAL if r.chance(p)]
    rows = []
    for c in cats:
        amount = round_step(annual_spend.get(c, 0) / 12 * r.uniform(.8, 1.25))
        for m in range(1, 13):
            month = f"2026-{m:02d}"
            bid = ids.budget_id(u.user_id, month, c)
            rows.append((bid, 1, u.user_id, month, c, amount, submitted(m)))
            if r.chance(.08):                   # mid-month revision; v1 stays as history (D23)
                rows.append((bid, 2, u.user_id, month, c, round_step(amount * r.uniform(.8, 1.3)),
                             submitted(m, r.randint(8, 20))))
    return rows

