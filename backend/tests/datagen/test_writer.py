import csv
import json

from app.datagen.generator import GenParams, generate
from app.datagen.writer import export_json, export_sql, fmt, repro, write_dataset

P = GenParams(users=8, transactions=2_500)


def test_fmt_rules():
    from datetime import UTC, date, datetime
    from decimal import Decimal
    assert fmt(None) == "" and fmt(True) == "true" and fmt(0) == "0"
    assert fmt(datetime(2025, 12, 31, 18, 40, tzinfo=UTC)) == "2025-12-31T18:40:00Z"
    assert fmt(date(2026, 2, 1)) == "2026-02-01" and fmt(Decimal("0.95")) == "0.95"


def test_write_and_manifest(tmp_path):
    m = write_dataset(generate(P), tmp_path)
    assert (tmp_path / "inputs" / "txn.csv").exists() and (tmp_path / "ground_truth" / "txn_label.csv").exists()
    assert m["seed"] == 20261022 and m["files"]["inputs/txn.csv"]["rows"] == 2_500
    raw = (tmp_path / "inputs" / "txn.csv").read_bytes()
    assert b"\r\n" not in raw
    with open(tmp_path / "inputs" / "txn.csv", encoding="utf-8", newline="") as f:
        first = next(csv.DictReader(f))
    assert first["txn_id"] == "TXN-2026-00000001" and first["posted_at"].endswith("Z")
    assert "generated_at" not in json.dumps(m) and len(m["files"]) == 16


def test_json_and_sql(tmp_path):
    write_dataset(generate(P), tmp_path)
    export_json(tmp_path)
    users = json.loads((tmp_path / "json" / "user_profile.json").read_text(encoding="utf-8"))
    assert users[0]["user_id"] == "USR-000001" and isinstance(users[0]["monthly_income_paise"], int)
    txns = json.loads((tmp_path / "json" / "txn.json").read_text(encoding="utf-8"))
    assert len(txns) == 2_500 and isinstance(txns[0]["amount_paise"], int)
    assert any(t["counterparty_vpa"] is None for t in txns)
    merchants = json.loads((tmp_path / "json" / "merchant.json").read_text(encoding="utf-8"))
    assert all(isinstance(m["is_online"], bool) for m in merchants)
    export_sql(tmp_path)
    sql = (tmp_path / "seed.sql").read_text(encoding="utf-8")
    assert "CREATE SCHEMA IF NOT EXISTS gt" in sql and "CREATE TABLE txn" in sql and "COPY txn (" in sql
    assert sql.count("\\.\n") == 16 and sql.rstrip().endswith("COMMIT;")


def test_repro_identical_across_interpreters(tmp_path):
    r = repro(P, tmp_path)
    assert r["match"] is True and r["runs"][0] == r["runs"][1] and len(r["files"]) == 16
