"""Entries PAM could not sort: your own remembered rules, and optional AI suggestions.

Both work through the ordinary category override, so they show up in the entry's history, in budgets straight away,
and can be changed by hand at any time. Neither touches the decision engine, which stays deterministic.
"""
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import Connection, text

from app import ai_sort
from app.api.common import EFFECTIVE, household
from app.api.deps import Caller, current_user
from app.api.entry import _rid, own
from app.api.me import apply_override, audit
from app.db import get_conn
from app.engine.normalize import normalize_descriptor, strip_variable
from app.jobs.pipeline_job import latest_run_id

router = APIRouter(prefix="/me", tags=["customer"])
MIN_CONFIDENCE = 0.6
MAX_PER_CALL = 40
CALLS_PER_HOUR = 6


def phrase_of(descriptor: str) -> str:
    return strip_variable(normalize_descriptor(descriptor))[:60]


def remember_rule(conn: Connection, user: str, descriptor: str, amount_paise: int, code: str) -> str | None:
    """Keep 'this kind of narration goes to this category' for the household. Returns the phrase, or None if the
    narration says too little to build a rule on."""
    phrase = phrase_of(descriptor)
    if len(phrase) < 3:
        return None
    conn.execute(
        text("INSERT INTO user_rule (rule_id, user_id, phrase, direction, category_code) VALUES (:i, :u, :p, :d, :c) "
             "ON CONFLICT (user_id, phrase, direction) DO UPDATE SET category_code = :c, created_at = now()"),
        {"i": "UR-" + secrets.token_hex(8), "u": user, "p": phrase, "d": "DR" if amount_paise < 0 else "CR", "c": code})
    return phrase


def _unsorted(conn: Connection, run: str, user: str, limit: int | None = None):
    sql = (f"SELECT txn_id, descriptor, local_date, amount_paise, channel FROM ({EFFECTIVE} AND e.user_id = :u) x "
           "WHERE kind = 'UNKNOWN' ORDER BY local_date DESC, txn_id DESC")
    if limit:
        sql += f" LIMIT {int(limit)}"
    return conn.execute(text(sql), {"run": run, "u": user}).all()


def apply_user_rules(conn: Connection, run: str | None, user: str, request_id: str | None) -> int:
    """Sort every still-unsorted entry that matches one of the household's rules. Caller commits."""
    if not run:
        return 0
    rules = conn.execute(text("SELECT phrase, direction, category_code FROM user_rule WHERE user_id = :u "
                              "ORDER BY length(phrase) DESC"), {"u": user}).all()
    if not rules:
        return 0
    n = 0
    for t in _unsorted(conn, run, user):
        norm, direction = phrase_of(t.descriptor), "DR" if t.amount_paise < 0 else "CR"
        hit = next((r for r in rules if r.direction == direction and r.phrase in norm), None)
        if hit is None:
            continue
        try:
            apply_override(conn, t.txn_id, hit.category_code, t.local_date, "RULE", f'Your rule: "{hit.phrase}"', request_id)
            n += 1
        except HTTPException:
            continue                      # the category was retired since the rule was made
    return n


@router.get("/sorting-rules")
def rules(user: str = Depends(household), conn: Connection = Depends(get_conn)):
    rows = conn.execute(text(
        "SELECT r.rule_id, r.phrase, r.direction, r.category_code, c.name, r.created_at FROM user_rule r "
        "LEFT JOIN category c USING (category_code) WHERE r.user_id = :u ORDER BY r.created_at DESC"), {"u": user})
    return [{"rule_id": r.rule_id, "phrase": r.phrase, "direction": r.direction, "category_code": r.category_code,
             "category_name": r.name, "created_at": r.created_at} for r in rows]


@router.delete("/sorting-rules/{rule_id}", status_code=204)
def delete_rule(rule_id: str, user: str = Depends(own), conn: Connection = Depends(get_conn)):
    """Removes the rule for the future; entries it already sorted keep their category (change them by hand)."""
    gone = conn.execute(text("DELETE FROM user_rule WHERE rule_id = :r AND user_id = :u"), {"r": rule_id, "u": user}).rowcount
    if not gone:
        raise HTTPException(404, "Not found.")
    conn.commit()


# ---------------------------------------------------------------- AI (opt-in)

class AiIn(BaseModel):
    enabled: bool


def _enabled(conn, user) -> bool:
    return bool(conn.execute(text("SELECT enabled FROM user_ai WHERE user_id = :u"), {"u": user}).scalar())


@router.get("/ai")
def ai_status(user: str = Depends(household), conn: Connection = Depends(get_conn)):
    return {
        "available": ai_sort.available(), "enabled": _enabled(conn, user), "provider": "Google Gemini",
        "what_is_sent": "Only the narration of an unsorted entry, with numbers, UPI IDs and e-mail addresses removed, "
                        "and whether money went out or in. Never amounts, dates, names of your accounts or who you are.",
    }


@router.put("/ai")
def ai_set(body: AiIn, user: str = Depends(own), conn: Connection = Depends(get_conn)):
    conn.execute(text("INSERT INTO user_ai (user_id, enabled) VALUES (:u, :e) ON CONFLICT (user_id) DO UPDATE SET "
                      "enabled = :e, updated_at = now()"), {"u": user, "e": body.enabled})
    conn.commit()
    return {"enabled": body.enabled, "available": ai_sort.available()}


@router.post("/ai/sort")
def ai_sort_unsorted(request: Request, user: str = Depends(own), caller: Caller = Depends(current_user),
                     conn: Connection = Depends(get_conn)):
    """Ask Gemini about up to 40 unsorted entries; sure answers become ordinary overrides labelled as AI."""
    if not ai_sort.available():
        raise HTTPException(503, "AI sorting is not set up on this server.")
    if not _enabled(conn, user):
        raise HTTPException(409, "Turn on AI sorting first.")
    recent = conn.execute(text("SELECT count(*) FROM audit_event WHERE action = 'AI_SORT' AND entity_id = :u "
                               "AND at > now() - interval '1 hour'"), {"u": user}).scalar()
    if recent >= CALLS_PER_HOUR:
        raise HTTPException(429, "That is enough AI sorting for this hour. Try again later.")
    run = latest_run_id(conn)
    rows = _unsorted(conn, run, user, MAX_PER_CALL) if run else []
    cats = {r.category_code: r.name for r in conn.execute(text(
        "SELECT category_code, name, kind FROM category WHERE effective_to IS NULL AND kind IN ('EXPENSE', 'INCOME') "
        "ORDER BY name"))}
    kinds = {r.category_code: r.kind for r in conn.execute(text("SELECT category_code, kind FROM category"))}
    keyed: dict[str, dict] = {}
    for t in rows:
        text_ = ai_sort.mask(t.descriptor)
        d = "DR" if t.amount_paise < 0 else "CR"
        if len(text_) < 3:
            continue
        keyed.setdefault(ai_sort.cache_key(text_, d, t.channel), {"text": text_, "direction": d, "channel": t.channel})
    got: dict[str, tuple[str, float]] = {}
    if keyed:
        for k, c, p in conn.execute(text("SELECT key, category_code, confidence FROM ai_cache WHERE key = ANY(:k)"),
                                    {"k": list(keyed)}).all():
            got[k] = (c, p)
    todo = [k for k in keyed if k not in got]
    error = None
    if todo:
        items = [{"id": i, **keyed[k]} for i, k in enumerate(todo)]
        try:
            for i, (c, p) in ai_sort.suggest(items, cats).items():
                got[todo[i]] = (c, p)
                conn.execute(text("INSERT INTO ai_cache (key, category_code, confidence, model) VALUES (:k, :c, :p, :m) "
                                  "ON CONFLICT DO NOTHING"), {"k": todo[i], "c": c, "p": p, "m": ai_sort.settings.gemini_model})
        except ai_sort.AiError as e:
            error = str(e)
    sorted_n = 0
    for t in rows:
        d = "DR" if t.amount_paise < 0 else "CR"
        k = ai_sort.cache_key(ai_sort.mask(t.descriptor), d, t.channel)
        code, p = got.get(k, (None, 0.0))
        want = "EXPENSE" if d == "DR" else "INCOME"
        if code is None or p < MIN_CONFIDENCE or kinds.get(code) != want:
            continue
        try:
            apply_override(conn, t.txn_id, code, t.local_date, "AI:gemini", f"Suggested by Gemini, {round(p * 100)}% sure",
                           _rid(request))
            sorted_n += 1
        except HTTPException:
            continue
    audit(conn, caller.email, "AI_SORT", "USER", user, _rid(request), {"asked": len(todo), "sorted": sorted_n, "error": error})
    conn.commit()
    if error and not sorted_n:
        raise HTTPException(502, f"{error}. Nothing was changed.")
    return {"checked": len(rows), "sorted": sorted_n, "left": len(rows) - sorted_n}
