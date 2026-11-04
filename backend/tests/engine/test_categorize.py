from datetime import UTC, datetime

from app.engine.categorize import Categorizer, Rule
from app.engine.normalize import normalize_descriptor
from app.engine.types import Txn

RULES = [
    Rule("RUL-0001", 1, 5, "SALARY", 0.95, pattern=r"\bsalary\b", direction="CR"),
    Rule("RUL-0002", 1, 10, "GROCERIES", 0.9, merchant_id="MER-0013", pattern=r"amazon fresh"),
    Rule("RUL-0003", 1, 50, "SHOPPING", 0.8, merchant_id="MER-0013"),
    Rule("RUL-0004", 1, 6, "CASH_WITHDRAWAL", 0.95, channel="ATM"),
    Rule("RUL-0005", 1, 90, "GROCERIES", 0.6, pattern=r"\bkirana\b"),
    Rule("RUL-0006", 1, 5, "CC_BILL_PAYMENT", 0.95, pattern=r"payment received", direction="CR",
         account_type="CREDIT_CARD"),
]
CAT = Categorizer(RULES, {"amazon-mrch@apl": "MER-0013"}, {"amazon": "MER-0013", "amazon fresh": "MER-0013",
                                                            "amzn mktp": "MER-0013"})


def t(desc, amt=-10000, channel="UPI", vpa=None, acc_type="SAVINGS"):
    return Txn("TXN-2026-00000001", "USR-000001", "ACC-USR-000001-01", acc_type,
               datetime(2026, 3, 1, tzinfo=UTC), amt, channel, desc, vpa)


def run(desc, **kw):
    return CAT.categorize(t(desc, **kw), normalize_descriptor(desc))


def test_priority_and_refinement():
    m, r = run("UPI/DR/612345678901/AMAZON FRESH/UTIB/x@y/Payment")
    assert m == "MER-0013" and r.category_code == "GROCERIES"
    m, r = run("ECOM AMZN MKTP BENGALURU", channel="CARD_ECOM")
    assert m == "MER-0013" and r.category_code == "SHOPPING"


def test_vpa_beats_alias_and_conditions():
    m, _ = run("UPI/DR/612345678901/SOMETHING/UTIB/amazon-mrch@apl/Payment", vpa="amazon-mrch@apl")
    assert m == "MER-0013"
    assert run("ATM WDL SBI ATM KORAMANGALA 612345", channel="ATM")[1].category_code == "CASH_WITHDRAWAL"
    assert run("NEFT CR-ACME-SALARY", amt=5000000, channel="NEFT")[1].category_code == "SALARY"
    assert run("NEFT DR-ACME-SALARY", amt=-5000, channel="NEFT")[1] is None          # direction CR only
    assert run("PAYMENT RECEIVED - THANK YOU 6123", amt=900, channel="INTERNAL")[1] is None   # savings, not card
    assert run("PAYMENT RECEIVED - THANK YOU 6123", amt=900, channel="INTERNAL",
               acc_type="CREDIT_CARD")[1].category_code == "CC_BILL_PAYMENT"


def test_alias_needs_word_boundaries():
    assert run("UPI/DR/612345678901/AMAZONIA TRADERS/YESB/q1@ybl/NA") == (None, None)


def test_long_tail_and_no_match():
    assert run("UPI/DR/612345678901/NEW BALAJI KIRANA/YESB/q1@ybl/Payment")[1].category_code == "GROCERIES"
    assert run("UPI/DR/612345678901/RAMESH K/SBIN/r@oksbi/Payment") == (None, None)


def test_cache_used():
    CAT.cache_hits = 0
    run("UPI/DR/612345678901/AMAZON FRESH/UTIB/x@y/Payment")
    run("UPI/DR/699999999999/AMAZON FRESH/UTIB/x@y/Payment")   # different RRN, same normalized text (E03)
    assert CAT.cache_hits >= 1
