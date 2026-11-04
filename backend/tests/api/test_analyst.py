import pytest
from sqlalchemy import text

from tests.api.conftest import login

pytestmark = pytest.mark.db
V1 = "/api/v1"


def test_customer_forbidden(client):
    h = login(client, "customer@pam.test")
    assert client.get(f"{V1}/analyst/exceptions", headers=h).status_code == 403
    assert client.get(f"{V1}/ops/transactions/TXN-2026-00000001", headers=h).status_code == 403


def test_exception_lifecycle_and_invalid_transition(client, api_db):
    h = login(client, "analyst@pam.test")
    with api_db.connect() as c:          # a fresh UNCATEGORIZED case nobody touched yet
        xid, tid = c.execute(text("SELECT exception_id, entity_id FROM exception_case WHERE exception_type = "
                                  "'UNCATEGORIZED' AND status = 'OPEN' ORDER BY exception_id DESC LIMIT 1")).one()
    page = client.get(f"{V1}/analyst/exceptions?status=OPEN&type=UNCATEGORIZED&limit=2", headers=h).json()
    assert page["items"] and all(i["status"] == "OPEN" and i["descriptor"] for i in page["items"])
    url = f"{V1}/analyst/exceptions/{xid}/transition"
    assert client.post(url, json={"to_status": "IN_REVIEW"}, headers=h).status_code == 200
    assert client.post(url, json={"to_status": "IN_REVIEW"}, headers=h).status_code == 409
    r = client.post(url, json={"to_status": "RESOLVED", "note": "groceries", "category_code": "GROCERIES"}, headers=h)
    assert r.status_code == 200 and r.json()["override_id"].startswith("OVR-")
    trace = client.get(f"{V1}/ops/transactions/{tid}", headers=h).json()
    assert trace["overrides"][0]["category_code"] == "GROCERIES" and "truth" not in trace
    assert trace["current"]["category_code"] == "GROCERIES"
    assert [e["to_status"] for e in trace["exceptions"][0]["events"]] == ["OPEN", "IN_REVIEW", "RESOLVED"]
    assert client.post(url, json={"to_status": "DISMISSED"}, headers=h).status_code == 409    # RESOLVED -> OPEN only
    reviewer = client.get(f"{V1}/ops/transactions/{tid}", headers=login(client, "reviewer@pam.test")).json()
    assert reviewer["truth"]["txn_id"] == tid


def test_exceptions_paging_and_counts(client):
    h = login(client, "analyst@pam.test")
    p1 = client.get(f"{V1}/analyst/exceptions?limit=3", headers=h).json()
    p2 = client.get(f"{V1}/analyst/exceptions?limit=3&cursor={p1['next_cursor']}", headers=h).json()
    ids = [i["exception_id"] for i in p1["items"] + p2["items"]]
    assert ids == sorted(ids) and len(set(ids)) == 6
    counts = client.get(f"{V1}/analyst/exceptions/counts", headers=h).json()
    assert sum(c["n"] for c in counts) >= 6


def test_rule_versioning_and_tester(client):
    h = login(client, "analyst@pam.test")
    new = client.post(f"{V1}/analyst/rules", json={"priority": 1, "category_code": "HEALTH",
                      "pattern": r"\bclinic\b", "direction": "DR", "confidence": 0.7, "note": "clinics"}, headers=h)
    assert new.status_code == 201
    rid = new.json()["rule_id"]
    probe = {"descriptor": "UPI/DR/612345678901/CITY CLINIC/SBIN/q@ybl/x", "channel": "UPI", "amount_paise": -50000,
             "account_type": "SAVINGS"}
    t = client.post(f"{V1}/analyst/rules/test", json=probe, headers=h).json()
    assert t["category_code"] == "HEALTH" and t["rule_id"] == rid and "612345678901" not in t["normalized"]
    v2 = client.post(f"{V1}/analyst/rules/{rid}/versions", json={"priority": 1, "category_code": "HEALTH",
                     "pattern": r"\b(clinic|hospital)\b", "direction": "DR", "confidence": 0.75}, headers=h)
    assert v2.status_code == 201 and v2.json()["version"] == 2
    listed = {r["rule_id"]: r for r in client.get(f"{V1}/analyst/rules", headers=h).json()}
    assert listed[rid]["version"] == 2
    assert client.post(f"{V1}/analyst/rules/{rid}/retire", headers=h).status_code == 200
    assert rid not in {r["rule_id"] for r in client.get(f"{V1}/analyst/rules", headers=h).json()}
    assert client.post(f"{V1}/analyst/rules/test", json=probe, headers=h).json()["rule_id"] != rid
    assert client.post(f"{V1}/analyst/rules/{rid}/versions", json={"priority": 1, "category_code": "HEALTH",
                       "pattern": "x"}, headers=h).status_code == 409


@pytest.mark.parametrize("body", [
    {"priority": 1, "category_code": "HEALTH", "pattern": "("},                # does not compile
    {"priority": 1, "category_code": "HEALTH", "pattern": "(a+)+$"},           # catastrophic backtracking
    {"priority": 1, "category_code": "HEALTH", "pattern": "x" * 201},
    {"priority": 1, "category_code": "HEALTH"},                                # no condition
    {"priority": 1, "category_code": "DINING_OUT", "pattern": "x"},            # retired category
    {"priority": 1, "category_code": "HEALTH", "merchant_id": "MER-9999"},     # unknown merchant
    {"priority": 1, "category_code": "HEALTH", "pattern": "x", "confidence": 1.5},
])
def test_bad_rules_rejected(client, body):
    h = login(client, "analyst@pam.test")
    assert client.post(f"{V1}/analyst/rules", json=body, headers=h).status_code == 422


def test_metrics_and_runs(client, api_db):
    from app.jobs.evaluate_job import run_evaluation
    h = login(client, "analyst@pam.test")
    with api_db.connect() as c:
        run_evaluation(c)
        c.commit()
    m = client.get(f"{V1}/analyst/metrics", headers=h).json()
    assert "categorization" in m and "recurring" in m and m["run_id"].startswith("RUN-")
    assert client.get(f"{V1}/analyst/runs", headers=h).json()[0]["status"] in ("SUCCEEDED", "FAILED")
