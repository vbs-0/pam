"""Checks over a persisted run: every transaction decided once, links consistent, ids resolvable,
exception histories well-formed, series events ordered. Results are stored as a validation_run."""
import json

from sqlalchemy import Connection, text

from app import schema
from app.datagen.validate import CheckResult, to_json
from app.jobs.pipeline_job import latest_run_id
from app.jobs.sql import next_number

CHECKS = {
    "completeness": "SELECT t.txn_id FROM txn t LEFT JOIN txn_enrichment e ON e.txn_id = t.txn_id AND e.run_id = :r "
                    "WHERE e.txn_id IS NULL",
    # E26: income + spend + transfers/reversals buckets are exhaustive and disjoint for every household
    "partition_identity": """
        SELECT e.user_id FROM txn_enrichment e JOIN txn t USING (txn_id) WHERE e.run_id = :r GROUP BY e.user_id
        HAVING sum(t.amount_paise) <>
            coalesce(sum(t.amount_paise) FILTER (WHERE e.kind = 'INCOME'
                                                 OR (e.kind = 'UNKNOWN' AND t.amount_paise > 0)), 0)
          + coalesce(sum(t.amount_paise) FILTER (WHERE e.kind IN ('EXPENSE', 'REFUND')
                                                 OR (e.kind = 'UNKNOWN' AND t.amount_paise < 0)), 0)
          + coalesce(sum(t.amount_paise) FILTER (WHERE e.kind IN ('TRANSFER', 'REVERSAL')), 0)""",
    "mutual_pairs_balance": """
        SELECT a.txn_id FROM txn_enrichment a JOIN txn ta ON ta.txn_id = a.txn_id
        LEFT JOIN txn_enrichment b ON b.run_id = a.run_id AND b.txn_id = a.link_txn_id
        LEFT JOIN txn tb ON tb.txn_id = b.txn_id
        WHERE a.run_id = :r AND a.kind IN ('TRANSFER','REVERSAL') AND a.link_txn_id IS NOT NULL
          AND (b.link_txn_id IS DISTINCT FROM a.txn_id OR ta.amount_paise + tb.amount_paise <> 0
               OR ta.user_id <> tb.user_id)""",
    "refund_links_to_earlier_purchase": """
        SELECT a.txn_id FROM txn_enrichment a JOIN txn ta ON ta.txn_id = a.txn_id
        JOIN txn tb ON tb.txn_id = a.link_txn_id
        WHERE a.run_id = :r AND a.kind = 'REFUND'
          AND (tb.amount_paise >= 0 OR tb.posted_at >= ta.posted_at OR tb.user_id <> ta.user_id)""",
    "series_ids_registered": "SELECT e.txn_id FROM txn_enrichment e LEFT JOIN recurring_series s USING (series_id) "
                             "WHERE e.run_id = :r AND e.series_id IS NOT NULL AND s.series_id IS NULL",
    "exception_entities_exist": """
        SELECT x.exception_id FROM exception_case x
        WHERE x.last_run_id = :r AND NOT CASE x.entity_type
          WHEN 'TXN' THEN EXISTS (SELECT 1 FROM txn WHERE txn_id = x.entity_id)
          WHEN 'BUDGET' THEN EXISTS (SELECT 1 FROM budget WHERE budget_id = x.entity_id)
          ELSE EXISTS (SELECT 1 FROM recurring_series WHERE series_id = x.entity_id) END""",
    "exception_event_chains": """
        SELECT exception_id FROM (
          SELECT exception_id, seq, from_status, to_status,
                 lag(to_status) OVER w AS prev, row_number() OVER w AS n
          FROM exception_event WINDOW w AS (PARTITION BY exception_id ORDER BY seq)) c
        WHERE seq <> n OR from_status IS DISTINCT FROM prev
        UNION
        SELECT x.exception_id FROM exception_case x
        JOIN LATERAL (SELECT to_status FROM exception_event v WHERE v.exception_id = x.exception_id
                      ORDER BY seq DESC LIMIT 1) last ON true WHERE last.to_status <> x.status""",
    "series_events_ordered": """
        SELECT series_id FROM (SELECT series_id, event_date, lag(event_date) OVER
          (PARTITION BY series_id ORDER BY seq) AS prev FROM recurring_series_event WHERE run_id = :r) s
        WHERE event_date < prev""",
    "insights_have_evidence": "SELECT insight_id FROM insight WHERE run_id = :r AND evidence = '{}'::jsonb",
}


def validate_outputs(conn: Connection, run_id: str | None = None) -> list[CheckResult]:
    run_id = run_id or latest_run_id(conn)
    if run_id is None:
        raise LookupError("no successful pipeline run to validate")
    results = []
    for name, sql in CHECKS.items():
        bad = [str(r[0]) for r in conn.execute(text(sql), {"r": run_id})]
        results.append(CheckResult(name, "FAIL" if bad else "PASS", len(bad), 0, bad[:5]))
    conn.execute(text("INSERT INTO validation_run (validation_id, scope, created_at, passed, results) "
                      "VALUES (:id, 'OUTPUTS', now(), :ok, CAST(:res AS jsonb))"),
                 {"id": f"VAL-{next_number(conn, schema.validation_run, 'validation_id'):06d}",
                  "ok": all(r.status == "PASS" for r in results),
                  "res": json.dumps({"run_id": run_id, "checks": json.loads(to_json(results))})})
    return results
