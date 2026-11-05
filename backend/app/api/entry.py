"""Real households enter their own data: profile, accounts, transactions, budgets. Every optional field has a safe
default. After each change the household is re-run through the engine inside the latest run, so the reply already
carries the category, transfer pairing and budget effect. Sample (synthetic) households are read-only here."""
import datetime as dt
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Connection, text

from app import schema
from app.api.common import EFFECTIVE, household
from app.api.deps import Caller, current_user
from app.api.me import _txn, apply_override, audit
from app.db import get_conn
from app.households import is_real, next_txn_id
from app.jobs.pipeline_job import latest_run_id, refresh_household, today
from app.timeutil import ist_to_utc

router = APIRouter(prefix="/me", tags=["customer: my data"])
MAX_PAISE = 10**11                                   # ₹100 crore: a typo guard, not a business limit
VPA = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}@[a-z][a-z0-9]{1,31}$")
CHANNEL = "^(" + "|".join(schema.CHANNELS) + ")$"


def own(user: str = Depends(household)) -> str:
    if not is_real(user):
        raise HTTPException(403, "Sample households are read-only. Sign in with Google to keep your own records.")
    return user


def _rid(request: Request):
    return getattr(request.state, "request_id", None)


def _vpa(v: str | None) -> str | None:
    if v is None or not v.strip():
        return None
    v = v.strip().lower()
    if not VPA.match(v):
        raise ValueError("UPI ID looks like name@bank (letters, digits, dot, dash, underscore)")
    return v


# ---------- profile ----------
class ProfileIn(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=80)
    city: str | None = Field(None, min_length=1, max_length=40)
    state: str | None = Field(None, pattern="^[A-Z]{2}$")
    monthly_income_paise: int | None = Field(None, ge=0, le=MAX_PAISE)
    household_size: int | None = Field(None, ge=1, le=20)
    persona: str | None = Field(None, pattern="^(SALARIED|SELF_EMPLOYED|RETIRED)$")


def _band(paise: int) -> str:
    rupees = paise // 100
    return "LOW" if rupees < 25_000 else "MID" if rupees < 75_000 else "HIGH" if rupees < 200_000 else "AFFLUENT"


@router.get("/profile")
def profile(user: str = Depends(household), conn: Connection = Depends(get_conn)):
    p = conn.execute(text("SELECT * FROM user_profile WHERE user_id = :u"), {"u": user}).first()
    return dict(p._mapping) | {"sample": not is_real(user), "has_run": latest_run_id(conn) is not None}


@router.patch("/profile")
def update_profile(body: ProfileIn, request: Request, user: str = Depends(own), caller: Caller = Depends(current_user),
                   conn: Connection = Depends(get_conn)):
    changes = body.model_dump(exclude_none=True)
    if "monthly_income_paise" in changes:
        changes["income_band"] = _band(changes["monthly_income_paise"])
    if changes:
        sets = ", ".join(f"{k} = :{k}" for k in changes)
        conn.execute(text(f"UPDATE user_profile SET {sets} WHERE user_id = :u"), changes | {"u": user})
        audit(conn, caller.email, "PROFILE_UPDATE", "USER", user, _rid(request), changes)
        conn.commit()
    return profile(user, conn)


# ---------- accounts ----------
class AccountIn(BaseModel):
    account_type: str = Field(pattern="^(" + "|".join(schema.ACCOUNT_TYPES) + ")$")
    bank_code: str = Field("OTHR", pattern="^(" + "|".join(schema.BANKS) + ")$")
    last4: str | None = Field(None, pattern=r"^\d{4}$")
    label: str | None = Field(None, max_length=40, description="A name for the account; required for a custom UPI app")
    vpa: str | None = Field(None, max_length=64, description="Your own UPI ID on this account, e.g. name@okhdfcbank")
    opened_on: dt.date | None = None
    opening_balance_paise: int = Field(0, ge=-MAX_PAISE, le=MAX_PAISE)
    credit_limit_paise: int | None = Field(None, gt=0, le=MAX_PAISE)

    @field_validator("vpa")
    @classmethod
    def check_vpa(cls, v):
        return _vpa(v)

    @field_validator("label")
    @classmethod
    def check_label(cls, v):
        v = " ".join((v or "").split())
        if v and not re.fullmatch(r"[\w .&'()/-]{1,40}", v):
            raise ValueError("Use letters, digits and simple punctuation in the name")
        return v or None


@router.post("/accounts", status_code=201)
def create_account(body: AccountIn, request: Request, user: str = Depends(own),
                   caller: Caller = Depends(current_user), conn: Connection = Depends(get_conn)):
    opened = body.opened_on or today()
    if opened > today():
        raise HTTPException(422, "Opening date can't be in the future.")
    if body.account_type != "CREDIT_CARD" and body.credit_limit_paise:
        raise HTTPException(422, "Only credit cards have a credit limit.")
    is_app = body.bank_code in schema.UPI_PROVIDERS
    if body.account_type == "UPI" and not (is_app or body.bank_code == "OTHR"):
        raise HTTPException(422, "Pick a UPI app, or Other and type its name.")
    if body.account_type != "UPI" and is_app:
        raise HTTPException(422, "UPI apps are added as a UPI account, not as a bank account.")
    if body.account_type == "UPI" and body.bank_code == "OTHR" and not body.label:
        raise HTTPException(422, "Type a name for this UPI app.")
    if body.vpa and conn.execute(text("SELECT 1 FROM account WHERE vpa = :v"), {"v": body.vpa}).first():
        raise HTTPException(409, "That UPI ID is already linked to another account.")
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:u))"), {"u": user})
    n = conn.execute(text("SELECT count(*) FROM account WHERE user_id = :u"), {"u": user}).scalar() + 1
    if n > 99:
        raise HTTPException(409, "A household can have at most 99 accounts.")
    acc = f"ACC-{user}-{n:02d}"
    last4 = body.last4 or "0000"
    masked = f"XXXX-XXXX-XXXX-{last4}" if body.account_type == "CREDIT_CARD" else f"XXXXXXXX{last4}"
    conn.execute(text(
        "INSERT INTO account VALUES (:a, :u, :t, :b, :m, :v, 'INR', :o, NULL, 'ACTIVE', :bal, :lim)"),
        {"a": acc, "u": user, "t": body.account_type, "b": body.bank_code, "m": masked, "v": body.vpa, "o": opened,
         "bal": body.opening_balance_paise, "lim": body.credit_limit_paise})
    if body.label:
        conn.execute(text("INSERT INTO account_label VALUES (:a, :l)"), {"a": acc, "l": body.label})
    conn.execute(text("INSERT INTO account_holder VALUES (:a, :u, 'PRIMARY', :o)"), {"a": acc, "u": user, "o": opened})
    _account_event(conn, acc, "OPENED", opened)
    audit(conn, caller.email, "ACCOUNT_CREATE", "ACCOUNT", acc, _rid(request), body.model_dump())
    conn.commit()
    return {"account_id": acc, "masked_number": masked}


def _account_event(conn, acc, kind, day) -> None:
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('account_event'))"))
    # own range (AEV-9xxxxx) so a dataset reload, which renumbers sample events from 1, never collides (A36)
    last = conn.execute(text("SELECT max(event_id) FROM account_event WHERE event_id LIKE 'AEV-9%'")).scalar()
    eid = f"AEV-{int(last[4:]) + 1 if last else 900_001:06d}"
    conn.execute(text("INSERT INTO account_event VALUES (:e, :a, :k, :d, NULL)"),
                 {"e": eid, "a": acc, "k": kind, "d": day})


class CloseIn(BaseModel):
    closed_on: dt.date | None = None


@router.post("/accounts/{account_id}/close")
def close_account(account_id: str, body: CloseIn, request: Request, user: str = Depends(own),
                  caller: Caller = Depends(current_user), conn: Connection = Depends(get_conn)):
    a = _own_account(conn, user, account_id)
    if a.status == "CLOSED":
        raise HTTPException(409, "This account is already closed.")
    day = body.closed_on or today()
    last = conn.execute(text("SELECT max((posted_at AT TIME ZONE 'Asia/Kolkata')::date) FROM txn "
                             "WHERE account_id = :a"), {"a": account_id}).scalar()
    if day < a.opened_on or day > today() or (last and day < last):
        raise HTTPException(422, f"Closing date must be between {last or a.opened_on} and today.")
    conn.execute(text("UPDATE account SET status = 'CLOSED', closed_on = :d WHERE account_id = :a"),
                 {"d": day, "a": account_id})
    _account_event(conn, account_id, "CLOSED", day)
    audit(conn, caller.email, "ACCOUNT_CLOSE", "ACCOUNT", account_id, _rid(request), {"closed_on": day})
    conn.commit()
    return {"account_id": account_id, "status": "CLOSED", "refreshed": refresh_household(conn, user)}


def _own_account(conn, user, account_id):
    a = conn.execute(text("SELECT * FROM account WHERE account_id = :a AND user_id = :u"),
                     {"a": account_id, "u": user}).first()
    if a is None:
        raise HTTPException(404, "Not found.")
    return a


# ---------- transactions ----------
class TxnIn(BaseModel):
    account_id: str = Field(max_length=32)
    date: dt.date
    time: dt.time | None = Field(None, description="IST wall-clock time; noon if omitted")
    amount_paise: int = Field(gt=0, le=MAX_PAISE, description="Always positive; direction says which way")
    direction: str = Field(pattern="^(DR|CR)$", description="DR money out, CR money in")
    description: str = Field(min_length=1, max_length=160)
    channel: str = Field("UPI", pattern=CHANNEL)
    counterparty_vpa: str | None = Field(None, max_length=64)
    reference_no: str | None = Field(None, max_length=24, pattern=r"^[A-Za-z0-9/-]+$")
    category_code: str | None = Field(None, max_length=40, description="Optional: skip to let PAM categorize it")

    @field_validator("counterparty_vpa")
    @classmethod
    def check_vpa(cls, v):
        return _vpa(v)

    @field_validator("description")
    @classmethod
    def _clean(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("description can't be blank")
        return v


class TxnPatch(BaseModel):
    date: dt.date | None = None
    time: dt.time | None = None
    amount_paise: int | None = Field(None, gt=0, le=MAX_PAISE)
    direction: str | None = Field(None, pattern="^(DR|CR)$")
    description: str | None = Field(None, min_length=1, max_length=160)
    channel: str | None = Field(None, pattern=CHANNEL)
    counterparty_vpa: str | None = Field(None, max_length=64)
    reference_no: str | None = Field(None, max_length=24, pattern=r"^[A-Za-z0-9/-]*$")

    @field_validator("counterparty_vpa")
    @classmethod
    def check_vpa(cls, v):
        return _vpa(v)


def _check_date(a, day: dt.date) -> None:
    if day > today():
        raise HTTPException(422, "Date can't be in the future.")
    if day < a.opened_on:
        raise HTTPException(422, f"This account was opened on {a.opened_on}; the date must be on or after that.")
    if a.closed_on and day > a.closed_on:
        raise HTTPException(409, f"This account was closed on {a.closed_on}.")


def _result(conn, user, txn_id, refreshed: bool, extra: dict) -> dict:
    run = latest_run_id(conn)
    row = conn.execute(text(f"{EFFECTIVE} AND t.txn_id = :t"), {"run": run, "t": txn_id}).first() if run else None
    return {"txn_id": txn_id, "processed": row is not None and refreshed,
            "transaction": _txn(row) if row else None} | extra


@router.post("/transactions", status_code=201)
def add_transaction(body: TxnIn, request: Request, user: str = Depends(own), caller: Caller = Depends(current_user),
                    conn: Connection = Depends(get_conn)):
    a = _own_account(conn, user, body.account_id)
    _check_date(a, body.date)
    posted = ist_to_utc(dt.datetime.combine(body.date, body.time or dt.time(12, 0)))
    amount = -body.amount_paise if body.direction == "DR" else body.amount_paise
    dup = conn.execute(text(
        "SELECT txn_id FROM txn WHERE account_id = :a AND amount_paise = :amt AND lower(descriptor) = lower(:d) "
        "AND (posted_at AT TIME ZONE 'Asia/Kolkata')::date = :day LIMIT 1"),
        {"a": body.account_id, "amt": amount, "d": body.description, "day": body.date}).scalar()
    txn_id = next_txn_id(conn, body.date.year)
    conn.execute(text("INSERT INTO txn VALUES (:t, :a, :u, :p, :amt, 'INR', :ch, :d, :v, :r)"),
                 {"t": txn_id, "a": body.account_id, "u": user, "p": posted, "amt": amount, "ch": body.channel,
                  "d": body.description, "v": body.counterparty_vpa, "r": body.reference_no})
    if body.category_code:
        apply_override(conn, txn_id, body.category_code.strip().upper(), body.date, caller.email, "set when added",
                       _rid(request))
    audit(conn, caller.email, "TXN_CREATE", "TXN", txn_id, _rid(request), body.model_dump())
    conn.commit()
    # saved either way; a duplicate is flagged, not blocked (two identical chai payments a day are real) (A39)
    return _result(conn, user, txn_id, refresh_household(conn, user), {"possible_duplicate_of": dup})


def _own_txn_row(conn, user, txn_id):
    t = conn.execute(text("SELECT t.*, (t.posted_at AT TIME ZONE 'Asia/Kolkata') AS local_ts FROM txn t "
                          "WHERE t.txn_id = :t AND t.user_id = :u"), {"t": txn_id, "u": user}).first()
    if t is None:
        raise HTTPException(404, "Not found.")
    return t


@router.patch("/transactions/{txn_id}")
def edit_transaction(txn_id: str, body: TxnPatch, request: Request, user: str = Depends(own),
                     caller: Caller = Depends(current_user), conn: Connection = Depends(get_conn)):
    t = _own_txn_row(conn, user, txn_id)
    ch = body.model_dump(exclude_unset=True)
    day = ch.get("date") or t.local_ts.date()
    if "date" in ch or "time" in ch:
        _check_date(_own_account(conn, user, t.account_id), day)
        if day.year != t.local_ts.year:
            raise HTTPException(422, "Moving a transaction to another year isn't supported; delete and add it again.")
    clock = ch["time"] if ch.get("time") else t.local_ts.time()
    amount = ch.get("amount_paise", abs(t.amount_paise))
    sign = ch.get("direction", "DR" if t.amount_paise < 0 else "CR")
    new = {"p": ist_to_utc(dt.datetime.combine(day, clock)), "amt": -amount if sign == "DR" else amount,
           "d": " ".join(ch["description"].split()) if ch.get("description") else t.descriptor,
           "ch": ch.get("channel") or t.channel,
           "v": ch.get("counterparty_vpa", t.counterparty_vpa),
           "r": (ch["reference_no"] or None) if "reference_no" in ch else t.reference_no}
    conn.execute(text("UPDATE txn SET posted_at = :p, amount_paise = :amt, descriptor = :d, channel = :ch, "
                      "counterparty_vpa = :v, reference_no = :r WHERE txn_id = :t"), new | {"t": txn_id})
    audit(conn, caller.email, "TXN_EDIT", "TXN", txn_id, _rid(request), {"before": dict(t._mapping), "after": new})
    conn.commit()
    return _result(conn, user, txn_id, refresh_household(conn, user), {})


def purge_txn(conn: Connection, txn_id: str) -> None:
    """Remove a transaction and everything hanging off it. Caller commits and re-runs the household."""
    p = {"t": txn_id}
    for sql in ("UPDATE txn_enrichment SET link_txn_id = NULL WHERE link_txn_id = :t",
                "DELETE FROM txn_enrichment WHERE txn_id = :t",
                "DELETE FROM category_override WHERE txn_id = :t",
                "DELETE FROM txn_note WHERE txn_id = :t",
                "DELETE FROM exception_event WHERE exception_id IN (SELECT exception_id FROM exception_case "
                "WHERE entity_type = 'TXN' AND entity_id = :t)",
                "DELETE FROM exception_case WHERE entity_type = 'TXN' AND entity_id = :t",
                "DELETE FROM txn WHERE txn_id = :t"):
        conn.execute(text(sql), p)


@router.delete("/transactions/{txn_id}", status_code=204)
def delete_transaction(txn_id: str, request: Request, user: str = Depends(own),
                       caller: Caller = Depends(current_user), conn: Connection = Depends(get_conn)):
    t = _own_txn_row(conn, user, txn_id)
    purge_txn(conn, txn_id)
    audit(conn, caller.email, "TXN_DELETE", "TXN", txn_id, _rid(request), dict(t._mapping))
    conn.commit()
    refresh_household(conn, user)                       # the pair / refund link it was part of gets re-decided
    return Response(status_code=204)


# ---------- budgets ----------
class BudgetIn(BaseModel):
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    category_code: str = Field(min_length=1, max_length=40)
    amount_paise: int = Field(ge=0, le=MAX_PAISE, description="0 means 'I plan to spend nothing here'")


@router.put("/budgets")
def set_budget(body: BudgetIn, request: Request, user: str = Depends(own), caller: Caller = Depends(current_user),
               conn: Connection = Depends(get_conn)):
    code = body.category_code.strip().upper()
    c = conn.execute(text("SELECT kind, effective_to, replaced_by FROM category WHERE category_code = :c"),
                     {"c": code}).first()
    if c is None or c.kind not in ("EXPENSE",) or c.effective_to is not None:
        hint = f" Use {c.replaced_by}." if c is not None and c.replaced_by else ""
        raise HTTPException(422, f"'{code}' is not a spending category you can budget for.{hint}")
    bid = f"BUD-{user}-{body.month}-{code}"
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:b))"), {"b": bid})
    v = conn.execute(text("SELECT COALESCE(max(version), 0) + 1 FROM budget WHERE budget_id = :b"), {"b": bid}).scalar()
    conn.execute(text("INSERT INTO budget VALUES (:b, :v, :u, :m, :c, :amt, now())"),
                 {"b": bid, "v": v, "u": user, "m": body.month, "c": code, "amt": body.amount_paise})
    audit(conn, caller.email, "BUDGET_SET", "BUDGET", bid, _rid(request), body.model_dump() | {"version": v})
    conn.commit()
    return {"budget_id": bid, "version": v, "refreshed": refresh_household(conn, user)}


@router.delete("/budgets/{month}/{category_code}", status_code=204)
def delete_budget(month: str, category_code: str, request: Request, user: str = Depends(own),
                  caller: Caller = Depends(current_user), conn: Connection = Depends(get_conn)):
    bid = f"BUD-{user}-{month}-{category_code.upper()}"
    for sql in ("DELETE FROM exception_event WHERE exception_id IN (SELECT exception_id FROM exception_case "
                "WHERE entity_type = 'BUDGET' AND entity_id = :b)",
                "DELETE FROM exception_case WHERE entity_type = 'BUDGET' AND entity_id = :b",
                "DELETE FROM budget_resolution WHERE budget_id = :b"):
        conn.execute(text(sql), {"b": bid})
    if conn.execute(text("DELETE FROM budget WHERE budget_id = :b"), {"b": bid}).rowcount == 0:
        conn.rollback()
        raise HTTPException(404, "Not found.")
    audit(conn, caller.email, "BUDGET_DELETE", "BUDGET", bid, _rid(request), None)
    conn.commit()
    refresh_household(conn, user)
    return Response(status_code=204)
