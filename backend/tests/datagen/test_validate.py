import csv
import hashlib
import json

import pytest

from app.datagen.generator import GenParams, generate
from app.datagen.validate import render_markdown, validate_dataset
from app.datagen.writer import write_dataset


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("ds")
    write_dataset(generate(GenParams(users=10, transactions=3_500)), d)
    return d


def _by_name(results):
    return {r.name: r for r in results}


def _fresh(tmp_path):
    write_dataset(generate(GenParams(users=6, transactions=2_200)), tmp_path)
    return tmp_path


def _corrupt(path, mutate, rehash=True):
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    mutate(rows)
    with open(path, "w", encoding="utf-8", newline="") as f:
        csv.writer(f, lineterminator="\n").writerows(rows)
    if rehash:   # keep the manifest consistent so only the targeted check fires
        m = json.loads((path.parents[1] / "manifest.json").read_text(encoding="utf-8"))
        rel = f"{path.parent.name}/{path.name}"
        m["files"][rel] = {"rows": len(rows) - 1, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        (path.parents[1] / "manifest.json").write_text(json.dumps(m), encoding="utf-8")


def test_clean_dataset_passes(data_dir):
    res = _by_name(validate_dataset(data_dir))
    assert all(r.status != "FAIL" for r in res.values()), [r for r in res.values() if r.status == "FAIL"]
    assert res["taxonomy_conformance"].labelled > 0
    assert len(res) == 17
    md = render_markdown(list(res.values()), "Dataset validation")
    assert "| `balances` | PASS |" in md


def test_detects_duplicate_pk_bad_fk_bad_enum(tmp_path):
    d = _fresh(tmp_path)
    _corrupt(d / "inputs" / "txn.csv", lambda r: (r.append(list(r[1])), r[2].__setitem__(1, "ACC-USR-999999-01"),
                                                  r[3].__setitem__(6, "BITCOIN")))
    res = _by_name(validate_dataset(d))
    assert res["pk_unique"].status == "FAIL"
    assert res["fk_integrity"].status == "FAIL"
    assert res["enums"].status == "FAIL"
    assert res["duplicates"].status == "FAIL"


def test_detects_unlabelled_taxonomy_violation(tmp_path):
    d = _fresh(tmp_path)

    def mutate(rows):  # corrupt a budget that is NOT a labelled anomaly
        i = next(i for i, row in enumerate(rows) if row[4] == "GROCERIES")
        rows[i][4] = "NOT_A_CODE"

    _corrupt(d / "inputs" / "budget.csv", mutate)
    res = _by_name(validate_dataset(d))["taxonomy_conformance"]
    assert res.status == "FAIL" and "not labelled" in res.examples[0]


def test_detects_broken_arithmetic_and_sign(tmp_path):
    d = _fresh(tmp_path)

    def mutate(rows):  # make one debit 1 paisa bigger and flip the sign of a UPI credit
        i = next(i for i, row in enumerate(rows) if row[7].startswith("UPI/DR/"))
        rows[i][4] = str(int(rows[i][4]) - 1)
        j = next(i for i, row in enumerate(rows) if row[7].startswith("UPI/CR/"))
        rows[j][4] = str(-int(rows[j][4]))

    _corrupt(d / "inputs" / "txn.csv", mutate)
    res = _by_name(validate_dataset(d))
    assert res["balances"].status == "FAIL" and res["sign_convention"].status == "FAIL"


def test_detects_truth_leak_and_column_drift(tmp_path):
    d = _fresh(tmp_path)

    def mutate(rows):
        rows[0].append("true_category_code")
        for row in rows[1:]:
            row.append("SHOPPING")

    _corrupt(d / "inputs" / "merchant.csv", mutate)
    res = _by_name(validate_dataset(d))
    assert res["truth_isolation"].status == "FAIL" and res["columns"].status == "FAIL"
    assert res["fk_integrity"].status == "PASS"          # other checks still run on the matching columns


def test_manifest_detects_edit(tmp_path):
    d = _fresh(tmp_path)
    _corrupt(d / "inputs" / "category.csv", lambda r: r[1].__setitem__(1, "Renamed"), rehash=False)
    assert _by_name(validate_dataset(d))["manifest_and_volume"].status == "FAIL"
