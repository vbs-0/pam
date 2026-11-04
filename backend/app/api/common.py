"""Shared read helpers: latest run, month and paging parameters, the caller's household, effective categories."""
import base64
import binascii
from datetime import date

from fastapi import Depends, HTTPException, Query
from sqlalchemy import Connection, text

from app.api.deps import Caller, current_user
from app.db import get_conn
from app.jobs.pipeline_job import latest_run_id

MONTH = r"^\d{4}-(0[1-9]|1[0-2])$"


def run_id(conn: Connection = Depends(get_conn)) -> str:
    rid = latest_run_id(conn)
    if rid is None:
        raise HTTPException(409, "No successful pipeline run yet. An admin needs to run the pipeline first.")
    return rid


def month_q(month: str = Query(..., pattern=MONTH, examples=["2026-03"])) -> str:
    return month


def limit_q(limit: int = Query(50, ge=1, le=100)) -> int:
    return limit


def household(user_id: str | None = Query(None, description="ADMIN only: whose household to view"),
              caller: Caller = Depends(current_user), conn: Connection = Depends(get_conn)) -> str:
    """The profile this request is about. Customers always get their own; admins name one for support."""
    if caller.role == "CUSTOMER":
        if user_id not in (None, caller.profile_user_id):
            raise HTTPException(404, "Not found.")
        if caller.profile_user_id is None:
            raise HTTPException(409, "Your login is not linked to a household yet. Ask an admin to link it.")
        return caller.profile_user_id
    if caller.role != "ADMIN":
        raise HTTPException(403, "Customer views are for customers (admins can pass ?user_id=).")
    if not user_id or not conn.execute(text("SELECT 1 FROM user_profile WHERE user_id = :u"), {"u": user_id}).first():
        raise HTTPException(404, "Pass ?user_id= of an existing household.")
    return user_id


def encode_cursor(*parts) -> str:
    return base64.urlsafe_b64encode("|".join(str(p) for p in parts).encode()).decode().rstrip("=")


def decode_cursor(cursor: str, n: int) -> list[str]:
    try:
        parts = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode().split("|")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        parts = []
    if len(parts) != n or not all(parts):
        raise HTTPException(400, "That page link is invalid or expired. Start again from the first page.")
    return parts


def parse_date(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise HTTPException(400, "That page link is invalid or expired. Start again from the first page.") from None


def like_escape(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


# Enrichment of the given run with the latest human override applied on top (an override made after the run must
# show at once, E14). Kind follows the override's category the same way the engine derives it (kind_for).
EFFECTIVE = """
WITH ov AS (SELECT DISTINCT ON (txn_id) txn_id, category_code, override_id FROM category_override
            ORDER BY txn_id, created_at DESC, override_id DESC)
SELECT t.txn_id, t.account_id, t.user_id, t.posted_at, t.amount_paise, t.channel, t.descriptor, t.counterparty_vpa,
       t.reference_no, e.local_date, e.local_month, e.merchant_id, m.name AS merchant_name, e.confidence,
       e.decision, e.link_txn_id, e.series_id, e.rule_id, e.rule_version,
       COALESCE(ov.category_code, e.category_code) AS category_code,
       CASE WHEN ov.txn_id IS NULL THEN e.kind
            WHEN oc.kind IN ('TRANSFER', 'INCOME', 'UNKNOWN') THEN oc.kind
            WHEN t.amount_paise < 0 THEN 'EXPENSE' ELSE 'REFUND' END AS kind,
       ov.override_id
FROM txn_enrichment e
JOIN txn t ON t.txn_id = e.txn_id
LEFT JOIN ov ON ov.txn_id = e.txn_id
LEFT JOIN category oc ON oc.category_code = ov.category_code
LEFT JOIN merchant m ON m.merchant_id = e.merchant_id
WHERE e.run_id = :run
"""
