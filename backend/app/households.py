"""Real households (people who sign in and enter their own data) next to the synthetic challenge households.

Both use the brief's id formats. Real ones are numbered from USR-500001, so a dataset reload can keep them and
evaluation can leave them out (no ground truth). Their transactions are numbered TXN-<year>-9xxxxxxx.
"""
from sqlalchemy import Connection, text

# ponytail: id-range split; add a source column if synthetic scales ever pass 500k households
REAL_FROM = "USR-500001"
REAL_TXN_BASE = 90_000_000


def is_real(user_id: str | None) -> bool:
    return bool(user_id) and user_id >= REAL_FROM


def create_household(conn: Connection, display_name: str) -> str:
    """A new, empty household. Caller holds the app_user advisory lock and commits."""
    last = conn.execute(text("SELECT max(user_id) FROM user_profile WHERE user_id >= :r"), {"r": REAL_FROM}).scalar()
    user_id = f"USR-{(int(last[4:]) + 1) if last else int(REAL_FROM[4:]):06d}"
    conn.execute(text(
        "INSERT INTO user_profile (user_id, display_name, city, state, city_tier, persona, income_band, "
        "monthly_income_paise, household_size, timezone, created_on) VALUES (:u, :n, 'Not set', 'NA', 2, "
        "'SALARIED', 'MID', 0, 1, 'Asia/Kolkata', (now() AT TIME ZONE 'Asia/Kolkata')::date)"),
        {"u": user_id, "n": display_name[:80] or "My household"})
    return user_id


def next_txn_id(conn: Connection, year: int) -> str:
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('real_txn_id'))"))
    last = conn.execute(text("SELECT max(txn_id) FROM txn WHERE txn_id LIKE :p"), {"p": f"TXN-{year}-9%"}).scalar()
    n = int(last.rsplit("-", 1)[1]) + 1 if last else REAL_TXN_BASE + 1
    return f"TXN-{year}-{n:08d}"


def delete_household(conn: Connection, user_id: str) -> None:
    """Remove a real household and everything it entered (accounts, entries, budgets, goals ...). Caller commits.
    The audit log keeps its rows (who did what is not user data). Refuses synthetic households."""
    if not is_real(user_id):
        raise ValueError("only real households can be deleted")
    p = {"u": user_id}
    for sql in (
        "DELETE FROM category_override WHERE txn_id IN (SELECT txn_id FROM txn WHERE user_id = :u)",
        "DELETE FROM txn_note WHERE user_id = :u",
        "DELETE FROM exception_event WHERE exception_id IN (SELECT exception_id FROM exception_case WHERE user_id = :u)",
        "DELETE FROM exception_case WHERE user_id = :u",
        "UPDATE txn_enrichment SET link_txn_id = NULL WHERE user_id = :u",
        "DELETE FROM txn_enrichment WHERE user_id = :u",
        "DELETE FROM txn WHERE user_id = :u",
        "DELETE FROM recurring_series_event WHERE series_id IN (SELECT series_id FROM recurring_series WHERE user_id = :u)",
        "DELETE FROM recurring_series_state WHERE series_id IN (SELECT series_id FROM recurring_series WHERE user_id = :u)",
        "DELETE FROM recurring_series WHERE user_id = :u",
        "DELETE FROM insight WHERE user_id = :u",
        "DELETE FROM budget_resolution WHERE budget_id LIKE 'BUD-' || :u || '-%'",
        "DELETE FROM budget WHERE user_id = :u",
        "DELETE FROM account_balance_monthly WHERE account_id IN (SELECT account_id FROM account WHERE user_id = :u)",
        "DELETE FROM account_event WHERE account_id IN (SELECT account_id FROM account WHERE user_id = :u)",
        "DELETE FROM account_holder WHERE user_id = :u OR account_id IN (SELECT account_id FROM account WHERE user_id = :u)",
        "DELETE FROM account_label WHERE account_id IN (SELECT account_id FROM account WHERE user_id = :u)",
        "DELETE FROM account_meta WHERE account_id IN (SELECT account_id FROM account WHERE user_id = :u)",
        "DELETE FROM account WHERE user_id = :u",
        "DELETE FROM goal WHERE user_id = :u",
        "DELETE FROM budget_carry WHERE user_id = :u",
        "DELETE FROM household_invite WHERE household_id = :u",
        "DELETE FROM user_profile WHERE user_id = :u",
    ):
        conn.execute(text(sql), p)
