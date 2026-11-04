import time

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.db
from app.config import settings
from app.datagen.generator import GenParams, generate
from app.datagen.writer import write_dataset
from app.jobs.load import load_dataset, seed_demo_users
from app.jobs.pipeline_job import run_pipeline

DEMO_PASSWORD = "demo-pass-123"
TINY: dict = {}


@pytest.fixture(scope="session")
def api_db(db_engine, tmp_path_factory):
    """A tiny dataset (4 households), demo logins and one pipeline run, shared by all API tests."""
    d = TINY["dir"] = tmp_path_factory.mktemp("tiny")
    write_dataset(generate(GenParams(4, 2000)), d)
    mp = pytest.MonkeyPatch()
    mp.setenv("DEMO_PASSWORD", DEMO_PASSWORD)
    with db_engine.connect() as conn:
        load_dataset(conn, d, "tiny")
        conn.execute(text("DELETE FROM app_user"))
        seed_demo_users(conn)
        conn.commit()
        run_pipeline(conn)
    mp.setattr(app.db, "engine", db_engine)
    yield db_engine
    mp.undo()


@pytest.fixture
def client(api_db):
    from app.api import auth
    from app.main import app as fastapi_app
    auth._fails.clear()
    return TestClient(fastapi_app, raise_server_exceptions=False)


def login(client, email, password=DEMO_PASSWORD) -> dict:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


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
