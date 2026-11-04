"""Monthly insights per household. Every insight names its numbers and the ids that back it."""
from collections import defaultdict
from dataclasses import dataclass

from app.engine.budgets import BudgetResolution, budget_lines
from app.engine.recurring import DetectedSeries
from app.money import fmt_inr

SPIKE_RATIO, SPIKE_MIN = 1.5, 200_000          # 1.5x the trailing 3-month mean and at least Rs 2,000 above it
LOW_SAVINGS = 0.10


@dataclass(slots=True, frozen=True)
class InsightRow:
    user_id: str
    month: str
    insight_type: str
    severity: str
    category_code: str | None
    metric_paise: int | None
    baseline_paise: int | None
    message: str
    evidence: dict


def _rupees(paise: int) -> str:
    """Whole rupees for prose (statements keep paise)."""
    s = fmt_inr(int(round(paise / 100)) * 100)
    return s[:-3] if s.endswith(".00") else s


def build_insights(spend: dict[tuple[str, str, str], int], income: dict[tuple[str, str], int],
                   resolutions: list[BudgetResolution], series: list[DetectedSeries], months: list[str],
                   names: dict[str, str], merchant_names: dict[str, str] | None = None) -> list[InsightRow]:
    merchant_names = merchant_names or {}
    out: list[InsightRow] = []
    by_um: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)
    for (u, m, c), v in spend.items():
        by_um[(u, m)][c] = v
    res_um: dict[tuple[str, str], list[BudgetResolution]] = defaultdict(list)
    for r in resolutions:
        res_um[(r.user_id, r.month)].append(r)

    for (u, m), rs in res_um.items():                          # budget vs actual
        for line in budget_lines(rs, by_um.get((u, m), {})):
            if line.status in ("OVER", "NEAR"):
                name = names.get(line.category_code, line.category_code)
                pct = f"{line.ratio:.0%}" if line.ratio is not None else "no budget amount"
                out.append(InsightRow(u, m, f"{line.status}_BUDGET", "ALERT" if line.status == "OVER" else "WARN",
                                      line.category_code, line.actual_paise, line.budget_paise,
                                      f"{name}: spent {_rupees(line.actual_paise)} of a "
                                      f"{_rupees(line.budget_paise or 0)} budget ({pct})",
                                      {"budget_ids": list(line.budget_ids)}))
        for r in rs:
            if r.resolution == "UNMAPPED":
                out.append(InsightRow(u, m, "UNMAPPED_BUDGET", "WARN", None, r.amount_paise, None,
                                      f"Budget category '{r.submitted_code}' is not in the category list, so its "
                                      f"{_rupees(r.amount_paise)} was not applied", {"budget_ids": [r.budget_id]}))

    index = {m: i for i, m in enumerate(months)}
    users = sorted({u for u, _ in by_um} | {u for u, _ in income})
    for u in users:
        cats = {c for (uu, _m), cs in by_um.items() if uu == u for c in cs}
        for m in months:
            i = index[m]
            if i >= 3:                                         # E28: needs three full prior months
                prior = months[i - 3:i]
                for c in sorted(cats):
                    now = by_um.get((u, m), {}).get(c, 0)
                    mean = sum(by_um.get((u, p), {}).get(c, 0) for p in prior) // 3
                    if mean > 0 and now >= SPIKE_RATIO * mean and now - mean >= SPIKE_MIN:
                        out.append(InsightRow(u, m, "SPEND_SPIKE", "WARN", c, now, mean,
                                              f"{names.get(c, c)}: {_rupees(now)} this month, {now / mean:.1f}x "
                                              f"the 3-month average of {_rupees(mean)}", {"prior_months": prior}))
            inc = income.get((u, m), 0)
            if inc > 0:                                        # E29: no income, no savings rate
                total = sum(by_um.get((u, m), {}).values())
                rate = (inc - total) / inc
                if rate < LOW_SAVINGS:
                    msg = (f"Saved {rate:.0%} of income ({_rupees(inc - total)} of {_rupees(inc)})" if rate >= 0
                           else f"Spent {_rupees(total - inc)} more than the {_rupees(inc)} that came in")
                    out.append(InsightRow(u, m, "LOW_SAVINGS", "WARN", None, inc - total, inc, msg,
                                          {"income_paise": inc, "spend_paise": total}))

    first = months[0] if months else None
    for s in series:
        label = merchant_names.get(s.merchant_id or "", "") or names.get(s.category_code, s.category_code)
        ev = {"series_key": "|".join(s.key), "txn_ids": s.member_txn_ids[-3:]}
        if s.first_seen.strftime("%Y-%m") != first:
            out.append(InsightRow(s.key[0], s.first_seen.strftime("%Y-%m"), "NEW_RECURRING", "INFO", s.category_code,
                                  s.typical_amount_paise, None,
                                  f"New recurring {'payment' if s.key[2] == 'DR' else 'credit'}: {label}, about "
                                  f"{_rupees(s.typical_amount_paise)} {s.cadence.lower()}", ev))
        for kind, d, detail in s.events:
            month = d.strftime("%Y-%m")
            if kind == "MISSED" and month in index:
                what = "payment" if s.key[2] == "DR" else "credit"
                out.append(InsightRow(s.key[0], month, "RECURRING_MISSED", "ALERT", s.category_code,
                                      s.typical_amount_paise, None,
                                      f"{label}: {what} expected around {d:%d %b} was not seen",
                                      {**ev, "expected_date": d.isoformat()}))
            elif kind == "AMOUNT_CHANGED":
                out.append(InsightRow(s.key[0], month, "RECURRING_PRICE_CHANGE", "INFO", s.category_code,
                                      detail["to_paise"], detail["from_paise"],
                                      f"{label} changed from {_rupees(detail['from_paise'])} to "
                                      f"{_rupees(detail['to_paise'])}", ev))
    out.sort(key=lambda x: (x.user_id, x.month, x.insight_type, x.category_code or "", x.message))
    return out
