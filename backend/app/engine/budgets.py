"""Budget taxonomy resolution, cash-basis spend per category and budget-vs-actual lines."""
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from app.engine.types import Category

SPEND_KINDS = {"EXPENSE", "REFUND"}


@dataclass(slots=True, frozen=True)
class BudgetIn:
    budget_id: str
    version: int
    user_id: str
    month: str
    category_code: str
    amount_paise: int


@dataclass(slots=True, frozen=True)
class BudgetResolution:
    budget_id: str
    version: int
    user_id: str
    month: str
    submitted_code: str
    resolved_code: str | None
    resolution: str
    amount_paise: int


@dataclass(slots=True, frozen=True)
class BudgetLine:
    category_code: str
    budget_paise: int | None
    actual_paise: int
    ratio: float | None
    status: str
    budget_ids: tuple[str, ...]


def resolve_category(code: str, month: str, categories: dict[str, Category],
                     synonyms: dict[str, str]) -> tuple[str | None, str]:
    """VALID, or remapped from a retired code, a case/spacing variant or a synonym; anything else (including
    income and transfer categories, E22) is UNMAPPED. A remap target must itself be an active expense category."""
    def usable(c: str | None) -> bool:
        cat = categories.get(c) if c else None
        return cat is not None and cat.kind == "EXPENSE" and cat.active_in(month)

    def retired(c: str) -> str | None:
        cat = categories.get(c)
        return cat.replaced_by if cat and cat.replaced_by and usable(cat.replaced_by) else None

    if usable(code):
        return code, "VALID"
    if r := retired(code):
        return r, "REMAPPED_RETIRED"
    canon = "_".join(code.strip().upper().replace("-", " ").split())
    if canon != code:
        if usable(canon):
            return canon, "REMAPPED_CASE"
        if r := retired(canon):
            return r, "REMAPPED_RETIRED"
    if usable(synonyms.get(canon)):
        return synonyms[canon], "REMAPPED_SYNONYM"
    return None, "UNMAPPED"


def resolve_budgets(budgets: Iterable[BudgetIn], categories: dict[str, Category],
                    synonyms: dict[str, str]) -> list[BudgetResolution]:
    """Latest version of each budget wins (E23 history is kept by the caller)."""
    latest: dict[str, BudgetIn] = {}
    for b in budgets:
        if b.budget_id not in latest or b.version > latest[b.budget_id].version:
            latest[b.budget_id] = b
    out = []
    for b in sorted(latest.values(), key=lambda x: x.budget_id):
        code, how = resolve_category(b.category_code, b.month, categories, synonyms)
        out.append(BudgetResolution(b.budget_id, b.version, b.user_id, b.month, b.category_code, code, how,
                                    b.amount_paise))
    return out


def spend_by_category(rows) -> dict[tuple[str, str, str], int]:
    """Cash basis: refunds reduce the bucket in the month they arrive (E13); uncategorized debits count (E25);
    transfers and reversals never count."""
    out: dict[tuple[str, str, str], int] = defaultdict(int)
    for user, month, cat, kind, amt in rows:
        if kind in SPEND_KINDS or (kind == "UNKNOWN" and amt < 0):
            out[(user, month, cat)] -= amt
    return dict(out)


def income_by_month(rows) -> dict[tuple[str, str], int]:
    out: dict[tuple[str, str], int] = defaultdict(int)
    for user, month, _cat, kind, amt in rows:
        if kind == "INCOME" or (kind == "UNKNOWN" and amt > 0):
            out[(user, month)] += amt
    return dict(out)


def budget_status(budget: int | None, actual: int) -> str:
    if budget is None:
        return "NO_BUDGET"
    if budget == 0:                                            # E24
        return "OVER" if actual > 0 else "UNDER"
    r = actual / budget
    return "OVER" if r > 1.0 else "NEAR" if r >= 0.8 else "UNDER"


def budget_lines(resolutions: Iterable[BudgetResolution], spend: dict[str, int]) -> list[BudgetLine]:
    """One line per category with a budget or with spend; budgets resolving to one category are summed (E23)."""
    agg: dict[str, list] = {}
    for r in resolutions:
        if r.resolved_code:
            a = agg.setdefault(r.resolved_code, [0, []])
            a[0] += r.amount_paise
            a[1].append(r.budget_id)
    lines = []
    for cat in sorted(set(agg) | {c for c, v in spend.items() if v}):
        budget = agg[cat][0] if cat in agg else None
        actual = spend.get(cat, 0)
        lines.append(BudgetLine(cat, budget, actual, round(actual / budget, 4) if budget else None,
                                budget_status(budget, actual), tuple(agg[cat][1]) if cat in agg else ()))
    return lines
