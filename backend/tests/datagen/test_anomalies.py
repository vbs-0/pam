from collections import defaultdict
from datetime import timedelta

import pytest

from app.datagen.anomalies import RATES
from app.datagen.catalog import CATEGORIES
from app.datagen.generator import GenParams, generate
from app.timeutil import IST

N = 40


@pytest.fixture(scope="module")
def ds():
    return generate(GenParams(users=N, transactions=16_000))


def _anoms(ds, issue):
    return [a for a in ds.truth["anomaly"] if a[1] == issue]


def test_every_issue_type_present_with_planned_counts(ds):
    got = defaultdict(int)
    for a in ds.truth["anomaly"]:
        got[a[1]] += 1
    assert set(got) == {"TRANSFER_DOUBLE_COUNT", "REFUND_AS_EXPENSE", "RECURRING_SKIP", "RECURRING_NOT_SKIP",
                        "TZ_BOUNDARY", "BUDGET_CATEGORY_MISMATCH"}
    for issue in ("TRANSFER_DOUBLE_COUNT", "REFUND_AS_EXPENSE", "RECURRING_SKIP", "RECURRING_NOT_SKIP", "TZ_BOUNDARY"):
        assert got[issue] == round(RATES[issue] * N), issue
    assert got["BUDGET_CATEGORY_MISMATCH"] == round(RATES["BUDGET_REMAP"] * N) + round(RATES["BUDGET_UNKNOWN"] * N)
    ids = [a[0] for a in ds.truth["anomaly"]]
    assert ids == [f"ANM-{i:06d}" for i in range(1, len(ids) + 1)]


def test_transfer_double_count_shape(ds):
    tx = {r[0]: r for r in ds.tables["txn"]}
    acc = {a[0]: a for a in ds.tables["account"]}
    for a in _anoms(ds, "TRANSFER_DOUBLE_COUNT"):
        d, c = tx[a[3]], tx[a[4]]
        assert d[2] == c[2] and d[1] != c[1] and d[4] == -c[4] and d[4] < 0
        assert "SELF" not in d[7].upper() and d[6] == "UPI" and a[5] == "EXCLUDE_BOTH_LEGS"
        assert timedelta(days=1) <= c[3] - d[3] <= timedelta(days=3)
        if acc[c[1]][2] == "SAVINGS":
            assert d[8] == acc[c[1]][5] and c[8] == acc[d[1]][5]   # each leg names the user's own other VPA


def test_refund_as_expense_has_no_keyword(ds):
    tx = {r[0]: r for r in ds.tables["txn"]}
    labels = {lb[0]: lb for lb in ds.truth["txn_label"]}
    for a in _anoms(ds, "REFUND_AS_EXPENSE"):
        r, orig = tx[a[3]], tx[a[4]]
        assert r[4] > 0 and orig[4] < 0 and orig[3] < r[3] and r[1] == orig[1]
        assert not any(k in r[7].lower() for k in ("refund", "rev", "rfnd"))
        assert a[5] == "NET_AGAINST:" + labels[orig[0]][2]


def test_skip_really_missing_and_decoy_present(ds):
    dates = defaultdict(list)
    tx = {r[0]: r for r in ds.tables["txn"]}
    for lb in ds.truth["txn_label"]:
        if lb[5]:
            dates[lb[5]].append(tx[lb[0]][3].astimezone(IST).date())
    for a in _anoms(ds, "RECURRING_SKIP"):
        assert a[2] == "SERIES" and a[5] == "MISSED_EVENT"
        assert all(abs((d - a[6]).days) > 10 for d in dates[a[3]])
        assert min(dates[a[3]]) < a[6] < max(dates[a[3]])            # a gap inside the series, not at its edges
    for a in _anoms(ds, "RECURRING_NOT_SKIP"):
        assert any(2 <= (d - a[6]).days <= 4 for d in dates[a[3]])


def test_tz_boundary_utc_month_differs(ds):
    tx = {r[0]: r for r in ds.tables["txn"]}
    for a in _anoms(ds, "TZ_BOUNDARY"):
        ts = tx[a[3]][3]
        local = ts.astimezone(IST)
        assert ts.strftime("%Y-%m") != local.strftime("%Y-%m") and local.day == 1 and local.hour < 6
        assert a[5] == "MONTH:" + local.strftime("%Y-%m")


def test_budget_mismatch_only_where_labelled(ds):
    active = {c.code for c in CATEGORIES if c.effective_to is None}
    bad = {b[0] for b in ds.tables["budget"] if b[4] not in active}
    labelled = {a[3] for a in _anoms(ds, "BUDGET_CATEGORY_MISMATCH")}
    assert bad == labelled and bad
    expected = {a[5].split(":")[0] for a in _anoms(ds, "BUDGET_CATEGORY_MISMATCH")}
    assert expected == {"REMAP_TO", "EXCEPTION"}
    versions = defaultdict(set)
    for b in ds.tables["budget"]:
        versions[b[0]].add(b[4])
    assert all(len(v) == 1 for v in versions.values())                  # all versions share the submitted code


def test_tiny_dataset_still_has_every_issue():
    ds = generate(GenParams(users=6, transactions=2_200))
    assert {a[1] for a in ds.truth["anomaly"]} >= {"TRANSFER_DOUBLE_COUNT", "REFUND_AS_EXPENSE", "TZ_BOUNDARY",
                                                   "BUDGET_CATEGORY_MISMATCH"}
