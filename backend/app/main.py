from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.middleware.gzip import GZipMiddleware

from app.api import auth, errors
from app.config import settings
from app.db import get_conn
from app.logging import RequestIdMiddleware, setup_logging


def create_app() -> FastAPI:
    settings.check()
    setup_logging()
    app = FastAPI(title="PAM API", version="0.1.0",
                  description="Payment Account Manager — categorization, recurring payments, budgets.")
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(CORSMiddleware, allow_origins=[o for o in settings.cors_origins.split(",") if o],
                       allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Request-ID"])
    app.add_middleware(RequestIdMiddleware)
    errors.install(app)
    app.include_router(auth.router)

    @app.get("/healthz", tags=["ops"])
    def healthz():
        return {"status": "ok"}

    @app.get("/readyz", tags=["ops"])
    def readyz(conn=Depends(get_conn)):
        conn.execute(text("SELECT 1"))
        return {"status": "ready"}

    return app


app = create_app()
