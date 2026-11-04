from collections import Counter, defaultdict
from datetime import date

import pytest

from app import ids, schema
from app.datagen.generator import GenParams, generate
from app.schema import account, gt_recurring_truth, gt_txn_label, txn
from app.timeutil import local_date, month_key

P = GenParams(users=24, transactions=9_000)
TX = {c.name: i for i, c in enumerate(txn.columns)}
AC = {c.name: i for i, c in enumerate(account.columns)}
LB = {c.name: i for i, c in enumerate(gt_txn_label.columns)}
RT = {c.name: i for i, c in enumerate(gt_recurring_truth.columns)}


@pytest.fixture(scope="module")
def ds():
    return generate(P)


def test_exact_counts_and_chronological_ids(ds):
    rows = ds.tables["txn"]
    assert len(ds.tables["user_profile"]) == 24 and len(rows) == 9_000
    assert rows[0][TX["txn_id"]] == "TXN-2026-00000001" and rows[-1][TX["txn_id"]] == "TXN-2026-00009000"
    posted = [r[TX["posted_at"]] for r in rows]
    assert posted == sorted(posted)
    assert posted[0].year == 2025          # 1 Jan before 05:30 IST is 31 Dec in UTC, yet the id says 2026 (D11)
    assert {month_key(local_date(t))[:4] for t in posted} == {"2026"}   # nothing outside the IST year (D16)


def test_rows_match_schema_shape_and_pk_order(ds):
    for t in schema.INPUT_TABLES:
        rows = ds.tables[t.name]
        assert rows and all(len(r) == len(t.columns) for r in rows), t.name
        pk = [i for i, c in enumerate(t.columns) if c.primary_key]
        keys = [tuple(r[i] for i in pk) for r in rows]
        assert keys == sorted(keys) and len(set(keys)) == len(keys), t.name
    for name, pattern in [("txn", "txn"), ("budget", "budget")]:
        assert all(ids.ID_PATTERNS[pattern].fullmatch(r[0]) for r in ds.tables[name])


def test_fk_and_owner_consistency(ds):
    acc = {a[AC["account_id"]]: a for a in ds.tables["account"]}
    for r in ds.tables["txn"]:
        a = acc[r[TX["account_id"]]]
        assert r[TX["user_id"]] == a[AC["user_id"]]
        assert r[TX["amount_paise"]] != 0
        d = local_date(r[TX["posted_at"]])
        assert a[AC["opened_on"]] <= d, "activity before the account opened (D02)"
        if a[AC["closed_on"]]:
            assert d <= a[AC["closed_on"]], "activity after closure (D03)"


def test_descriptor_sign_convention(ds):
    for r in ds.tables["txn"]:
        d, amt = r[TX["descriptor"]], r[TX["amount_paise"]]
        if d.startswith(("UPI/DR/", "ATM WDL", "ACH D-", "IMPS/P2A/", "BBPS/", "POS ", "CC BILL")):
            assert amt < 0, d
        if d.startswith(("UPI/CR/", "UPI/REV/", "NEFT CR", "IMPS/CR/", "INT.PD", "PAYMENT RECEIVED")):
            assert amt > 0, d


def test_balances_reconcile_and_savings_never_negative(ds):
    by_acc = defaultdict(list)
    for r in ds.tables["txn"]:
        by_acc[r[TX["account_id"]]].append(r)
    for a in ds.tables["account"]:
        bal = a[AC["opening_balance_paise"]]
        for r in by_acc[a[AC["account_id"]]]:
            bal += r[TX["amount_paise"]]
            if a[AC["account_type"]] == "SAVINGS":
                assert bal >= 0, a[AC["account_id"]]
        if a[AC["status"]] == "CLOSED":
            assert bal == 0
        months = [b for b in ds.tables["account_balance_monthly"] if b[0] == a[AC["account_id"]]]
        assert months[-1][5] == bal and months[0][2] == a[AC["opening_balance_paise"]]
    for b in ds.tables["account_balance_monthly"]:
        assert b[2] + b[3] + b[4] == b[5] and b[3] >= 0 >= b[4]


def test_references_unique_except_transfer_legs_and_reversals(ds):
    by_ref = defaultdict(list)
    for r in ds.tables["txn"]:
        by_ref[r[TX["reference_no"]]].append(r)
    for ref, rows in by_ref.items():
        assert ref and len(rows) <= 2, ref                                  # D10
        if len(rows) == 2:
            assert rows[0][TX["amount_paise"]] == -rows[1][TX["amount_paise"]]


def test_labels_complete_linked_and_truth_month_is_ist(ds):
    labels = {lb[LB["txn_id"]]: lb for lb in ds.truth["txn_label"]}
    assert len(labels) == len(ds.tables["txn"])
    for r in ds.tables["txn"]:
        lb = labels[r[TX["txn_id"]]]
        assert lb[LB["true_local_month"]] == month_key(local_date(r[TX["posted_at"]]))
        link = lb[LB["true_link_txn_id"]]
        if link and lb[LB["true_kind"]] in ("TRANSFER", "REVERSAL"):
            assert labels[link][LB["true_link_txn_id"]] == lb[LB["txn_id"]]   # both legs point at each other
    series = {t[RT["truth_series_id"]] for t in ds.truth["recurring_truth"]}
    used = Counter(lb[LB["true_series_id"]] for lb in labels.values() if lb[LB["true_series_id"]])
    assert set(used) == series and min(used.values()) >= 3


def test_refunds_never_exceed_their_purchase(ds):
    amt = {r[TX["txn_id"]]: r[TX["amount_paise"]] for r in ds.tables["txn"]}
    refunded = defaultdict(int)
    for lb in ds.truth["txn_label"]:
        if lb[LB["true_kind"]] == "REFUND" and lb[LB["true_link_txn_id"]]:
            refunded[lb[LB["true_link_txn_id"]]] += amt[lb[LB["txn_id"]]]
    assert refunded and all(v <= -amt[k] for k, v in refunded.items())   # D17


def test_coverage_of_required_phenomena(ds):
    kinds = Counter(lb[LB["true_kind"]] for lb in ds.truth["txn_label"])
    assert {"EXPENSE", "INCOME", "TRANSFER", "REFUND", "REVERSAL"} <= set(kinds)
    types = {t[RT["series_type"]] for t in ds.truth["recurring_truth"]}
    assert {"SALARY", "RENT", "SUBSCRIPTION", "UTILITY", "INTEREST"} <= types
    swiggy = {r[TX["descriptor"]].split("/")[3] for r in ds.tables["txn"]
              if "SWIG" in r[TX["descriptor"]].upper() and r[TX["descriptor"]].startswith("UPI/")}
    assert len(swiggy) >= 2                                                  # merchant aliases
    lt = {lb[LB["true_category_code"]] for lb in ds.truth["txn_label"]
          if lb[LB["true_merchant_id"]] is None and lb[LB["true_kind"]] == "EXPENSE"
          and lb[LB["true_category_code"]] not in ("CASH_WITHDRAWAL",)}
    assert len(lt) >= 3                                                      # long tail spans categories (D19)
    assert any(lb[LB["true_kind"]] == "REFUND" and lb[LB["true_link_txn_id"]] is None
               for lb in ds.truth["txn_label"])                             # orphan refund (D18)
    statuses = {t[RT["status_at_end"]] for t in ds.truth["recurring_truth"]}
    assert statuses == {"ACTIVE", "ENDED"}
    assert any(a[AC["status"]] == "CLOSED" for a in ds.tables["account"])


def test_card_bills_follow_statements(ds):
    acc = {a[AC["account_id"]]: a for a in ds.tables["account"]}
    for a in acc.values():
        if a[AC["account_type"]] != "CREDIT_CARD":
            continue
        rows = [r for r in ds.tables["txn"] if r[TX["account_id"]] == a[AC["account_id"]]]
        paid = sum(r[TX["amount_paise"]] for r in rows if r[TX["channel"]] == "INTERNAL")
        assert paid >= 0
        if a[AC["opened_on"]] >= date(2026, 1, 1):
            assert a[AC["opening_balance_paise"]] == 0                       # new card: nothing outstanding


def test_seasonal_shopping_peak():
    big = generate(GenParams(users=60, transactions=25_000))
    labels = {lb[0]: lb for lb in big.truth["txn_label"]}
    by_month = Counter(labels[r[0]][LB["true_local_month"]] for r in big.tables["txn"]
                       if labels[r[0]][LB["true_category_code"]] == "SHOPPING")
    assert by_month["2026-10"] + by_month["2026-11"] > 1.3 * (by_month["2026-03"] + by_month["2026-04"])


def test_deterministic():
    a, b = generate(P), generate(P)
    assert a.tables == b.tables and a.truth == b.truth


def test_too_few_transactions_rejected():
    with pytest.raises(ValueError):
        generate(GenParams(users=20, transactions=500))


def test_ground_truth_not_in_inputs():
    for t in schema.INPUT_TABLES:
        assert not any(c.name.startswith("true_") for c in t.columns)
