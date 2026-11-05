"""Replay protection for writes.

The phone queues changes made without a network and sends them later, and a request can be cut off after the server
applied it but before the answer arrived. Every queued write carries an `Idempotency-Key`; the first successful
answer is stored and any repeat with the same key (and the same sign-in) gets that answer back without running again.
A lock held for the whole request makes two simultaneous repeats wait for each other instead of both running.
"""
import hashlib

from sqlalchemy import text
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Message, Receive, Scope, Send

import app.db as db

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def _key(scope: Scope) -> str | None:
    if scope["type"] != "http" or scope["method"] not in MUTATING or not scope["path"].startswith("/api/v1/me/"):
        return None
    h = {k.decode().lower(): v.decode("latin-1") for k, v in scope["headers"]}
    k = h.get("idempotency-key", "")
    if not (8 <= len(k) <= 80) or not k.replace("-", "").replace("_", "").isalnum():
        return None
    who = h.get("authorization", "")
    return hashlib.sha256(f"{who}|{scope['method']}|{scope['path']}|{k}".encode()).hexdigest()


class IdempotencyMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        key = _key(scope)
        if key is None:
            return await self.app(scope, receive, send)
        conn = await run_in_threadpool(db.engine.connect)
        try:
            row = await run_in_threadpool(self._begin, conn, key)
            if row is not None:
                await send({"type": "http.response.start", "status": row.status,
                            "headers": [(b"content-type", row.content_type.encode()), (b"x-idempotent-replay", b"1")]})
                await send({"type": "http.response.body", "body": bytes(row.body)})
                return
            status = 500
            ctype = "application/json"
            chunks: list[bytes] = []

            async def capture(msg: Message):
                nonlocal status, ctype
                if msg["type"] == "http.response.start":
                    status = msg["status"]
                    for k, v in msg.get("headers", []):
                        if k.lower() == b"content-type":
                            ctype = v.decode("latin-1")
                elif msg["type"] == "http.response.body":
                    chunks.append(msg.get("body", b""))
                await send(msg)

            await self.app(scope, receive, capture)
            if 200 <= status < 300:
                await run_in_threadpool(self._store, conn, key, status, b"".join(chunks), ctype)
        finally:
            await run_in_threadpool(self._end, conn)

    @staticmethod
    def _begin(conn, key):
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": key})
        q = text("SELECT status, body, content_type FROM idempotency_key WHERE key = :k")
        return conn.execute(q, {"k": key}).first()

    @staticmethod
    def _store(conn, key, status, body, ctype):
        conn.execute(text("INSERT INTO idempotency_key (key, status, body, content_type) VALUES (:k, :s, :b, :c) "
                          "ON CONFLICT DO NOTHING"), {"k": key, "s": status, "b": body, "c": ctype})
        conn.execute(text("DELETE FROM idempotency_key WHERE created_at < now() - interval '14 days' "
                          "AND random() < 0.02"))
        conn.commit()

    @staticmethod
    def _end(conn):
        try:
            conn.rollback()      # releases the transaction lock when nothing was stored
        finally:
            conn.close()
