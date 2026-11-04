from app.engine.normalize import normalize_descriptor, strip_variable


def test_upi_descriptor():
    s = "UPI/DR/612345678901/SWIGGY/YESB/swiggy-mrch@ybl/Payment"
    assert normalize_descriptor(s) == "upi dr swiggy yesb swiggy mrch@ybl payment"


def test_neft_salary_strips_ifsc_and_keeps_words():
    s = "NEFT CR-HDFC0000123-ACME TECHNOLOGIES PVT LTD-SALARY JAN 2026"
    assert normalize_descriptor(s) == "neft cr acme technologies pvt ltd salary jan 2026"
    assert strip_variable(normalize_descriptor(s)) == "neft cr acme technologies pvt ltd salary"


def test_card_mask_removed():
    assert normalize_descriptor("POS 412345XXXXXX1234 DMART AVENUE BENGALURU") == "pos dmart avenue bengaluru"


def test_month_words_only_whole_tokens():
    assert strip_variable("payment to mayur stores mar") == "payment to mayur stores"


def test_interest_descriptor_keeps_int_pd():
    assert normalize_descriptor("INT.PD:01-01-2026 TO 31-03-2026").startswith("int.pd ")


def test_rrn_only_difference_normalizes_equal():
    a = normalize_descriptor("UPI/DR/612345678901/ZOMATO/HDFC/zomato-mrch@axl/Payment")
    b = normalize_descriptor("UPI/DR/699999999999/ZOMATO/HDFC/zomato-mrch@axl/Payment")
    assert a == b
