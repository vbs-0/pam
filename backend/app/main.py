import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.middleware.gzip import GZipMiddleware

from app.api import admin, analyst, analytics, auth, entries_plus, entry, errors, me, me_plus, review
from app.config import settings
from app.db import get_conn
from app.idempotency import IdempotencyMiddleware
from app.logging import RequestIdMiddleware, setup_logging


@asynccontextmanager
async def lifespan(_app):
    import app.db
    from app.jobs.runner import fail_orphans
    try:
        with app.db.engine.connect() as conn:
            fail_orphans(conn)                    # jobs cut off by the previous shutdown (A15)
    except Exception:                             # DB down at boot: /readyz reports it; don't crash the process
        logging.getLogger("pam").exception("startup: could not reach the database")
    import asyncio

    from app.digest import digest_loop
    task = asyncio.create_task(digest_loop())
    yield
    task.cancel()


def create_app() -> FastAPI:
    settings.check()
    setup_logging()
    app = FastAPI(title="PAM API", version="0.1.0", lifespan=lifespan,
                  description="Payment Account Manager — categorization, recurring payments, budgets.")
    app.add_middleware(IdempotencyMiddleware)   # innermost: sees the uncompressed answer it stores
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(CORSMiddleware, allow_origins=[o for o in settings.cors_origins.split(",") if o],
                       allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Request-ID"])
    app.add_middleware(RequestIdMiddleware)
    errors.install(app)
    v1 = APIRouter(prefix="/api/v1")
    for r in (auth.router, me.router, entry.router, entries_plus.router, me_plus.router, analytics.router,
              analyst.router, analyst.ops, review.router, admin.router):
        v1.include_router(r)
    app.include_router(v1)

    @app.get("/healthz", tags=["ops"])
    def healthz():
        return {"status": "ok"}

    @app.get("/readyz", tags=["ops"])
    def readyz(conn=Depends(get_conn)):
        conn.execute(text("SELECT 1"))
        return {"status": "ready"}

    return app


app = create_app()
