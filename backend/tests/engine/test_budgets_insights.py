from datetime import date

from app.engine.budgets import (
    BudgetIn,
    BudgetResolution,
    budget_lines,
    budget_status,
    income_by_month,
    resolve_budgets,
    resolve_category,
    spend_by_category,
)
from app.engine.insights import build_insights
from app.engine.types import Category

D0 = date(2020, 1, 1)
CATS = {c.code: c for c in [
    Category("FOOD_DINING", "EXPENSE", D0, name="Food & Dining"), Category("GROCERIES", "EXPENSE", D0),
    Category("UTILITIES", "EXPENSE", D0), Category("SALARY", "INCOME", D0),
    Category("DINING_OUT", "EXPENSE", D0, date(2025, 12, 31), "FOOD_DINING"),
    Category("UNCATEGORIZED", "UNKNOWN", D0)]}
SYN = {"FOOD_AND_DINING": "FOOD_DINING", "BILLS": "UTILITIES"}
MONTHS = [f"2026-{m:02d}" for m in range(1, 13)]


def test_resolution_paths():
    assert resolve_category("FOOD_DINING", "2026-03", CATS, SYN) == ("FOOD_DINING", "VALID")
    assert resolve_category("DINING_OUT", "2026-03", CATS, SYN) == ("FOOD_DINING", "REMAPPED_RETIRED")
    assert resolve_category("groceries", "2026-03", CATS, SYN) == ("GROCERIES", "REMAPPED_CASE")
    assert resolve_category(" food-dining ", "2026-03", CATS, SYN) == ("FOOD_DINING", "REMAPPED_CASE")
    assert resolve_category("dining_out", "2026-03", CATS, SYN) == ("FOOD_DINING", "REMAPPED_RETIRED")
    assert resolve_category("BILLS", "2026-03", CATS, SYN) == ("UTILITIES", "REMAPPED_SYNONYM")
    assert resolve_category("food_and_dining", "2026-03", CATS, SYN) == ("FOOD_DINING", "REMAPPED_SYNONYM")
    assert resolve_category("GYM_FITNESS", "2026-03", CATS, SYN) == (None, "UNMAPPED")
    assert resolve_category("SALARY", "2026-03", CATS, SYN) == (None, "UNMAPPED")  # not an expense (E22)


def test_retired_code_still_valid_before_retirement():
    assert resolve_category("DINING_OUT", "2025-12", CATS, SYN) == ("DINING_OUT", "VALID")


def test_latest_version_wins():
    b = [BudgetIn("BUD-USR-000001-2026-03-GROCERIES", 2, "USR-000001", "2026-03", "GROCERIES", 600000),
         BudgetIn("BUD-USR-000001-2026-03-GROCERIES", 1, "USR-000001", "2026-03", "GROCERIES", 500000)]
    r = resolve_budgets(b, CATS, SYN)
    assert len(r) == 1 and r[0].version == 2 and r[0].amount_paise == 600000


def test_spend_partition_refund_nets_transfer_excluded():
    rows = [("U", "2026-03", "FOOD_DINING", "EXPENSE", -100000), ("U", "2026-03", "FOOD_DINING", "REFUND", 30000),
            ("U", "2026-03", "SELF_TRANSFER", "TRANSFER", -500000), ("U", "2026-03", "SALARY", "INCOME", 9000000),
            ("U", "2026-03", "UNCATEGORIZED", "UNKNOWN", -20000), ("U", "2026-03", "SHOPPING", "REVERSAL", -5000)]
    assert spend_by_category(rows) == {("U", "2026-03", "FOOD_DINING"): 70000,
                                       ("U", "2026-03", "UNCATEGORIZED"): 20000}
    assert income_by_month(rows) == {("U", "2026-03"): 9000000}


def test_status_thresholds_and_lines():
    assert budget_status(None, 10) == "NO_BUDGET"
    assert budget_status(100, 101) == "OVER" and budget_status(100, 80) == "NEAR" and budget_status(100, 79) == "UNDER"
    assert budget_status(0, 1) == "OVER" and budget_status(0, 0) == "UNDER"                         # E24
    b = [BudgetIn("BUD-USR-000001-2026-03-DINING_OUT", 1, "U", "2026-03", "DINING_OUT", 100000),
         BudgetIn("BUD-USR-000001-2026-03-FOOD_AND_DINING", 1, "U", "2026-03", "FOOD_AND_DINING", 50000)]
    lines = budget_lines(resolve_budgets(b, CATS, SYN), {"FOOD_DINING": 160000, "GROCERIES": 1000})
    food = next(x for x in lines if x.category_code == "FOOD_DINING")
    assert food.budget_paise == 150000 and food.status == "OVER" and len(food.budget_ids) == 2      # E23
    assert next(x for x in lines if x.category_code == "GROCERIES").status == "NO_BUDGET"


def _res(cat, amount, month="2026-03"):
    return BudgetResolution(f"BUD-U-{month}-{cat}", 1, "U", month, cat, cat, "VALID", amount)


def test_budget_insights_have_numbers_and_evidence():
    out = build_insights({("U", "2026-03", "FOOD_DINING"): 1_200_000}, {}, [_res("FOOD_DINING", 1_000_000)], [],
                         MONTHS, {c: v.name or c for c, v in CATS.items()})
    ins = [i for i in out if i.insight_type == "OVER_BUDGET"]
    assert len(ins) == 1 and ins[0].severity == "ALERT" and ins[0].metric_paise == 1_200_000
    assert ins[0].message == "Food & Dining: spent ₹12,000 of a ₹10,000 budget (120%)"
    assert ins[0].evidence == {"budget_ids": ["BUD-U-2026-03-FOOD_DINING"]}


def test_spike_needs_three_prior_months():
    spend = {("U", "2026-02", "GROCERIES"): 100_000, ("U", "2026-03", "GROCERIES"): 900_000}   # E28
    assert not [i for i in build_insights(spend, {}, [], [], MONTHS, {}) if i.insight_type == "SPEND_SPIKE"]
    spend = {("U", f"2026-0{m}", "GROCERIES"): 400_000 for m in (1, 2, 3)} | {("U", "2026-04", "GROCERIES"): 900_000}
    spikes = [i for i in build_insights(spend, {}, [], [], MONTHS, {}) if i.insight_type == "SPEND_SPIKE"]
    assert len(spikes) == 1 and spikes[0].month == "2026-04" and spikes[0].baseline_paise == 400_000


def test_low_savings_zero_income():
    spend = {("U", "2026-03", "GROCERIES"): 900_000}
    assert not [i for i in build_insights(spend, {}, [], [], MONTHS, {}) if i.insight_type == "LOW_SAVINGS"]  # E29
    low = [i for i in build_insights(spend, {("U", "2026-03"): 950_000}, [], [], MONTHS, {})
           if i.insight_type == "LOW_SAVINGS"]
    assert len(low) == 1 and low[0].metric_paise == 50_000


def test_unmapped_budget_insight():
    r = BudgetResolution("BUD-U-2026-03-PETS", 1, "U", "2026-03", "PETS", None, "UNMAPPED", 200_000)
    ins = build_insights({}, {}, [r], [], MONTHS, {})
    assert [i.insight_type for i in ins] == ["UNMAPPED_BUDGET"] and ins[0].category_code is None
