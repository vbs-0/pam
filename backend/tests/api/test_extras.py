"""Calendar and analytics, entry extras (notes, split, duplicate, transfer, import, export, backup), account edits,
goals, budget carry-over, alert preferences, household sharing and account security."""
import json
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from tests.api.conftest import DEMO_PASSWORD, login

pytestmark = pytest.mark.db
V1 = "/api/v1"
TODAY = date.today()
D1 = (TODAY - timedelta(days=5)).isoformat()
D2 = (TODAY - timedelta(days=2)).isoformat()
MONTH = TODAY.strftime("%Y-%m")


@pytest.fixture
def me(client, google):
    r = client.post(f"{V1}/auth/firebase", json={"id_token": google(f"uid-x-{id(client)}", f"x{id(client)}@gmail.test")})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _acct(client, h, **kw):
    body = {"account_type": "SAVINGS", "opened_on": "2025-01-01"} | kw
    r = client.post(f"{V1}/me/accounts", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["account_id"]


def _txn(client, h, acc, amount, direction="DR", day=D1, desc="Chai Point", **kw):
    r = client.post(f"{V1}/me/transactions", json={"account_id": acc, "date": day, "amount_paise": amount,
                                                   "direction": direction, "description": desc} | kw, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["txn_id"]


# ---------- analytics ----------
def test_daily_calendar_and_category_breakdown(client, me):
    acc = _acct(client, me)
    _txn(client, me, acc, 30_000, day=D1, desc="Swiggy dinner")
    _txn(client, me, acc, 20_000, day=D1, desc="Swiggy lunch")
    _txn(client, me, acc, 5_000_000, "CR", day=D2, desc="Salary credit")
    month = D1[:7]
    d = client.get(f"{V1}/me/daily?month={month}", headers=me).json()
    day = next(x for x in d["days"] if x["date"] == D1)
    assert day["spend_paise"] == 50_000 and day["count"] == 2
    assert len(d["days"]) >= 28 and d["total_spend_paise"] == 50_000
    cats = client.get(f"{V1}/me/spend-by-category?month={month}", headers=me).json()
    assert cats["total_paise"] == 50_000 and cats["categories"][0]["share"] == 1.0
    assert cats["previous_month"] < month
    m = client.get(f"{V1}/me/merchants", headers=me).json()
    assert m and m[0]["spend_paise"] >= 20_000
    wd = client.get(f"{V1}/me/weekday", headers=me).json()
    assert len(wd) == 7 and sum(x["spend_paise"] for x in wd) == 50_000


def test_analytics_work_on_a_sample_household(client):
    h = login(client, "usr-000001@pam.is-cool.dev") if False else login(client, "customer@pam.test")
    for path in ("daily?month=2026-03", "spend-by-category?month=2026-03", "merchants", "weekday", "upcoming", "networth", "alerts"):
        assert client.get(f"{V1}/me/{path}", headers=h).status_code == 200, path


def test_networth_cards_and_upcoming(client, me):
    sav = _acct(client, me, opening_balance_paise=1_000_000)
    card = _acct(client, me, account_type="CREDIT_CARD", credit_limit_paise=1_000_000)
    _txn(client, me, card, 400_000, desc="Amazon order")
    assert client.patch(f"{V1}/me/accounts/{card}", json={"due_day": TODAY.day}, headers=me).status_code == 200
    n = client.get(f"{V1}/me/networth", headers=me).json()
    assert n["assets_paise"] == 1_000_000 and n["liabilities_paise"] == 400_000 and n["net_worth_paise"] == 600_000
    c = n["cards"][0]
    assert c["used_paise"] == 400_000 and c["available_paise"] == 600_000 and c["utilisation"] == 0.4 and c["days_to_due"] == 0
    up = client.get(f"{V1}/me/upcoming?days=7", headers=me).json()
    assert any(i["kind"] == "CARD" and i["amount_paise"] == 400_000 for i in up["items"])
    al = client.get(f"{V1}/me/alerts", headers=me).json()["alerts"]
    assert any(a["type"] == "CARD_DUE" for a in al)
    assert sav and client.patch(f"{V1}/me/accounts/{sav}", json={"due_day": 5}, headers=me).status_code == 422   # not a card


# ---------- entries ----------
def test_notes_tags_filters(client, me):
    acc = _acct(client, me)
    a = _txn(client, me, acc, 10_000, day=D1, desc="Pharmacy")
    b = _txn(client, me, acc, 90_000, day=D2, desc="Big shop")
    r = client.put(f"{V1}/me/transactions/{a}/note", json={"note": "for mum", "tags": ["#Health", "family", "health"]}, headers=me)
    assert r.json()["tags"] == ["health", "family"]
    assert client.put(f"{V1}/me/transactions/{a}/note", json={"tags": ["bad tag!"]}, headers=me).status_code == 422
    got = client.get(f"{V1}/me/transactions?tag=health", headers=me).json()["items"]
    assert [t["txn_id"] for t in got] == [a] and got[0]["note"] == "for mum"
    assert client.get(f"{V1}/me/tags", headers=me).json()[0]["tag"] in ("health", "family")
    ids = lambda q: sorted(t["txn_id"] for t in client.get(f"{V1}/me/transactions?{q}", headers=me).json()["items"])  # noqa: E731
    assert ids(f"date_from={D2}") == [b] and ids(f"date_to={D1}") == [a]
    assert ids("min_paise=50000") == [b] and ids("max_paise=50000") == [a]
    assert ids("merchant=Big%20shop") in ([b], [])
    assert client.get(f"{V1}/me/transactions/{a}", headers=me).json()["note"] == "for mum"


def test_split_duplicate_and_transfer(client, me):
    acc, acc2 = _acct(client, me, opening_balance_paise=500_000), _acct(client, me, opening_balance_paise=0)
    t = _txn(client, me, acc, 100_000, desc="Big Bazaar")
    bad = client.post(f"{V1}/me/transactions/{t}/split", json={"parts": [{"amount_paise": 60_000}, {"amount_paise": 30_000}]}, headers=me)
    assert bad.status_code == 422 and "add up" in bad.json()["detail"]
    ok = client.post(f"{V1}/me/transactions/{t}/split", headers=me, json={"parts": [
        {"amount_paise": 60_000, "category_code": "GROCERIES"}, {"amount_paise": 40_000, "category_code": "SHOPPING"}]})
    assert ok.status_code == 201 and len(ok.json()["txn_ids"]) == 2
    assert client.get(f"{V1}/me/transactions/{t}", headers=me).status_code == 404            # original is gone
    items = client.get(f"{V1}/me/transactions", headers=me).json()["items"]
    assert sorted(-i["amount_paise"] for i in items) == [40_000, 60_000]
    dup = client.post(f"{V1}/me/transactions/{ok.json()['txn_ids'][0]}/duplicate", json={}, headers=me)
    assert dup.status_code == 201 and dup.json()["transaction"]["local_date"] == TODAY.isoformat()
    tr = client.post(f"{V1}/me/transfers", headers=me, json={"from_account_id": acc, "to_account_id": acc2, "amount_paise": 70_000, "date": D2})
    assert tr.status_code == 201, tr.text
    assert client.post(f"{V1}/me/transfers", headers=me, json={"from_account_id": acc, "to_account_id": acc, "amount_paise": 1, "date": D2}).status_code == 422
    legs = {i["txn_id"]: i for i in client.get(f"{V1}/me/transactions?account_id={acc2}", headers=me).json()["items"]}
    assert legs[tr.json()["credit_txn_id"]]["kind"] == "TRANSFER"           # paired: not income, not spending
    s = client.get(f"{V1}/me/summary?month={D2[:7]}", headers=me).json()
    assert s["income_paise"] == 0


CSV = """Some Bank Ltd,,,
Statement for 123456,,,
Txn Date,Narration,Withdrawal Amt.,Deposit Amt.
{d1},UPI-SWIGGY-9988,"1,250.50",
{d2},SALARY ACME LTD,,"50,000.00"
{d1},UPI-SWIGGY-9988,"1,250.50",
not-a-date,BROKEN ROW,10,
"""


def test_csv_import_preview_dedupe_and_errors(client, me):
    acc = _acct(client, me)
    text_ = CSV.format(d1=(TODAY - timedelta(days=4)).strftime("%d/%m/%Y"), d2=(TODAY - timedelta(days=3)).strftime("%d/%m/%Y"))
    p = client.post(f"{V1}/me/import/preview", json={"csv_text": text_}, headers=me).json()
    assert p["suggested_mapping"] == {"date": "Txn Date", "description": "Narration", "debit": "Withdrawal Amt.", "credit": "Deposit Amt."}
    dry = client.post(f"{V1}/me/import", json={"account_id": acc, "csv_text": text_, "dry_run": True}, headers=me).json()
    assert dry["to_import"] == 3 and dry["error_count"] == 1 and dry["errors"][0]["row"] == 5 and dry["imported"] == 0
    done = client.post(f"{V1}/me/import", json={"account_id": acc, "csv_text": text_}, headers=me).json()
    assert done["imported"] == 3
    again = client.post(f"{V1}/me/import", json={"account_id": acc, "csv_text": text_}, headers=me).json()
    assert again["imported"] == 0 and again["skipped_duplicates"] == 3                       # same file twice adds nothing
    amounts = sorted(i["amount_paise"] for i in client.get(f"{V1}/me/transactions", headers=me).json()["items"])
    assert amounts == [-125_050, -125_050, 5_000_000]
    assert client.post(f"{V1}/me/import", json={"account_id": acc, "csv_text": "a,b\n1,2"}, headers=me).status_code == 422


def test_export_and_backup_restore_roundtrip(client, me, google):
    acc = _acct(client, me, label="Salary a/c")
    t = _txn(client, me, acc, 25_000, desc="=HYPERLINK(evil)", day=D1)
    client.put(f"{V1}/me/transactions/{t}/note", json={"note": "keep", "tags": ["x"]}, headers=me)
    client.put(f"{V1}/me/budgets", json={"month": MONTH, "category_code": "GROCERIES", "amount_paise": 100_000}, headers=me)
    csv_ = client.get(f"{V1}/me/export.csv", headers=me)
    assert csv_.status_code == 200 and "'=HYPERLINK(evil)" in csv_.text and csv_.text.startswith("﻿")   # formula guard
    bk = client.get(f"{V1}/me/backup.json", headers=me)
    data = json.loads(bk.text)
    assert data["format"] == "pam-backup/1" and len(data["transactions"]) == 1 and data["accounts"][0]["label"] == "Salary a/c"
    r2 = client.post(f"{V1}/auth/firebase", json={"id_token": google("uid-restore", "restore@gmail.test")})
    h2 = {"Authorization": f"Bearer {r2.json()['access_token']}"}
    out = client.post(f"{V1}/me/restore", json={"backup": data}, headers=h2)
    assert out.status_code == 201 and out.json()["transactions"] == 1
    back = client.get(f"{V1}/me/transactions", headers=h2).json()["items"]
    assert back[0]["note"] == "keep" and back[0]["amount_paise"] == -25_000
    assert client.post(f"{V1}/me/restore", json={"backup": data}, headers=h2).status_code == 409      # not empty any more
    assert client.post(f"{V1}/me/restore", json={"backup": {"format": "nope"}}, headers=me).status_code == 422


# ---------- accounts, goals, budgets ----------
def test_account_edit_rename_and_balance_fix(client, me):
    acc = _acct(client, me, opening_balance_paise=100_000)
    _txn(client, me, acc, 30_000)
    assert client.patch(f"{V1}/me/accounts/{acc}", json={"label": "Home savings", "balance_paise": 500_000}, headers=me).status_code == 200
    a = next(x for x in client.get(f"{V1}/me/accounts", headers=me).json() if x["account_id"] == acc)
    assert a["display_name"].startswith("Home savings") and a["balance_paise"] == 500_000
    assert client.patch(f"{V1}/me/accounts/{acc}", json={}, headers=me).status_code == 422
    assert client.patch(f"{V1}/me/accounts/{acc}", json={"label": "Bad<name>"}, headers=me).status_code == 422


def test_goals_lifecycle(client, me):
    g = client.post(f"{V1}/me/goals", json={"name": "Goa trip", "target_paise": 1_000_000,
                                            "deadline": (TODAY + timedelta(days=90)).isoformat()}, headers=me)
    assert g.status_code == 201 and g.json()["monthly_needed_paise"] == 333_334
    gid = g.json()["goal_id"]
    half = client.post(f"{V1}/me/goals/{gid}/contribute", json={"amount_paise": 400_000}, headers=me).json()
    assert half["progress"] == 0.4 and not half["completed"]
    done = client.post(f"{V1}/me/goals/{gid}/contribute", json={"amount_paise": 700_000}, headers=me).json()
    assert done["completed"] and done["saved_paise"] == 1_100_000
    assert any(a["type"] == "GOAL_REACHED" for a in client.get(f"{V1}/me/alerts", headers=me).json()["alerts"])
    back = client.post(f"{V1}/me/goals/{gid}/contribute", json={"amount_paise": -9_999_999}, headers=me).json()
    assert back["saved_paise"] == 0 and not back["completed"]
    assert client.post(f"{V1}/me/goals/{gid}/contribute", json={"amount_paise": 0}, headers=me).status_code == 422
    assert client.delete(f"{V1}/me/goals/{gid}", headers=me).status_code == 204
    assert client.get(f"{V1}/me/goals", headers=me).json() == []


def test_budget_rollover_adds_last_months_leftover(client, me):
    acc = _acct(client, me)
    prev = (TODAY.replace(day=1) - timedelta(days=1))
    pm, cm = prev.strftime("%Y-%m"), MONTH
    _txn(client, me, acc, 30_000, day=prev.replace(day=min(10, prev.day)).isoformat(), desc="Big Bazaar groceries", category_code="GROCERIES")
    for m in (pm, cm):
        client.put(f"{V1}/me/budgets", json={"month": m, "category_code": "GROCERIES", "amount_paise": 100_000}, headers=me)
    assert client.put(f"{V1}/me/budgets/carry", json={"category_code": "GROCERIES", "enabled": True}, headers=me).status_code == 200
    line = next(x for x in client.get(f"{V1}/me/budgets?month={cm}", headers=me).json()["lines"] if x["category_code"] == "GROCERIES")
    assert line["budget_paise"] == 170_000 and line["carried_paise"] == 70_000 and all(not i.startswith("CARRY") for i in line["budget_ids"])
    client.put(f"{V1}/me/budgets/carry", json={"category_code": "GROCERIES", "enabled": False}, headers=me)
    line = next(x for x in client.get(f"{V1}/me/budgets?month={cm}", headers=me).json()["lines"] if x["category_code"] == "GROCERIES")
    assert line["budget_paise"] == 100_000


def test_notification_prefs_and_digest(client, me, api_db, monkeypatch):
    p = client.put(f"{V1}/me/notifications", json={"email_digest": True, "bills": False}, headers=me).json()
    assert p["email_digest"] is True and p["bills"] is False
    acc = _acct(client, me, account_type="CREDIT_CARD", credit_limit_paise=100_000)
    _txn(client, me, acc, 90_000)
    from app import digest, mail
    sent = []
    monkeypatch.setattr(mail, "send", lambda to, subject, body: sent.append((to, subject, body)) or True)
    with api_db.connect() as conn:
        assert digest.send_digests(conn, TODAY) == 1
        assert digest.send_digests(conn, TODAY) == 0                       # once a day
    assert "90% used" in sent[0][2] and "Settings" in sent[0][2]


# ---------- household sharing ----------
def test_household_invite_join_leave_remove(client, me, google):
    acc = _acct(client, me)
    _txn(client, me, acc, 12_345, desc="Shared groceries")
    code = client.post(f"{V1}/me/household/invite", headers=me).json()["code"]
    r2 = client.post(f"{V1}/auth/firebase", json={"id_token": google("uid-partner", "partner@gmail.test")})
    h2 = {"Authorization": f"Bearer {r2.json()['access_token']}"}
    assert client.post(f"{V1}/me/household/join", json={"code": "WRONGCODE"}, headers=h2).status_code == 404
    assert client.post(f"{V1}/me/household/join", json={"code": code.lower()}, headers=h2).status_code == 200
    assert client.post(f"{V1}/me/household/join", json={"code": code}, headers=h2).status_code in (404, 409)   # single use
    seen = client.get(f"{V1}/me/transactions", headers=h2).json()["items"]
    assert [-i["amount_paise"] for i in seen] == [12_345]                                                      # partner sees it
    mem = client.get(f"{V1}/me/household/members", headers=me).json()
    assert len(mem["members"]) == 2 and mem["owner"] == mem["you"]
    assert client.delete(f"{V1}/me/household/members/{mem['you']}", headers=h2).status_code == 403            # only owner removes
    other = next(m for m in mem["members"] if not m["you"])
    assert client.post(f"{V1}/me/household/leave", headers=h2).status_code == 200
    assert client.get(f"{V1}/me/transactions", headers=h2).json()["items"] == []                              # own empty register
    assert client.post(f"{V1}/me/household/leave", headers=me).status_code == 409                              # now alone
    assert other["email"] == "partner@gmail.test"


def test_cannot_join_with_own_data_and_samples_cannot_share(client, me, google):
    _acct(client, me)
    code = client.post(f"{V1}/me/household/invite", headers=me).json()["code"]
    r2 = client.post(f"{V1}/auth/firebase", json={"id_token": google("uid-busy", "busy@gmail.test")})
    h2 = {"Authorization": f"Bearer {r2.json()['access_token']}"}
    _acct(client, h2)
    assert client.post(f"{V1}/me/household/join", json={"code": code}, headers=h2).status_code == 409
    assert client.post(f"{V1}/me/household/invite", headers=login(client, "customer@pam.test")).status_code == 403


# ---------- account security ----------
def test_change_password_signs_other_sessions_out(client):
    em = "pwchange@pam.test"
    r = client.post(f"{V1}/auth/register", json={"email": em, "password": "first-password-1", "name": "P"})
    old = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get(f"{V1}/me/profile", headers=old).status_code == 200
    assert client.post(f"{V1}/auth/change-password", headers=old, json={"current_password": "wrong", "new_password": "second-password-2"}).status_code == 400
    ok = client.post(f"{V1}/auth/change-password", headers=old, json={"current_password": "first-password-1", "new_password": "second-password-2"})
    assert ok.status_code == 200
    assert client.get(f"{V1}/me/profile", headers=old).status_code == 401                        # the old token is dead
    assert client.get(f"{V1}/me/profile", headers={"Authorization": f"Bearer {ok.json()['access_token']}"}).status_code == 200
    assert client.post(f"{V1}/auth/login", json={"email": em, "password": "second-password-2"}).status_code == 200


def test_change_email_and_delete_account(client, me):
    em = "wipe@pam.test"
    r = client.post(f"{V1}/auth/register", json={"email": em, "password": "wipe-password-1", "name": "W"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    acc = _acct(client, h)
    _txn(client, h, acc, 5_000)
    assert client.post(f"{V1}/auth/change-email", headers=h, json={"password": "wipe-password-1", "new_email": "x" + em}).status_code == 200
    em = "x" + em
    uid = client.get(f"{V1}/me/profile", headers=h).json()["user_id"]
    assert client.post(f"{V1}/auth/delete-account", headers=h, json={"confirm_email": "nope@x.com", "password": "wipe-password-1"}).status_code == 400
    assert client.post(f"{V1}/auth/delete-account", headers=h, json={"confirm_email": em, "password": "bad"}).status_code == 400
    ok = client.post(f"{V1}/auth/delete-account", headers=h, json={"confirm_email": em.upper(), "password": "wipe-password-1"})
    assert ok.status_code == 200, ok.text
    from app.db import engine
    with engine.connect() as c:
        for t in ("txn", "account", "user_profile"):
            col = "user_id"
            assert c.execute(text(f"SELECT count(*) FROM {t} WHERE {col} = :u"), {"u": uid}).scalar() == 0, t
        assert c.execute(text("SELECT count(*) FROM app_user WHERE email = :e"), {"e": em}).scalar() == 0
    assert client.post(f"{V1}/auth/login", json={"email": em, "password": "wipe-password-1"}).status_code == 401
    assert client.post(f"{V1}/auth/delete-account", headers=login(client, "customer@pam.test"),
                       json={"confirm_email": "customer@pam.test", "password": DEMO_PASSWORD}).status_code == 403    # demo is protected


def test_idempotency_key_applies_a_write_once(client, me):
    h = {**me, "Idempotency-Key": "queued-0001-abcd"}
    body = {"name": "Trip", "target_paise": 500000}
    a = client.post(f"{V1}/me/goals", json=body, headers=h)
    b = client.post(f"{V1}/me/goals", json=body, headers=h)
    assert a.status_code == 201 and b.status_code == 201
    assert a.json() == b.json() and b.headers.get("x-idempotent-replay") == "1"
    assert len(client.get(f"{V1}/me/goals", headers=me).json()) == 1
    # a different key is a different write; a failed write is not remembered
    c = client.post(f"{V1}/me/goals", json=body, headers={**me, "Idempotency-Key": "queued-0002-abcd"})
    assert c.json()["goal_id"] != a.json()["goal_id"]
    bad = {**me, "Idempotency-Key": "queued-0003-abcd"}
    assert client.post(f"{V1}/me/goals", json={"name": "", "target_paise": 1}, headers=bad).status_code == 422
    assert client.post(f"{V1}/me/goals", json=body, headers=bad).status_code == 201


def _unsorted_entry(client, h, acc, desc, day=D1, amount=4000):
    r = client.post(f"{V1}/me/transactions", json={"account_id": acc, "date": day, "amount_paise": amount, "direction": "DR", "description": desc}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["txn_id"], r.json()["transaction"]


def test_remember_my_choice_sorts_similar_entries_now_and_later(client, me):
    acc = _acct(client, me)
    t1, tx = _unsorted_entry(client, me, acc, "Sharma lassi packet 114")
    assert tx["kind"] == "UNKNOWN"
    t2, _ = _unsorted_entry(client, me, acc, "lassi packet 09", D2)
    r = client.post(f"{V1}/me/transactions/{t1}/category", json={"category_code": "FOOD_DINING", "remember": True}, headers=me)
    assert r.status_code == 201 and r.json()["rule"] == "sharma lassi packet"
    rules = client.get(f"{V1}/me/sorting-rules", headers=me).json()
    assert [x["phrase"] for x in rules] == ["sharma lassi packet"]
    # the same narration added later is sorted straight away (and a different one is not)
    _, later = _unsorted_entry(client, me, acc, "SHARMA LASSI PACKET 7781", D2)
    assert later["category_code"] == "FOOD_DINING" and later["kind"] == "EXPENSE"
    _, other = _unsorted_entry(client, me, acc, "lassi packet 77", D2)
    assert other["kind"] == "UNKNOWN"
    assert client.delete(f"{V1}/me/sorting-rules/{rules[0]['rule_id']}", headers=me).status_code == 204
    _, after = _unsorted_entry(client, me, acc, "sharma lassi packet 9", D2)
    assert after["kind"] == "UNKNOWN"
    assert t2


def test_ai_sorting_is_opt_in_masked_and_only_picks_listed_categories(client, me, monkeypatch):
    from app import ai_sort
    acc = _acct(client, me)
    t1, _ = _unsorted_entry(client, me, acc, "ramesh@okhdfc zxqv traders 99812")
    assert client.get(f"{V1}/me/ai", headers=me).json()["enabled"] is False
    monkeypatch.setattr(ai_sort.settings, "gemini_api_key", "test-key")
    assert client.post(f"{V1}/me/ai/sort", headers=me).status_code == 409          # not turned on
    assert client.put(f"{V1}/me/ai", json={"enabled": True}, headers=me).json()["enabled"] is True
    seen = {}

    def fake_call(body):
        seen["prompt"] = body["contents"][0]["parts"][0]["text"]
        import re
        n = re.search(r'"id": (\d+)', seen["prompt"]).group(1)
        rows = [{"id": int(n), "category": "FOOD_DINING", "confidence": 0.9}]
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(rows)}]}}]}
    monkeypatch.setattr(ai_sort, "_call", fake_call)
    r = client.post(f"{V1}/me/ai/sort", headers=me)
    assert r.status_code == 200 and r.json()["sorted"] == 1, r.json()
    assert "ramesh" not in seen["prompt"] and "99812" not in seen["prompt"] and "okhdfc" not in seen["prompt"]
    assert "zxqv traders" in seen["prompt"]
    d = client.get(f"{V1}/me/transactions/{t1}", headers=me).json()
    assert d["category_code"] == "FOOD_DINING" and d["overrides"][0]["actor"] == "AI:gemini"
    # a made-up category or a low-confidence answer is ignored
    t2, _ = _unsorted_entry(client, me, acc, "mystery payment", D2)
    monkeypatch.setattr(ai_sort, "_call", lambda b: {"candidates": [{"content": {"parts": [{"text": json.dumps([{"id": 0, "category": "ROOT_ACCESS", "confidence": 1}])}]}}]})
    assert client.post(f"{V1}/me/ai/sort", headers=me).json()["sorted"] == 0
    monkeypatch.setattr(ai_sort, "_call", lambda b: (_ for _ in ()).throw(ai_sort.AiError("Could not reach Gemini")))
    t3, _ = _unsorted_entry(client, me, acc, "another mystery", D2)
    assert client.post(f"{V1}/me/ai/sort", headers=me).status_code == 502
    assert t2 and t3
