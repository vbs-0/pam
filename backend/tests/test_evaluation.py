from datetime import date

import pytest

from app.datagen.generator import GenParams, generate
from app.engine.pipeline import input_from_rows, run_engine
from app.evaluation import classification_report, evaluate, from_engine, match_series, missed_event_eval, prf, set_prf


def test_prf_and_sets():
    assert prf(8, 2, 0) == {"precision": 0.8, "recall": 1.0, "f1": 0.8889, "tp": 8, "fp": 2, "fn": 0}
    assert set_prf({"a", "b"}, {"b", "c"})["f1"] == 0.5
    assert prf(0, 0, 0)["f1"] == 0.0


def test_classification_report():
    r = classification_report([("A", "A"), ("A", "B"), ("B", "B"), ("C", "C")])
    assert r["accuracy"] == 0.75 and r["confusion"]["A|B"] == 1
    assert r["per_class"]["A"]["recall"] == 0.5 and r["per_class"]["B"]["precision"] == 0.5


def test_series_match_and_missed_events():
    m = match_series({"REC-1": {"t1", "t2", "t3"}, "REC-2": {"t9"}}, {"TRS-1": {"t1", "t2", "t4"}})
    assert m == {"TRS-1": "REC-1"}
    res = missed_event_eval([("REC-1", date(2026, 6, 4)), ("REC-1", date(2026, 9, 1))],
                            skips=[("TRS-1", date(2026, 6, 5))], decoys=[("TRS-1", date(2026, 9, 3))],
                            truth_to_pred=m)
    assert res["precision"] == 0.5 and res["recall"] == 1.0 and res["decoy_false_alarm_rate"] == 1.0


@pytest.fixture(scope="module")
def starter():
    return generate(GenParams.for_scale("starter"))


@pytest.fixture(scope="module")
def starter_metrics(starter):
    ds = starter
    decided, events, resolutions, exceptions = from_engine(run_engine(input_from_rows(ds.tables)))
    return evaluate(decided, ds.truth["txn_label"], ds.truth["recurring_truth"], ds.truth["anomaly"], events,
                    resolutions, exceptions)


def test_starter_meets_acceptance_thresholds(starter_metrics):
    failing = {k: v for k, v in starter_metrics["thresholds"].items() if not v["pass"]}
    assert not failing, failing


def test_naive_baseline_overstates_and_every_issue_scored(starter_metrics):
    nb = starter_metrics["naive_baseline"]
    assert nb["naive_overstatement"] > 0.2 and abs(nb["system_error"]) < abs(nb["naive_overstatement"])
    assert set(starter_metrics["anomalies"]) == {"TRANSFER_DOUBLE_COUNT", "REFUND_AS_EXPENSE", "RECURRING_SKIP",
                                                 "RECURRING_NOT_SKIP", "TZ_BOUNDARY", "BUDGET_CATEGORY_MISMATCH"}
    assert starter_metrics["timezone"]["naive_utc_month_accuracy"] < starter_metrics["timezone"]["month_accuracy"]


def test_every_salary_and_pension_series_found(starter, starter_metrics):
    by_type = starter_metrics["recurring"]["by_type"]
    assert by_type["SALARY"]["matched"] == by_type["SALARY"]["truth"]
    pensioners = {u[0] for u in starter.tables["user_profile"] if u[5] == "RETIRED"}
    assert any(r[1] in pensioners and r[3] == "SALARY" for r in starter.truth["recurring_truth"])      # D25
    self_employed = {u[0] for u in starter.tables["user_profile"] if u[5] == "SELF_EMPLOYED"}
    assert self_employed and not any(r[1] in self_employed and r[3] == "SALARY"
                                     for r in starter.truth["recurring_truth"])                          # D24
