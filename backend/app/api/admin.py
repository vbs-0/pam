"""Admin API: overview, background jobs, validation and reproducibility results, dataset exports, logins."""
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

import app.db
from app.api.common import decode_cursor, encode_cursor, limit_q
from app.api.deps import Caller, require
from app.api.me import audit
from app.db import get_conn
from app.jobs import runner
from app.jobs.pipeline_job import latest_run_id

router = APIRouter(prefix="/admin", tags=["admin"])
ADMIN = require("ADMIN")


def _rid(request: Request):
    return getattr(request.state, "request_id", None)


@router.get("/overview")
def overview(_: Caller = Depends(ADMIN), conn: Connection = Depends(get_conn)):
    load = conn.execute(text("SELECT * FROM dataset_load ORDER BY load_id DESC LIMIT 1")).first()
    run = latest_run_id(conn)
    ev = conn.execute(text("SELECT run_id, created_at, metrics->'all_pass' AS all_pass, metrics->'headline' AS "
                           "headline FROM evaluation_run ORDER BY created_at DESC LIMIT 1")).first()
    counts = dict(conn.execute(text(
        "SELECT 'households', count(*) FROM user_profile UNION ALL "
        "SELECT 'real_households', count(*) FROM user_profile WHERE user_id >= 'USR-500001' UNION ALL "
        "SELECT 'transactions', count(*) FROM txn UNION ALL "
        "SELECT 'open_exceptions', count(*) FROM exception_case WHERE status IN ('OPEN', 'IN_REVIEW') UNION ALL "
        "SELECT 'logins', count(*) FROM app_user")).all())
    return {"dataset": dict(load._mapping) if load else None, "latest_run_id": run,
            "evaluation": dict(ev._mapping) if ev else None, "counts": counts,
            "running_jobs": [dict(r._mapping) for r in conn.execute(text(
                "SELECT job_id, job_type, status, created_at FROM job WHERE status IN ('QUEUED', 'RUNNING')"))]}


class JobIn(BaseModel):
    job_type: str = Field(pattern="^(GENERATE_LOAD|PIPELINE|EVALUATE|VALIDATE|EXPORT|REPRO)$")
    params: dict = Field(default_factory=dict)


@router.post("/jobs", status_code=202)
def start_job(body: JobIn, request: Request, caller: Caller = Depends(ADMIN), conn: Connection = Depends(get_conn)):
    if len(json.dumps(body.params)) > 500:
        raise HTTPException(422, "params too large")
    try:
        job_id = runner.submit(conn, app.db.engine, body.job_type, body.params, caller.email)
    except runner.JobRejected as e:
        conn.rollback()
        raise HTTPException(409 if "already" in str(e) else 422, str(e)) from None
    with app.db.engine.begin() as c:
        audit(c, caller.email, "JOB_START", "JOB", job_id, _rid(request), body.model_dump())
    return {"job_id": job_id, "status": "QUEUED"}


@router.get("/jobs")
def jobs(cursor: str | None = None, limit: int = Depends(limit_q), _: Caller = Depends(ADMIN),
         conn: Connection = Depends(get_conn)):
    before = decode_cursor(cursor, 1)[0] if cursor else None
    rows = conn.execute(text("SELECT * FROM job WHERE CAST(:b AS text) IS NULL OR job_id < :b "
                             "ORDER BY job_id DESC LIMIT :lim"), {"b": before, "lim": limit + 1}).all()
    more, rows = len(rows) > limit, rows[:limit]
    return {"items": [dict(r._mapping) for r in rows], "next_cursor": encode_cursor(rows[-1].job_id) if more else None}


@router.get("/jobs/{job_id}")
def job(job_id: str, _: Caller = Depends(ADMIN), conn: Connection = Depends(get_conn)):
    r = conn.execute(text("SELECT * FROM job WHERE job_id = :j"), {"j": job_id}).first()
    if r is None:
        raise HTTPException(404, "Not found.")
    return dict(r._mapping)


@router.get("/validation")
def validation(scope: str = Query("OUTPUTS", pattern="^(DATASET|OUTPUTS)$"), _: Caller = Depends(ADMIN),
               conn: Connection = Depends(get_conn)):
    r = conn.execute(text("SELECT * FROM validation_run WHERE scope = :s ORDER BY validation_id DESC LIMIT 1"),
                     {"s": scope}).first()
    if r is None:
        raise HTTPException(404, f"No {scope.lower()} validation yet. Start a VALIDATE job.")
    return dict(r._mapping)


@router.get("/reproducibility")
def reproducibility(scale: str = Query("starter", pattern="^[a-z]+$"), _: Caller = Depends(ADMIN),
                    conn: Connection = Depends(get_conn)):
    r = conn.execute(text("SELECT job_id, finished_at, result FROM job WHERE job_type = 'REPRO' AND status = "
                          "'SUCCEEDED' AND params->>'scale' = :s ORDER BY job_id DESC LIMIT 1"), {"s": scale}).first()
    if r is not None:
        return {"source": r.job_id, "checked_at": r.finished_at, **r.result}
    path = Path(runner.data_root()).parent / "reports" / scale / f"repro-{scale}.json"   # committed CLI evidence
    if path.is_file():
        return {"source": "cli", **json.loads(path.read_text(encoding="utf-8"))}
    raise HTTPException(404, "No reproducibility check yet. Start a REPRO job.")


def _scale_dir(scale: str) -> Path:
    try:
        d = runner.scale_dir(scale)
    except runner.JobRejected:
        raise HTTPException(404, "Not found.") from None
    if not (d / "manifest.json").is_file():
        raise HTTPException(404, f"No {scale} dataset on this server.")
    return d


@router.get("/exports/{scale}")
def export_manifest(scale: str, _: Caller = Depends(ADMIN)):
    d = _scale_dir(scale)
    m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    extra = [p.relative_to(d).as_posix() for p in [d / "seed.sql", *sorted((d / "json").glob("*.json"))]
             if p.is_file()]
    return m | {"downloads": sorted(m["files"]) + extra + ["manifest.json"]}


@router.get("/exports/{scale}/files/{path:path}")
def export_file(scale: str, path: str, _: Caller = Depends(ADMIN)):
    """Only files the manifest lists (plus seed.sql, json/*.json, manifest.json), kept inside the scale dir (A16)."""
    d = _scale_dir(scale)
    m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    allowed = set(m["files"]) | {"seed.sql", "manifest.json"} | {
        p.relative_to(d).as_posix() for p in (d / "json").glob("*.json")}
    target = (d / path).resolve()
    if path not in allowed or not target.is_relative_to(d.resolve()) or not target.is_file():
        raise HTTPException(404, "Not found.")
    media = "text/csv" if path.endswith(".csv") else "application/json" if path.endswith(".json") else "text/plain"
    return FileResponse(target, media_type=media, filename=Path(path).name)


@router.get("/users")
def users(q: str | None = Query(None, max_length=120), role: str | None = Query(None, pattern="^[A-Z]{5,10}$"),
          cursor: str | None = None, limit: int = Depends(limit_q), _: Caller = Depends(ADMIN),
          conn: Connection = Depends(get_conn)):
    after = decode_cursor(cursor, 1)[0] if cursor else None
    like = None if not q else "%" + q.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    rows = conn.execute(text(
        "SELECT app_user_id, email, role, profile_user_id, disabled, created_at, firebase_uid IS NOT NULL AS google, "
        "password_hash IS NOT NULL AS password FROM app_user WHERE (CAST(:q AS text) IS NULL OR email LIKE :q "
        r"ESCAPE '\') AND (CAST(:r AS text) IS NULL OR role = :r) AND (CAST(:a AS text) IS NULL OR app_user_id > :a) "
        "ORDER BY app_user_id LIMIT :lim"), {"q": like, "r": role, "a": after, "lim": limit + 1}).all()
    more, rows = len(rows) > limit, rows[:limit]
    return {"items": [dict(r._mapping) for r in rows],
            "next_cursor": encode_cursor(rows[-1].app_user_id) if more else None}


class UserPatch(BaseModel):
    role: str | None = Field(None, pattern="^(CUSTOMER|ANALYST|REVIEWER|ADMIN)$")
    profile_user_id: str | None = Field(None, max_length=32)
    disabled: bool | None = None


@router.patch("/users/{app_user_id}")
def update_user(app_user_id: str, body: UserPatch, request: Request, caller: Caller = Depends(ADMIN),
                conn: Connection = Depends(get_conn)):
    u = conn.execute(text("SELECT * FROM app_user WHERE app_user_id = :i FOR UPDATE"), {"i": app_user_id}).first()
    if u is None:
        raise HTTPException(404, "Not found.")
    ch = body.model_dump(exclude_unset=True)
    if app_user_id == caller.app_user_id and (ch.get("role", "ADMIN") != "ADMIN" or ch.get("disabled")):
        raise HTTPException(409, "You can't demote or disable your own login; ask another admin.")
    if ch.get("profile_user_id") and not conn.execute(text("SELECT 1 FROM user_profile WHERE user_id = :u"),
                                                       {"u": ch["profile_user_id"]}).first():
        raise HTTPException(422, "That household does not exist.")
    if (ch.get("role", u.role) == "CUSTOMER") and not ch.get("profile_user_id", u.profile_user_id):
        raise HTTPException(422, "A customer login needs a household (profile_user_id).")
    if u.role == "ADMIN" and (ch.get("role", "ADMIN") != "ADMIN" or ch.get("disabled")):
        left = conn.execute(text("SELECT count(*) FROM app_user WHERE role = 'ADMIN' AND NOT disabled AND "
                                 "app_user_id <> :i"), {"i": app_user_id}).scalar()
        if left == 0:
            raise HTTPException(409, "This is the last active admin.")
    if ch:
        sets = ", ".join(f"{k} = :{k}" for k in ch)
        conn.execute(text(f"UPDATE app_user SET {sets} WHERE app_user_id = :i"), ch | {"i": app_user_id})
        audit(conn, caller.email, "USER_UPDATE", "APP_USER", app_user_id, _rid(request),
              {"before": {k: getattr(u, k) for k in ch}, "after": ch})
        conn.commit()
    return dict(conn.execute(text("SELECT app_user_id, email, role, profile_user_id, disabled FROM app_user "
                                  "WHERE app_user_id = :i"), {"i": app_user_id}).first()._mapping)
