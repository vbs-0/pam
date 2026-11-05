import pytest

from app.datagen.generator import GenParams, generate
from app.engine.pipeline import input_from_rows, run_engine


@pytest.fixture(scope="module")
def ds():
    return generate(GenParams(users=6, transactions=2_500))


def test_pipeline_end_to_end_partition_and_exceptions(ds):
    out = run_engine(input_from_rows(ds.tables))
    assert len(out.enriched) == 2_500
    total = sum(e.txn.amount_paise for e in out.enriched)
    spend = sum(-e.txn.amount_paise for e in out.enriched
                if e.kind in ("EXPENSE", "REFUND") or (e.kind == "UNKNOWN" and e.txn.amount_paise < 0))
    income = sum(e.txn.amount_paise for e in out.enriched
                 if e.kind == "INCOME" or (e.kind == "UNKNOWN" and e.txn.amount_paise > 0))
    other = sum(e.txn.amount_paise for e in out.enriched if e.kind in ("TRANSFER", "REVERSAL"))
    assert total == income - spend + other                                            # E26
    assert out.stats["transfer_pairs"] > 0 and out.series and out.stats["cache_hits"] > 0
    assert any(x.exception_type == "BUDGET_CATEGORY_UNMAPPED" for x in out.exceptions)
    assert {i.insight_type for i in out.insights} & {"OVER_BUDGET", "NEAR_BUDGET"}
    assert all(e.local_month.startswith("2026") for e in out.enriched)


def test_override_locks_decision(ds):
    inp = input_from_rows(ds.tables)
    tid = inp.txns[10].txn_id
    inp.overrides[tid] = ("HEALTH", "OVR-000001")
    e = next(x for x in run_engine(inp).enriched if x.txn.txn_id == tid)
    assert e.category_code == "HEALTH" and e.locked and e.decision == "OVERRIDE:OVR-000001"


def test_deterministic(ds):
    a, b = run_engine(input_from_rows(ds.tables)), run_engine(input_from_rows(ds.tables))
    assert [(e.category_code, e.kind, e.link_txn_id, e.series_key) for e in a.enriched] == \
           [(e.category_code, e.kind, e.link_txn_id, e.series_key) for e in b.enriched]
    assert a.insights == b.insights and a.exceptions == b.exceptions


def test_transfer_without_counterpart_becomes_unmatched_transfer_exception():          # E09
    from datetime import UTC, date, datetime

    from app.engine.pipeline import _exceptions
    from app.engine.types import Enriched, Txn
    t = Txn("TXN-1", "USR-000001", "ACC-USR-000001-01", "UPI", datetime(2026, 3, 1, tzinfo=UTC), -50_000, "UPI", "UPI/DR/x")
    lonely = Enriched(t, "x", date(2026, 3, 1), "2026-03", kind="TRANSFER", rule_id="R-TRANSFER")
    paired = Enriched(t, "x", date(2026, 3, 1), "2026-03", kind="TRANSFER", link_txn_id="TXN-2")
    kept = Enriched(t, "x", date(2026, 3, 1), "2026-03", kind="TRANSFER", locked=True)
    out = _exceptions([lonely, paired, kept], [], [])
    assert [x.exception_type for x in out] == ["UNMATCHED_TRANSFER"] and out[0].entity_id == "TXN-1"
