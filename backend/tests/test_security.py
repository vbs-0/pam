import time
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app import security
from app.config import settings
from app.security import (
    AuthError,
    hash_password,
    issue_local_token,
    token_kind,
    verify_firebase_token,
    verify_local_token,
    verify_password,
)

PROJECT = "demo-proj"


@pytest.fixture(scope="module")
def keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "securetoken.test")])
    now = datetime.now(UTC)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(1).not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=1))
            .sign(key, hashes.SHA256()))
    return key, cert.public_bytes(serialization.Encoding.PEM).decode()


@pytest.fixture
def firebase(monkeypatch, keypair):
    monkeypatch.setattr(settings, "firebase_project_id", PROJECT)
    monkeypatch.setattr(security, "_google_certs", lambda: {"k1": keypair[1]})
    return keypair[0]


def _fb(key, kid="k1", **over):
    now = int(time.time())
    claims = {"sub": "uid-123", "aud": PROJECT, "iss": f"https://securetoken.google.com/{PROJECT}", "iat": now,
              "exp": now + 3600, "auth_time": now, "email": "a@b.test"} | over
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, key, algorithm="RS256",
                      headers={"kid": kid})


def test_firebase_valid_token(firebase):
    assert verify_firebase_token(_fb(firebase))["sub"] == "uid-123"
    assert token_kind(_fb(firebase)) == "firebase"


@pytest.mark.parametrize("over", [{"aud": "other-proj"}, {"iss": "https://securetoken.google.com/other"},
                                  {"exp": int(time.time()) - 120}, {"sub": ""}, {"sub": None},
                                  {"auth_time": int(time.time()) + 3600}])
def test_firebase_bad_claims_rejected(firebase, over):
    with pytest.raises(AuthError):
        verify_firebase_token(_fb(firebase, **over))


def test_firebase_unknown_kid_and_other_signer(firebase):
    with pytest.raises(AuthError):
        verify_firebase_token(_fb(firebase, kid="nope"))
    stranger = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(AuthError):
        verify_firebase_token(_fb(stranger))


def test_algorithm_confusion_rejected(firebase, keypair):
    """HS256 token whose HMAC secret is Google's public certificate must not verify as Firebase or local."""
    now = int(time.time())
    forged = jwt.encode({"sub": "x", "aud": PROJECT, "iss": f"https://securetoken.google.com/{PROJECT}",
                         "iat": now, "exp": now + 60}, "public-cert-bytes-as-hmac-secret-0123456789", algorithm="HS256",
                        headers={"kid": "k1"})
    with pytest.raises(AuthError):
        verify_firebase_token(forged)
    with pytest.raises(AuthError):
        verify_local_token(forged)
    unsigned = jwt.encode({"sub": "x"}, None, algorithm="none")
    with pytest.raises(AuthError):
        token_kind(unsigned)


def test_firebase_disabled_without_project(monkeypatch, keypair):
    monkeypatch.setattr(settings, "firebase_project_id", None)
    with pytest.raises(AuthError, match="not configured"):
        verify_firebase_token(_fb(keypair[0]))


def test_local_token_roundtrip_and_failures(monkeypatch):
    tok = issue_local_token("APP-000001", "ADMIN")
    assert verify_local_token(tok)["sub"] == "APP-000001" and token_kind(tok) == "local"
    expired = jwt.encode({"sub": "a", "iss": "pam", "iat": 1, "exp": int(time.time()) - 120}, settings.jwt_secret,
                         algorithm="HS256")
    wrong = jwt.encode({"sub": "a", "iss": "pam", "iat": 1, "exp": int(time.time()) + 60}, "x" * 40,
                       algorithm="HS256")
    for bad in (expired, wrong, "not-a-jwt"):
        with pytest.raises(AuthError):
            verify_local_token(bad)


def test_passwords():
    h = hash_password("s3cret-pass")
    assert h.startswith("$argon2id$") and verify_password(h, "s3cret-pass")
    assert not verify_password(h, "wrong") and not verify_password("garbage", "x")
    assert not verify_password(None, "anything")          # unknown user still pays for a hash check


def test_cert_cache_max_age():
    assert security._max_age("public, max-age=19302, must-revalidate, no-transform") == 19302
    assert security._max_age("") == 3600
