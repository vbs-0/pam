"""Run the decision engine against the database and persist one numbered run.

Single-flight (advisory lock), stable ids across runs: recurring series keep their REC- id for the same natural key,
exceptions keep their EXC- id and status (E27). A failed run is marked FAILED and leaves no outputs; readers keep
using the last SUCCEEDED run (E30).

Two populations go through the engine separately: the synthetic challenge households (judged "as of" the dataset's
last month) and real households people create by signing in (judged as of today, so a bill due next week is not
"missed"). A real household can also be refreshed on its own inside the latest run right after its owner edits
data (refresh_household); the full run re-processes real households last so edits made while it ran are included.
"""
import hashlib
import json
from datetime import date, datetime

from sqlalchemy import Connection, text
from sqlalchemy.exc import OperationalError

from app import schema
from app.db import PIPELINE_LOCK, advisory_lock
from app.engine.pipeline import EngineOutput, input_from_rows, run_engine
from app.households import REAL_FROM
from app.jobs.sql import copy_rows, next_number, select_rows
from app.timeutil import IST

ENGINE_INPUTS = [schema.user_profile, schema.category, schema.category_synonym, schema.merchant,
                 schema.merchant_alias, schema.category_rule, schema.account, schema.txn, schema.budget]
PER_USER = {"user_profile", "account", "txn", "budget"}
SYNTHETIC, REAL = "WHERE user_id < :real", "WHERE user_id >= :real"


def latest_run_id(conn: Connection) -> str | None:
    return conn.execute(text("SELECT max(run_id) FROM pipeline_run WHERE status = 'SUCCEEDED'")).scalar()


def _ruleset_hash(rules) -> str:
    rows = sorted((r.rule_id, r.version, r.priority, r.category_code, r.merchant_id or "", r.pattern or "",
                   r.channel or "", r.direction, r.account_type or "", r.confidence) for r in rules)
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


def run_pipeline(conn: Connection, fail_after_writes: bool = False) -> str:
    with advisory_lock(conn):
        n = next_number(conn, schema.pipeline_run, "run_id")
        run_id = f"RUN-{n:06d}"
        conn.execute(text("INSERT INTO pipeline_run (run_id, status, started_at) VALUES (:r, 'RUNNING', now())"),
                     {"r": run_id})
        conn.commit()
        try:
            stats = _run(conn, run_id)
            if fail_after_writes:                              # test hook for E30
                raise RuntimeError("injected failure after writes")
            conn.execute(text("UPDATE pipeline_run SET status = 'SUCCEEDED', finished_at = now(), "
                              "stats = CAST(:s AS jsonb), ruleset_hash = :h WHERE run_id = :r"),
                         {"s": json.dumps(stats), "h": stats.pop("_ruleset_hash"), "r": run_id})
            conn.commit()
        except Exception as e:
            conn.rollback()
            conn.execute(text("UPDATE pipeline_run SET status = 'FAILED', finished_at = now(), error = :e "
                              "WHERE run_id = :r"), {"e": f"{type(e).__name__}: {e}"[:2000], "r": run_id})
            conn.commit()
            raise
        return run_id


def refresh_household(conn: Connection, user_id: str) -> bool:
    """Re-run the engine for one real household inside the latest run. Call after committing the edit.
    Returns False (edit stays queued for the next run) when a full run holds the lock for more than 3 s."""
    run_id = latest_run_id(conn)
    if run_id is None or user_id < REAL_FROM:
        return False
    try:
        conn.execute(text("SET LOCAL lock_timeout = '3s'"))
        conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": PIPELINE_LOCK})
        conn.execute(text("SET LOCAL lock_timeout = 0"))
    except OperationalError:
        conn.rollback()
        return False
    p = {"run": run_id, "u": user_id}
    for sql in ("DELETE FROM txn_enrichment WHERE run_id = :run AND user_id = :u",
                "DELETE FROM recurring_series_event WHERE run_id = :run AND series_id IN "
                "(SELECT series_id FROM recurring_series WHERE user_id = :u)",
                "DELETE FROM recurring_series_state WHERE run_id = :run AND series_id IN "
                "(SELECT series_id FROM recurring_series WHERE user_id = :u)",
                "DELETE FROM budget_resolution WHERE run_id = :run AND budget_id LIKE 'BUD-' || :u || '-%'",
                "DELETE FROM insight WHERE run_id = :run AND user_id = :u"):
        conn.execute(text(sql), p)
    _process(conn, run_id, "WHERE user_id = :u", {"u": user_id}, as_of=today())
    conn.commit()
    return True


def today() -> date:
    return datetime.now(IST).date()


def _run(conn: Connection, run_id: str) -> dict:
    stats = _process(conn, run_id, SYNTHETIC, {"real": REAL_FROM})
    real = _process(conn, run_id, REAL, {"real": REAL_FROM}, as_of=today())
    stats["real_households_txns"] = real["txns"]
    return stats


def _process(conn: Connection, run_id: str, where: str, params: dict, as_of: date | None = None) -> dict:
    tables = {t.name: select_rows(conn, t, where if t.name in PER_USER else "", params) for t in ENGINE_INPUTS}
    inp = input_from_rows(tables)
    del tables
    if as_of:
        inp.data_end = as_of
    for txn_id, code, oid in conn.execute(text(
            "SELECT DISTINCT ON (txn_id) txn_id, category_code, override_id FROM category_override "
            "ORDER BY txn_id, created_at DESC, override_id DESC")):
        inp.overrides[txn_id] = (code, oid)
    out = run_engine(inp)
    return _write(conn, run_id, out) | {"_ruleset_hash": _ruleset_hash(inp.rules)}


def _write(conn: Connection, run_id: str, out: EngineOutput) -> dict:
    run_no = int(run_id.rsplit("-", 1)[1])
    # stable series ids: existing natural keys keep theirs, new keys (sorted) continue the sequence
    registry = {(u, k, d): sid for sid, u, k, d in conn.execute(text(
        "SELECT series_id, user_id, counterparty_key, direction FROM recurring_series"))}
    nxt = next_number(conn, schema.recurring_series, "series_id")
    new = []
    for key in sorted({s.key for s in out.series} - set(registry)):
        registry[key] = f"REC-{nxt:06d}"
        new.append((registry[key], key[0], key[1], key[2], run_id))
        nxt += 1
    copy_rows(conn, schema.recurring_series, new)

    copy_rows(conn, schema.txn_enrichment, (
        (run_id, e.txn.txn_id, e.txn.user_id, e.local_date, e.local_month, e.merchant_id, e.category_code,
         e.rule_id, e.rule_version, round(e.confidence, 2), e.kind, e.link_txn_id,
         registry[e.series_key] if e.series_key else None, e.decision) for e in out.enriched))
    copy_rows(conn, schema.recurring_series_state, (
        (run_id, registry[s.key], s.account_id, s.merchant_id, s.category_code, s.series_type, s.cadence,
         s.median_gap_days, s.typical_amount_paise, s.first_seen, s.last_seen, s.next_expected, s.status,
         len(s.member_txn_ids)) for s in out.series))
    copy_rows(conn, schema.recurring_series_event, (
        (run_id, registry[s.key], i, kind, d, detail or None)
        for s in out.series for i, (kind, d, detail) in enumerate(s.events, 1)))
    copy_rows(conn, schema.budget_resolution, (
        (run_id, r.budget_id, r.version, r.resolved_code, r.resolution) for r in out.resolutions))
    per_user: dict[str, int] = {}

    def insight_id(user: str) -> str:            # per household, so refreshing one household never collides
        per_user[user] = per_user.get(user, 0) + 1
        return f"INS-{run_no:04d}-{user}-{per_user[user]:04d}"
    copy_rows(conn, schema.insight, (
        (insight_id(x.user_id), run_id, x.user_id, x.month, x.insight_type, x.severity, x.category_code,
         x.metric_paise, x.baseline_paise, x.message, _evidence(x.evidence, registry)) for x in out.insights))

    # exceptions: same (type, entity) keeps its id and status; only last_run_id moves
    existing = {(t, e): xid for xid, t, e in conn.execute(text(
        "SELECT exception_id, exception_type, entity_id FROM exception_case"))}
    seen, fresh = [], []
    nxt = next_number(conn, schema.exception_case, "exception_id")
    for x in out.exceptions:
        entity = registry[_split_key(x.entity_id)] if x.entity_type == "SERIES" else x.entity_id
        if (x.exception_type, entity) in existing:
            seen.append(existing[(x.exception_type, entity)])
        else:
            xid = f"EXC-{nxt:06d}"
            nxt += 1
            existing[(x.exception_type, entity)] = xid
            fresh.append((xid, x.exception_type, x.entity_type, entity, x.user_id, x.detail))
    if seen:
        conn.execute(text("UPDATE exception_case SET last_run_id = :r WHERE exception_id = ANY(:ids)"),
                     {"r": run_id, "ids": seen})
    now = conn.execute(text("SELECT now()")).scalar()
    copy_rows(conn, schema.exception_case, (
        (xid, t, et, e, u, "OPEN", run_id, run_id, d, now, now) for xid, t, et, e, u, d in fresh))
    copy_rows(conn, schema.exception_event, ((f[0], 1, None, "OPEN", "system", None, now) for f in fresh))
    return dict(out.stats, new_series=len(new), new_exceptions=len(fresh))


def _split_key(joined: str) -> tuple[str, str, str]:
    """'user|<counterparty key, itself containing |>|DR' -> (user, counterparty key, direction)."""
    user, rest = joined.split("|", 1)
    cp, direction = rest.rsplit("|", 1)
    return user, cp, direction


def _evidence(ev: dict, registry: dict) -> dict:
    """Replace the engine's natural series key with the stable REC- id."""
    if "series_key" in ev:
        ev = {**ev, "series_id": registry.get(_split_key(ev["series_key"]))}
        ev.pop("series_key")
    return ev
