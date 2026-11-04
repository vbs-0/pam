"""Passwords and tokens. Tokens prove identity only; roles always come from the database.

Two token kinds reach the API: local HS256 tokens (seeded demo users, offline review) and Firebase ID tokens
(RS256, verified against Google's published x509 certificates). The algorithm is pinned per kind, so an HS256
token signed with Google's public certificate (algorithm confusion) or an ``alg: none`` token never passes.
"""
import json
import re
import threading
import time
import urllib.request

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.x509 import load_pem_x509_certificate

from app.config import settings

GOOGLE_CERTS = "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
LOCAL_ISSUER = "pam"
LEEWAY_S = 30                      # tolerate small clock skew between phone, Google and this server
_ph = PasswordHasher()             # argon2id with library defaults
_certs: dict = {"keys": {}, "expires": 0.0}
_certs_lock = threading.Lock()
_dummy_hash: str | None = None


class AuthError(Exception):
    def __init__(self, detail: str, status: int = 401):
        super().__init__(detail)
        self.detail, self.status = detail, status


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(hashed: str | None, password: str) -> bool:
    """Constant-ish time even for unknown users: a missing hash is checked against a dummy hash."""
    global _dummy_hash
    if hashed is None:
        _dummy_hash = _dummy_hash or _ph.hash("not-a-real-password")
        hashed, password = _dummy_hash, password + "\0"
    try:
        return _ph.verify(hashed, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def issue_local_token(app_user_id: str, role: str) -> str:
    now = int(time.time())
    claims = {"sub": app_user_id, "role": role, "iss": LOCAL_ISSUER, "iat": now,
              "exp": now + settings.jwt_ttl_minutes * 60}
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


def verify_local_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], issuer=LOCAL_ISSUER, leeway=LEEWAY_S,
                          options={"require": ["exp", "iat", "sub", "iss"]})
    except jwt.ExpiredSignatureError as e:
        raise AuthError("token expired") from e
    except jwt.PyJWTError as e:
        raise AuthError("invalid token") from e


def _max_age(cache_control: str) -> int:
    m = re.search(r"max-age=(\d+)", cache_control or "")
    return int(m.group(1)) if m else 3600


def _google_certs() -> dict[str, str]:
    """Google's signing certificates, cached for the max-age Google sends (keys rotate every few hours)."""
    with _certs_lock:
        if time.time() < _certs["expires"] and _certs["keys"]:
            return _certs["keys"]
        try:
            with urllib.request.urlopen(GOOGLE_CERTS, timeout=5) as r:
                keys = json.loads(r.read().decode())
                ttl = _max_age(r.headers.get("Cache-Control", ""))
        except OSError as e:
            if _certs["keys"]:                       # serve stale keys rather than lock everyone out
                return _certs["keys"]
            raise AuthError("cannot reach Google to verify the sign-in", status=503) from e
        _certs.update(keys=keys, expires=time.time() + ttl)
        return keys


def verify_firebase_token(token: str) -> dict:
    project = settings.firebase_project_id
    if not project:
        raise AuthError("Google sign-in is not configured on this server")
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as e:
        raise AuthError("invalid token") from e
    if header.get("alg") != "RS256":
        raise AuthError("invalid token")
    pem = _google_certs().get(header.get("kid", ""))
    if pem is None:
        raise AuthError("invalid token signing key")
    key = load_pem_x509_certificate(pem.encode()).public_key()
    try:
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=project,
                            issuer=f"https://securetoken.google.com/{project}", leeway=LEEWAY_S,
                            options={"require": ["exp", "iat", "sub", "aud", "iss"]})
    except jwt.ExpiredSignatureError as e:
        raise AuthError("token expired") from e
    except jwt.PyJWTError as e:
        raise AuthError("invalid token") from e
    if not claims.get("sub") or len(claims["sub"]) > 128:
        raise AuthError("invalid token subject")
    if claims.get("auth_time", 0) > time.time() + LEEWAY_S:
        raise AuthError("invalid token")
    return claims


def token_kind(token: str) -> str:
    """'local' or 'firebase' by the pinned algorithm in the header; anything else is rejected."""
    try:
        alg = jwt.get_unverified_header(token).get("alg")
    except jwt.PyJWTError as e:
        raise AuthError("invalid token") from e
    if alg == "HS256":
        return "local"
    if alg == "RS256":
        return "firebase"
    raise AuthError("invalid token")
