import pytest
from sqlalchemy import text

from app.datagen.generator import GenParams, generate
from app.datagen.writer import write_dataset
from app.jobs.evaluate_job import run_evaluation
from app.jobs.load import load_dataset, seed_demo_users
from app.jobs.outputs_validate import validate_outputs
from app.jobs.pipeline_job import latest_run_id, run_pipeline

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def loaded(db_engine, tmp_path_factory):
    d = tmp_path_factory.mktemp("starter")
    write_dataset(generate(GenParams.for_scale("starter")), d)
    with db_engine.connect() as conn:
        counts = load_dataset(conn, d, "starter")
        conn.commit()
        run_id = run_pipeline(conn)
        yield conn, run_id, counts, d


def test_load_counts(loaded):
    conn, _, counts, _ = loaded
    assert counts["txn"] == 25_000
    # real households created by earlier API tests survive the load (A36), so count the sample ones
    assert conn.execute(text("SELECT count(*) FROM txn WHERE user_id < 'USR-500001'")).scalar() == 25_000
    assert conn.execute(text("SELECT count(*) FROM gt.txn_label")).scalar() == 25_000
    assert conn.execute(text("SELECT scale FROM dataset_load ORDER BY load_id DESC LIMIT 1")).scalar() == "starter"


def test_thresholds_on_starter(loaded):
    conn, run_id, _, _ = loaded
    m = run_evaluation(conn, run_id)
    conn.commit()
    assert m["all_pass"], {k: v for k, v in m["thresholds"].items() if not v["pass"]}
    n = conn.execute(text("SELECT count(*) FROM anomaly_outcome WHERE run_id = :r"), {"r": run_id}).scalar()
    assert n == conn.execute(text("SELECT count(*) FROM gt.anomaly")).scalar()


def test_outputs_validate_and_rerun_keeps_ids(loaded):
    conn, run_id, _, _ = loaded
    failing = [r for r in validate_outputs(conn, run_id) if r.status == "FAIL"]
    conn.commit()
    assert not failing, failing
    before = conn.execute(text("SELECT series_id, counterparty_key FROM recurring_series ORDER BY 1")).all()
    conn.execute(text("UPDATE exception_case SET status = 'RESOLVED' WHERE exception_id = "
                      "(SELECT min(exception_id) FROM exception_case)"))
    conn.commit()
    exc_before = conn.execute(text("SELECT exception_id, status FROM exception_case ORDER BY 1")).all()
    run2 = run_pipeline(conn)
    assert run2 != run_id and latest_run_id(conn) == run2
    assert conn.execute(text("SELECT series_id, counterparty_key FROM recurring_series ORDER BY 1")).all() == before
    assert conn.execute(text("SELECT exception_id, status FROM exception_case ORDER BY 1")).all() == exc_before
    n = conn.execute(text("SELECT count(*) FROM txn_enrichment WHERE run_id = :r"), {"r": run2}).scalar()
    assert n == conn.execute(text("SELECT count(*) FROM txn")).scalar()


def test_failed_run_is_invisible(loaded):
    conn, _, _, _ = loaded
    good = latest_run_id(conn)
    with pytest.raises(RuntimeError):
        run_pipeline(conn, fail_after_writes=True)
    failed = conn.execute(text("SELECT run_id, error FROM pipeline_run WHERE status = 'FAILED'")).one()
    assert "injected" in failed.error and latest_run_id(conn) == good
    assert conn.execute(text("SELECT count(*) FROM txn_enrichment WHERE run_id = :r"),
                        {"r": failed.run_id}).scalar() == 0


def test_override_survives_rerun(loaded):
    conn, _, _, _ = loaded
    tid = conn.execute(text("SELECT min(txn_id) FROM txn WHERE amount_paise < 0")).scalar()
    conn.execute(text("INSERT INTO category_override VALUES ('OVR-000001', :t, 'HEALTH', 'test', NULL, now())"),
                 {"t": tid})
    conn.commit()
    run = run_pipeline(conn)
    row = conn.execute(text("SELECT category_code, decision FROM txn_enrichment WHERE run_id = :r AND txn_id = :t"),
                       {"r": run, "t": tid}).one()
    assert row == ("HEALTH", "OVERRIDE:OVR-000001")


def test_reload_keeps_app_users(loaded, monkeypatch):
    conn, _, _, d = loaded
    monkeypatch.setenv("DEMO_PASSWORD", "demo-pass-123")
    conn.execute(text("DELETE FROM app_user"))
    seed_demo_users(conn)
    conn.commit()
    users = conn.execute(text("SELECT email, role, profile_user_id FROM app_user ORDER BY 1")).all()
    assert ("customer@pam.test", "CUSTOMER", "USR-000001") in users and len(users) == 4
    load_dataset(conn, d, "starter")
    conn.commit()
    assert conn.execute(text("SELECT email, role, profile_user_id FROM app_user ORDER BY 1")).all() == users
    assert conn.execute(text("SELECT count(*) FROM pipeline_run")).scalar() == 0
    assert seed_demo_users(conn) == 0                                               # never overwrites
