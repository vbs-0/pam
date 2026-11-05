from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.jobs.load import load_dataset, seed_household_logins
from app.jobs.pipeline_job import run_pipeline
from tests.api.conftest import TINY, login

pytestmark = pytest.mark.db
V1 = "/api/v1"
TODAY = date.today()
D = (TODAY - timedelta(days=3)).isoformat()


@pytest.fixture
def me(client, google):
    """A brand-new Google user with an empty household of their own."""
    r = client.post(f"{V1}/auth/firebase", json={"id_token": google(f"uid-{id(client)}", f"u{id(client)}@gmail.test")})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()["user"]["profile_user_id"]


def _acct(client, h, **kw):
    body = {"account_type": "SAVINGS", "opened_on": "2025-01-01"} | kw
    r = client.post(f"{V1}/me/accounts", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["account_id"]


def test_new_user_gets_own_empty_household(client, me):
    h, uid = me
    assert uid >= "USR-500001"
    p = client.get(f"{V1}/me/profile", headers=h).json()
    assert p["user_id"] == uid and p["sample"] is False
    assert client.get(f"{V1}/me/transactions", headers=h).json() == {"items": [], "next_cursor": None}
    s = client.get(f"{V1}/me/summary?month=2026-03", headers=h).json()
    assert s["income_paise"] == s["spend_paise"] == 0 and s["savings_rate"] is None
    assert client.patch(f"{V1}/me/profile", json={"city": "Pune", "state": "MH", "monthly_income_paise": 9_000_000},
                        headers=h).json()["income_band"] == "HIGH"


def test_add_edit_delete_transaction_updates_budget(client, me):
    h, _ = me
    acc = _acct(client, h, bank_code="HDFC", last4="1234", vpa="me.test@okhdfcbank")
    month = D[:7]
    assert client.put(f"{V1}/me/budgets", json={"month": month, "category_code": "FOOD_DINING",
                                                "amount_paise": 500_000}, headers=h).json()["version"] == 1
    r = client.post(f"{V1}/me/transactions", json={"account_id": acc, "date": D, "amount_paise": 45_000,
                                                   "direction": "DR", "description": "  Dinner   with team ",
                                                   "category_code": "FOOD_DINING"}, headers=h)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["processed"] and body["transaction"]["kind"] == "EXPENSE"
    assert body["transaction"]["descriptor"] == "Dinner with team" and body["transaction"]["amount_paise"] == -45_000
    tid = body["txn_id"]
    assert tid.split("-")[2].startswith("9")

    def line():
        lines = client.get(f"{V1}/me/budgets?month={month}", headers=h).json()["lines"]
        return next(x for x in lines if x["category_code"] == "FOOD_DINING")
    assert line()["actual_paise"] == 45_000 and line()["budget_paise"] == 500_000
    again = client.post(f"{V1}/me/transactions", json={"account_id": acc, "date": D, "amount_paise": 45_000,
                                                       "direction": "DR", "description": "dinner with team"},
                        headers=h).json()
    assert again["possible_duplicate_of"] == tid                       # flagged, still saved
    assert client.patch(f"{V1}/me/transactions/{tid}", json={"amount_paise": 60_000}, headers=h).status_code == 200
    client.delete(f"{V1}/me/transactions/{again['txn_id']}", headers=h)
    assert line()["actual_paise"] == 60_000
    assert client.put(f"{V1}/me/budgets", json={"month": month, "category_code": "FOOD_DINING",
                                                "amount_paise": 50_000}, headers=h).json()["version"] == 2
    assert line()["status"] == "OVER"
    assert client.delete(f"{V1}/me/transactions/{tid}", headers=h).status_code == 204
    assert client.get(f"{V1}/me/transactions/{tid}", headers=h).status_code == 404
    assert client.delete(f"{V1}/me/budgets/{month}/FOOD_DINING", headers=h).status_code == 204
    assert all(x["category_code"] != "FOOD_DINING"
               for x in client.get(f"{V1}/me/budgets?month={month}", headers=h).json()["lines"])


def test_transfer_between_own_accounts_is_paired(client, me):
    h, _ = me
    a = _acct(client, h, vpa="mine.a@oksbi")
    b = _acct(client, h, vpa="mine.b@okicici")
    out = client.post(f"{V1}/me/transactions", json={"account_id": a, "date": D, "amount_paise": 1_000_000,
                                                     "direction": "DR", "description": "to savings",
                                                     "counterparty_vpa": "mine.b@okicici"}, headers=h).json()
    inn = client.post(f"{V1}/me/transactions", json={"account_id": b, "date": D, "amount_paise": 1_000_000,
                                                     "direction": "CR", "description": "from salary acct",
                                                     "counterparty_vpa": "mine.a@oksbi"}, headers=h).json()
    o = client.get(f"{V1}/me/transactions/{out['txn_id']}", headers=h).json()
    assert o["kind"] == inn["transaction"]["kind"] == "TRANSFER" and o["link_txn_id"] == inn["txn_id"]
    s = client.get(f"{V1}/me/summary?month={D[:7]}", headers=h).json()
    assert s["spend_paise"] == 0 and s["income_paise"] == 0                 # moving money is not spending


@pytest.mark.parametrize("bad", [
    {"date": (TODAY + timedelta(days=2)).isoformat()},                      # future
    {"date": "2024-12-31"},                                                  # before the account opened
    {"amount_paise": 0}, {"amount_paise": -5}, {"amount_paise": 10**12},
    {"direction": "OUT"}, {"description": "   "}, {"channel": "PAYPAL"},
    {"counterparty_vpa": "not a vpa"}, {"category_code": "UNCATEGORIZED"}, {"category_code": "DINING_OUT"},
])
def test_bad_transactions_rejected(client, me, bad):
    h, _ = me
    acc = _acct(client, h)
    body = {"account_id": acc, "date": D, "amount_paise": 100, "direction": "DR", "description": "x"} | bad
    assert client.post(f"{V1}/me/transactions", json=body, headers=h).status_code == 422


def test_ownership_closed_accounts_and_samples_read_only(client, me, api_db):
    h, _ = me
    sample = login(client, "customer@pam.test")
    assert client.post(f"{V1}/me/accounts", json={"account_type": "SAVINGS"}, headers=sample).status_code == 403
    with api_db.connect() as c:
        other_acc, other_txn = c.execute(text("SELECT account_id, txn_id FROM txn LIMIT 1")).one()
    assert client.post(f"{V1}/me/transactions", json={"account_id": other_acc, "date": D, "amount_paise": 100,
                                                      "direction": "DR", "description": "x"},
                       headers=h).status_code == 404
    assert client.delete(f"{V1}/me/transactions/{other_txn}", headers=h).status_code == 404
    acc = _acct(client, h, vpa="dup.vpa@oksbi")
    assert client.post(f"{V1}/me/accounts", json={"account_type": "SAVINGS", "vpa": "dup.vpa@oksbi"},
                       headers=h).status_code == 409
    assert client.post(f"{V1}/me/accounts", json={"account_type": "SAVINGS", "credit_limit_paise": 100},
                       headers=h).status_code == 422
    assert client.post(f"{V1}/me/accounts/{acc}/close", json={"closed_on": D}, headers=h).status_code == 200
    late = (TODAY - timedelta(days=1)).isoformat()
    assert client.post(f"{V1}/me/transactions", json={"account_id": acc, "date": late, "amount_paise": 100,
                                                      "direction": "DR", "description": "x"},
                       headers=h).status_code == 409
    assert client.put(f"{V1}/me/budgets", json={"month": "2026-03", "category_code": "SALARY", "amount_paise": 1},
                      headers=h).status_code == 422


def test_sample_household_logins(client, api_db, monkeypatch):
    monkeypatch.setenv("HOUSEHOLD_PASSWORD", "password123")
    with api_db.connect() as c:
        made = seed_household_logins(c)
        c.commit()
        assert made >= 3 and seed_household_logins(c) == 0                  # idempotent
    h = login(client, "usr-000002@pam.is-cool.dev", "password123")
    p = client.get(f"{V1}/me/profile", headers=h).json()
    assert p["user_id"] == "USR-000002" and p["sample"] is True
    assert client.get(f"{V1}/me/transactions?limit=1", headers=h).json()["items"]


def test_full_run_and_reload_keep_real_households(client, me, api_db):
    """Last in the file: reloads the dataset, then restores a pipeline run for the tests that follow."""
    h, uid = me
    acc = _acct(client, h)
    tid = client.post(f"{V1}/me/transactions", json={"account_id": acc, "date": D, "amount_paise": 2500,
                                                     "direction": "DR", "description": "chai"},
                      headers=h).json()["txn_id"]
    with api_db.connect() as c:
        run = run_pipeline(c)
        assert c.execute(text("SELECT count(*) FROM txn_enrichment WHERE run_id = :r AND txn_id = :t"),
                         {"r": run, "t": tid}).scalar() == 1
        load_dataset(c, TINY["dir"], "tiny")
        c.commit()
        assert c.execute(text("SELECT count(*) FROM txn WHERE txn_id = :t"), {"t": tid}).scalar() == 1
        assert c.execute(text("SELECT count(*) FROM account WHERE user_id = :u"), {"u": uid}).scalar() == 1
        run_pipeline(c)
    assert client.get(f"{V1}/me/transactions/{tid}", headers=h).json()["descriptor"] == "chai"


def test_upi_app_accounts_and_custom_names(client, me):
    h, _ = me
    phonepe = _acct(client, h, account_type="UPI", bank_code="PHPE", vpa="asha@ybl", opening_balance_paise=250_000)
    custom = _acct(client, h, account_type="UPI", bank_code="OTHR", label="  Slice   Pay ")
    bank = _acct(client, h, bank_code="OTHR", label="Federal Bank", last4="4321")
    rows = {a["account_id"]: a for a in client.get(f"{V1}/me/accounts", headers=h).json()}
    assert rows[phonepe]["display_name"] == "PhonePe UPI" and rows[phonepe]["balance_paise"] == 250_000
    assert rows[custom]["display_name"] == "Slice Pay" and rows[custom]["label"] == "Slice Pay"
    assert rows[bank]["display_name"] == "Federal Bank savings ··4321"
    # an entry on the UPI app is filed and counted like any other
    r = client.post(f"{V1}/me/transactions", json={"account_id": phonepe, "date": D, "amount_paise": 12_000, "direction": "DR",
                                                   "description": "Chai at stall", "category_code": "FOOD_DINING"}, headers=h)
    assert r.status_code == 201 and r.json()["processed"]
    # rejections: custom app without a name, UPI app as a bank, UPI app as card, credit limit on UPI, odd characters
    bad = [
        {"account_type": "UPI", "bank_code": "OTHR"},
        {"account_type": "SAVINGS", "bank_code": "PHPE"},
        {"account_type": "CREDIT_CARD", "bank_code": "GPAY"},
        {"account_type": "UPI", "bank_code": "PTYM", "credit_limit_paise": 100_000},
        {"account_type": "UPI", "bank_code": "OTHR", "label": "<script>"},
        {"account_type": "UPI", "bank_code": "HDFC"},
    ]
    for body in bad:
        assert client.post(f"{V1}/me/accounts", json=body | {"opened_on": "2025-01-01"}, headers=h).status_code == 422, body
    assert client.post(f"{V1}/me/accounts", json={"account_type": "UPI", "bank_code": "PHPE", "vpa": "asha@ybl"},
                       headers=h).status_code == 409           # the same UPI ID cannot be linked twice
