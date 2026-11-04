from datetime import UTC, date, datetime, timedelta

from app.engine.recurring import detect_recurring
from app.engine.types import Enriched, Txn

END = date(2026, 12, 31)
_n = iter(range(1, 100_000))


def occ(day: date, amt: int, cat="SUBSCRIPTIONS", merchant="MER-0051", vpa=None, kind=None, channel="UPI",
        account="ACC-USR-000001-01"):
    dt = datetime(day.year, day.month, day.day, 6, tzinfo=UTC)
    t = Txn(f"TXN-2026-{next(_n):08d}", "USR-000001", account, "SAVINGS", dt, amt, channel, "x", vpa)
    return Enriched(t, "x", day, day.strftime("%Y-%m"), merchant_id=merchant, category_code=cat,
                    kind=kind or ("EXPENSE" if amt < 0 else "INCOME"))


def monthly(day=5, months=range(1, 13), amt=-49900, **kw):
    return [occ(date(2026, m, day), amt, **kw) for m in months]


def test_detects_monthly_active_series():
    s = detect_recurring(monthly(), END)
    assert len(s) == 1 and s[0].cadence == "MONTHLY" and s[0].status == "ACTIVE"
    assert s[0].series_type == "SUBSCRIPTION" and s[0].median_gap_days == 31
    assert s[0].next_expected == date(2027, 1, 5)  # last 5 Dec + round(median gap 31)


def test_true_skip_emits_missed_and_resumed():
    items = [x for x in monthly() if x.local_date.month != 6]
    ev = [e for e in detect_recurring(items, END)[0].events if e[0] in ("MISSED", "RESUMED")]
    assert ev[0][0] == "MISSED" and abs((ev[0][1] - date(2026, 6, 5)).days) <= 7 and ev[1][0] == "RESUMED"


def test_double_skip_two_missed():
    items = [x for x in monthly() if x.local_date.month not in (6, 7)]
    ev = [e for e in detect_recurring(items, END)[0].events if e[0] == "MISSED"]
    assert len(ev) == 2 and abs((ev[1][1] - date(2026, 7, 5)).days) <= 7


def test_shift_and_month_end_clamp_are_not_skips():
    items = monthly(day=28)
    items[4] = occ(date(2026, 5, 28) + timedelta(days=4), -49900)        # retry 4 days late
    clamp = [occ(date(2026, m, 31 if m in (1, 3, 5, 7, 8, 10, 12) else (28 if m == 2 else 30)), -49900,
                 merchant="MER-0052") for m in range(1, 13)]
    for s in detect_recurring(items + clamp, END):
        assert not any(e[0] == "MISSED" for e in s.events)


def test_price_change_allowed_and_logged():
    items = monthly(months=range(1, 7)) + monthly(months=range(7, 13), amt=-64900)
    s = detect_recurring(items, END)[0]
    assert [e[0] for e in s.events].count("AMOUNT_CHANGED") == 1 and s.typical_amount_paise == 64900


def test_cancelled_series_ends():
    s = detect_recurring(monthly(months=range(1, 8)), END)[0]
    assert s.status == "ENDED" and s.next_expected is None


def test_tail_gap_is_missed_not_ended():
    s = detect_recurring(monthly(months=range(1, 12)), END)[0]          # last seen 5 Nov, 56 days before end
    assert s.status == "MISSED" and s.next_expected == date(2026, 12, 6)


def test_two_occurrences_not_series():
    assert detect_recurring(monthly(months=range(1, 3)), END) == []


def test_discretionary_noise_rejected():
    items = [occ(date(2026, 1, 1) + timedelta(days=3 * i), -(20000 + 7000 * (i % 5)), cat="FOOD_DINING",
                 merchant="MER-0001") for i in range(100)]
    assert detect_recurring(items, END) == []


def test_uncategorized_p2p_monthly_becomes_rent():
    items = monthly(day=3, amt=-1800000, cat="UNCATEGORIZED", merchant=None, vpa="landlord.000001@okaxis",
                    kind="UNKNOWN")
    s = detect_recurring(items, END)[0]
    assert s.series_type == "RENT" and all(x.category_code == "RENT" and x.decision == "RECUR_RENT" for x in items)


def test_small_p2p_is_not_rent():
    items = monthly(day=3, amt=-200000, cat="UNCATEGORIZED", merchant=None, vpa="friend@okaxis", kind="UNKNOWN")
    s = detect_recurring(items, END)[0]
    assert s.series_type == "OTHER" and all(x.category_code == "UNCATEGORIZED" for x in items)


def test_quarterly_interest_with_varying_amounts():
    items = [occ(date(2026, m, 28 if m == 2 else 30), amt, cat="INTEREST", merchant=None, kind="INCOME")
             for m, amt in zip([3, 6, 9, 12], [24267, 49643, 94699, 128919], strict=True)]   # 2-4x jumps
    s = detect_recurring(items, END)
    assert s and s[0].cadence == "QUARTERLY" and s[0].series_type == "INTEREST"
    assert not any(e[0] == "AMOUNT_CHANGED" for e in s[0].events)


def test_series_on_closed_account_ends():
    acc = "ACC-USR-000001-02"
    items = [occ(date(2026, m, 30 if m != 3 else 31), 9000, cat="INTEREST", merchant=None, kind="INCOME",
                 account=acc) for m in (3, 6, 9)]
    s = detect_recurring(items, END, closed={acc: date(2026, 10, 14)})[0]
    assert s.status == "ENDED" and s.next_expected is None and s.events[-1] == ("ENDED", date(2026, 10, 14),
                                                                                 {"reason": "account closed"})


def test_same_merchant_two_series():
    broadband = monthly(day=12, amt=-79900, cat="UTILITIES", merchant="MER-0034", channel="BBPS")
    prepaid = [occ(date(2026, 1, 3) + timedelta(days=28 * i), -34900, cat="UTILITIES", merchant="MER-0034")
               for i in range(13)]
    s = detect_recurring(broadband + prepaid, END)
    assert len(s) == 2 and sorted(x.median_gap_days for x in s) == [28, 31]
    assert all(len(x.member_txn_ids) in (12, 13) for x in s)
