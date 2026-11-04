import pytest
from sqlalchemy import text

from tests.api.conftest import login

pytestmark = pytest.mark.db
V1 = "/api/v1"


@pytest.fixture
def h(client):
    return login(client, "customer@pam.test")


def test_transactions_keyset_pagination_and_isolation(client, h):
    p1 = client.get(f"{V1}/me/transactions?month=2026-03&limit=10", headers=h).json()
    assert len(p1["items"]) == 10 and p1["next_cursor"]
    p2 = client.get(f"{V1}/me/transactions?month=2026-03&limit=10&cursor={p1['next_cursor']}", headers=h).json()
    assert not {i["txn_id"] for i in p1["items"]} & {i["txn_id"] for i in p2["items"]}
    keys = [(i["local_date"], i["txn_id"]) for i in p1["items"] + p2["items"]]
    assert keys == sorted(keys, reverse=True) and all(k[0].startswith("2026-03") for k in keys)
    accounts = {a["account_id"] for a in client.get(f"{V1}/me/accounts", headers=h).json()}
    assert all(i["account_id"] in accounts for i in p1["items"] + p2["items"])


def test_walk_all_pages_matches_count(client, h, api_db):
    seen, cursor = [], None
    while True:
        url = f"{V1}/me/transactions?month=2026-05&limit=100" + (f"&cursor={cursor}" if cursor else "")
        page = client.get(url, headers=h).json()
        seen += [i["txn_id"] for i in page["items"]]
        if not (cursor := page["next_cursor"]):
            break
    with api_db.connect() as c:
        n = c.execute(text("SELECT count(*) FROM txn_enrichment e JOIN txn t USING (txn_id) WHERE e.run_id = "
                           "(SELECT max(run_id) FROM pipeline_run WHERE status = 'SUCCEEDED') AND e.local_month = "
                           "'2026-05' AND t.account_id IN (SELECT account_id FROM account_holder WHERE "
                           "user_id = 'USR-000001')")).scalar()
    assert len(seen) == len(set(seen)) == n


def test_cannot_read_other_users_txn(client, h, api_db):
    with api_db.connect() as c:
        other = c.execute(text("SELECT txn_id FROM txn WHERE account_id NOT IN "
                               "(SELECT account_id FROM account_holder WHERE user_id = 'USR-000001') LIMIT 1")).scalar()
    assert client.get(f"{V1}/me/transactions/{other}", headers=h).status_code == 404
    assert client.get(f"{V1}/me/transactions/TXN-2026-99999999", headers=h).status_code == 404
    assert client.post(f"{V1}/me/transactions/{other}/category", json={"category_code": "HEALTH"},
                       headers=h).status_code == 404
    assert client.get(f"{V1}/me/accounts?user_id=USR-000002", headers=h).status_code == 404


def test_override_changes_budget_actual_immediately(client, h, api_db):
    tx = client.get(f"{V1}/me/transactions?month=2026-03&kind=EXPENSE&limit=1", headers=h).json()["items"][0]
    before = {x["category_code"]: x["actual_paise"] for x in
              client.get(f"{V1}/me/budgets?month=2026-03", headers=h).json()["lines"]}
    r = client.post(f"{V1}/me/transactions/{tx['txn_id']}/category",
                    json={"category_code": "personal_care", "reason": "test"}, headers=h)
    assert r.status_code == 201 and r.json()["override_id"].startswith("OVR-")
    after = {x["category_code"]: x["actual_paise"] for x in
             client.get(f"{V1}/me/budgets?month=2026-03", headers=h).json()["lines"]}
    assert after["PERSONAL_CARE"] == before.get("PERSONAL_CARE", 0) - tx["amount_paise"]
    assert after.get(tx["category_code"], 0) == before[tx["category_code"]] + tx["amount_paise"]
    detail = client.get(f"{V1}/me/transactions/{tx['txn_id']}", headers=h).json()
    assert detail["overridden"] and detail["overrides"][0]["category_code"] == "PERSONAL_CARE"
    assert detail["category_code"] == "PERSONAL_CARE" and detail["kind"] == "EXPENSE"
    with api_db.connect() as c:
        assert c.execute(text("SELECT count(*) FROM audit_event WHERE action = 'CATEGORY_OVERRIDE' AND entity_id = :t"),
                         {"t": tx["txn_id"]}).scalar() == 1


def test_override_resolves_uncategorized_exception(client, h, api_db):
    with api_db.connect() as c:
        x = c.execute(text("SELECT exception_id, entity_id FROM exception_case WHERE exception_type = 'UNCATEGORIZED' "
                           "AND status = 'OPEN' AND user_id = 'USR-000001' LIMIT 1")).first()
    if x is None:
        pytest.skip("tiny dataset has no uncategorized txn for USR-000001")
    assert client.post(f"{V1}/me/transactions/{x.entity_id}/category", json={"category_code": "SHOPPING"},
                       headers=h).status_code == 201
    with api_db.connect() as c:
        assert c.execute(text("SELECT status FROM exception_case WHERE exception_id = :x"),
                         {"x": x.exception_id}).scalar() == "RESOLVED"
        assert c.execute(text("SELECT to_status FROM exception_event WHERE exception_id = :x ORDER BY seq DESC "
                              "LIMIT 1"), {"x": x.exception_id}).scalar() == "RESOLVED"


def test_invalid_category_rejected(client, h):
    tx = client.get(f"{V1}/me/transactions?month=2026-03&limit=1", headers=h).json()["items"][0]
    for code in ("DINING_OUT", "UNCATEGORIZED", "NOPE"):
        r = client.post(f"{V1}/me/transactions/{tx['txn_id']}/category", json={"category_code": code}, headers=h)
        assert r.status_code == 422, code
    r = client.post(f"{V1}/me/transactions/{tx['txn_id']}/category", json={"category_code": "DINING_OUT"}, headers=h)
    assert "FOOD_DINING" in r.json()["detail"]


def test_summary_recurring_insights_shapes(client, h):
    s = client.get(f"{V1}/me/summary?month=2026-03", headers=h).json()
    assert {"income_paise", "spend_paise", "savings_rate", "top_categories", "over_budget_count"} <= set(s)
    assert s["income_paise"] > 0 and s["spend_paise"] > 0
    assert s["naive_spend_paise"] >= s["spend_paise"] >= 0 and s["transfers_out_paise"] >= 0
    tr = client.get(f"{V1}/me/trend?months=6", headers=h).json()
    assert 1 <= len(tr) <= 6 and [x["month"] for x in tr] == sorted(x["month"] for x in tr)
    rec = client.get(f"{V1}/me/recurring", headers=h).json()
    assert rec and {"series_id", "status", "next_expected", "events"} <= set(rec[0]) and len(rec[0]["events"]) <= 12
    assert isinstance(client.get(f"{V1}/me/insights?month=2026-03", headers=h).json(), list)
    for bad in ("2026-13", "26-1", "2026-3"):
        assert client.get(f"{V1}/me/summary?month={bad}", headers=h).status_code == 422


def test_bad_cursor_limit_and_search(client, h):
    assert client.get(f"{V1}/me/transactions?cursor=bm9wZQ", headers=h).status_code == 400
    assert client.get(f"{V1}/me/transactions?cursor=%%%", headers=h).status_code == 400
    for lim in (0, 101, 10_000):
        assert client.get(f"{V1}/me/transactions?limit={lim}", headers=h).status_code == 422
    assert client.get(f"{V1}/me/transactions?q=%25", headers=h).json()["items"] == []      # '%' matched literally
    assert client.get(f"{V1}/me/transactions?q=___", headers=h).json()["items"] == []


def test_roles_and_admin_support_view(client):
    a = login(client, "analyst@pam.test")
    assert client.get(f"{V1}/me/accounts", headers=a).status_code == 403
    adm = login(client, "admin@pam.test")
    assert client.get(f"{V1}/me/accounts", headers=adm).status_code == 404
    assert client.get(f"{V1}/me/accounts?user_id=USR-000002", headers=adm).json()
    assert client.get(f"{V1}/categories", headers=a).json()


def test_no_run_409(client, h, api_db):
    with api_db.begin() as c:
        c.execute(text("UPDATE pipeline_run SET status = 'FAILED' WHERE status = 'SUCCEEDED'"))
    try:
        r = client.get(f"{V1}/me/summary?month=2026-03", headers=h)
        assert r.status_code == 409 and "pipeline" in r.json()["detail"]
    finally:
        with api_db.begin() as c:
            c.execute(text("UPDATE pipeline_run SET status = 'SUCCEEDED' WHERE error IS NULL"))
