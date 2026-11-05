import pytest
from sqlalchemy import text

from app import security
from tests.api.conftest import DEMO_PASSWORD, login

pytestmark = pytest.mark.db


def test_login_me_and_role_from_db(client, api_db):
    h = login(client, "Analyst@PAM.test ")
    me = client.get("/api/v1/auth/me", headers=h).json()
    assert me["role"] == "ANALYST" and me["email"] == "analyst@pam.test"
    cust = client.get("/api/v1/auth/me", headers=login(client, "customer@pam.test")).json()
    assert cust["profile_user_id"] == "USR-000001"
    with api_db.begin() as c:                                  # demotion applies to the existing token at once
        c.execute(text("UPDATE app_user SET role = 'CUSTOMER' WHERE email = 'analyst@pam.test'"))
    try:
        assert client.get("/api/v1/auth/me", headers=h).json()["role"] == "CUSTOMER"
    finally:
        with api_db.begin() as c:
            c.execute(text("UPDATE app_user SET role = 'ANALYST' WHERE email = 'analyst@pam.test'"))


def test_wrong_password_is_problem_json_and_vague(client):
    a = client.post("/api/v1/auth/login", json={"email": "admin@pam.test", "password": "nope"})
    b = client.post("/api/v1/auth/login", json={"email": "ghost@pam.test", "password": "nope"})
    assert a.status_code == b.status_code == 401
    assert a.headers["content-type"] == "application/problem+json"
    assert a.json()["detail"] == b.json()["detail"] and a.json()["request_id"]


def test_lockout_after_repeated_failures(client):
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"email": "reviewer@pam.test", "password": "bad"})
    r = client.post("/api/v1/auth/login", json={"email": "reviewer@pam.test", "password": DEMO_PASSWORD})
    assert r.status_code == 429


def test_validation_errors_list_fields(client):
    r = client.post("/api/v1/auth/login", json={"email": "x"})
    assert r.status_code == 422 and {e["field"] for e in r.json()["errors"]} >= {"email", "password"}


@pytest.mark.parametrize("header", [None, "Bearer", "Basic abc", "Bearer not-a-jwt"])
def test_missing_or_bad_tokens(client, header):
    r = client.get("/api/v1/auth/me", headers={"Authorization": header} if header else {})
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"


def test_disabled_and_deleted_logins(client, api_db):
    h = login(client, "reviewer@pam.test")
    with api_db.begin() as c:
        c.execute(text("UPDATE app_user SET disabled = true WHERE email = 'reviewer@pam.test'"))
    try:
        assert client.get("/api/v1/auth/me", headers=h).status_code == 403
        r = client.post("/api/v1/auth/login", json={"email": "reviewer@pam.test", "password": DEMO_PASSWORD})
        assert r.status_code == 403
    finally:
        with api_db.begin() as c:
            c.execute(text("UPDATE app_user SET disabled = false WHERE email = 'reviewer@pam.test'"))
    ghost = security.issue_local_token("APP-999999", "ADMIN")       # a role claim in the token grants nothing
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {ghost}"}).status_code == 401


def test_google_signup_link_and_conflicts(client, google, api_db):
    r = client.post("/api/v1/auth/firebase", json={"id_token": google("uid-new-1", "New.Person@gmail.test")})
    u = r.json()["user"]
    assert r.status_code == 200 and u["role"] == "CUSTOMER" and u["profile_user_id"] not in (None, "USR-000001")
    again = client.post("/api/v1/auth/firebase", json={"id_token": google("uid-new-1", "new.person@gmail.test")}).json()
    assert again["user"]["app_user_id"] == u["app_user_id"]
    boss = client.post("/api/v1/auth/firebase", json={"id_token": google("uid-boss", "boss@corp.test")}).json()
    assert boss["user"]["role"] == "ADMIN" and boss["user"]["profile_user_id"] is None
    linked = client.post("/api/v1/auth/firebase", json={"id_token": google("uid-demo", "customer@pam.test")}).json()
    assert linked["user"]["profile_user_id"] == "USR-000001"           # existing login gets linked, not duplicated
    clash = client.post("/api/v1/auth/firebase", json={"id_token": google("uid-other", "customer@pam.test")})
    assert clash.status_code == 409
    unverified = client.post("/api/v1/auth/firebase",
                             json={"id_token": google("uid-x", "x@gmail.test", verified=False)})
    assert unverified.status_code == 403
    with api_db.begin() as c:
        n = c.execute(text("SELECT count(*) FROM app_user WHERE email = 'customer@pam.test'")).scalar()
        logins = c.execute(text("SELECT count(*) FROM audit_event WHERE action = 'LOGIN'")).scalar()
    assert n == 1 and logins >= 4


def test_unhandled_error_is_generic_500(client, monkeypatch):
    from app.api import auth

    def boom(*a, **k):
        raise ValueError("secret internals")
    monkeypatch.setattr(auth, "verify_password", boom)
    r = client.post("/api/v1/auth/login", json={"email": "admin@pam.test", "password": "x"})
    assert r.status_code == 500 and "secret" not in r.text and r.json()["request_id"]


def test_register_gives_own_empty_household_and_is_limited(client, api_db, google):
    from app.api import auth
    auth.SIGNUPS.clear()
    r = client.post("/api/v1/auth/register", json={"email": "New.Owner@Mail.test", "password": "long-enough-pass", "name": "Asha"})
    assert r.status_code == 201, r.text
    u = r.json()["user"]
    assert u["role"] == "CUSTOMER" and u["profile_user_id"] >= "USR-500001" and u["email"] == "new.owner@mail.test"
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/v1/me/transactions", headers=h).json()["items"] == []
    assert client.post("/api/v1/auth/login", json={"email": "new.owner@mail.test", "password": "long-enough-pass"}).status_code == 200
    dup = client.post("/api/v1/auth/register", json={"email": "new.owner@mail.test", "password": "long-enough-pass"})
    assert dup.status_code == 409
    for bad in ({"email": "nope", "password": "long-enough-pass"}, {"email": "a@b.test", "password": "short"}):
        assert client.post("/api/v1/auth/register", json=bad).status_code == 422
    # a later Google sign-in with the same email takes the account over and kills the unverified password (A48)
    g = client.post("/api/v1/auth/firebase", json={"id_token": google("uid-owner", "new.owner@mail.test")})
    assert g.status_code == 200 and g.json()["user"]["app_user_id"] == u["app_user_id"]
    assert client.post("/api/v1/auth/login", json={"email": "new.owner@mail.test", "password": "long-enough-pass"}).status_code == 401
    auth.SIGNUPS.clear()
    codes = [client.post("/api/v1/auth/register", json={"email": f"x{i}@mail.test", "password": "long-enough-pass"}).status_code for i in range(6)]
    assert codes == [201] * 5 + [429]
    auth.SIGNUPS.clear()


def test_session_length_depends_on_client(client):
    body = {"email": "analyst@pam.test", "password": DEMO_PASSWORD}
    assert client.post("/api/v1/auth/login", json=body).json()["expires_in"] == 7 * 24 * 3600
    mobile = client.post("/api/v1/auth/login", json=body, headers={"X-PAM-Client": "mobile"}).json()
    assert mobile["expires_in"] == 30 * 24 * 3600
