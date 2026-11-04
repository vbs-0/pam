from datetime import date

from app.datagen.calendar import clamp_day, is_bank_working_day, last_working_day, next_working_day
from app.datagen.people import make_users, master_rows


def test_calendar_rules():
    assert not is_bank_working_day(date(2026, 1, 26))      # Republic Day
    assert not is_bank_working_day(date(2026, 3, 14))      # 2nd Saturday
    assert not is_bank_working_day(date(2026, 3, 28))      # 4th Saturday
    assert is_bank_working_day(date(2026, 3, 7))           # 1st Saturday works
    assert not is_bank_working_day(date(2026, 3, 1))       # Sunday
    assert last_working_day(2026, 1) == date(2026, 1, 31)  # 5th Saturday works
    assert last_working_day(2026, 5) == date(2026, 5, 30)  # Sun 31 May closed
    assert next_working_day(date(2026, 8, 15)) == date(2026, 8, 17)  # Independence Day (Sat) -> Mon
    assert clamp_day(2026, 2, 31) == date(2026, 2, 28)


def test_users_deterministic_and_independent_of_count():
    small, big = make_users(10, 20261022), make_users(30, 20261022)
    assert [u.user_id for u in small] == [f"USR-{i:06d}" for i in range(1, 11)]
    key = [(u.persona, u.income_paise, u.city, [a.account_id for a in u.accounts]) for u in small]
    assert key == [(u.persona, u.income_paise, u.city, [a.account_id for a in u.accounts]) for u in big[:10]]


def test_master_rows_integrity():
    users = make_users(200, 20261022)
    rows = master_rows(users)
    accounts = rows["account"]
    assert len(rows["user_profile"]) == 200
    assert all(a[0][4:14] == a[1] for a in accounts)                         # id embeds owner (D01)
    assert all(a[2] == "SAVINGS" for a in accounts if a[0].endswith("-01"))  # primary always savings
    vpas = [a[5] for a in accounts if a[5]]
    assert len(vpas) == len(set(vpas))
    assert all(a[5] is None for a in accounts if a[2] == "CREDIT_CARD")
    holders = rows["account_holder"]
    assert {h[2] for h in holders} == {"PRIMARY", "JOINT"}
    owner = {a[0]: a[1] for a in accounts}
    assert all(h[1] != owner[h[0]] for h in holders if h[2] == "JOINT")      # joint holder is someone else
    closed = [a for a in accounts if a[9] == "CLOSED"]
    assert closed and all(a[8] is not None and a[8] >= a[7] for a in closed)
    assert sum(1 for e in rows["account_event"] if e[2] == "CLOSED") == len(closed)
    assert any(date(2026, 1, 1) < a[7] for a in accounts if a[2] == "CREDIT_CARD")  # card opened in 2026 (D02)
    assert [e[0] for e in rows["account_event"]][:2] == ["AEV-000001", "AEV-000002"]


def test_tiny_population_still_covers_lifecycle_cases():
    users = make_users(12, 20261022)
    rows = master_rows(users)
    if any(a.kind == "SECONDARY" for u in users for a in u.accounts):
        assert any(a[9] == "CLOSED" for a in rows["account"])
