import csv
import hashlib
import json

import pytest

from app.datagen.generator import GenParams, generate
from app.datagen.validate import render_markdown, validate_dataset
from app.datagen.writer import export_json, export_sql, write_dataset, write_provenance


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
    assert len(res) == 22
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


def _first(rows, col, value):
    return next(i for i, r in enumerate(rows) if i and r[col] == value)


@pytest.mark.parametrize("table, mutate, check", [
    # a credit limit on a savings account
    ("account", lambda r: r[_first(r, 2, "SAVINGS")].__setitem__(11, "500000"), "account_rules"),
    # a card without a limit
    ("account", lambda r: r[_first(r, 2, "CREDIT_CARD")].__setitem__(11, ""), "account_rules"),
    # an account id that does not embed its owner
    ("account", lambda r: r[1].__setitem__(1, "USR-000099"), "account_rules"),
    # an account that loses its only PRIMARY holder
    ("account_holder", lambda r: r.pop(_first(r, 2, "PRIMARY")), "holders"),
    # a holder who joins before the account exists
    ("account_holder", lambda r: r[1].__setitem__(3, "2000-01-01"), "holders"),
    # a hole in an account's monthly balances
    ("account_balance_monthly", lambda r: r.pop(3), "balance_months"),
    # a balance chain that does not continue
    ("account_balance_monthly", lambda r: r[3].__setitem__(2, "123456789"), "balance_months"),
    # a rule retired before it started
    ("category_rule", lambda r: r[1].__setitem__(11, "2000-01-01T00:00:00Z"), "effective_dates"),
    # a category that ends before it starts
    ("category", lambda r: r[1].__setitem__(5, "2000-01-01"), "effective_dates"),
])
def test_structural_rules_are_enforced(tmp_path, table, mutate, check):
    d = _fresh(tmp_path)
    assert _by_name(validate_dataset(d))[check].status == "PASS"
    _corrupt(d / "inputs" / f"{table}.csv", mutate)
    assert _by_name(validate_dataset(d))[check].status == "FAIL"


def test_artifact_set_and_exports_are_cross_checked(tmp_path):
    d = _fresh(tmp_path)
    export_json(d)
    export_sql(d)
    prov = write_provenance(d)
    assert prov["synthetic_only"] is True and prov["exports"]["seed.sql"]["sha256"]
    assert _by_name(validate_dataset(d))["artifacts"].status == "PASS"
    # an extra file in the data folders
    (d / "inputs" / "notes.csv").write_text("x\n", encoding="utf-8")
    assert _by_name(validate_dataset(d))["artifacts"].status == "FAIL"
    (d / "inputs" / "notes.csv").unlink()
    # a JSON export that lost a row, and one that no longer matches provenance.json
    j = d / "json" / "txn.json"
    lines = j.read_text(encoding="utf-8").split("\n")
    j.write_text("\n".join(lines[:5] + lines[6:]), encoding="utf-8")
    assert _by_name(validate_dataset(d))["artifacts"].status == "FAIL"
    # a seed.sql whose COPY block was shortened
    d2 = _fresh(tmp_path / "second")
    export_json(d2)
    export_sql(d2)
    write_provenance(d2)
    sql = d2 / "seed.sql"
    text = sql.read_text(encoding="utf-8")
    i = text.index("COPY txn ")
    j2 = text.index("\n", text.index("\n", i) + 1)
    sql.write_text(text[:j2 + 1] + text[text.index("\n", j2 + 1) + 1:], encoding="utf-8")
    assert _by_name(validate_dataset(d2))["artifacts"].status == "FAIL"
