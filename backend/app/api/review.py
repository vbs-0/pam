"""Reviewer API (read-only): did the engine catch each labelled anomaly, recall per issue type, the audit trail."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Connection, text

from app.api.common import decode_cursor, encode_cursor, limit_q
from app.api.deps import Caller, require
from app.db import get_conn

router = APIRouter(prefix="/review", tags=["reviewer"])
REVIEWER = require("REVIEWER", "ADMIN")


def _evaluated_run(conn, run_id: str | None) -> str:
    r = conn.execute(text("SELECT run_id FROM evaluation_run WHERE CAST(:r AS text) IS NULL OR run_id = :r "
                          "ORDER BY created_at DESC LIMIT 1"), {"r": run_id}).scalar()
    if r is None:
        raise HTTPException(404, "No evaluated run yet. An admin can run an evaluation from the Jobs page.")
    return r


@router.get("/anomalies")
def anomalies(issue_type: str | None = Query(None, pattern="^[A-Z_]{3,28}$"),
              outcome: str | None = Query(None, pattern="^(CAUGHT|MISSED)$"),
              run_id: str | None = Query(None, max_length=32),
              _: Caller = Depends(REVIEWER), conn: Connection = Depends(get_conn)):
    run = _evaluated_run(conn, run_id)
    rows = conn.execute(text(
        "SELECT a.*, o.outcome, o.observed, o.run_id FROM gt.anomaly a "
        "JOIN anomaly_outcome o ON o.anomaly_id = a.anomaly_id AND o.run_id = :r "
        "WHERE (CAST(:t AS text) IS NULL OR a.issue_type = :t) AND (CAST(:o AS text) IS NULL OR o.outcome = :o) "
        "ORDER BY a.anomaly_id"), {"r": run, "t": issue_type, "o": outcome})
    return [dict(r._mapping) for r in rows]


@router.get("/summary")
def summary(run_id: str | None = Query(None, max_length=32), _: Caller = Depends(REVIEWER),
            conn: Connection = Depends(get_conn)):
    run = _evaluated_run(conn, run_id)
    rows = conn.execute(text(
        "SELECT a.issue_type, count(*) AS labelled, count(*) FILTER (WHERE o.outcome = 'CAUGHT') AS caught "
        "FROM gt.anomaly a JOIN anomaly_outcome o ON o.anomaly_id = a.anomaly_id AND o.run_id = :r "
        "GROUP BY 1 ORDER BY 1"), {"r": run}).all()
    m = conn.execute(text("SELECT metrics FROM evaluation_run WHERE run_id = :r"), {"r": run}).scalar()
    return {"run_id": run, "all_pass": m.get("all_pass"), "thresholds": m.get("thresholds"),
            "by_issue": [{"issue_type": r.issue_type, "labelled": r.labelled, "caught": r.caught,
                          "recall": round(r.caught / r.labelled, 4) if r.labelled else None} for r in rows]}


@router.get("/audit")
def audit_log(entity_type: str | None = Query(None, max_length=30), entity_id: str | None = Query(None, max_length=64),
              actor: str | None = Query(None, max_length=120), action: str | None = Query(None, max_length=60),
              cursor: str | None = None, limit: int = Depends(limit_q),
              _: Caller = Depends(REVIEWER), conn: Connection = Depends(get_conn)):
    p: dict = {"et": entity_type, "e": entity_id, "a": actor and actor.lower(), "ac": action, "lim": limit + 1,
               "before": int(decode_cursor(cursor, 1)[0]) if cursor else None}
    rows = conn.execute(text(
        "SELECT * FROM audit_event WHERE (CAST(:et AS text) IS NULL OR entity_type = :et) "
        "AND (CAST(:e AS text) IS NULL OR entity_id = :e) AND (CAST(:a AS text) IS NULL OR lower(actor) = :a) "
        "AND (CAST(:ac AS text) IS NULL OR action = :ac) AND (CAST(:before AS bigint) IS NULL OR id < :before) "
        "ORDER BY id DESC LIMIT :lim"), p).all()
    more, rows = len(rows) > limit, rows[:limit]
    return {"items": [dict(r._mapping) for r in rows], "next_cursor": encode_cursor(rows[-1].id) if more else None}
