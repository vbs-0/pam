"""Background jobs started from the admin console. Each job is a row in `job`; a thread in the API process runs it.

ponytail: in-process threads, one job at a time; move to a worker process if jobs ever need to outlive deploys.
A job that was QUEUED/RUNNING when the process stopped is marked FAILED at the next start (A15).
"""
import json
import logging
import tempfile
import threading
import traceback
from pathlib import Path

from sqlalchemy import Connection, text

from app import schema
from app.config import settings
from app.datagen.generator import SCALES, GenParams, generate
from app.datagen.validate import to_json, validate_dataset
from app.datagen.writer import export_json, export_sql, repro, write_dataset
from app.jobs.sql import next_number

log = logging.getLogger("pam")
LOCKING = {"GENERATE_LOAD", "PIPELINE"}          # change the dataset or the latest run: one at a time
_one_at_a_time = threading.Lock()


class JobRejected(Exception):
    pass


def data_root() -> Path:
    return Path(settings.data_dir).resolve()


def scale_dir(scale: str) -> Path:
    if scale not in SCALES:
        raise JobRejected(f"unknown scale '{scale}' (use {', '.join(SCALES)})")
    return data_root() / scale


def check_params(job_type: str, params: dict) -> dict:
    if job_type == "GENERATE_LOAD":
        scale = params.get("scale", "starter")
        scale_dir(scale)
        if SCALES[scale][1] > settings.max_job_transactions:
            raise JobRejected(f"this server is sized for up to {settings.max_job_transactions:,} transactions; "
                              "generate the full scale offline with the CLI")
        return {"scale": scale, "seed": int(params.get("seed", 20261022))}
    if job_type == "VALIDATE":
        if params.get("scope", "OUTPUTS") not in ("DATASET", "OUTPUTS"):
            raise JobRejected("scope is DATASET or OUTPUTS")
        return {"scope": params.get("scope", "OUTPUTS")}
    if job_type in ("EXPORT", "REPRO"):
        scale = params.get("scale", "starter")
        scale_dir(scale)
        if job_type == "EXPORT" and not (scale_dir(scale) / "manifest.json").exists():
            raise JobRejected(f"no {scale} dataset on the server yet")
        if job_type == "REPRO" and SCALES[scale][1] > settings.max_job_transactions:
            raise JobRejected("reproducibility at this scale is a CLI job on a bigger machine")
        return {"scale": scale}
    return {}


def submit(conn: Connection, engine, job_type: str, params: dict, actor: str) -> str:
    params = check_params(job_type, params)
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('job'))"))
    if job_type in LOCKING and conn.execute(text(
            "SELECT 1 FROM job WHERE status IN ('QUEUED', 'RUNNING') AND job_type = ANY(:t)"),
            {"t": list(LOCKING)}).first():
        raise JobRejected("a dataset job is already queued or running; wait for it to finish")
    job_id = f"JOB-{next_number(conn, schema.job, 'job_id'):06d}"
    conn.execute(text("INSERT INTO job (job_id, job_type, params, status, created_by, created_at) "
                      "VALUES (:j, :t, CAST(:p AS jsonb), 'QUEUED', :a, now())"),
                 {"j": job_id, "t": job_type, "p": json.dumps(params), "a": actor})
    conn.commit()
    threading.Thread(target=_run, args=(engine, job_id, job_type, params), daemon=True, name=job_id).start()
    return job_id


def _run(engine, job_id: str, job_type: str, params: dict) -> None:
    with _one_at_a_time, engine.connect() as conn:
        conn.execute(text("UPDATE job SET status = 'RUNNING', started_at = now() WHERE job_id = :j"), {"j": job_id})
        conn.commit()
        try:
            result = WORK[job_type](conn, params)
            conn.commit()
            conn.execute(text("UPDATE job SET status = 'SUCCEEDED', finished_at = now(), result = CAST(:r AS jsonb) "
                              "WHERE job_id = :j"), {"j": job_id, "r": json.dumps(result, default=str)})
        except Exception as e:
            conn.rollback()
            log.error("job failed", extra={"extra_fields": {"job": job_id, "tb": traceback.format_exc()}})
            conn.execute(text("UPDATE job SET status = 'FAILED', finished_at = now(), error = :e WHERE job_id = :j"),
                         {"j": job_id, "e": f"{type(e).__name__}: {e}"[:2000]})
        conn.commit()


def fail_orphans(conn: Connection) -> int:
    n = conn.execute(text("UPDATE job SET status = 'FAILED', finished_at = now(), error = 'server restarted while "
                          "the job was queued or running' WHERE status IN ('QUEUED', 'RUNNING')")).rowcount
    conn.commit()
    return n


def _generate_load(conn, p):
    from app.jobs.load import load_dataset, seed_demo_users, seed_household_logins
    from app.jobs.pipeline_job import run_pipeline
    users, txns = SCALES[p["scale"]]
    out = scale_dir(p["scale"])
    write_dataset(generate(GenParams(users, txns, p["seed"])), out)
    counts = load_dataset(conn, out, p["scale"])
    logins = seed_demo_users(conn) + seed_household_logins(conn)
    conn.commit()
    return {"rows": counts, "logins_created": logins, "run_id": run_pipeline(conn)}


def _pipeline(conn, p):
    from app.jobs.pipeline_job import run_pipeline
    run_id = run_pipeline(conn)
    stats = conn.execute(text("SELECT stats FROM pipeline_run WHERE run_id = :r"), {"r": run_id}).scalar()
    return {"run_id": run_id, "stats": stats}


def _evaluate(conn, p):
    from app.jobs.evaluate_job import run_evaluation
    m = run_evaluation(conn)
    return {"run_id": m["run_id"], "all_pass": m["all_pass"], "thresholds": m["thresholds"]}


def _validate(conn, p):
    if p["scope"] == "OUTPUTS":
        from app.jobs.outputs_validate import validate_outputs
        results = validate_outputs(conn)
    else:
        scale = conn.execute(text("SELECT scale FROM dataset_load ORDER BY load_id DESC LIMIT 1")).scalar()
        if scale is None:
            raise JobRejected("no dataset loaded")
        results = validate_dataset(scale_dir(scale))
        conn.execute(text("INSERT INTO validation_run (validation_id, scope, created_at, passed, results) "
                          "VALUES (:id, 'DATASET', now(), :ok, CAST(:res AS jsonb))"),
                     {"id": f"VAL-{next_number(conn, schema.validation_run, 'validation_id'):06d}",
                      "ok": all(r.status != "FAIL" for r in results),
                      "res": json.dumps({"scale": scale, "checks": json.loads(to_json(results))})})
    return {"passed": all(r.status != "FAIL" for r in results), "checks": len(results),
            "failed": [r.name for r in results if r.status == "FAIL"]}


def _export(conn, p):
    out = scale_dir(p["scale"])
    export_json(out)
    export_sql(out)
    return {"scale": p["scale"], "files": ["seed.sql", "json/"]}


def _repro(conn, p):
    users, txns = SCALES[p["scale"]]
    with tempfile.TemporaryDirectory(prefix="pam-repro-") as tmp:
        return repro(GenParams(users, txns), Path(tmp))


WORK = {"GENERATE_LOAD": _generate_load, "PIPELINE": _pipeline, "EVALUATE": _evaluate, "VALIDATE": _validate,
        "EXPORT": _export, "REPRO": _repro}
