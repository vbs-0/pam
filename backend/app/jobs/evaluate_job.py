"""Score a persisted run against ground truth and store the metrics and per-anomaly outcomes."""
import json

from sqlalchemy import Connection, text

from app import schema
from app.evaluation import Decided, evaluate
from app.jobs.pipeline_job import latest_run_id
from app.jobs.sql import copy_rows, select_rows


def run_evaluation(conn: Connection, run_id: str | None = None) -> dict:
    run_id = run_id or latest_run_id(conn)
    if run_id is None:
        raise LookupError("no successful pipeline run to evaluate")
    p = {"r": run_id}
    decided = [Decided(*r) for r in conn.execute(text(
        "SELECT e.txn_id, e.user_id, e.local_month, e.category_code, e.kind, e.link_txn_id, e.series_id, "
        "t.amount_paise, t.posted_at, t.descriptor FROM txn_enrichment e JOIN txn t USING (txn_id) "
        "WHERE e.run_id = :r"), p)]
    events = [tuple(r) for r in conn.execute(text(
        "SELECT series_id, event_type, event_date FROM recurring_series_event WHERE run_id = :r"), p)]
    resolutions = {b: (c, how) for b, c, how in conn.execute(text(
        "SELECT budget_id, resolved_category_code, resolution FROM budget_resolution WHERE run_id = :r"), p)}
    exceptions = {(t, e) for t, e in conn.execute(text(
        "SELECT exception_type, entity_id FROM exception_case WHERE last_run_id = :r"), p)}
    m = evaluate(decided, select_rows(conn, schema.gt_txn_label), select_rows(conn, schema.gt_recurring_truth),
                 select_rows(conn, schema.gt_anomaly), events, resolutions, exceptions)
    m["run_id"] = run_id
    conn.execute(text("DELETE FROM anomaly_outcome WHERE run_id = :r"), p)
    conn.execute(text("DELETE FROM evaluation_run WHERE run_id = :r"), p)
    conn.execute(text("INSERT INTO evaluation_run (run_id, created_at, metrics) VALUES (:r, now(), CAST(:m AS jsonb))"),
                 {"r": run_id, "m": json.dumps(m, default=str)})
    copy_rows(conn, schema.anomaly_outcome,
              ((run_id, o["anomaly_id"], o["outcome"], o["observed"]) for o in m["anomaly_outcomes"]))
    return m
