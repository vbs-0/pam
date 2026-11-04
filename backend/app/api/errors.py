"""Every error leaves the API as RFC 9457 problem+json with the request id, never a stack trace."""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.db import LockBusy
from app.security import AuthError

log = logging.getLogger("pam")
TITLES = {400: "Bad request", 401: "Not signed in", 403: "Forbidden", 404: "Not found", 409: "Conflict",
          422: "Invalid input", 429: "Too many attempts", 500: "Server error", 503: "Unavailable"}


def problem(request: Request, status: int, detail: str, **extra) -> JSONResponse:
    body = {"type": "about:blank", "title": TITLES.get(status, "Error"), "status": status, "detail": detail,
            "instance": request.url.path, "request_id": getattr(request.state, "request_id", None), **extra}
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return JSONResponse(body, status, headers=headers, media_type="application/problem+json")


def install(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http(request: Request, e: HTTPException):
        return problem(request, e.status_code, str(e.detail))

    @app.exception_handler(AuthError)
    async def auth(request: Request, e: AuthError):
        return problem(request, e.status, e.detail)

    @app.exception_handler(LockBusy)
    async def busy(request: Request, e: LockBusy):
        return problem(request, 409, str(e))

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, e: RequestValidationError):
        errors = [{"field": ".".join(str(p) for p in err["loc"][1:]), "message": err["msg"]} for err in e.errors()]
        return problem(request, 422, "Some fields are invalid.", errors=errors)

    @app.exception_handler(Exception)
    async def crash(request: Request, e: Exception):
        log.exception("unhandled", extra={"extra_fields": {"rid": getattr(request.state, "request_id", None)}})
        return problem(request, 500, "Something went wrong on our side. Quote the request id if you report it.")
