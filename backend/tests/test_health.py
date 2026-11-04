from fastapi.testclient import TestClient

from app.main import create_app


def test_healthz_and_request_id_echo():
    r = TestClient(create_app()).get("/healthz", headers={"X-Request-ID": "abc123"})
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert r.headers["X-Request-ID"] == "abc123"


def test_request_id_generated_when_missing_or_unsafe():
    client = TestClient(create_app())
    assert len(client.get("/healthz").headers["X-Request-ID"]) == 32
    evil = client.get("/healthz", headers={"X-Request-ID": "x\r\nSet-Cookie: a=b"})
    assert len(evil.headers["X-Request-ID"]) == 32
