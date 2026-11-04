from datetime import UTC, date, datetime

import pytest

from app import ids, timeutil
from app.money import fmt_inr


def test_id_formats():
    assert ids.user_id(1) == "USR-000001"
    assert ids.account_id("USR-000001", 1) == "ACC-USR-000001-01"
    assert ids.txn_id(2026, 1) == "TXN-2026-00000001"
    assert ids.budget_id("USR-000001", "2026-01", "FOOD_DINING") == "BUD-USR-000001-2026-01-FOOD_DINING"
    assert ids.series_id(1) == "REC-000001"
    assert ids.seq("EXC", 42) == "EXC-000042" and ids.seq_number("EXC-000042") == 42
    assert ids.ID_PATTERNS["account"].fullmatch("ACC-USR-000001-01")
    assert not ids.ID_PATTERNS["txn"].fullmatch("TXN-2026-1")


def test_local_date_crosses_utc_boundary():
    ts = datetime(2026, 1, 31, 18, 45, tzinfo=UTC)  # 00:15 IST on 1 Feb
    assert timeutil.local_date(ts) == date(2026, 2, 1)
    assert timeutil.month_key(timeutil.local_date(ts)) == "2026-02"
    assert timeutil.local_date(datetime(2025, 12, 31, 18, 40, tzinfo=UTC)) == date(2026, 1, 1)


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        timeutil.local_date(datetime(2026, 1, 1))


def test_ist_roundtrip_and_iso():
    utc = timeutil.ist_to_utc(datetime(2026, 2, 1, 0, 15))
    assert timeutil.iso_z(utc) == "2026-01-31T18:45:00Z"
    assert timeutil.parse_z("2026-01-31T18:45:00Z") == utc
    assert timeutil.utc_to_ist_naive(utc) == datetime(2026, 2, 1, 0, 15)
    # fast offset path agrees with zoneinfo for the whole year
    for m in range(1, 13):
        d = datetime(2026, m, 1, 0, 1)
        assert timeutil.ist_to_utc(d) == d.replace(tzinfo=timeutil.IST).astimezone(UTC)


def test_month_helpers():
    assert timeutil.month_end("2026-02") == date(2026, 2, 28)
    assert timeutil.add_months("2026-12", 1) == "2027-01"
    assert timeutil.add_months("2026-01", -1) == "2025-12"
    assert timeutil.months(2026)[0] == "2026-01" and len(timeutil.months(2026)) == 12


@pytest.mark.parametrize("paise,text", [
    (0, "₹0.00"), (99, "₹0.99"), (100000, "₹1,000.00"), (12345678, "₹1,23,456.78"),
    (100000000, "₹10,00,000.00"), (1000000000, "₹1,00,00,000.00"), (-50000, "-₹500.00")])
def test_fmt_inr_indian_grouping(paise, text):
    assert fmt_inr(paise) == text
