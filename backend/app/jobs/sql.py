"""Small database helpers shared by the jobs: COPY in, typed SELECT out, next sequential ids."""
import json
from collections.abc import Iterable

from sqlalchemy import Connection, Table, text


def copy_rows(conn: Connection, t: Table, rows: Iterable[tuple]) -> int:
    """Binary-safe bulk insert through COPY on the same transaction as ``conn``. dict values go in as JSON."""
    cols = ", ".join(c.name for c in t.columns)
    n = 0
    with conn.connection.driver_connection.cursor() as cur, cur.copy(f"COPY {t.fullname} ({cols}) FROM STDIN") as cp:
        for r in rows:
            cp.write_row([json.dumps(v, default=str) if isinstance(v, dict | list) else v for v in r])
            n += 1
    return n


def select_rows(conn: Connection, t: Table, where: str = "", params: dict | None = None) -> list[tuple]:
    """Rows in schema column order, sorted by primary key (the same shape the generator produces)."""
    cols = ", ".join(c.name for c in t.columns)
    order = ", ".join(c.name for c in t.primary_key)
    return [tuple(r) for r in conn.execute(text(f"SELECT {cols} FROM {t.fullname} {where} ORDER BY {order}"),
                                           params or {})]


def next_number(conn: Connection, t: Table, column: str) -> int:
    """1 + the largest trailing counter of ids like 'RUN-000041' (ids are fixed-width, so max() sorts right)."""
    last = conn.execute(text(f"SELECT max({column}) FROM {t.fullname}")).scalar()
    return int(last.rsplit("-", 1)[1]) + 1 if last else 1
