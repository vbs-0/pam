from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Connection, create_engine, text

from app.config import settings

engine = create_engine(settings.database_url, pool_size=10, max_overflow=10, pool_pre_ping=True)
PIPELINE_LOCK = 72_610_221  # one dataset-mutating job at a time, across all workers


class LockBusy(RuntimeError):
    pass


def get_conn() -> Iterator[Connection]:
    # looked up at call time so tests can swap app.db.engine
    with globals()["engine"].connect() as conn:
        yield conn


@contextmanager
def advisory_lock(conn: Connection, key: int = PIPELINE_LOCK):
    if not conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}).scalar():
        raise LockBusy("another dataset job is running")
    try:
        yield
    finally:
        conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})


def lock_is_free(conn: Connection, key: int = PIPELINE_LOCK) -> bool:
    sql = "SELECT count(*) = 0 FROM pg_locks WHERE locktype = 'advisory' AND objid = :k AND granted"
    return bool(conn.execute(text(sql), {"k": key}).scalar())
