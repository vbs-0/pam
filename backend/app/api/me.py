"""Customer API: one household's accounts, transactions, budgets vs actual, recurring payments and insights.

Visibility: transactions on every account the household holds (joint accounts included); money totals and budgets
follow the engine and count a transaction for the account owner's household (docs/edge-cases.md A28).
"""
import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from app import schema
from app.api.common import (
    EFFECTIVE,
    decode_cursor,
    encode_cursor,
    household,
    like_escape,
    limit_q,
    month_q,
    parse_date,
    run_id,
)
from app.api.deps import Caller, current_user
from app.db import get_conn
from app.engine.budgets import BudgetResolution, budget_lines
from app.jobs.sql import next_number

router = APIRouter(tags=["customer"])
me = APIRouter(prefix="/me", tags=["customer"])
TXN_FIELDS = ("txn_id", "local_date", "posted_at", "account_id", "amount_paise", "channel", "descriptor",
              "counterparty_vpa", "merchant_id", "merchant_name", "category_code", "kind", "confidence", "decision")
HELD = "SELECT account_id FROM account_holder WHERE user_id = :u"


def _txn(r) -> dict:
    d = {k: getattr(r, k) for k in TXN_FIELDS}
    d["confidence"] = float(d["confidence"]) if d["confidence"] is not None else None
    d["overridden"] = r.override_id is not None
    return d


@router.get("/categories")
def categories(conn: Connection = Depends(get_conn), _: Caller = Depends(current_user)):
    rows = conn.execute(text("SELECT category_code, name, group_code, kind, effective_to, replaced_by FROM category "
                             "ORDER BY group_code, name"))
    return [{"code": r.category_code, "name": r.name, "group": r.group_code, "kind": r.kind,
             "active": r.effective_to is None and r.kind != "UNKNOWN", "replaced_by": r.replaced_by} for r in rows]


@me.get("/accounts")
def accounts(user: str = Depends(household), conn: Connection = Depends(get_conn)):
    rows = conn.execute(text(
        "SELECT a.account_id, a.account_type, a.bank_code, a.masked_number, a.vpa, l.label, a.status, a.opened_on, "
        "a.closed_on, a.credit_limit_paise, h.holder_role, a.user_id <> :u AS shared_from_other_household, "
        "a.opening_balance_paise + COALESCE((SELECT sum(amount_paise) FROM txn t WHERE t.account_id = a.account_id),"
        " 0) AS balance_paise "
        "FROM account_holder h JOIN account a USING (account_id) LEFT JOIN account_label l USING (account_id) "
        "WHERE h.user_id = :u ORDER BY a.account_id"),
        {"u": user})
    return [{**r._mapping, "display_name": display_name(r)} for r in rows]


TYPE_NAMES = {"SAVINGS": "Savings", "CREDIT_CARD": "Credit card", "UPI": "UPI"}


def display_name(a) -> str:
    """'HDFC Bank savings ··4321', 'PhonePe UPI', or the user's own name for it."""
    last4 = a.masked_number[-4:]
    base = a.label or schema.UPI_PROVIDERS.get(a.bank_code) or schema.BANK_NAMES.get(a.bank_code) or "Other bank"
    if a.account_type == "UPI":
        return a.label or f"{base} UPI"
    kind = TYPE_NAMES.get(a.account_type, a.account_type).lower()
    return f"{base} {kind} ··{last4}" if last4 != "0000" else f"{base} {kind}"


@me.get("/transactions")
def transactions(user: str = Depends(household), run: str = Depends(run_id), limit: int = Depends(limit_q),
                 month: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
                 category: str | None = Query(None, max_length=40), account_id: str | None = Query(None, max_length=32),
                 kind: str | None = Query(None, pattern="^(EXPENSE|REFUND|INCOME|TRANSFER|REVERSAL|UNKNOWN)$"),
                 q: str | None = Query(None, min_length=1, max_length=60), cursor: str | None = None,
                 conn: Connection = Depends(get_conn)):
    sql = [f"SELECT * FROM ({EFFECTIVE} AND t.account_id IN ({HELD})) x WHERE true"]
    p: dict = {"run": run, "u": user, "lim": limit + 1}
    for col, val in (("local_month", month), ("category_code", category), ("account_id", account_id),
                     ("kind", kind)):
        if val:
            sql.append(f"AND {col} = :{col}")
            p[col] = val
    if q:
        sql.append(r"AND descriptor ILIKE :q ESCAPE '\'")
        p["q"] = like_escape(q)
    if cursor:
        d, tid = decode_cursor(cursor, 2)
        sql.append("AND (local_date, txn_id) < (:cd, :ct)")
        p.update(cd=parse_date(d), ct=tid)
    sql.append("ORDER BY local_date DESC, txn_id DESC LIMIT :lim")
    rows = conn.execute(text(" ".join(sql)), p).all()
    more = len(rows) > limit
    rows = rows[:limit]
    return {"items": [_txn(r) for r in rows],
            "next_cursor": encode_cursor(rows[-1].local_date, rows[-1].txn_id) if more else None}


def _own_txn(conn, run, user, txn_id):
    r = conn.execute(text(f"{EFFECTIVE} AND t.txn_id = :t AND t.account_id IN ({HELD})"),
                     {"run": run, "t": txn_id, "u": user}).first()
    if r is None:
        raise HTTPException(404, "Not found.")          # someone else's txn looks exactly like a missing one (A01)
    return r


@me.get("/transactions/{txn_id}")
def transaction(txn_id: str, user: str = Depends(household), run: str = Depends(run_id),
                conn: Connection = Depends(get_conn)):
    r = _own_txn(conn, run, user, txn_id)
    d = _txn(r) | {"reference_no": r.reference_no, "link_txn_id": r.link_txn_id, "series_id": r.series_id,
                   "rule_id": r.rule_id, "rule_version": r.rule_version}
    d["overrides"] = [dict(o._mapping) for o in conn.execute(text(
        "SELECT override_id, category_code, actor, reason, created_at FROM category_override WHERE txn_id = :t "
        "ORDER BY created_at DESC, override_id DESC"), {"t": txn_id})]
    return d


class CategoryIn(BaseModel):
    category_code: str = Field(min_length=1, max_length=40)
    reason: str | None = Field(None, max_length=300)


def apply_override(conn: Connection, txn_id: str, code: str, local_date: date, actor: str, reason: str | None,
                   request_id: str | None) -> str:
    """Validate the category, record the override, close an open UNCATEGORIZED case, audit. Caller commits."""
    cat = conn.execute(text("SELECT kind, effective_from, effective_to, replaced_by FROM category "
                            "WHERE category_code = :c"), {"c": code}).first()
    if cat is None or cat.kind == "UNKNOWN":
        raise HTTPException(422, f"'{code}' is not a category you can choose.")
    if cat.effective_to is not None and cat.effective_to < local_date.replace(day=1) \
            or cat.effective_from > local_date:
        hint = f" Use {cat.replaced_by} instead." if cat.replaced_by else ""
        raise HTTPException(422, f"'{code}' was not in use on {local_date}.{hint}")
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('category_override'))"))
    oid = f"OVR-{next_number(conn, schema.category_override, 'override_id'):06d}"
    conn.execute(text("INSERT INTO category_override VALUES (:o, :t, :c, :a, :r, clock_timestamp())"),
                 {"o": oid, "t": txn_id, "c": code, "a": actor, "r": reason})
    for x in conn.execute(text("SELECT exception_id, status FROM exception_case WHERE exception_type = "
                               "'UNCATEGORIZED' AND entity_id = :t AND status IN ('OPEN', 'IN_REVIEW') FOR UPDATE"),
                          {"t": txn_id}).all():
        conn.execute(text("UPDATE exception_case SET status = 'RESOLVED', updated_at = now() "
                          "WHERE exception_id = :x"), {"x": x.exception_id})
        conn.execute(text("INSERT INTO exception_event SELECT CAST(:x AS varchar), COALESCE(max(seq), 0) + 1, "
                          ":f, 'RESOLVED', :a, "
                          ":n, now() FROM exception_event WHERE exception_id = :x"),
                     {"x": x.exception_id, "f": x.status, "a": actor, "n": f"category set to {code} ({oid})"})
    audit(conn, actor, "CATEGORY_OVERRIDE", "TXN", txn_id, request_id, {"override_id": oid, "category_code": code})
    return oid


def audit(conn, actor, action, entity_type, entity_id, request_id, detail) -> None:
    conn.execute(text("INSERT INTO audit_event (at, actor, action, entity_type, entity_id, request_id, detail) "
                      "VALUES (now(), :a, :ac, :et, :e, :r, CAST(:d AS jsonb))"),
                 {"a": actor, "ac": action, "et": entity_type, "e": entity_id, "r": request_id,
                  "d": json.dumps(detail, default=str)})


@me.post("/transactions/{txn_id}/category", status_code=201)
def set_category(txn_id: str, body: CategoryIn, request: Request,
                 user: str = Depends(household), run: str = Depends(run_id), caller: Caller = Depends(current_user),
                 conn: Connection = Depends(get_conn)):
    r = _own_txn(conn, run, user, txn_id)
    code = body.category_code.strip().upper()
    oid = apply_override(conn, txn_id, code, r.local_date, caller.email, body.reason,
                         getattr(request.state, "request_id", None))
    conn.commit()
    return {"override_id": oid, "category_code": code}


def _budget(conn, run, user, month):
    rows = conn.execute(text(
        "SELECT b.budget_id, b.version, b.category_code AS submitted, b.amount_paise, r.resolved_category_code, "
        "r.resolution FROM budget_resolution r JOIN budget b USING (budget_id, version) "
        "WHERE r.run_id = :run AND b.user_id = :u AND b.month = :m ORDER BY b.budget_id"),
        {"run": run, "u": user, "m": month}).all()
    res = [BudgetResolution(r.budget_id, r.version, user, month, r.submitted, r.resolved_category_code, r.resolution,
                            r.amount_paise) for r in rows]
    spend = {c: v for c, v in conn.execute(text(
        f"SELECT category_code, -sum(amount_paise) FROM ({EFFECTIVE} AND e.user_id = :u AND e.local_month = :m) x "
        "WHERE kind IN ('EXPENSE', 'REFUND') OR (kind = 'UNKNOWN' AND amount_paise < 0) GROUP BY 1"),
        {"run": run, "u": user, "m": month})}
    income = conn.execute(text(
        f"SELECT COALESCE(sum(amount_paise), 0) FROM ({EFFECTIVE} AND e.user_id = :u AND e.local_month = :m) x "
        "WHERE kind = 'INCOME' OR (kind = 'UNKNOWN' AND amount_paise > 0)"), {"run": run, "u": user, "m": month}
    ).scalar()
    return budget_lines(res, spend), res, spend, int(income)


@me.get("/budgets")
def budgets(month: str = Depends(month_q), user: str = Depends(household), run: str = Depends(run_id),
            conn: Connection = Depends(get_conn)):
    lines, res, _, _ = _budget(conn, run, user, month)
    names = dict(conn.execute(text("SELECT category_code, name FROM category")).all())
    return {"month": month,
            "lines": [{"category_code": x.category_code, "category_name": names.get(x.category_code),
                       "budget_paise": x.budget_paise, "actual_paise": x.actual_paise, "ratio": x.ratio,
                       "status": x.status, "budget_ids": list(x.budget_ids)} for x in lines],
            "total_budget_paise": sum(x.budget_paise or 0 for x in lines),
            "total_actual_paise": sum(x.actual_paise for x in lines),
            "remapped": [{"budget_id": r.budget_id, "submitted_code": r.submitted_code, "resolved_code":
                          r.resolved_code, "resolution": r.resolution} for r in res
                         if r.resolution != "VALID" and r.resolved_code],
            "unmapped": [{"budget_id": r.budget_id, "submitted_code": r.submitted_code, "amount_paise":
                          r.amount_paise} for r in res if not r.resolved_code]}


@me.get("/summary")
def summary(month: str = Depends(month_q), user: str = Depends(household), run: str = Depends(run_id),
            conn: Connection = Depends(get_conn)):
    lines, _, spend, income = _budget(conn, run, user, month)
    total = sum(spend.values())
    top = sorted(((c, v) for c, v in spend.items() if v > 0), key=lambda cv: -cv[1])[:5]
    naive, contra = conn.execute(text(
        f"SELECT COALESCE(-sum(amount_paise) FILTER (WHERE amount_paise < 0), 0), "
        f"COALESCE(-sum(amount_paise) FILTER (WHERE amount_paise < 0 AND kind = 'TRANSFER'), 0) "
        f"FROM ({EFFECTIVE} AND e.user_id = :u AND e.local_month = :m) x"), {"run": run, "u": user, "m": month}).one()
    return {"month": month, "income_paise": income, "spend_paise": total,
            "naive_spend_paise": int(naive), "transfers_out_paise": int(contra),
            "savings_rate": round((income - total) / income, 4) if income > 0 else None,
            "top_categories": [{"code": c, "spend_paise": v} for c, v in top],
            "over_budget_count": sum(x.status == "OVER" for x in lines),
            "near_budget_count": sum(x.status == "NEAR" for x in lines)}


@me.get("/trend")
def trend(months: int = Query(12, ge=1, le=36), user: str = Depends(household), run: str = Depends(run_id),
          conn: Connection = Depends(get_conn)):
    """Spend and income per month, oldest first, same rules as the summary."""
    rows = conn.execute(text(
        f"SELECT local_month AS month, COALESCE(-sum(amount_paise) FILTER (WHERE kind IN ('EXPENSE', 'REFUND') OR "
        f"(kind = 'UNKNOWN' AND amount_paise < 0)), 0) AS spend_paise, COALESCE(sum(amount_paise) FILTER (WHERE "
        f"kind = 'INCOME' OR (kind = 'UNKNOWN' AND amount_paise > 0)), 0) AS income_paise "
        f"FROM ({EFFECTIVE} AND e.user_id = :u) x GROUP BY 1 ORDER BY 1 DESC LIMIT :n"),
        {"run": run, "u": user, "n": months}).all()
    return [{"month": r.month, "spend_paise": int(r.spend_paise), "income_paise": int(r.income_paise)}
            for r in reversed(rows)]


@me.get("/recurring")
def recurring(user: str = Depends(household), run: str = Depends(run_id), conn: Connection = Depends(get_conn)):
    rows = conn.execute(text(
        "SELECT s.*, m.name AS merchant_name, rs.counterparty_key, rs.direction FROM recurring_series_state s "
        "JOIN recurring_series rs USING (series_id) LEFT JOIN merchant m ON m.merchant_id = s.merchant_id "
        "WHERE s.run_id = :run AND rs.user_id = :u ORDER BY s.status, s.next_expected NULLS LAST, s.series_id"),
        {"run": run, "u": user}).all()
    events: dict[str, list] = {}
    for e in conn.execute(text(
            "SELECT e.series_id, e.seq, e.event_type, e.event_date, e.detail FROM recurring_series_event e "
            "JOIN recurring_series rs USING (series_id) WHERE e.run_id = :run AND rs.user_id = :u "
            "ORDER BY e.series_id, e.seq"), {"run": run, "u": user}):
        events.setdefault(e.series_id, []).append({"seq": e.seq, "type": e.event_type, "date": e.event_date,
                                                   "detail": e.detail})
    out = []
    for r in rows:
        d = dict(r._mapping)
        d.pop("run_id")
        d["events"] = events.get(r.series_id, [])[-12:]
        out.append(d)
    return out


@me.get("/insights")
def insights(month: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), user: str = Depends(household),
             run: str = Depends(run_id), conn: Connection = Depends(get_conn)):
    rows = conn.execute(text(
        "SELECT insight_id, month, insight_type, severity, category_code, metric_paise, baseline_paise, message, "
        "evidence FROM insight WHERE run_id = :run AND user_id = :u AND (CAST(:m AS text) IS NULL OR month = :m) "
        "ORDER BY month DESC, CASE severity WHEN 'ALERT' THEN 0 WHEN 'WARN' THEN 1 ELSE 2 END, insight_id"),
        {"run": run, "u": user, "m": month})
    return [dict(r._mapping) for r in rows]


router.include_router(me)
