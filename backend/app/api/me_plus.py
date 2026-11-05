"""Account edits, savings goals, budget carry-over, alert preferences, and household sharing (invite a partner so two
logins see one register). Writes are for real households only."""

import datetime as dt
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Connection, text

from app import mail
from app.api.common import household
from app.api.deps import Caller, current_user
from app.api.entry import MAX_PAISE, _own_account, _rid, _vpa, own
from app.api.me import audit
from app.db import get_conn
from app.households import create_household, is_real
from app.jobs.pipeline_job import today

router = APIRouter(prefix="/me", tags=["customer: more"])


# ---------- account edits ----------
class AccountPatch(BaseModel):
    label: str | None = Field(None, max_length=40, description="Rename the account; empty clears the custom name")
    credit_limit_paise: int | None = Field(None, gt=0, le=MAX_PAISE)
    vpa: str | None = Field(None, max_length=64)
    due_day: int | None = Field(None, ge=1, le=31, description="Credit cards: day of month the bill is due")
    statement_day: int | None = Field(None, ge=1, le=31)
    balance_paise: int | None = Field(
        None, ge=-MAX_PAISE, le=MAX_PAISE, description="What the account really holds today; fixes the opening balance"
    )

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
        return v


@router.patch("/accounts/{account_id}")
def edit_account(
    account_id: str,
    body: AccountPatch,
    request: Request,
    user: str = Depends(own),
    caller: Caller = Depends(current_user),
    conn: Connection = Depends(get_conn),
):
    a = _own_account(conn, user, account_id)
    ch = body.model_dump(exclude_unset=True)
    if not ch:
        raise HTTPException(422, "Nothing to change.")
    if a.account_type != "CREDIT_CARD" and ({"credit_limit_paise", "due_day", "statement_day"} & ch.keys()):
        raise HTTPException(422, "Credit limit and due dates apply to credit cards only.")
    if "label" in ch:
        if not ch["label"] and a.account_type == "UPI" and a.bank_code == "OTHR":
            raise HTTPException(422, "A custom UPI app needs a name.")
        if ch["label"]:
            conn.execute(
                text("INSERT INTO account_label VALUES (:a, :l) ON CONFLICT (account_id) DO UPDATE SET label = :l"),
                {"a": account_id, "l": ch["label"]},
            )
        else:
            conn.execute(text("DELETE FROM account_label WHERE account_id = :a"), {"a": account_id})
    if "credit_limit_paise" in ch:
        conn.execute(
            text("UPDATE account SET credit_limit_paise = :v WHERE account_id = :a"),
            {"v": ch["credit_limit_paise"], "a": account_id},
        )
    if "vpa" in ch:
        if (
            ch["vpa"]
            and conn.execute(
                text("SELECT 1 FROM account WHERE vpa = :v AND account_id <> :a"), {"v": ch["vpa"], "a": account_id}
            ).first()
        ):
            raise HTTPException(409, "That UPI ID is already linked to another account.")
        if a.account_type == "CREDIT_CARD" and ch["vpa"]:
            raise HTTPException(422, "A credit card has no UPI ID.")
        conn.execute(text("UPDATE account SET vpa = :v WHERE account_id = :a"), {"v": ch["vpa"], "a": account_id})
    if {"due_day", "statement_day"} & ch.keys():
        conn.execute(
            text(
                "INSERT INTO account_meta (account_id, due_day, statement_day) VALUES (:a, :d, :s) ON CONFLICT "
                "(account_id) DO UPDATE SET due_day = COALESCE(:d, account_meta.due_day), "
                "statement_day = COALESCE(:s, account_meta.statement_day)"
            ),
            {"a": account_id, "d": ch.get("due_day"), "s": ch.get("statement_day")},
        )
    if "balance_paise" in ch and ch["balance_paise"] is not None:
        moved = conn.execute(
            text("SELECT COALESCE(sum(amount_paise), 0) FROM txn WHERE account_id = :a"), {"a": account_id}
        ).scalar()
        conn.execute(
            text("UPDATE account SET opening_balance_paise = :o WHERE account_id = :a"),
            {"o": ch["balance_paise"] - int(moved), "a": account_id},
        )
    audit(conn, caller.email, "ACCOUNT_EDIT", "ACCOUNT", account_id, _rid(request), ch)
    conn.commit()
    return {"account_id": account_id, "updated": sorted(ch)}


# ---------- goals ----------
class GoalIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    target_paise: int = Field(gt=0, le=MAX_PAISE)
    deadline: dt.date | None = None
    saved_paise: int = Field(0, ge=0, le=MAX_PAISE)

    @field_validator("name")
    @classmethod
    def _n(cls, v):
        v = " ".join(v.split())
        if not v:
            raise ValueError("Give the goal a name")
        return v


class GoalPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=60)
    target_paise: int | None = Field(None, gt=0, le=MAX_PAISE)
    deadline: dt.date | None = None


class Contribute(BaseModel):
    amount_paise: int = Field(description="Positive to add, negative to take back out")

    @field_validator("amount_paise")
    @classmethod
    def _a(cls, v):
        if v == 0 or abs(v) > MAX_PAISE:
            raise ValueError("Enter a non-zero amount")
        return v


def _goal_out(g) -> dict:
    t = today()
    left = max(int(g.target_paise) - int(g.saved_paise), 0)
    days = (g.deadline - t).days if g.deadline else None
    months = max(-(-days // 30), 1) if days is not None and days > 0 else None
    return {
        "goal_id": g.goal_id,
        "name": g.name,
        "target_paise": int(g.target_paise),
        "saved_paise": int(g.saved_paise),
        "remaining_paise": left,
        "progress": round(min(int(g.saved_paise) / int(g.target_paise), 1), 4),
        "deadline": g.deadline,
        "days_left": days,
        "monthly_needed_paise": -(-left // months) if months and left else None,
        "completed": g.completed_at is not None,
        "completed_at": g.completed_at,
    }


@router.get("/goals")
def goals(user: str = Depends(household), conn: Connection = Depends(get_conn)):
    rows = conn.execute(
        text(
            "SELECT * FROM goal WHERE user_id = :u ORDER BY completed_at IS NOT NULL, deadline NULLS LAST, created_at"
        ),
        {"u": user},
    )
    return [_goal_out(g) for g in rows]


def _own_goal(conn, user, goal_id):
    g = conn.execute(
        text("SELECT * FROM goal WHERE goal_id = :g AND user_id = :u FOR UPDATE"), {"g": goal_id, "u": user}
    ).first()
    if g is None:
        raise HTTPException(404, "Not found.")
    return g


@router.post("/goals", status_code=201)
def add_goal(body: GoalIn, user: str = Depends(own), conn: Connection = Depends(get_conn)):
    if body.deadline and body.deadline <= today():
        raise HTTPException(422, "The deadline has to be a future date.")
    if conn.execute(text("SELECT count(*) FROM goal WHERE user_id = :u"), {"u": user}).scalar() >= 30:
        raise HTTPException(409, "You can keep up to 30 goals.")
    gid = f"GOL-{user}-{secrets.token_hex(3)}"
    done = body.saved_paise >= body.target_paise
    conn.execute(
        text(
            "INSERT INTO goal (goal_id, user_id, name, target_paise, saved_paise, deadline, completed_at) VALUES "
            "(:i, :u, :n, :t, :s, :d, CASE WHEN :done THEN now() END)"
        ),
        {
            "i": gid,
            "u": user,
            "n": body.name,
            "t": body.target_paise,
            "s": body.saved_paise,
            "d": body.deadline,
            "done": done,
        },
    )
    conn.commit()
    return _goal_out(_own_goal(conn, user, gid))


@router.patch("/goals/{goal_id}")
def edit_goal(goal_id: str, body: GoalPatch, user: str = Depends(own), conn: Connection = Depends(get_conn)):
    g = _own_goal(conn, user, goal_id)
    ch = body.model_dump(exclude_unset=True)
    name = " ".join(ch["name"].split()) if ch.get("name") else g.name
    target = ch.get("target_paise") or g.target_paise
    deadline = ch.get("deadline", g.deadline)
    conn.execute(
        text(
            "UPDATE goal SET name = :n, target_paise = :t, deadline = :d, completed_at = CASE WHEN saved_paise >= :t "
            "THEN COALESCE(completed_at, now()) END WHERE goal_id = :g"
        ),
        {"n": name, "t": target, "d": deadline, "g": goal_id},
    )
    conn.commit()
    return _goal_out(_own_goal(conn, user, goal_id))


@router.post("/goals/{goal_id}/contribute")
def contribute(goal_id: str, body: Contribute, user: str = Depends(own), conn: Connection = Depends(get_conn)):
    g = _own_goal(conn, user, goal_id)
    saved = max(int(g.saved_paise) + body.amount_paise, 0)
    conn.execute(
        text(
            "UPDATE goal SET saved_paise = :s, completed_at = CASE WHEN :s >= target_paise THEN COALESCE(completed_at, now()) "
            "END WHERE goal_id = :g"
        ),
        {"s": saved, "g": goal_id},
    )
    conn.commit()
    return _goal_out(_own_goal(conn, user, goal_id))


@router.delete("/goals/{goal_id}", status_code=204)
def delete_goal(goal_id: str, user: str = Depends(own), conn: Connection = Depends(get_conn)):
    _own_goal(conn, user, goal_id)
    conn.execute(text("DELETE FROM goal WHERE goal_id = :g"), {"g": goal_id})
    conn.commit()


# ---------- budget carry-over ----------
class CarryIn(BaseModel):
    category_code: str = Field(min_length=1, max_length=40)
    enabled: bool


@router.put("/budgets/carry")
def set_carry(
    body: CarryIn,
    request: Request,
    user: str = Depends(own),
    caller: Caller = Depends(current_user),
    conn: Connection = Depends(get_conn),
):
    """Turn rollover on or off for one category: what you did not spend last month is added to this month's limit."""
    code = body.category_code.strip().upper()
    if (
        conn.execute(text("SELECT 1 FROM category WHERE category_code = :c AND kind = 'EXPENSE'"), {"c": code}).first()
        is None
    ):
        raise HTTPException(422, f"'{code}' is not a spending category.")
    if body.enabled:
        conn.execute(text("INSERT INTO budget_carry VALUES (:u, :c) ON CONFLICT DO NOTHING"), {"u": user, "c": code})
    else:
        conn.execute(text("DELETE FROM budget_carry WHERE user_id = :u AND category_code = :c"), {"u": user, "c": code})
    audit(conn, caller.email, "BUDGET_CARRY", "USER", user, _rid(request), body.model_dump())
    conn.commit()
    return {"category_code": code, "enabled": body.enabled}


# ---------- alert preferences ----------
class NotifyIn(BaseModel):
    email_digest: bool
    bills: bool = True
    budgets: bool = True
    cards: bool = True


@router.get("/notifications")
def get_notifications(caller: Caller = Depends(current_user), conn: Connection = Depends(get_conn)):
    r = conn.execute(
        text("SELECT email_digest, bills, budgets, cards, last_sent_on FROM notify_pref WHERE app_user_id = :i"),
        {"i": caller.app_user_id},
    ).first()
    base = {"email_digest": False, "bills": True, "budgets": True, "cards": True, "last_sent_on": None}
    return (dict(r._mapping) if r else base) | {"email": caller.email, "mail_configured": mail.configured()}


@router.put("/notifications")
def put_notifications(body: NotifyIn, caller: Caller = Depends(current_user), conn: Connection = Depends(get_conn)):
    conn.execute(
        text(
            "INSERT INTO notify_pref (app_user_id, email_digest, bills, budgets, cards) VALUES (:i, :e, :b, :g, :c) "
            "ON CONFLICT (app_user_id) DO UPDATE SET email_digest = :e, bills = :b, budgets = :g, cards = :c"
        ),
        {"i": caller.app_user_id, "e": body.email_digest, "b": body.bills, "g": body.budgets, "c": body.cards},
    )
    conn.commit()
    return get_notifications(caller, conn)


# ---------- household sharing ----------
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I


def _need_household(caller: Caller) -> str:
    if caller.role != "CUSTOMER" or not caller.profile_user_id or not is_real(caller.profile_user_id):
        raise HTTPException(403, "Sharing is for your own register. Sample households and staff logins cannot share.")
    return caller.profile_user_id


@router.get("/household/members")
def members(caller: Caller = Depends(current_user), conn: Connection = Depends(get_conn)):
    hh = _need_household(caller)
    rows = conn.execute(
        text(
            "SELECT app_user_id, email, created_at FROM app_user WHERE profile_user_id = :h AND role = 'CUSTOMER' "
            "ORDER BY created_at, app_user_id"
        ),
        {"h": hh},
    ).all()
    owner = rows[0].app_user_id if rows else None
    invites = conn.execute(
        text(
            "SELECT code, expires_at FROM household_invite WHERE household_id = :h AND used_by IS NULL AND "
            "expires_at > now() ORDER BY expires_at"
        ),
        {"h": hh},
    ).all()
    return {
        "household_id": hh,
        "you": caller.app_user_id,
        "owner": owner,
        "members": [
            {
                "app_user_id": r.app_user_id,
                "email": r.email,
                "joined": r.created_at,
                "is_owner": r.app_user_id == owner,
                "you": r.app_user_id == caller.app_user_id,
            }
            for r in rows
        ],
        "invites": [{"code": i.code, "expires_at": i.expires_at} for i in invites],
    }


@router.post("/household/invite", status_code=201)
def invite(request: Request, caller: Caller = Depends(current_user), conn: Connection = Depends(get_conn)):
    """A one-time code (valid 3 days) the other person enters after signing in, to join this register."""
    hh = _need_household(caller)
    if (
        conn.execute(
            text(
                "SELECT count(*) FROM household_invite WHERE household_id = :h AND used_by IS NULL AND expires_at > now()"
            ),
            {"h": hh},
        ).scalar()
        >= 5
    ):
        raise HTTPException(409, "You have 5 unused invites. Wait for them to expire or be used.")
    if conn.execute(text("SELECT count(*) FROM app_user WHERE profile_user_id = :h"), {"h": hh}).scalar() >= 6:
        raise HTTPException(409, "A household can have up to 6 logins.")
    code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    conn.execute(
        text("INSERT INTO household_invite VALUES (:c, :h, :b, now() + interval '3 days', NULL, NULL)"),
        {"c": code, "h": hh, "b": caller.app_user_id},
    )
    audit(conn, caller.email, "HOUSEHOLD_INVITE", "USER", hh, _rid(request), None)
    conn.commit()
    return {"code": code, "expires_in_days": 3}


class JoinIn(BaseModel):
    code: str = Field(min_length=6, max_length=12)


def _empty(conn, hh: str) -> bool:
    return conn.execute(text("SELECT 1 FROM account WHERE user_id = :h LIMIT 1"), {"h": hh}).first() is None


@router.post("/household/join")
def join(body: JoinIn, request: Request, caller: Caller = Depends(current_user), conn: Connection = Depends(get_conn)):
    """Use an invite code: this login now sees the inviter's register. Only allowed while your own register is empty."""
    if caller.role != "CUSTOMER":
        raise HTTPException(403, "Only customer logins can join a household.")
    code = body.code.strip().upper().replace("-", "").replace(" ", "")
    inv = conn.execute(text("SELECT * FROM household_invite WHERE code = :c FOR UPDATE"), {"c": code}).first()
    if inv is None or inv.used_by or inv.expires_at < dt.datetime.now(dt.UTC):
        raise HTTPException(404, "That code is not valid. Ask for a new invite.")
    if caller.profile_user_id == inv.household_id:
        raise HTTPException(409, "You are already in this household.")
    if caller.profile_user_id and not _empty(conn, caller.profile_user_id):
        raise HTTPException(
            409, "You already have accounts of your own. Export a backup, then start from an empty register to join."
        )
    conn.execute(
        text("UPDATE app_user SET profile_user_id = :h WHERE app_user_id = :i"),
        {"h": inv.household_id, "i": caller.app_user_id},
    )
    conn.execute(
        text("UPDATE household_invite SET used_by = :i, used_at = now() WHERE code = :c"),
        {"i": caller.app_user_id, "c": code},
    )
    audit(
        conn, caller.email, "HOUSEHOLD_JOIN", "USER", inv.household_id, _rid(request), {"from": caller.profile_user_id}
    )
    conn.commit()
    return {"household_id": inv.household_id}


def _move_out(conn, app_user_id: str, email: str) -> str:
    """Give a login a fresh, empty household of its own."""
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('app_user'))"))
    hh = create_household(conn, email.split("@")[0])
    conn.execute(text("UPDATE app_user SET profile_user_id = :h WHERE app_user_id = :i"), {"h": hh, "i": app_user_id})
    return hh


@router.post("/household/leave")
def leave(request: Request, caller: Caller = Depends(current_user), conn: Connection = Depends(get_conn)):
    hh = _need_household(caller)
    if conn.execute(text("SELECT count(*) FROM app_user WHERE profile_user_id = :h"), {"h": hh}).scalar() < 2:
        raise HTTPException(409, "You are the only login in this household.")
    new = _move_out(conn, caller.app_user_id, caller.email)
    audit(conn, caller.email, "HOUSEHOLD_LEAVE", "USER", hh, _rid(request), {"to": new})
    conn.commit()
    return {"household_id": new}


@router.delete("/household/members/{app_user_id}", status_code=204)
def remove_member(
    app_user_id: str, request: Request, caller: Caller = Depends(current_user), conn: Connection = Depends(get_conn)
):
    """The first login in a household (its owner) can remove another; they get an empty register of their own."""
    hh = _need_household(caller)
    rows = conn.execute(
        text(
            "SELECT app_user_id, email FROM app_user WHERE profile_user_id = :h AND role = 'CUSTOMER' "
            "ORDER BY created_at, app_user_id"
        ),
        {"h": hh},
    ).all()
    if not rows or rows[0].app_user_id != caller.app_user_id:
        raise HTTPException(403, "Only the household's owner can remove someone.")
    target = next((r for r in rows if r.app_user_id == app_user_id), None)
    if target is None or target.app_user_id == caller.app_user_id:
        raise HTTPException(404, "Not found.")
    _move_out(conn, target.app_user_id, target.email)
    audit(conn, caller.email, "HOUSEHOLD_REMOVE", "USER", hh, _rid(request), {"removed": target.email})
    conn.commit()
