import re

import pytest

from app import mail, security
from app.api import auth
from app.config import settings
from tests.api.conftest import DEMO_PASSWORD

pytestmark = pytest.mark.db


@pytest.fixture
def outbox(monkeypatch):
    sent: list[tuple[str, str, str]] = []
    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(settings, "smtp_user", "u")
    monkeypatch.setattr(settings, "smtp_password", "p")
    monkeypatch.setattr(settings, "mail_from", "noreply@pam.test")
    monkeypatch.setattr(mail, "send", lambda to, subject, body: sent.append((to, subject, body)) or True)
    auth.FORGOTS.clear()
    yield sent
    auth.FORGOTS.clear()


def _token(outbox) -> str:
    return re.search(r"token=([\w.\-]+)", outbox[-1][2]).group(1)


def test_forgot_is_uniform_and_sends_only_for_real_password_logins(client, outbox):
    known = client.post("/api/v1/auth/forgot", json={"email": " Customer@PAM.test "})
    ghost = client.post("/api/v1/auth/forgot", json={"email": "ghost@pam.test"})
    assert known.status_code == ghost.status_code == 202 and known.json() == ghost.json()
    assert [m[0] for m in outbox] == ["customer@pam.test"] and "token=" in outbox[0][2]


def test_reset_changes_password_once_and_clears_lockout(client, outbox):
    client.post("/api/v1/auth/forgot", json={"email": "reviewer@pam.test"})
    token = _token(outbox)
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"email": "reviewer@pam.test", "password": "bad"})
    assert client.post("/api/v1/auth/login", json={"email": "reviewer@pam.test", "password": DEMO_PASSWORD}).status_code == 429
    new = "a-brand-new-password"
    ok = client.post("/api/v1/auth/reset", json={"token": token, "password": new})
    assert ok.status_code == 200
    assert client.post("/api/v1/auth/login", json={"email": "reviewer@pam.test", "password": new}).status_code == 200
    again = client.post("/api/v1/auth/reset", json={"token": token, "password": "another-new-password"})
    assert again.status_code == 400 and again.headers["content-type"] == "application/problem+json"   # single use
    # restore for the other tests sharing this database
    client.post("/api/v1/auth/forgot", json={"email": "reviewer@pam.test"})
    assert client.post("/api/v1/auth/reset", json={"token": _token(outbox), "password": DEMO_PASSWORD + "-x"}).status_code == 200
    client.post("/api/v1/auth/forgot", json={"email": "reviewer@pam.test"})
    assert client.post("/api/v1/auth/reset", json={"token": _token(outbox), "password": DEMO_PASSWORD}).status_code == 200


def test_bad_short_expired_and_wrong_purpose_tokens(client, outbox, monkeypatch):
    for bad in ("x" * 30, "a.b.c" * 10):
        assert client.post("/api/v1/auth/reset", json={"token": bad, "password": "long-enough-pass"}).status_code == 400
    assert client.post("/api/v1/auth/reset", json={"token": "short", "password": "long-enough-pass"}).status_code == 422
    client.post("/api/v1/auth/forgot", json={"email": "admin@pam.test"})
    token = _token(outbox)
    assert client.post("/api/v1/auth/reset", json={"token": token, "password": "short"}).status_code == 422
    monkeypatch.setattr(security, "RESET_TTL_S", -120)              # issued already expired
    client.post("/api/v1/auth/forgot", json={"email": "admin@pam.test"})
    expired = client.post("/api/v1/auth/reset", json={"token": _token(outbox), "password": "long-enough-pass"})
    assert expired.status_code == 400
    # a reset link must never work as a login token
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_forgot_is_rate_limited_and_skipped_without_smtp(client, outbox, monkeypatch):
    codes = [client.post("/api/v1/auth/forgot", json={"email": "analyst@pam.test"}).status_code for _ in range(4)]
    assert codes == [202, 202, 202, 429] and len(outbox) == 3
    monkeypatch.setattr(settings, "smtp_host", None)
    auth.FORGOTS.clear()
    outbox.clear()
    assert client.post("/api/v1/auth/forgot", json={"email": "analyst@pam.test"}).status_code == 202 and not outbox
