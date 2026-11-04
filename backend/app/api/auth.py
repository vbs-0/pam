"""Sign-in. Both routes return the same short-lived PAM token, so the rest of the API checks one token kind.

* POST /auth/login     email + password (seeded demo logins, offline review)
* POST /auth/firebase  a Firebase ID token from Google sign-in, exchanged once for a PAM token
"""
import threading
import time

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from app import schema
from app.api.deps import Caller, current_user
from app.config import settings
from app.db import get_conn
from app.households import create_household
from app.jobs.sql import next_number
from app.security import AuthError, issue_local_token, verify_firebase_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])
MAX_FAILS, WINDOW_S = 5, 900
_fails: dict[str, list[float]] = {}
_fails_lock = threading.Lock()
# ponytail: per-process lockout; move to Redis/DB if the API ever runs more than one worker


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=200)


class FirebaseIn(BaseModel):
    id_token: str = Field(min_length=20, max_length=4096)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


def _throttle(email: str) -> None:
    now = time.time()
    with _fails_lock:
        recent = [t for t in _fails.get(email, []) if now - t < WINDOW_S]
        _fails[email] = recent
        if len(recent) >= MAX_FAILS:
            raise AuthError(f"too many failed attempts; try again in {int(WINDOW_S - (now - recent[0])) // 60 + 1} "
                            "min", status=429)


def _failed(email: str) -> None:
    with _fails_lock:
        _fails.setdefault(email, []).append(time.time())


def _issue(conn: Connection, row, how: str, request: Request) -> TokenOut:
    conn.execute(text("INSERT INTO audit_event (at, actor, action, entity_type, entity_id, request_id, detail) "
                      "VALUES (now(), :a, 'LOGIN', 'APP_USER', :i, :r, CAST(:d AS jsonb))"),
                 {"a": row.email, "i": row.app_user_id, "r": getattr(request.state, "request_id", None),
                  "d": f'{{"method": "{how}"}}'})
    conn.commit()
    user = {"app_user_id": row.app_user_id, "email": row.email, "role": row.role,
            "profile_user_id": row.profile_user_id}
    return TokenOut(access_token=issue_local_token(row.app_user_id, row.role),
                    expires_in=settings.jwt_ttl_minutes * 60, user=user)


USER_COLS = "app_user_id, email, role, profile_user_id, password_hash, firebase_uid, disabled"


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, conn: Connection = Depends(get_conn)):
    email = body.email.strip().lower()
    _throttle(email)
    row = conn.execute(text(f"SELECT {USER_COLS} FROM app_user WHERE email = :e"), {"e": email}).first()
    # same message and (argon2) cost whether the email is unknown, the password wrong or the login Google-only
    if not verify_password(row.password_hash if row else None, body.password):
        _failed(email)
        raise AuthError("email or password is wrong")
    if row.disabled:
        raise AuthError("this login is disabled", status=403)
    with _fails_lock:
        _fails.pop(email, None)
    return _issue(conn, row, "password", request)


@router.post("/firebase", response_model=TokenOut)
def firebase(body: FirebaseIn, request: Request, conn: Connection = Depends(get_conn)):
    claims = verify_firebase_token(body.id_token)
    uid, email = claims["sub"], (claims.get("email") or "").strip().lower()
    if not email or not claims.get("email_verified"):
        raise AuthError("your Google account needs a verified email", status=403)
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('app_user'))"))   # first sign-ins can race
    row = conn.execute(text(f"SELECT {USER_COLS} FROM app_user WHERE firebase_uid = :u"), {"u": uid}).first()
    if row is None:
        row = conn.execute(text(f"SELECT {USER_COLS} FROM app_user WHERE email = :e"), {"e": email}).first()
        if row is not None and row.firebase_uid not in (None, uid):
            raise AuthError("this email is linked to a different Google account", status=409)
        if row is not None:      # existing invited/demo login: link it to this Google account
            conn.execute(text("UPDATE app_user SET firebase_uid = :u WHERE app_user_id = :i"),
                         {"u": uid, "i": row.app_user_id})
        else:
            row = _create(conn, uid, email, (claims.get("name") or "").strip())
    if row.disabled:
        conn.commit()
        raise AuthError("this login is disabled", status=403)
    return _issue(conn, row, "google", request)


def _create(conn: Connection, uid: str, email: str, name: str):
    """New Google user. Admin emails from config become ADMIN; everyone else gets a new, empty household of their
    own to fill in (A23). Sample households are only reachable with their own email + password logins."""
    role = "ADMIN" if email in settings.admin_email_set else "CUSTOMER"
    profile = create_household(conn, name or email.split("@")[0]) if role == "CUSTOMER" else None
    app_id = f"APP-{next_number(conn, schema.app_user, 'app_user_id'):06d}"
    conn.execute(text("INSERT INTO app_user (app_user_id, email, role, profile_user_id, password_hash, firebase_uid, "
                      "disabled, created_at) VALUES (:i, :e, :r, :p, NULL, :u, false, now())"),
                 {"i": app_id, "e": email, "r": role, "p": profile, "u": uid})
    return conn.execute(text(f"SELECT {USER_COLS} FROM app_user WHERE app_user_id = :i"), {"i": app_id}).first()


@router.get("/me")
def me(caller: Caller = Depends(current_user)):
    return caller.__dict__
