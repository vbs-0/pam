"""More ways to work with entries: notes and tags, split one payment across categories, duplicate, move money between
your own accounts, import a bank CSV, export your register, and back it up or restore it.

Every write is for real households only (sample households are read-only) and is audited. After a batch the household
is re-run through the engine once, so categories, transfer pairs, recurring series and budgets are current in the reply.
"""

import contextlib
import csv
import datetime as dt
import functools
import io
import json
import re
import secrets
from collections import Counter
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Connection, text

from app import schema
from app.api.common import EFFECTIVE, household, run_id
from app.api.deps import Caller, current_user
from app.api.entry import (
    CHANNEL,
    MAX_PAISE,
    AccountIn,
    TxnIn,
    _check_date,
    _own_account,
    _own_txn_row,
    _rid,
    add_transaction,
    create_account,
    own,
    purge_txn,
)
from app.api.me import apply_override, audit, display_name
from app.db import get_conn
from app.households import next_txn_id
from app.jobs.pipeline_job import latest_run_id, refresh_household, today
from app.timeutil import ist_to_utc

router = APIRouter(prefix="/me", tags=["customer: entries plus"])
IST_TZ = dt.timezone(dt.timedelta(hours=5, minutes=30))
IMPORT_MAX_ROWS = 5000
IMPORT_MAX_CHARS = 2_000_000


# ---------- notes and tags ----------
class NoteIn(BaseModel):
    note: str = Field("", max_length=300)
    tags: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("note")
    @classmethod
    def _note(cls, v: str) -> str:
        return " ".join(v.split())

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for t in v:
            t = " ".join(t.strip().lower().lstrip("#").split())
            if not re.fullmatch(r"[a-z0-9][a-z0-9 _-]{0,23}", t):
                raise ValueError("A tag is 1 to 24 letters, digits, spaces, dashes or underscores")
            if t not in out:
                out.append(t)
        return out


@router.put("/transactions/{txn_id}/note")
def set_note(txn_id: str, body: NoteIn, user: str = Depends(own), conn: Connection = Depends(get_conn)):
    _own_txn_row(conn, user, txn_id)
    if not body.note and not body.tags:
        conn.execute(text("DELETE FROM txn_note WHERE txn_id = :t"), {"t": txn_id})
    else:
        conn.execute(
            text(
                "INSERT INTO txn_note (txn_id, user_id, note, tags) VALUES (:t, :u, :n, :g) ON CONFLICT "
                "(txn_id) DO UPDATE SET note = :n, tags = :g, updated_at = now()"
            ),
            {"t": txn_id, "u": user, "n": body.note, "g": body.tags},
        )
    conn.commit()
    return {"txn_id": txn_id, "note": body.note, "tags": body.tags}


@router.get("/tags")
def tags(user: str = Depends(household), conn: Connection = Depends(get_conn)):
    """Every tag you have used, most used first."""
    rows = conn.execute(
        text(
            "SELECT t AS tag, count(*) AS n FROM txn_note, unnest(tags) AS t WHERE user_id = :u "
            "GROUP BY 1 ORDER BY n DESC, tag"
        ),
        {"u": user},
    )
    return [{"tag": r.tag, "count": r.n} for r in rows]


# ---------- split / duplicate ----------
class SplitPart(BaseModel):
    amount_paise: int = Field(gt=0, le=MAX_PAISE)
    category_code: str | None = Field(None, max_length=40)
    description: str | None = Field(None, min_length=1, max_length=120)


class SplitIn(BaseModel):
    parts: list[SplitPart] = Field(min_length=2, max_length=10)


def _insert(conn, user, account_id, posted, amount, channel, descriptor, vpa=None, ref=None) -> str:
    txn_id = next_txn_id(conn, posted.astimezone(dt.timezone(dt.timedelta(hours=5, minutes=30))).year)
    conn.execute(
        text("INSERT INTO txn VALUES (:t, :a, :u, :p, :amt, 'INR', :ch, :d, :v, :r)"),
        {
            "t": txn_id,
            "a": account_id,
            "u": user,
            "p": posted,
            "amt": amount,
            "ch": channel,
            "d": descriptor,
            "v": vpa,
            "r": ref,
        },
    )
    return txn_id


@router.post("/transactions/{txn_id}/split", status_code=201)
def split_transaction(
    txn_id: str,
    body: SplitIn,
    request: Request,
    user: str = Depends(own),
    caller: Caller = Depends(current_user),
    conn: Connection = Depends(get_conn),
):
    """Replace one entry with several that add up to the same amount (a shop bill that was half groceries, half
    household). The original is removed; each part is filed under the category you pick."""
    t = _own_txn_row(conn, user, txn_id)
    total = abs(t.amount_paise)
    got = sum(p.amount_paise for p in body.parts)
    if got != total:
        raise HTTPException(422, f"The parts add up to ₹{got / 100:,.2f} but the entry is ₹{total / 100:,.2f}.")
    sign = -1 if t.amount_paise < 0 else 1
    day = t.local_ts.date()
    ids = []
    for i, p in enumerate(body.parts, 1):
        base = " ".join((p.description or t.descriptor).split())[:140]
        new = _insert(
            conn,
            user,
            t.account_id,
            t.posted_at,
            sign * p.amount_paise,
            t.channel,
            f"{base} (split {i}/{len(body.parts)})",
            t.counterparty_vpa,
        )
        if p.category_code:
            apply_override(
                conn, new, p.category_code.strip().upper(), day, caller.email, f"split of {txn_id}", _rid(request)
            )
        ids.append(new)
    purge_txn(conn, txn_id)
    audit(conn, caller.email, "TXN_SPLIT", "TXN", txn_id, _rid(request), {"into": ids})
    conn.commit()
    return {"original": txn_id, "txn_ids": ids, "refreshed": refresh_household(conn, user)}


class DuplicateIn(BaseModel):
    date: dt.date | None = None


@router.post("/transactions/{txn_id}/duplicate", status_code=201)
def duplicate_transaction(
    txn_id: str,
    request: Request,
    body: DuplicateIn | None = None,
    user: str = Depends(own),
    caller: Caller = Depends(current_user),
    conn: Connection = Depends(get_conn),
):
    """Copy an entry to another date (today by default): the same payment you make every week."""
    t = _own_txn_row(conn, user, txn_id)
    cat = conn.execute(
        text(
            "SELECT category_code FROM category_override WHERE txn_id = :t ORDER BY created_at DESC, "
            "override_id DESC LIMIT 1"
        ),
        {"t": txn_id},
    ).scalar()
    copy = TxnIn(
        account_id=t.account_id,
        date=(body.date if body and body.date else today()),
        amount_paise=abs(t.amount_paise),
        direction="DR" if t.amount_paise < 0 else "CR",
        description=t.descriptor,
        channel=t.channel,
        counterparty_vpa=t.counterparty_vpa,
        category_code=cat,
    )
    return add_transaction(copy, request, user, caller, conn)


# ---------- transfers between your own accounts ----------
class TransferIn(BaseModel):
    from_account_id: str = Field(max_length=32)
    to_account_id: str = Field(max_length=32)
    amount_paise: int = Field(gt=0, le=MAX_PAISE)
    date: dt.date
    time: dt.time | None = None


def _acct_label(conn, account_id: str) -> str:
    a = conn.execute(
        text(
            "SELECT a.account_type, a.bank_code, a.masked_number, l.label FROM account a "
            "LEFT JOIN account_label l USING (account_id) WHERE a.account_id = :a"
        ),
        {"a": account_id},
    ).one()
    return display_name(a)


@router.post("/transfers", status_code=201)
def transfer(
    body: TransferIn,
    request: Request,
    user: str = Depends(own),
    caller: Caller = Depends(current_user),
    conn: Connection = Depends(get_conn),
):
    """Money moved between two of your accounts, written as the two matching entries a bank would show. PAM pairs them
    as a transfer, so it is not counted as spending or income."""
    if body.from_account_id == body.to_account_id:
        raise HTTPException(422, "Pick two different accounts.")
    src, dst = _own_account(conn, user, body.from_account_id), _own_account(conn, user, body.to_account_id)
    _check_date(src, body.date)
    _check_date(dst, body.date)
    posted = ist_to_utc(dt.datetime.combine(body.date, body.time or dt.time(12, 0)))
    ref = f"TRF{secrets.randbelow(10**9):09d}"
    out = _insert(
        conn,
        user,
        src.account_id,
        posted,
        -body.amount_paise,
        "IMPS",
        f"Transfer to {_acct_label(conn, dst.account_id)}",
        None,
        ref,
    )
    inn = _insert(
        conn,
        user,
        dst.account_id,
        posted,
        body.amount_paise,
        "IMPS",
        f"Transfer from {_acct_label(conn, src.account_id)}",
        None,
        ref,
    )
    audit(conn, caller.email, "TRANSFER_CREATE", "TXN", out, _rid(request), body.model_dump() | {"credit_leg": inn})
    conn.commit()
    return {"debit_txn_id": out, "credit_txn_id": inn, "refreshed": refresh_household(conn, user)}


# ---------- CSV import ----------
DATE_FORMATS = [
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y-%m-%d",
    "%d/%m/%y",
    "%d-%m-%y",
    "%d %b %Y",
    "%d-%b-%Y",
    "%d-%b-%y",
    "%d %B %Y",
    "%m/%d/%Y",
]
HEADER_HINTS = {
    "date": ("txn date", "transaction date", "posting date", "date", "value date"),
    "description": ("narration", "description", "particulars", "details", "remarks", "transaction remarks"),
    "debit": ("debit", "withdrawal", "withdrawals", "dr amount", "debit amount"),
    "credit": ("credit", "deposit", "deposits", "cr amount", "credit amount"),
    "amount": ("amount", "transaction amount"),
    "type": ("dr/cr", "type", "cr/dr", "transaction type"),
}


def _read_csv(text_: str) -> tuple[list[str], list[list[str]]]:
    text_ = text_.lstrip("﻿")
    try:
        dialect = csv.Sniffer().sniff(text_[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(text_), dialect) if any(c.strip() for c in r)]
    if len(rows) < 2:
        raise HTTPException(422, "That file has no data rows. It needs a header line and at least one entry.")
    # bank files often have a few title lines first: the header is the first row that names a date column
    for i, r in enumerate(rows[:15]):
        if any(re.search(r"date", c, re.I) for c in r) and sum(bool(c) for c in r) >= 3:
            return r, rows[i + 1 :]
    return rows[0], rows[1:]


def _suggest(headers: list[str]) -> dict[str, str]:
    low = [h.strip().lower() for h in headers]
    out: dict[str, str] = {}
    for key, hints in HEADER_HINTS.items():
        for hint in hints:
            hit = next((headers[i] for i, h in enumerate(low) if h == hint), None) or next(
                (headers[i] for i, h in enumerate(low) if hint in h and headers[i] not in out.values()), None
            )
            if hit:
                out[key] = hit
                break
    if "debit" in out or "credit" in out:
        out.pop("amount", None)
        out.pop("type", None)
    return out


def _cell(row: list[str], ix: dict[str, int], key: str) -> str:
    return row[ix[key]] if key in ix and ix[key] < len(row) else ""


def _paise(v: str) -> int | None:
    s = v.strip().replace("₹", "").replace("Rs.", "").replace("INR", "").replace(",", "").replace(" ", "")
    if not s or s in ("-", "--"):
        return None
    neg = s.startswith("(") and s.endswith(")") or s.startswith("-") or s.upper().endswith("DR")
    s = s.strip("()-").upper().removesuffix("DR").removesuffix("CR")
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError(f"'{v}' is not an amount") from None
    p = int((d * 100).to_integral_value())
    return -abs(p) if neg else p


def _date(v: str, fmt: str | None) -> dt.date:
    v = v.strip()
    for f in [fmt] if fmt else DATE_FORMATS:
        try:
            return dt.datetime.strptime(v, f).date()
        except ValueError:
            continue
    raise ValueError(f"'{v}' is not a date")


class ImportPreviewIn(BaseModel):
    csv_text: str = Field(max_length=IMPORT_MAX_CHARS)


@router.post("/import/preview")
def import_preview(body: ImportPreviewIn, _: str = Depends(own)):
    headers, rows = _read_csv(body.csv_text)
    return {
        "headers": headers,
        "suggested_mapping": _suggest(headers),
        "rows_total": len(rows),
        "sample": rows[:5],
        "max_rows": IMPORT_MAX_ROWS,
    }


class ImportIn(BaseModel):
    account_id: str = Field(max_length=32)
    csv_text: str = Field(max_length=IMPORT_MAX_CHARS)
    mapping: dict[str, str] | None = None
    date_format: str | None = Field(None, max_length=20)
    channel: str = Field("UPI", pattern=CHANNEL)
    dry_run: bool = False


@router.post("/import")
def import_csv(
    body: ImportIn,
    request: Request,
    user: str = Depends(own),
    caller: Caller = Depends(current_user),
    conn: Connection = Depends(get_conn),
):
    """Add the rows of a bank or UPI statement CSV to one account. Rows already on file (same date, amount and
    narration) are skipped, so importing the same file twice adds nothing. Bad rows are reported, never silently lost."""
    acc = _own_account(conn, user, body.account_id)
    headers, rows = _read_csv(body.csv_text)
    if len(rows) > IMPORT_MAX_ROWS:
        raise HTTPException(422, f"That file has {len(rows)} rows; import at most {IMPORT_MAX_ROWS} at a time.")
    m = body.mapping or _suggest(headers)
    for need in ("date", "description"):
        if need not in m:
            raise HTTPException(422, f"Could not find the {need} column. Pick it from the list.")
    if not ("amount" in m or "debit" in m or "credit" in m):
        raise HTTPException(422, "Could not find the amount columns. Pick amount, or debit and credit.")
    for col in m.values():
        if col not in headers:
            raise HTTPException(422, f"Column '{col}' is not in the file.")
    ix = {k: headers.index(c) for k, c in m.items()}
    existing = Counter(
        (d, a, s.lower())
        for d, a, s in conn.execute(
            text(
                "SELECT (posted_at AT TIME ZONE 'Asia/Kolkata')::date, amount_paise, descriptor FROM txn WHERE account_id = :a"
            ),
            {"a": body.account_id},
        )
    )
    parsed, errors, skipped = [], [], 0
    for n, r in enumerate(rows, start=2):
        try:
            cell = functools.partial(_cell, r, ix)
            day = _date(cell("date"), body.date_format)
            desc = " ".join(cell("description").split())[:160]
            if not desc:
                raise ValueError("the narration is empty")
            if "debit" in ix or "credit" in ix:
                dr, cr = (
                    _paise(cell("debit")) if "debit" in ix else None,
                    _paise(cell("credit")) if "credit" in ix else None,
                )
                amount = -abs(dr) if dr else abs(cr) if cr else None
            else:
                amount = _paise(cell("amount"))
                if amount is not None and "type" in ix:
                    amount = -abs(amount) if cell("type").strip().upper().startswith("D") else abs(amount)
            if not amount:
                raise ValueError("no amount")
            if abs(amount) > MAX_PAISE:
                raise ValueError("amount is too large")
            _check_date(acc, day)
        except (ValueError, HTTPException) as e:
            if len(errors) < 50:
                errors.append({"row": n, "message": e.detail if isinstance(e, HTTPException) else str(e)})
            continue
        key = (day, amount, desc.lower())
        if existing[key] > 0:
            existing[key] -= 1
            skipped += 1
            continue
        parsed.append((day, amount, desc))
    result = {
        "dry_run": body.dry_run,
        "rows_total": len(rows),
        "to_import": len(parsed),
        "skipped_duplicates": skipped,
        "error_count": len(rows) - len(parsed) - skipped,
        "errors": errors,
        "mapping": m,
        "sample": [{"date": d, "amount_paise": a, "description": s} for d, a, s in parsed[:5]],
    }
    if body.dry_run or not parsed:
        return result | {"imported": 0}
    counters: dict[int, int] = {}
    batch = []
    for day, amount, desc in parsed:
        if day.year not in counters:
            counters[day.year] = int(next_txn_id(conn, day.year).rsplit("-", 1)[1])
        else:
            counters[day.year] += 1
        batch.append(
            {
                "t": f"TXN-{day.year}-{counters[day.year]:08d}",
                "a": body.account_id,
                "u": user,
                "p": ist_to_utc(dt.datetime.combine(day, dt.time(12, 0))),
                "amt": amount,
                "ch": body.channel,
                "d": desc,
            }
        )
    conn.execute(text("INSERT INTO txn VALUES (:t, :a, :u, :p, :amt, 'INR', :ch, :d, NULL, NULL)"), batch)
    audit(
        conn,
        caller.email,
        "TXN_IMPORT",
        "ACCOUNT",
        body.account_id,
        _rid(request),
        {"rows": len(batch), "skipped": skipped},
    )
    conn.commit()
    refreshed = refresh_household(conn, user)
    if refreshed:
        from app.api.sorting import apply_user_rules  # lazy: sorting imports entry
        apply_user_rules(conn, latest_run_id(conn), user, _rid(request))
        conn.commit()
    return result | {"imported": len(batch), "refreshed": refreshed}


# ---------- export / backup / restore ----------
def _csv_cell(v) -> str:
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in "=+-@\t\r" and not re.fullmatch(r"-?\d+(\.\d+)?", s) else s  # spreadsheet formula guard


@router.get("/export.csv")
def export_csv(
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    account_id: str | None = Query(None, max_length=32),
    user: str = Depends(household),
    run: str = Depends(run_id),
    conn: Connection = Depends(get_conn),
):
    """Your register as a spreadsheet-friendly CSV (UTF-8 with a BOM so Excel shows ₹ and Hindi correctly)."""
    where, p = "", {"run": run, "u": user}
    if date_from:
        where += " AND x.local_date >= :df"
        p["df"] = date_from
    if date_to:
        where += " AND x.local_date <= :dt"
        p["dt"] = date_to
    if account_id:
        where += " AND x.account_id = :acc"
        p["acc"] = account_id
    rows = conn.execute(
        text(
            f"SELECT x.local_date, x.posted_at, x.account_id, x.descriptor, x.merchant_name, x.category_code, x.kind, "
            f"x.amount_paise, x.channel, x.reference_no, n.note, n.tags FROM ({EFFECTIVE} AND t.account_id IN "
            f"(SELECT account_id FROM account_holder WHERE user_id = :u)) x LEFT JOIN txn_note n USING (txn_id) WHERE true"
            f"{where} ORDER BY x.local_date, x.txn_id"
        ),
        p,
    )
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\r\n")
    w.writerow(
        [
            "Date",
            "Account",
            "Description",
            "Merchant",
            "Category",
            "Type",
            "Debit (INR)",
            "Credit (INR)",
            "Channel",
            "Reference",
            "Note",
            "Tags",
        ]
    )
    for r in rows:
        a = r.amount_paise
        w.writerow(
            [
                r.local_date.isoformat(),
                r.account_id,
                _csv_cell(r.descriptor),
                _csv_cell(r.merchant_name),
                r.category_code,
                r.kind,
                f"{-a / 100:.2f}" if a < 0 else "",
                f"{a / 100:.2f}" if a > 0 else "",
                r.channel,
                _csv_cell(r.reference_no),
                _csv_cell(r.note),
                _csv_cell(" ".join(r.tags or [])),
            ]
        )
    name = f"pam-register-{today().isoformat()}.csv"
    return Response(
        "﻿" + out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/backup.json")
def backup(user: str = Depends(household), conn: Connection = Depends(get_conn)):
    """Everything you entered, as one JSON file you can keep and later restore into an empty register."""
    q = lambda sql, **k: [dict(r._mapping) for r in conn.execute(text(sql), {"u": user} | k)]  # noqa: E731
    accounts = q(
        "SELECT a.account_id, a.account_type, a.bank_code, a.masked_number, a.vpa, l.label, a.opened_on, a.closed_on, "
        "a.status, a.opening_balance_paise, a.credit_limit_paise, m.due_day, m.statement_day FROM account a "
        "LEFT JOIN account_label l USING (account_id) LEFT JOIN account_meta m USING (account_id) "
        "WHERE a.user_id = :u ORDER BY a.account_id"
    )
    txns = q(
        "SELECT t.txn_id, t.account_id, t.posted_at, t.amount_paise, t.channel, t.descriptor, t.counterparty_vpa, "
        "t.reference_no, (SELECT category_code FROM category_override o WHERE o.txn_id = t.txn_id ORDER BY created_at DESC, "
        "override_id DESC LIMIT 1) AS category_code, n.note, n.tags FROM txn t LEFT JOIN txn_note n USING (txn_id) "
        "WHERE t.user_id = :u ORDER BY t.posted_at, t.txn_id"
    )
    data = {
        "format": "pam-backup/1",
        "exported_at": dt.datetime.now(dt.UTC).isoformat(),
        "household": user,
        "profile": q(
            "SELECT display_name, city, state, monthly_income_paise, household_size, persona FROM user_profile "
            "WHERE user_id = :u"
        )[0],
        "accounts": accounts,
        "transactions": txns,
        "budgets": q(
            "SELECT DISTINCT ON (budget_id) month, category_code, amount_paise FROM budget WHERE user_id = :u "
            "ORDER BY budget_id, version DESC"
        ),
        "goals": q(
            "SELECT name, target_paise, saved_paise, deadline, completed_at FROM goal WHERE user_id = :u ORDER BY created_at"
        ),
        "carry": [r["category_code"] for r in q("SELECT category_code FROM budget_carry WHERE user_id = :u")],
    }
    name = f"pam-backup-{today().isoformat()}.json"
    return Response(
        json.dumps(data, default=str, ensure_ascii=False, indent=1),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


class RestoreIn(BaseModel):
    backup: dict


@router.post("/restore", status_code=201)
def restore(
    body: RestoreIn,
    request: Request,
    user: str = Depends(own),
    caller: Caller = Depends(current_user),
    conn: Connection = Depends(get_conn),
):
    """Load a backup made by /me/backup.json into an EMPTY register (no accounts yet). Ids are re-issued."""
    b = body.backup
    if b.get("format") != "pam-backup/1":
        raise HTTPException(422, "That is not a PAM backup file.")
    if conn.execute(text("SELECT 1 FROM account WHERE user_id = :u LIMIT 1"), {"u": user}).first():
        raise HTTPException(409, "Restore only works into an empty register. This one already has accounts.")
    if len(b.get("transactions", [])) > 50_000 or len(b.get("accounts", [])) > 99:
        raise HTTPException(422, "That backup is larger than this server restores.")
    amap: dict[str, str] = {}
    for a in b.get("accounts", []):
        new = AccountIn(
            account_type=a["account_type"],
            bank_code=a["bank_code"],
            last4=(a.get("masked_number") or "")[-4:] or None,
            label=a.get("label"),
            vpa=a.get("vpa"),
            opened_on=dt.date.fromisoformat(str(a["opened_on"])),
            opening_balance_paise=a.get("opening_balance_paise") or 0,
            credit_limit_paise=a.get("credit_limit_paise"),
        )
        amap[a["account_id"]] = create_account(new, request, user, caller, conn)["account_id"]
        if a.get("due_day") or a.get("statement_day"):
            conn.execute(
                text("INSERT INTO account_meta VALUES (:a, :d, :s)"),
                {"a": amap[a["account_id"]], "d": a.get("due_day"), "s": a.get("statement_day")},
            )
        if a.get("status") == "CLOSED" and a.get("closed_on"):
            conn.execute(
                text("UPDATE account SET status = 'CLOSED', closed_on = :d WHERE account_id = :a"),
                {"d": dt.date.fromisoformat(str(a["closed_on"])), "a": amap[a["account_id"]]},
            )
    n = 0
    counters: dict[int, int] = {}
    for t in sorted(b.get("transactions", []), key=lambda x: str(x["posted_at"])):
        if t["account_id"] not in amap:
            continue
        posted = dt.datetime.fromisoformat(str(t["posted_at"]).replace("Z", "+00:00"))
        year = posted.astimezone(dt.timezone(dt.timedelta(hours=5, minutes=30))).year
        counters[year] = (counters[year] + 1) if year in counters else int(next_txn_id(conn, year).rsplit("-", 1)[1])
        tid = f"TXN-{year}-{counters[year]:08d}"
        conn.execute(
            text("INSERT INTO txn VALUES (:t, :a, :u, :p, :amt, 'INR', :ch, :d, :v, :r)"),
            {
                "t": tid,
                "a": amap[t["account_id"]],
                "u": user,
                "p": posted,
                "amt": t["amount_paise"],
                "ch": t.get("channel") or "UPI",
                "d": t["descriptor"],
                "v": t.get("counterparty_vpa"),
                "r": t.get("reference_no"),
            },
        )
        if t.get("category_code"):
            with contextlib.suppress(HTTPException):  # a category retired since the backup: PAM categorizes it
                apply_override(
                    conn, tid, t["category_code"], posted.astimezone(IST_TZ).date(), caller.email, "restored", _rid(request)
                )
        if t.get("note") or t.get("tags"):
            conn.execute(
                text("INSERT INTO txn_note (txn_id, user_id, note, tags) VALUES (:t, :u, :n, :g)"),
                {"t": tid, "u": user, "n": t.get("note") or "", "g": t.get("tags") or []},
            )
        n += 1
    for g in b.get("goals", []):
        conn.execute(
            text(
                "INSERT INTO goal (goal_id, user_id, name, target_paise, saved_paise, deadline, completed_at) "
                "VALUES (:i, :u, :n, :t, :s, :d, :c)"
            ),
            {
                "i": f"GOL-{user}-{secrets.token_hex(3)}",
                "u": user,
                "n": g["name"],
                "t": g["target_paise"],
                "s": g.get("saved_paise") or 0,
                "d": g.get("deadline"),
                "c": g.get("completed_at"),
            },
        )
    audit(conn, caller.email, "BACKUP_RESTORE", "USER", user, _rid(request), {"accounts": len(amap), "transactions": n})
    conn.commit()
    for bud in b.get("budgets", []):  # budgets go through the normal setter (validation, versioning)
        from app.api.entry import BudgetIn, set_budget

        try:
            set_budget(
                BudgetIn(month=bud["month"], category_code=bud["category_code"], amount_paise=bud["amount_paise"]),
                request,
                user,
                caller,
                conn,
            )
        except HTTPException:
            conn.rollback()
    for code in b.get("carry", []):
        conn.execute(text("INSERT INTO budget_carry VALUES (:u, :c) ON CONFLICT DO NOTHING"), {"u": user, "c": code})
    conn.commit()
    return {"accounts": len(amap), "transactions": n, "refreshed": refresh_household(conn, user)}


__all__ = ["router", "schema"]
