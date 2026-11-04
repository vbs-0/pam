import time

import jwt
import pytest
from sqlalchemy import text

from app import security
from app.config import settings
from tests.api.conftest import DEMO_PASSWORD, login

pytestmark = pytest.mark.db


def test_login_me_and_role_from_db(client, api_db):
    h = login(client, "Analyst@PAM.test ")
    me = client.get("/auth/me", headers=h).json()
    assert me["role"] == "ANALYST" and me["email"] == "analyst@pam.test"
    cust = client.get("/auth/me", headers=login(client, "customer@pam.test")).json()
    assert cust["profile_user_id"] == "USR-000001"
    with api_db.begin() as c:                                  # demotion applies to the existing token at once
        c.execute(text("UPDATE app_user SET role = 'CUSTOMER' WHERE email = 'analyst@pam.test'"))
    try:
        assert client.get("/auth/me", headers=h).json()["role"] == "CUSTOMER"
    finally:
        with api_db.begin() as c:
            c.execute(text("UPDATE app_user SET role = 'ANALYST' WHERE email = 'analyst@pam.test'"))


def test_wrong_password_is_problem_json_and_vague(client):
    a = client.post("/auth/login", json={"email": "admin@pam.test", "password": "nope"})
    b = client.post("/auth/login", json={"email": "ghost@pam.test", "password": "nope"})
    assert a.status_code == b.status_code == 401
    assert a.headers["content-type"] == "application/problem+json"
    assert a.json()["detail"] == b.json()["detail"] and a.json()["request_id"]


def test_lockout_after_repeated_failures(client):
    for _ in range(5):
        client.post("/auth/login", json={"email": "reviewer@pam.test", "password": "bad"})
    r = client.post("/auth/login", json={"email": "reviewer@pam.test", "password": DEMO_PASSWORD})
    assert r.status_code == 429


def test_validation_errors_list_fields(client):
    r = client.post("/auth/login", json={"email": "x"})
    assert r.status_code == 422 and {e["field"] for e in r.json()["errors"]} >= {"email", "password"}


@pytest.mark.parametrize("header", [None, "Bearer", "Basic abc", "Bearer not-a-jwt"])
def test_missing_or_bad_tokens(client, header):
    r = client.get("/auth/me", headers={"Authorization": header} if header else {})
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"


def test_disabled_and_deleted_logins(client, api_db):
    h = login(client, "reviewer@pam.test")
    with api_db.begin() as c:
        c.execute(text("UPDATE app_user SET disabled = true WHERE email = 'reviewer@pam.test'"))
    try:
        assert client.get("/auth/me", headers=h).status_code == 403
        r = client.post("/auth/login", json={"email": "reviewer@pam.test", "password": DEMO_PASSWORD})
        assert r.status_code == 403
    finally:
        with api_db.begin() as c:
            c.execute(text("UPDATE app_user SET disabled = false WHERE email = 'reviewer@pam.test'"))
    ghost = security.issue_local_token("APP-999999", "ADMIN")       # a role claim in the token grants nothing
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {ghost}"}).status_code == 401


@pytest.fixture
def google(monkeypatch):
    """Signatures are covered in test_security; here we test account linking, so verification is a plain decode."""
    from cryptography.hazmat.primitives.asymmetric import rsa

    from app.api import auth
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(settings, "admin_emails", "boss@corp.test")
    monkeypatch.setattr(auth, "verify_firebase_token",
                        lambda t: jwt.decode(t, key.public_key(), algorithms=["RS256"], audience="demo-proj"))

    def tok(uid, email, verified=True):
        now = int(time.time())
        return jwt.encode({"sub": uid, "email": email, "email_verified": verified, "aud": "demo-proj", "iat": now,
                           "exp": now + 600}, key, algorithm="RS256")
    return tok


def test_google_signup_link_and_conflicts(client, google, api_db):
    r = client.post("/auth/firebase", json={"id_token": google("uid-new-1", "New.Person@gmail.test")})
    u = r.json()["user"]
    assert r.status_code == 200 and u["role"] == "CUSTOMER" and u["profile_user_id"] not in (None, "USR-000001")
    again = client.post("/auth/firebase", json={"id_token": google("uid-new-1", "new.person@gmail.test")}).json()
    assert again["user"]["app_user_id"] == u["app_user_id"]
    boss = client.post("/auth/firebase", json={"id_token": google("uid-boss", "boss@corp.test")}).json()
    assert boss["user"]["role"] == "ADMIN" and boss["user"]["profile_user_id"] is None
    linked = client.post("/auth/firebase", json={"id_token": google("uid-demo", "customer@pam.test")}).json()
    assert linked["user"]["profile_user_id"] == "USR-000001"           # existing login gets linked, not duplicated
    clash = client.post("/auth/firebase", json={"id_token": google("uid-other", "customer@pam.test")})
    assert clash.status_code == 409
    unverified = client.post("/auth/firebase", json={"id_token": google("uid-x", "x@gmail.test", verified=False)})
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
    r = client.post("/auth/login", json={"email": "admin@pam.test", "password": "x"})
    assert r.status_code == 500 and "secret" not in r.text and r.json()["request_id"]
