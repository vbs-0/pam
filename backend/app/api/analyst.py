"""Analyst API: exception queue and workflow, versioned categorization rules, run metrics, transaction trace."""
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Connection, text

from app import schema
from app.api.common import EFFECTIVE, decode_cursor, encode_cursor, limit_q
from app.api.deps import Caller, require
from app.api.me import apply_override, audit
from app.db import get_conn
from app.engine.categorize import Categorizer, Rule
from app.engine.normalize import normalize_descriptor
from app.engine.types import Txn
from app.jobs.pipeline_job import latest_run_id
from app.jobs.sql import next_number

router = APIRouter(prefix="/analyst", tags=["analyst"])
ops = APIRouter(prefix="/ops", tags=["analyst"])
ANALYST = require("ANALYST", "ADMIN")
ALLOWED = {"OPEN": {"IN_REVIEW", "RESOLVED", "DISMISSED"}, "IN_REVIEW": {"RESOLVED", "DISMISSED", "OPEN"},
           "RESOLVED": {"OPEN"}, "DISMISSED": {"OPEN"}}
# nested quantifier such as (a+)+ or (a|aa)* : catastrophic backtracking on a crafted descriptor (A33)
_NESTED = re.compile(r"\([^()]*[+*}][^()]*\)\s*[+*{]")


def _rid(request: Request):
    return getattr(request.state, "request_id", None)


@router.get("/exceptions")
def exceptions(type: str | None = Query(None, pattern="^[A-Z_]{3,28}$"),
               status: str | None = Query(None, pattern="^(OPEN|IN_REVIEW|RESOLVED|DISMISSED)$"),
               user_id: str | None = Query(None, max_length=32), cursor: str | None = None,
               limit: int = Depends(limit_q), _: Caller = Depends(ANALYST), conn: Connection = Depends(get_conn)):
    run = latest_run_id(conn)
    sql = ["SELECT x.*, t.descriptor, t.amount_paise, t.posted_at, b.category_code AS budget_code, b.month AS "
           "budget_month, b.amount_paise AS budget_paise FROM exception_case x "
           "LEFT JOIN txn t ON x.entity_type = 'TXN' AND t.txn_id = x.entity_id "
           "LEFT JOIN LATERAL (SELECT * FROM budget WHERE x.entity_type = 'BUDGET' AND budget_id = x.entity_id "
           "ORDER BY version DESC LIMIT 1) b ON true WHERE true"]
    p: dict = {"lim": limit + 1}
    for col, val in (("exception_type", type), ("status", status), ("user_id", user_id)):
        if val:
            sql.append(f"AND x.{col} = :{col}")
            p[col] = val
    if cursor:
        (p["after"],) = decode_cursor(cursor, 1)
        sql.append("AND x.exception_id > :after")
    sql.append("ORDER BY x.exception_id LIMIT :lim")
    rows = conn.execute(text(" ".join(sql)), p).all()
    more, rows = len(rows) > limit, rows[:limit]
    items = []
    for r in rows:
        d = dict(r._mapping)
        d["current"] = r.last_run_id == run          # no longer raised by the latest run (fixed by a rule/override)
        items.append(d)
    return {"items": items, "next_cursor": encode_cursor(rows[-1].exception_id) if more else None}


@router.get("/exceptions/counts")
def exception_counts(_: Caller = Depends(ANALYST), conn: Connection = Depends(get_conn)):
    rows = conn.execute(text("SELECT exception_type, status, count(*) AS n FROM exception_case GROUP BY 1, 2 "
                             "ORDER BY 1, 2"))
    return [dict(r._mapping) for r in rows]


class TransitionIn(BaseModel):
    to_status: str = Field(pattern="^(OPEN|IN_REVIEW|RESOLVED|DISMISSED)$")
    note: str | None = Field(None, max_length=500)
    category_code: str | None = Field(None, max_length=40)


@router.post("/exceptions/{exception_id}/transition")
def transition(exception_id: str, body: TransitionIn, request: Request, caller: Caller = Depends(ANALYST),
               conn: Connection = Depends(get_conn)):
    x = conn.execute(text("SELECT * FROM exception_case WHERE exception_id = :x"), {"x": exception_id}).first()
    if x is None:
        raise HTTPException(404, "Not found.")
    if body.to_status not in ALLOWED[x.status]:
        raise HTTPException(409, f"Can't move an exception from {x.status} to {body.to_status}.")
    if body.category_code and (x.entity_type != "TXN" or body.to_status != "RESOLVED"):
        raise HTTPException(422, "A category can only be set when resolving a transaction exception.")
    # optimistic concurrency: if someone else moved it first, this matches no row (A13)
    n = conn.execute(text("UPDATE exception_case SET status = :to, updated_at = now() "
                          "WHERE exception_id = :x AND status = :from"),
                     {"to": body.to_status, "x": exception_id, "from": x.status}).rowcount
    if n == 0:
        conn.rollback()
        raise HTTPException(409, "Someone else changed this exception just now. Reload and try again.")
    override_id = None
    if body.category_code:
        day = conn.execute(text("SELECT (posted_at AT TIME ZONE 'Asia/Kolkata')::date FROM txn WHERE txn_id = :t"),
                           {"t": x.entity_id}).scalar()
        override_id = apply_override(conn, x.entity_id, body.category_code.strip().upper(), day, caller.email,
                                     body.note, _rid(request))
    conn.execute(text("INSERT INTO exception_event SELECT CAST(:x AS varchar), COALESCE(max(seq), 0) + 1, :f, :to, "
                      ":a, :n, now() FROM exception_event WHERE exception_id = :x"),
                 {"x": exception_id, "f": x.status, "to": body.to_status, "a": caller.email,
                  "n": body.note or (f"category set ({override_id})" if override_id else None)})
    audit(conn, caller.email, "EXCEPTION_TRANSITION", "EXCEPTION", exception_id, _rid(request),
          {"from": x.status, "to": body.to_status, "override_id": override_id})
    conn.commit()
    return {"exception_id": exception_id, "status": body.to_status, "override_id": override_id}


class RuleIn(BaseModel):
    priority: int = Field(ge=1, le=999)
    category_code: str = Field(min_length=1, max_length=40)
    merchant_id: str | None = Field(None, max_length=32)
    pattern: str | None = Field(None, min_length=1, max_length=200)
    channel: str | None = Field(None, pattern="^(" + "|".join(schema.CHANNELS) + ")$")
    direction: str = Field("ANY", pattern="^(DR|CR|ANY)$")
    account_type: str | None = Field(None, pattern="^(SAVINGS|CREDIT_CARD)$")
    confidence: float = Field(0.8, ge=0, le=1)
    note: str | None = Field(None, max_length=300)

    @field_validator("pattern")
    @classmethod
    def _regex(cls, v):
        if v is None:
            return v
        try:
            re.compile(v)
        except re.error as e:
            raise ValueError(f"not a valid regular expression: {e}") from None
        if _NESTED.search(v):
            raise ValueError("nested repetition like (a+)+ can hang the matcher; simplify the pattern")
        return v


def _check_rule(conn, body: RuleIn) -> None:
    if not (body.merchant_id or body.pattern or body.channel or body.account_type):
        raise HTTPException(422, "A rule needs at least one condition: merchant, pattern, channel or account type.")
    cat = conn.execute(text("SELECT kind, effective_to FROM category WHERE category_code = :c"),
                       {"c": body.category_code}).first()
    if cat is None or cat.kind == "UNKNOWN" or cat.effective_to is not None:
        raise HTTPException(422, f"'{body.category_code}' is not an active category.")
    if body.merchant_id and not conn.execute(text("SELECT 1 FROM merchant WHERE merchant_id = :m"),
                                             {"m": body.merchant_id}).first():
        raise HTTPException(422, f"Merchant {body.merchant_id} does not exist.")


def _insert_rule(conn, rule_id, version, body: RuleIn, actor) -> None:
    conn.execute(text("INSERT INTO category_rule VALUES (:id, :v, :p, :c, :m, :pat, :ch, :d, :at, :conf, now(), NULL, "
                      ":by, :note)"),
                 {"id": rule_id, "v": version, "p": body.priority, "c": body.category_code, "m": body.merchant_id,
                  "pat": body.pattern, "ch": body.channel, "d": body.direction, "at": body.account_type,
                  "conf": body.confidence, "by": actor, "note": body.note})


@router.get("/rules")
def rules(include_retired: bool = False, _: Caller = Depends(ANALYST), conn: Connection = Depends(get_conn)):
    """Latest version of each rule, in evaluation order (lower priority number runs first)."""
    rows = conn.execute(text(
        "SELECT DISTINCT ON (rule_id) * FROM category_rule ORDER BY rule_id, version DESC"))
    out = [dict(r._mapping) | {"confidence": float(r.confidence)} for r in rows
           if include_retired or r.retired_at is None]
    return sorted(out, key=lambda r: (r["priority"], r["rule_id"]))


@router.post("/rules", status_code=201)
def create_rule(body: RuleIn, request: Request, caller: Caller = Depends(ANALYST),
                conn: Connection = Depends(get_conn)):
    _check_rule(conn, body)
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('category_rule'))"))
    rule_id = f"RUL-{next_number(conn, schema.category_rule, 'rule_id'):04d}"
    _insert_rule(conn, rule_id, 1, body, caller.email)
    audit(conn, caller.email, "RULE_CREATE", "RULE", rule_id, _rid(request), body.model_dump())
    conn.commit()
    return {"rule_id": rule_id, "version": 1}


@router.post("/rules/{rule_id}/versions", status_code=201)
def new_version(rule_id: str, body: RuleIn, request: Request, caller: Caller = Depends(ANALYST),
                conn: Connection = Depends(get_conn)):
    _check_rule(conn, body)
    cur = conn.execute(text("SELECT version, retired_at FROM category_rule WHERE rule_id = :r ORDER BY version DESC "
                            "LIMIT 1 FOR UPDATE"), {"r": rule_id}).first()
    if cur is None:
        raise HTTPException(404, "Not found.")
    if cur.retired_at is not None:
        raise HTTPException(409, "This rule is retired. Create a new rule instead.")
    conn.execute(text("UPDATE category_rule SET retired_at = now() WHERE rule_id = :r AND version = :v"),
                 {"r": rule_id, "v": cur.version})
    _insert_rule(conn, rule_id, cur.version + 1, body, caller.email)
    audit(conn, caller.email, "RULE_VERSION", "RULE", rule_id, _rid(request),
          body.model_dump() | {"version": cur.version + 1})
    conn.commit()
    return {"rule_id": rule_id, "version": cur.version + 1}


@router.post("/rules/{rule_id}/retire")
def retire(rule_id: str, request: Request, caller: Caller = Depends(ANALYST), conn: Connection = Depends(get_conn)):
    n = conn.execute(text("UPDATE category_rule SET retired_at = now() WHERE rule_id = :r AND retired_at IS NULL"),
                     {"r": rule_id}).rowcount
    if n == 0:
        raise HTTPException(404, "No active rule with that id.")
    audit(conn, caller.email, "RULE_RETIRE", "RULE", rule_id, _rid(request), None)
    conn.commit()
    return {"rule_id": rule_id, "retired": True}


class RuleTestIn(BaseModel):
    descriptor: str = Field(min_length=1, max_length=160)
    channel: str = Field(pattern="^(" + "|".join(schema.CHANNELS) + ")$")
    amount_paise: int
    account_type: str = Field("SAVINGS", pattern="^(SAVINGS|CREDIT_CARD)$")
    counterparty_vpa: str | None = Field(None, max_length=64)


@router.post("/rules/test")
def test_rule(body: RuleTestIn, _: Caller = Depends(ANALYST), conn: Connection = Depends(get_conn)):
    """Dry-run the active rules on one narration. Nothing is saved; the next pipeline run applies rule changes."""
    rules = [Rule(r.rule_id, r.version, r.priority, r.category_code, float(r.confidence), r.merchant_id, r.pattern,
                  r.channel, r.direction, r.account_type)
             for r in conn.execute(text("SELECT * FROM category_rule WHERE retired_at IS NULL"))]
    vpas = dict(conn.execute(text("SELECT vpa, merchant_id FROM merchant WHERE vpa IS NOT NULL")).all())
    aliases = dict(conn.execute(text("SELECT alias, merchant_id FROM merchant_alias")).all())
    cat = Categorizer(rules, vpas, aliases)
    norm = normalize_descriptor(body.descriptor)
    t = Txn("TEST", "TEST", "TEST", body.account_type, None, body.amount_paise, body.channel, body.descriptor,
            body.counterparty_vpa)
    merchant, rule = cat.categorize(t, norm)
    return {"normalized": norm, "merchant_id": merchant, "rule_id": rule.rule_id if rule else None,
            "rule_version": rule.version if rule else None,
            "category_code": rule.category_code if rule else "UNCATEGORIZED",
            "confidence": rule.confidence if rule else 0.0}


@router.get("/metrics")
def metrics(run_id: str | None = Query(None, max_length=32), _: Caller = Depends(ANALYST),
            conn: Connection = Depends(get_conn)):
    row = conn.execute(text("SELECT run_id, created_at, metrics FROM evaluation_run "
                            "WHERE CAST(:r AS text) IS NULL OR run_id = :r ORDER BY created_at DESC LIMIT 1"),
                       {"r": run_id}).first()
    if row is None:
        raise HTTPException(404, "No evaluation yet. An admin can run one from the Jobs page.")
    return row.metrics | {"run_id": row.run_id, "evaluated_at": row.created_at}


@router.get("/runs")
def runs(_: Caller = Depends(ANALYST), conn: Connection = Depends(get_conn)):
    rows = conn.execute(text("SELECT run_id, status, started_at, finished_at, ruleset_hash, stats, error "
                             "FROM pipeline_run ORDER BY run_id DESC LIMIT 50"))
    return [dict(r._mapping) for r in rows]


@ops.get("/transactions/{txn_id}")
def trace(txn_id: str, caller: Caller = Depends(require("ANALYST", "REVIEWER", "ADMIN")),
          conn: Connection = Depends(get_conn)):
    """Everything about one transaction: raw row, every run's decision, overrides, exceptions; truth for reviewers."""
    t = conn.execute(text("SELECT t.*, a.account_type, a.masked_number, a.status AS account_status FROM txn t "
                          "JOIN account a USING (account_id) WHERE t.txn_id = :t"), {"t": txn_id}).first()
    if t is None:
        raise HTTPException(404, "Not found.")
    out = {"txn": dict(t._mapping)}
    run = latest_run_id(conn)
    if run:
        cur = conn.execute(text(f"{EFFECTIVE} AND t.txn_id = :t"), {"run": run, "t": txn_id}).first()
        out["current"] = dict(cur._mapping) if cur else None
    out["runs"] = [dict(r._mapping) for r in conn.execute(text(
        "SELECT * FROM txn_enrichment WHERE txn_id = :t ORDER BY run_id DESC"), {"t": txn_id})]
    out["overrides"] = [dict(r._mapping) for r in conn.execute(text(
        "SELECT * FROM category_override WHERE txn_id = :t ORDER BY created_at DESC, override_id DESC"),
        {"t": txn_id})]
    out["exceptions"] = []
    for x in conn.execute(text("SELECT * FROM exception_case WHERE entity_type = 'TXN' AND entity_id = :t "
                               "ORDER BY exception_id"), {"t": txn_id}):
        d = dict(x._mapping)
        d["events"] = [dict(e._mapping) for e in conn.execute(text(
            "SELECT seq, from_status, to_status, actor, note, at FROM exception_event WHERE exception_id = :x "
            "ORDER BY seq"), {"x": x.exception_id})]
        out["exceptions"].append(d)
    if caller.role in ("REVIEWER", "ADMIN"):           # ground truth never reaches analysts or customers
        lab = conn.execute(text("SELECT * FROM gt.txn_label WHERE txn_id = :t"), {"t": txn_id}).first()
        out["truth"] = dict(lab._mapping) if lab else None
    return out
