import shutil
import time

import pytest
from sqlalchemy import text

from app.config import settings
from app.jobs.evaluate_job import run_evaluation
from app.jobs.runner import fail_orphans
from tests.api.conftest import TINY, login

pytestmark = pytest.mark.db
V1 = "/api/v1"


def _wait(client, h, job_id):
    for _ in range(120):
        j = client.get(f"{V1}/admin/jobs/{job_id}", headers=h).json()
        if j["status"] in ("SUCCEEDED", "FAILED"):
            return j
        time.sleep(0.5)
    raise AssertionError(f"job {job_id} still {j['status']}")


@pytest.fixture
def adm(client):
    return login(client, "admin@pam.test")


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    shutil.copytree(TINY["dir"], tmp_path / "starter")
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    return tmp_path


def test_reviewer_read_only_and_sees_outcomes(client, api_db):
    with api_db.connect() as c:
        run_evaluation(c)
        c.commit()
    for _ in range(3):                                     # each login is an audit event
        h = login(client, "reviewer@pam.test")
    a = client.get(f"{V1}/review/anomalies", headers=h)
    assert a.status_code == 200 and a.json() and {x["outcome"] for x in a.json()} <= {"CAUGHT", "MISSED"}
    s = client.get(f"{V1}/review/summary", headers=h).json()
    assert s["by_issue"] and all(0 <= b["recall"] <= 1 for b in s["by_issue"])
    caught = client.get(f"{V1}/review/anomalies?outcome=CAUGHT", headers=h).json()
    assert all(x["outcome"] == "CAUGHT" for x in caught)
    assert client.post(f"{V1}/admin/jobs", json={"job_type": "PIPELINE"}, headers=h).status_code == 403
    assert client.get(f"{V1}/review/anomalies", headers=login(client, "analyst@pam.test")).status_code == 403
    audit = client.get(f"{V1}/review/audit?limit=2", headers=h).json()
    nxt = client.get(f"{V1}/review/audit?limit=2&cursor={audit['next_cursor']}", headers=h).json()
    assert audit["items"][0]["id"] > audit["items"][1]["id"] > nxt["items"][0]["id"]


def test_admin_jobs_lifecycle_and_single_flight(client, adm, api_db, data_root):
    r = client.post(f"{V1}/admin/jobs", json={"job_type": "VALIDATE", "params": {"scope": "OUTPUTS"}}, headers=adm)
    assert r.status_code == 202
    j = _wait(client, adm, r.json()["job_id"])
    assert j["status"] == "SUCCEEDED", j
    assert client.get(f"{V1}/admin/validation?scope=OUTPUTS", headers=adm).json()["scope"] == "OUTPUTS"
    with api_db.begin() as c:            # a dataset job "running" elsewhere blocks a second one
        c.execute(text("INSERT INTO job (job_id, job_type, params, status, created_by, created_at) VALUES "
                       "('JOB-999999', 'PIPELINE', '{}', 'RUNNING', 'test', now())"))
    try:
        assert client.post(f"{V1}/admin/jobs", json={"job_type": "PIPELINE"}, headers=adm).status_code == 409
    finally:
        with api_db.connect() as c:
            assert fail_orphans(c) >= 1
            assert c.execute(text("SELECT status FROM job WHERE job_id = 'JOB-999999'")).scalar() == "FAILED"
    assert client.post(f"{V1}/admin/jobs", json={"job_type": "GENERATE_LOAD", "params": {"scale": "full"}},
                       headers=adm).status_code == 422
    assert client.post(f"{V1}/admin/jobs", json={"job_type": "NUKE"}, headers=adm).status_code == 422
    assert client.get(f"{V1}/admin/overview", headers=adm).json()["counts"]["transactions"] > 0


def test_export_job_and_downloads(client, adm, data_root):
    j = _wait(client, adm, client.post(f"{V1}/admin/jobs", json={"job_type": "EXPORT", "params": {"scale": "starter"}},
                                       headers=adm).json()["job_id"])
    assert j["status"] == "SUCCEEDED", j
    m = client.get(f"{V1}/admin/exports/starter", headers=adm).json()
    assert "seed.sql" in m["downloads"] and "inputs/txn.csv" in m["downloads"]
    f = client.get(f"{V1}/admin/exports/starter/files/inputs/txn.csv", headers=adm)
    assert f.status_code == 200 and f.text.startswith("txn_id,")
    assert client.get(f"{V1}/admin/exports/starter/files/json/txn.json", headers=adm).status_code == 200
    for bad in ("..%2F..%2Fbackend%2F.env", "../manifest.json", "inputs/../../starter/manifest.json", "nope.csv"):
        assert client.get(f"{V1}/admin/exports/starter/files/{bad}", headers=adm).status_code in (400, 404), bad
    assert client.get(f"{V1}/admin/exports/..%2F..", headers=adm).status_code == 404


def test_admin_user_management(client, adm):
    me = client.get(f"{V1}/auth/me", headers=adm).json()
    assert client.patch(f"{V1}/admin/users/{me['app_user_id']}", json={"role": "CUSTOMER"},
                        headers=adm).status_code == 409
    assert client.patch(f"{V1}/admin/users/{me['app_user_id']}", json={"disabled": True},
                        headers=adm).status_code == 409
    users = client.get(f"{V1}/admin/users?q=analyst", headers=adm).json()["items"]
    aid = users[0]["app_user_id"]
    assert client.patch(f"{V1}/admin/users/{aid}", json={"role": "CUSTOMER"}, headers=adm).status_code == 422
    assert client.patch(f"{V1}/admin/users/{aid}", json={"profile_user_id": "USR-999999"},
                        headers=adm).status_code == 422
    r = client.patch(f"{V1}/admin/users/{aid}", json={"role": "REVIEWER"}, headers=adm)
    assert r.status_code == 200 and r.json()["role"] == "REVIEWER"
    client.patch(f"{V1}/admin/users/{aid}", json={"role": "ANALYST"}, headers=adm)
    assert client.get(f"{V1}/admin/users?q=%25", headers=adm).json()["items"] == []
