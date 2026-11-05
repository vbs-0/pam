"""Sign-in. Both routes return the same short-lived PAM token, so the rest of the API checks one token kind.

* POST /auth/login     email + password (seeded demo logins, offline review)
* POST /auth/firebase  a Firebase ID token from Google sign-in, exchanged once for a PAM token
"""
import threading
import time

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from app import mail, schema
from app.api.deps import Caller, current_user
from app.config import settings
from app.db import get_conn
from app.households import REAL_FROM, create_household
from app.jobs.sql import next_number
from app.security import (
    AuthError,
    hash_password,
    issue_local_token,
    issue_reset_token,
    read_reset_token,
    reset_fingerprint_ok,
    verify_firebase_token,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])
MAX_FAILS, WINDOW_S = 5, 900
_fails: dict[str, list[float]] = {}
_fails_lock = threading.Lock()
# ponytail: per-process lockout; move to Redis/DB if the API ever runs more than one worker


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=200)


class RegisterIn(BaseModel):
    email: str = Field(min_length=5, max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
    password: str = Field(min_length=10, max_length=128)
    name: str = Field("", max_length=80)


class ForgotIn(BaseModel):
    email: str = Field(min_length=5, max_length=120)


class ResetIn(BaseModel):
    token: str = Field(min_length=20, max_length=2000)
    password: str = Field(min_length=10, max_length=128)


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
    mobile = request.headers.get("x-pam-client") == "mobile"
    minutes = settings.jwt_ttl_minutes_mobile if mobile else settings.jwt_ttl_minutes
    return TokenOut(access_token=issue_local_token(row.app_user_id, row.role, minutes),
                    expires_in=minutes * 60, user=user)


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


SIGNUPS: dict[str, list[float]] = {}


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, request: Request, tasks: BackgroundTasks, conn: Connection = Depends(get_conn)):
    """Email + password sign-up for a new, empty household (works without Google). 5 per hour per address.
    ponytail: no email verification yet (needs outbound mail); a Google sign-in later takes the login over (A48)."""
    if not settings.allow_signup:
        raise AuthError("sign-up is closed on this server", status=403)
    ip = request.client.host if request.client else "?"
    now = time.time()
    with _fails_lock:
        recent = [t for t in SIGNUPS.get(ip, []) if now - t < 3600]
        if len(recent) >= 5:
            raise AuthError("too many sign-ups from this address; try again in an hour", status=429)
        SIGNUPS[ip] = [*recent, now]
    email = body.email.strip().lower()
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('app_user'))"))
    if conn.execute(text("SELECT 1 FROM app_user WHERE email = :e"), {"e": email}).first():
        raise AuthError("an account with this email already exists; sign in instead", status=409)
    profile = create_household(conn, body.name.strip() or email.split("@")[0])
    app_id = f"APP-{next_number(conn, schema.app_user, 'app_user_id'):06d}"
    conn.execute(text("INSERT INTO app_user (app_user_id, email, role, profile_user_id, password_hash, firebase_uid, "
                      "disabled, created_at) VALUES (:i, :e, 'CUSTOMER', :p, :h, NULL, false, now())"),
                 {"i": app_id, "e": email, "p": profile, "h": hash_password(body.password)})
    row = conn.execute(text(f"SELECT {USER_COLS} FROM app_user WHERE app_user_id = :i"), {"i": app_id}).first()
    tasks.add_task(mail.welcome, email, body.name)      # rate-limited with sign-up itself (5/hour/client)
    return _issue(conn, row, "register", request)


FORGOTS: dict[str, list[float]] = {}


@router.post("/forgot", status_code=202)
def forgot(body: ForgotIn, request: Request, tasks: BackgroundTasks, conn: Connection = Depends(get_conn)):
    """Always answers the same way, so it cannot be used to find out which emails have accounts. 3 mails per hour
    per address and 10 per hour per client; Google-only and disabled logins get nothing."""
    email = body.email.strip().lower()
    ip = request.client.host if request.client else "?"
    now = time.time()
    with _fails_lock:
        for key, cap in ((f"e:{email}", 3), (f"i:{ip}", 10)):
            recent = [t for t in FORGOTS.get(key, []) if now - t < 3600]
            if len(recent) >= cap:
                raise AuthError("too many reset requests; try again in an hour", status=429)
            FORGOTS[key] = [*recent, now]
    row = conn.execute(text("SELECT app_user_id, password_hash, disabled FROM app_user WHERE email = :e"),
                       {"e": email}).first()
    if row and row.password_hash and not row.disabled and mail.configured():
        link = f"{settings.app_url.rstrip('/')}/reset?token={issue_reset_token(row.app_user_id, row.password_hash)}"
        tasks.add_task(mail.send, email, "Reset your PAM password",
                       "Someone asked to reset the password for this PAM account.\n\nOpen this link within 30 "
                       f"minutes to choose a new one:\n{link}\n\nIf it was not you, ignore this email; nothing "
                       "changes until the link is used.")
    return {"detail": "If that email has a password login, a reset link is on its way."}


@router.post("/reset")
def reset(body: ResetIn, request: Request, tasks: BackgroundTasks, conn: Connection = Depends(get_conn)):
    claims = read_reset_token(body.token)
    row = conn.execute(text("SELECT app_user_id, email, password_hash, disabled FROM app_user "
                            "WHERE app_user_id = :i FOR UPDATE"), {"i": claims["sub"]}).first()
    if row is None or row.disabled or not reset_fingerprint_ok(claims, row.password_hash):
        raise AuthError("this reset link is invalid or has expired", status=400)
    conn.execute(text("UPDATE app_user SET password_hash = :h WHERE app_user_id = :i"),
                 {"h": hash_password(body.password), "i": row.app_user_id})
    conn.execute(text("INSERT INTO audit_event (at, actor, action, entity_type, entity_id, request_id, detail) "
                      "VALUES (now(), :a, 'PASSWORD_RESET', 'APP_USER', :i, :r, NULL)"),
                 {"a": row.email, "i": row.app_user_id, "r": getattr(request.state, "request_id", None)})
    conn.commit()
    with _fails_lock:
        _fails.pop(row.email, None)
    tasks.add_task(mail.password_changed, row.email)
    return {"detail": "Password changed. You can sign in now."}


@router.post("/firebase", response_model=TokenOut)
def firebase(body: FirebaseIn, request: Request, tasks: BackgroundTasks, conn: Connection = Depends(get_conn)):
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
            # a self-registered (unverified) email login hands over to the verified Google owner: drop its password
            drop = row.profile_user_id is not None and row.profile_user_id >= REAL_FROM
            conn.execute(text("UPDATE app_user SET firebase_uid = :u, password_hash = CASE WHEN :d THEN NULL "
                              "ELSE password_hash END WHERE app_user_id = :i"),
                         {"u": uid, "i": row.app_user_id, "d": drop})
        else:
            name = (claims.get("name") or "").strip()
            row = _create(conn, uid, email, name)
            tasks.add_task(mail.welcome, email, name)
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
