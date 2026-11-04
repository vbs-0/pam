"""Load a generated dataset into Postgres. A load is an explicit reset of inputs, ground truth and outputs;
logins, jobs, audit and validation history survive (app users reference profiles softly, A18)."""
import hashlib
import json
from pathlib import Path

from sqlalchemy import Connection, text

from app import schema
from app.config import Settings
from app.households import REAL_FROM
from app.jobs.sql import next_number
from app.security import hash_password

FOLDER = {**{t.name: "inputs" for t in schema.INPUT_TABLES}, **{t.name: "ground_truth" for t in schema.GT_TABLES}}
REAL_ACCOUNT = "account_id IN (SELECT account_id FROM account WHERE user_id >= :real)"
KEEP = [("user_profile", "user_id >= :real"), ("account", "user_id >= :real"),
        ("account_holder", REAL_ACCOUNT), ("account_event", REAL_ACCOUNT), ("account_balance_monthly", REAL_ACCOUNT),
        ("txn", "user_id >= :real"), ("budget", "user_id >= :real"),
        ("category_override", "txn_id IN (SELECT txn_id FROM txn WHERE user_id >= :real)")]   # FK order
DEMO = [("admin@pam.test", "ADMIN"), ("analyst@pam.test", "ANALYST"), ("reviewer@pam.test", "REVIEWER"),
        ("customer@pam.test", "CUSTOMER")]


def load_dataset(conn: Connection, data_dir: Path, scale: str) -> dict:
    data_dir = Path(data_dir)
    raw_manifest = (data_dir / "manifest.json").read_bytes()
    manifest = json.loads(raw_manifest)
    resettable = schema.INPUT_TABLES + schema.GT_TABLES + schema.OUTPUT_TABLES
    for name, where in KEEP:                                  # real households survive a reload (A36)
        conn.execute(text(f"CREATE TEMP TABLE keep_{name} ON COMMIT DROP AS SELECT * FROM {name} WHERE {where}"),
                     {"real": REAL_FROM})
    conn.execute(text(f"TRUNCATE {', '.join(t.fullname for t in resettable)} RESTART IDENTITY"))
    conn.execute(text("SET LOCAL synchronous_commit = off"))    # one big load; durability comes from COMMIT
    counts = {}
    with conn.connection.driver_connection.cursor() as cur:
        for t in schema.INPUT_TABLES + schema.GT_TABLES:          # FK order
            cols = ", ".join(c.name for c in t.columns)
            path = data_dir / FOLDER[t.name] / f"{t.name}.csv"
            sql = f"COPY {t.fullname} ({cols}) FROM STDIN WITH (FORMAT csv, HEADER true)"
            with open(path, "rb") as f, cur.copy(sql) as cp:
                while chunk := f.read(1 << 20):
                    cp.write(chunk)
            counts[t.name] = manifest["files"][f"{FOLDER[t.name]}/{t.name}.csv"]["rows"]
    for name, _ in KEEP:
        conn.execute(text(f"INSERT INTO {name} SELECT * FROM keep_{name}"))
    for t in schema.INPUT_TABLES + schema.GT_TABLES:
        conn.execute(text(f"ANALYZE {t.fullname}"))
    conn.execute(text("INSERT INTO dataset_load (load_id, loaded_at, scale, seed, manifest_sha256, rows) "
                      "VALUES (:id, now(), :scale, :seed, :sha, CAST(:rows AS jsonb))"),
                 {"id": f"DSL-{next_number(conn, schema.dataset_load, 'load_id'):06d}", "scale": scale,
                  "seed": manifest["seed"], "sha": hashlib.sha256(raw_manifest).hexdigest(),
                  "rows": json.dumps(counts)})
    return counts


def seed_demo_users(conn: Connection) -> int:
    """One login per role when DEMO_PASSWORD is set (read now, so tests and env changes apply). Existing
    accounts are never overwritten. The customer is linked to USR-000001 when that profile exists."""
    password = Settings().demo_password
    if not password:
        return 0
    has_profile = conn.execute(text("SELECT 1 FROM user_profile WHERE user_id = 'USR-000001'")).first() is not None
    made = 0
    for email, role in DEMO:
        if conn.execute(text("SELECT 1 FROM app_user WHERE email = :e"), {"e": email}).first():
            continue
        conn.execute(text("INSERT INTO app_user (app_user_id, email, role, profile_user_id, password_hash, "
                          "firebase_uid, disabled, created_at) VALUES (:id, :e, :r, :p, :h, NULL, false, now()) "
                          "ON CONFLICT (email) DO NOTHING"),
                     {"id": f"APP-{next_number(conn, schema.app_user, 'app_user_id'):06d}", "e": email, "r": role,
                      "p": "USR-000001" if role == "CUSTOMER" and has_profile else None,
                      "h": hash_password(password)})
        made += 1
    return made


HOUSEHOLD_DOMAIN = "pam.is-cool.dev"


def seed_household_logins(conn: Connection) -> int:
    """One CUSTOMER login per synthetic household (usr-000001@pam.is-cool.dev ...) sharing HOUSEHOLD_PASSWORD, so
    reviewers can open any sample household. Sample data only: real households sign in with Google. Existing logins
    and anyone who changed their password are left alone."""
    password = Settings().household_password
    if not password:
        return 0
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('app_user'))"))
    start = next_number(conn, schema.app_user, "app_user_id")
    shared = hash_password(password)                 # one argon2 hash for all: 1,000 hashes would take a minute
    rows = conn.execute(text(
        "INSERT INTO app_user (app_user_id, email, role, profile_user_id, password_hash, firebase_uid, disabled, "
        "created_at) SELECT 'APP-' || lpad((:start + row_number() OVER (ORDER BY p.user_id) - 1)::text, 6, '0'), "
        "lower(p.user_id) || '@' || :dom, 'CUSTOMER', p.user_id, :h, NULL, false, now() FROM user_profile p "
        "WHERE p.user_id < :real AND NOT EXISTS (SELECT 1 FROM app_user a WHERE a.email = lower(p.user_id) || '@' "
        "|| :dom) ORDER BY p.user_id"), {"start": start, "dom": HOUSEHOLD_DOMAIN, "h": shared, "real": REAL_FROM})
    return rows.rowcount
