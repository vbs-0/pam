"""Read-only views over a household's register: daily totals (calendar), spend by category with month-on-month change,
top merchants, weekday pattern, upcoming bills and income, net worth with card dues, and the alert list.

Spend uses the same rule as /me/summary and /me/trend: EXPENSE and REFUND rows (and unsorted debits), so a transfer
between your own accounts never counts as spending. Everything here also works for the read-only sample households.
"""

import calendar
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Connection, text

from app.api.common import EFFECTIVE, household, month_q, run_id
from app.api.me import _budget, display_name
from app.db import get_conn
from app.jobs.pipeline_job import today

router = APIRouter(prefix="/me", tags=["customer: analytics"])

SPEND = "(kind IN ('EXPENSE', 'REFUND') OR (kind = 'UNKNOWN' AND amount_paise < 0))"
INCOME = "(kind = 'INCOME' OR (kind = 'UNKNOWN' AND amount_paise > 0))"


def prev_month(m: str) -> str:
    y, mo = int(m[:4]), int(m[5:])
    return f"{y - (mo == 1)}-{12 if mo == 1 else mo - 1:02d}"


@router.get("/daily")
def daily(
    month: str = Depends(month_q),
    user: str = Depends(household),
    run: str = Depends(run_id),
    conn: Connection = Depends(get_conn),
):
    """One row per day of the month (empty days included) for a calendar grid: spend, income and entry count."""
    rows = conn.execute(
        text(
            f"SELECT local_date, COALESCE(-sum(amount_paise) FILTER (WHERE {SPEND}), 0) AS spend, "
            f"COALESCE(sum(amount_paise) FILTER (WHERE {INCOME}), 0) AS income, count(*) AS n "
            f"FROM ({EFFECTIVE} AND e.user_id = :u AND e.local_month = :m) x GROUP BY 1"
        ),
        {"run": run, "u": user, "m": month},
    ).all()
    by = {r.local_date: r for r in rows}
    y, mo = int(month[:4]), int(month[5:])
    days = []
    for d in range(1, calendar.monthrange(y, mo)[1] + 1):
        day = date(y, mo, d)
        r = by.get(day)
        days.append(
            {
                "date": day,
                "spend_paise": int(r.spend) if r else 0,
                "income_paise": int(r.income) if r else 0,
                "count": r.n if r else 0,
            }
        )
    spent = [x["spend_paise"] for x in days if x["count"]]
    t = today()
    elapsed = (
        (t.day if (t.year, t.month) == (y, mo) else calendar.monthrange(y, mo)[1])
        if (y, mo) <= (t.year, t.month)
        else 0
    )
    total = sum(x["spend_paise"] for x in days)
    left = max(calendar.monthrange(y, mo)[1] - t.day, 0) if (t.year, t.month) == (y, mo) else 0
    return {
        "month": month,
        "days": days,
        "total_spend_paise": total,
        "busiest": max(days, key=lambda x: x["spend_paise"])["date"] if spent else None,
        "daily_average_paise": total // elapsed if elapsed else 0,
        "days_elapsed": elapsed,
        "days_left": left,
    }


@router.get("/spend-by-category")
def spend_by_category(
    month: str = Depends(month_q),
    user: str = Depends(household),
    run: str = Depends(run_id),
    conn: Connection = Depends(get_conn),
):
    """Every category with spend this month, its share, and the change against the month before."""

    def spend(m: str) -> dict[str, int]:
        return {
            c: int(v)
            for c, v in conn.execute(
                text(
                    f"SELECT category_code, -sum(amount_paise) FROM ({EFFECTIVE} AND e.user_id = :u AND e.local_month = :m) x "
                    f"WHERE {SPEND} GROUP BY 1"
                ),
                {"run": run, "u": user, "m": m},
            )
            if v
        }

    cur, prev = spend(month), spend(prev_month(month))
    names = dict(conn.execute(text("SELECT category_code, name FROM category")).all())
    total, prev_total = sum(v for v in cur.values() if v > 0), sum(v for v in prev.values() if v > 0)
    rows = [
        {
            "code": c,
            "name": names.get(c, c),
            "spend_paise": v,
            "previous_paise": prev.get(c, 0),
            "change_paise": v - prev.get(c, 0),
            "share": round(v / total, 4) if total else 0,
        }
        for c, v in sorted(cur.items(), key=lambda kv: -kv[1])
        if v > 0
    ]
    for c, v in prev.items():  # categories you spent on last month but not this one
        if c not in cur and v > 0:
            rows.append(
                {
                    "code": c,
                    "name": names.get(c, c),
                    "spend_paise": 0,
                    "previous_paise": v,
                    "change_paise": -v,
                    "share": 0,
                }
            )
    return {
        "month": month,
        "previous_month": prev_month(month),
        "total_paise": total,
        "previous_total_paise": prev_total,
        "change_paise": total - prev_total,
        "categories": rows,
    }


@router.get("/merchants")
def merchants(
    months: int = Query(6, ge=1, le=36),
    limit: int = Query(15, ge=1, le=50),
    user: str = Depends(household),
    run: str = Depends(run_id),
    conn: Connection = Depends(get_conn),
):
    """Where the money goes: top payees by spend over the last N months, with count and last payment date."""
    rows = conn.execute(
        text(
            f"SELECT COALESCE(merchant_name, descriptor) AS name, -sum(amount_paise) AS spend, count(*) AS n, "
            f"max(local_date) AS last_date, min(category_code) AS category_code "
            f"FROM ({EFFECTIVE} AND e.user_id = :u AND e.local_month >= :from_m) x WHERE {SPEND} AND amount_paise < 0 "
            f"GROUP BY 1 HAVING -sum(amount_paise) > 0 ORDER BY spend DESC LIMIT :lim"
        ),
        {"run": run, "u": user, "from_m": _months_ago(months), "lim": limit},
    ).all()
    return [
        {
            "name": r.name,
            "spend_paise": int(r.spend),
            "count": r.n,
            "last_date": r.last_date,
            "category_code": r.category_code,
        }
        for r in rows
    ]


def _months_ago(n: int) -> str:
    t = today()
    total = t.year * 12 + t.month - 1 - (n - 1)
    return f"{total // 12}-{total % 12 + 1:02d}"


@router.get("/weekday")
def weekday(
    months: int = Query(6, ge=1, le=36),
    user: str = Depends(household),
    run: str = Depends(run_id),
    conn: Connection = Depends(get_conn),
):
    """Spending by day of week over the last N months (0 = Monday): total, number of days seen, average per day."""
    rows = conn.execute(
        text(
            f"SELECT (EXTRACT(ISODOW FROM local_date)::int - 1) AS wd, -sum(amount_paise) AS spend, "
            f"count(DISTINCT local_date) AS days, count(*) AS n FROM ({EFFECTIVE} AND e.user_id = :u AND e.local_month >= :m) x "
            f"WHERE {SPEND} GROUP BY 1 ORDER BY 1"
        ),
        {"run": run, "u": user, "m": _months_ago(months)},
    ).all()
    by = {r.wd: r for r in rows}
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    return [
        {
            "weekday": i,
            "name": names[i],
            "spend_paise": int(by[i].spend) if i in by else 0,
            "days": by[i].days if i in by else 0,
            "count": by[i].n if i in by else 0,
            "average_paise": int(by[i].spend) // by[i].days if i in by and by[i].days else 0,
        }
        for i in range(7)
    ]


@router.get("/upcoming")
def upcoming(
    days: int = Query(30, ge=1, le=90),
    user: str = Depends(household),
    run: str = Depends(run_id),
    conn: Connection = Depends(get_conn),
):
    """Bills and income the engine expects soon, from recurring payments, plus credit-card due dates."""
    t = today()
    horizon = t + timedelta(days=days)
    rows = conn.execute(
        text(
            "SELECT s.series_id, s.series_type, s.cadence, s.typical_amount_paise, s.next_expected, s.status, "
            "s.category_code, COALESCE(m.name, rs.counterparty_key) AS name, rs.direction FROM recurring_series_state s "
            "JOIN recurring_series rs USING (series_id) LEFT JOIN merchant m ON m.merchant_id = s.merchant_id "
            "WHERE s.run_id = :run AND rs.user_id = :u AND s.status IN ('ACTIVE', 'MISSED') AND s.next_expected IS NOT NULL "
            "AND s.next_expected <= :h ORDER BY s.next_expected, s.series_id"
        ),
        {"run": run, "u": user, "h": horizon},
    ).all()
    items = [
        {
            "kind": "RECURRING",
            "id": r.series_id,
            "name": r.name,
            "direction": r.direction,
            "amount_paise": int(r.typical_amount_paise),
            "due": r.next_expected,
            "days_away": (r.next_expected - t).days,
            "overdue": r.next_expected < t,
            "series_type": r.series_type,
            "cadence": r.cadence,
            "category_code": r.category_code,
        }
        for r in rows
    ]
    for c in _cards(conn, user, run):
        if c["due_date"] and c["due_date"] <= horizon and c["balance_paise"] < 0:
            items.append(
                {
                    "kind": "CARD",
                    "id": c["account_id"],
                    "name": c["display_name"],
                    "direction": "DR",
                    "amount_paise": -c["balance_paise"],
                    "due": c["due_date"],
                    "days_away": (c["due_date"] - t).days,
                    "overdue": False,
                    "series_type": "CARD",
                    "cadence": "MONTHLY",
                    "category_code": None,
                }
            )
    items.sort(key=lambda i: (i["due"], i["name"]))
    out_total = sum(i["amount_paise"] for i in items if i["direction"] == "DR")
    in_total = sum(i["amount_paise"] for i in items if i["direction"] == "CR")
    return {"days": days, "items": items, "due_out_paise": out_total, "due_in_paise": in_total}


def _next_due(day: int, t: date) -> date:
    """The next date on or after today whose day-of-month is `day` (clamped to short months)."""
    y, m = t.year, t.month
    for _ in range(2):
        d = date(y, m, min(day, calendar.monthrange(y, m)[1]))
        if d >= t:
            return d
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return d


def _cards(conn, user, run) -> list[dict]:
    rows = conn.execute(
        text(
            "SELECT a.account_id, a.account_type, a.bank_code, a.masked_number, l.label, a.status, a.credit_limit_paise, "
            "m.due_day, m.statement_day, a.opening_balance_paise + COALESCE((SELECT sum(amount_paise) FROM txn t "
            "WHERE t.account_id = a.account_id), 0) AS balance_paise FROM account_holder h JOIN account a USING (account_id) "
            "LEFT JOIN account_label l USING (account_id) LEFT JOIN account_meta m USING (account_id) "
            "WHERE h.user_id = :u AND a.account_type = 'CREDIT_CARD' AND a.status = 'ACTIVE' ORDER BY a.account_id"
        ),
        {"u": user},
    ).all()
    t = today()
    out = []
    for r in rows:
        bal = int(r.balance_paise)
        limit = int(r.credit_limit_paise) if r.credit_limit_paise else None
        due = _next_due(r.due_day, t) if r.due_day else None
        out.append(
            {
                "account_id": r.account_id,
                "display_name": display_name(r),
                "balance_paise": bal,
                "limit_paise": limit,
                "used_paise": max(-bal, 0),
                "available_paise": (limit + bal) if limit else None,
                "utilisation": round(max(-bal, 0) / limit, 4) if limit else None,
                "due_day": r.due_day,
                "statement_day": r.statement_day,
                "due_date": due,
                "days_to_due": (due - t).days if due else None,
            }
        )
    return out


@router.get("/networth")
def networth(user: str = Depends(household), run: str = Depends(run_id), conn: Connection = Depends(get_conn)):
    """What you own minus what you owe: savings and UPI balances against credit-card dues, plus each card's headroom."""
    rows = conn.execute(
        text(
            "SELECT a.account_id, a.account_type, a.bank_code, a.masked_number, l.label, a.status, "
            "a.opening_balance_paise + COALESCE((SELECT sum(amount_paise) FROM txn t WHERE t.account_id = a.account_id), 0) "
            "AS balance_paise FROM account_holder h JOIN account a USING (account_id) LEFT JOIN account_label l USING (account_id) "
            "WHERE h.user_id = :u AND a.status = 'ACTIVE' ORDER BY a.account_id"
        ),
        {"u": user},
    ).all()
    assets = sum(int(r.balance_paise) for r in rows if r.account_type != "CREDIT_CARD" and r.balance_paise > 0)
    debts = sum(-int(r.balance_paise) for r in rows if r.balance_paise < 0)
    cards = _cards(conn, user, run)
    return {
        "net_worth_paise": assets - debts,
        "assets_paise": assets,
        "liabilities_paise": debts,
        "accounts": [
            {
                "account_id": r.account_id,
                "display_name": display_name(r),
                "account_type": r.account_type,
                "balance_paise": int(r.balance_paise),
            }
            for r in rows
        ],
        "cards": cards,
    }


@router.get("/alerts")
def alerts(user: str = Depends(household), run: str = Depends(run_id), conn: Connection = Depends(get_conn)):
    """Things worth a look right now: bills due in 3 days or overdue, budgets over or nearly over, cards due soon or
    nearly maxed, and savings goals that were reached."""
    t = today()
    month = f"{t.year}-{t.month:02d}"
    out: list[dict] = []
    for i in upcoming(7, user, run, conn)["items"]:
        if i["kind"] == "RECURRING" and i["overdue"]:
            out.append(
                {
                    "type": "BILL_OVERDUE",
                    "severity": "WARN",
                    "title": f"{i['name']} looks overdue",
                    "detail": f"Expected {i['due']}, nothing paid yet.",
                    "amount_paise": i["amount_paise"],
                }
            )
        elif i["direction"] == "DR" and i["days_away"] <= 3:
            when = "today" if i["days_away"] == 0 else f"in {i['days_away']} day{'s' if i['days_away'] != 1 else ''}"
            out.append(
                {
                    "type": "BILL_DUE",
                    "severity": "INFO",
                    "title": f"{i['name']} is due {when}",
                    "detail": f"About ₹{i['amount_paise'] / 100:,.2f}.",
                    "amount_paise": i["amount_paise"],
                }
            )
    lines = _budget(conn, run, user, month)[0]
    names = dict(conn.execute(text("SELECT category_code, name FROM category")).all())
    for x in lines:
        label = names.get(x.category_code, x.category_code)
        if x.status == "OVER":
            out.append(
                {
                    "type": "BUDGET_OVER",
                    "severity": "ALERT",
                    "title": f"{label} is over budget",
                    "detail": f"₹{x.actual_paise / 100:,.0f} spent of ₹{(x.budget_paise or 0) / 100:,.0f}.",
                    "amount_paise": x.actual_paise,
                }
            )
        elif x.status == "NEAR":
            out.append(
                {
                    "type": "BUDGET_NEAR",
                    "severity": "WARN",
                    "title": f"{label} is close to its limit",
                    "detail": f"₹{x.actual_paise / 100:,.0f} spent of ₹{(x.budget_paise or 0) / 100:,.0f}.",
                    "amount_paise": x.actual_paise,
                }
            )
    for c in _cards(conn, user, run):
        if c["days_to_due"] is not None and c["days_to_due"] <= 5 and c["used_paise"] > 0:
            out.append(
                {
                    "type": "CARD_DUE",
                    "severity": "WARN",
                    "title": f"{c['display_name']} payment due {c['due_date']}",
                    "detail": f"₹{c['used_paise'] / 100:,.2f} outstanding.",
                    "amount_paise": c["used_paise"],
                }
            )
        if c["utilisation"] is not None and c["utilisation"] >= 0.8:
            out.append(
                {
                    "type": "CARD_LIMIT",
                    "severity": "WARN",
                    "title": f"{c['display_name']} is {round(c['utilisation'] * 100)}% used",
                    "detail": "Close to the credit limit.",
                    "amount_paise": c["used_paise"],
                }
            )
    for g in conn.execute(
        text(
            "SELECT name, target_paise FROM goal WHERE user_id = :u AND completed_at IS NOT NULL "
            "AND completed_at > now() - interval '7 days'"
        ),
        {"u": user},
    ):
        out.append(
            {
                "type": "GOAL_REACHED",
                "severity": "INFO",
                "title": f"Goal reached: {g.name}",
                "detail": f"₹{g.target_paise / 100:,.0f} saved.",
                "amount_paise": int(g.target_paise),
            }
        )
    order = {"ALERT": 0, "WARN": 1, "INFO": 2}
    out.sort(key=lambda a: order[a["severity"]])
    return {"count": len(out), "alerts": out}
