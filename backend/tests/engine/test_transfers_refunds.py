from datetime import UTC, date, datetime, timedelta

from app.engine.refunds import link_refunds
from app.engine.transfers import match_transfers
from app.engine.types import Category, Enriched, Txn, kind_for

CATS = {c.code: c for c in [
    Category("SELF_TRANSFER", "TRANSFER", date(2020, 1, 1)), Category("CC_BILL_PAYMENT", "TRANSFER", date(2020, 1, 1)),
    Category("UNCATEGORIZED", "UNKNOWN", date(2020, 1, 1)), Category("OTHER_INCOME", "INCOME", date(2020, 1, 1)),
    Category("SHOPPING", "EXPENSE", date(2020, 1, 1)), Category("FOOD_DINING", "EXPENSE", date(2020, 1, 1))]}
T0 = datetime(2026, 3, 30, 10, tzinfo=UTC)
_n = iter(range(1, 10_000))


def e(acc, amt, cat="UNCATEGORIZED", dt=T0, acc_type="SAVINGS", merchant=None, ref=None, desc="x", user="USR-000001"):
    t = Txn(f"TXN-2026-{next(_n):08d}", user, acc, acc_type, dt, amt, "UPI", desc, None, ref)
    x = Enriched(t, desc.lower(), dt.date(), dt.strftime("%Y-%m"), merchant_id=merchant, category_code=cat)
    x.kind = kind_for(CATS[cat].kind, amt)
    return x


def test_pairs_delayed_cross_month_transfer_and_not_other_users():
    d = e("ACC-USR-000001-01", -500000)
    c = e("ACC-USR-000001-02", 500000, cat="OTHER_INCOME", dt=T0 + timedelta(days=2, hours=20))
    stranger = e("ACC-USR-000002-01", 500000, cat="OTHER_INCOME", user="USR-000002")
    assert match_transfers([d, c, stranger], CATS) == 1
    assert d.kind == c.kind == "TRANSFER" and d.link_txn_id == c.txn.txn_id and stranger.kind == "INCOME"
    assert d.category_code == "SELF_TRANSFER" and c.local_month == "2026-04"     # credit lands next month


def test_card_payment_and_window_and_same_account():
    d = e("ACC-USR-000001-01", -900000, cat="CC_BILL_PAYMENT")
    c = e("ACC-USR-000001-03", 900000, cat="CC_BILL_PAYMENT", acc_type="CREDIT_CARD", dt=T0 + timedelta(hours=3))
    late = e("ACC-USR-000001-02", 700000, dt=T0 + timedelta(days=4))
    d2 = e("ACC-USR-000001-01", -700000)
    same = e("ACC-USR-000001-01", 700000)
    assert match_transfers([d, c, late, d2, same], CATS) == 1
    assert d.category_code == c.category_code == "CC_BILL_PAYMENT"
    assert d2.kind == "UNKNOWN"


def test_two_identical_transfers_pair_one_to_one():
    d1, d2 = e("ACC-USR-000001-01", -250000), e("ACC-USR-000001-01", -250000, dt=T0 + timedelta(hours=6))
    c1 = e("ACC-USR-000001-02", 250000, dt=T0 + timedelta(minutes=5))
    c2 = e("ACC-USR-000001-02", 250000, dt=T0 + timedelta(hours=6, minutes=2))
    assert match_transfers([d1, d2, c1, c2], CATS) == 2
    assert d1.link_txn_id == c1.txn.txn_id and d2.link_txn_id == c2.txn.txn_id


def test_credit_before_debit_within_a_day():
    c = e("ACC-USR-000001-02", 120000, dt=T0 - timedelta(hours=20))
    d = e("ACC-USR-000001-01", -120000)
    too_early = e("ACC-USR-000001-02", 130000, dt=T0 - timedelta(days=2))
    d2 = e("ACC-USR-000001-01", -130000)
    assert match_transfers([c, d, too_early, d2], CATS) == 1 and c.link_txn_id == d.txn.txn_id


def test_locked_items_untouched():
    d, c = e("ACC-USR-000001-01", -100), e("ACC-USR-000001-02", 100)
    d.locked = True
    assert match_transfers([d, c], CATS) == 0


def test_partial_refunds_link_and_net():
    buy = e("ACC-USR-000001-01", -200000, cat="SHOPPING", merchant="MER-0014")
    r1 = e("ACC-USR-000001-01", 50000, cat="SHOPPING", merchant="MER-0014", dt=T0 + timedelta(days=3))
    r2 = e("ACC-USR-000001-01", 150000, cat="SHOPPING", merchant="MER-0014", dt=T0 + timedelta(days=40))
    too_much = e("ACC-USR-000001-01", 10000, cat="SHOPPING", merchant="MER-0014", dt=T0 + timedelta(days=41))
    out = link_refunds([buy, r1, r2, too_much], CATS)
    assert r1.link_txn_id == r2.link_txn_id == buy.txn.txn_id and r1.kind == "REFUND"
    assert too_much.kind == "REFUND" and too_much.link_txn_id is None and too_much.decision == "REFUND_ORPHAN"
    assert out == {"reversals": 0, "linked": 2, "orphans": 1}


def test_refund_prefers_exact_amount_over_latest_purchase():
    old = e("ACC-USR-000001-01", -50000, cat="FOOD_DINING", merchant="MER-0001")
    newer = e("ACC-USR-000001-01", -70000, cat="FOOD_DINING", merchant="MER-0001", dt=T0 + timedelta(days=5))
    refund = e("ACC-USR-000001-01", 50000, cat="FOOD_DINING", merchant="MER-0001", dt=T0 + timedelta(days=6))
    link_refunds([old, newer, refund], CATS)
    assert refund.link_txn_id == old.txn.txn_id


def test_refund_category_follows_original_and_reversal_by_rrn():
    buy = e("ACC-USR-000001-01", -30000, cat="FOOD_DINING", merchant="MER-0013")
    cr = e("ACC-USR-000001-01", 30000, cat="SHOPPING", merchant="MER-0013", dt=T0 + timedelta(days=1))
    fail = e("ACC-USR-000001-01", -45000, cat="SHOPPING", merchant="MER-0014", ref="612345678901")
    rev = e("ACC-USR-000001-01", 45000, cat="UNCATEGORIZED", ref="612345678901", dt=T0 + timedelta(hours=5),
            desc="upi rev")
    link_refunds([buy, cr, fail, rev], CATS)
    assert cr.category_code == "FOOD_DINING" and cr.link_txn_id == buy.txn.txn_id
    assert fail.kind == rev.kind == "REVERSAL" and rev.category_code == "SHOPPING"


def test_orphan_refund_non_expense_becomes_uncategorized():
    r = e("ACC-USR-000001-01", 20000, cat="OTHER_INCOME", desc="neft cr refund of deposit")
    assert link_refunds([r], CATS)["orphans"] == 1
    assert r.kind == "REFUND" and r.category_code == "UNCATEGORIZED"
