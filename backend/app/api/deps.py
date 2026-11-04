"""Who is calling. The token names the login; role, profile and disabled flag are read from the DB every request,
so a demotion or disable takes effect immediately (A-series: stale roles in tokens)."""
from dataclasses import dataclass

from fastapi import Depends, Header
from sqlalchemy import Connection, text

from app.db import get_conn
from app.security import AuthError, verify_local_token


@dataclass(frozen=True)
class Caller:
    app_user_id: str
    email: str
    role: str
    profile_user_id: str | None


def current_user(authorization: str | None = Header(None), conn: Connection = Depends(get_conn)) -> Caller:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthError("sign in first")
    claims = verify_local_token(token.strip())
    row = conn.execute(text("SELECT app_user_id, email, role, profile_user_id, disabled FROM app_user "
                            "WHERE app_user_id = :i"), {"i": claims["sub"]}).first()
    if row is None:
        raise AuthError("this login no longer exists")
    if row.disabled:
        raise AuthError("this login is disabled", status=403)
    return Caller(row.app_user_id, row.email, row.role, row.profile_user_id)


def require(*roles: str):
    def check(caller: Caller = Depends(current_user)) -> Caller:
        if caller.role not in roles:
            raise AuthError(f"needs role {' or '.join(roles)}", status=403)
        return caller
    return check
