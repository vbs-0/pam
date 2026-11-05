"""Dataset files: CSV (canonical), typed JSON, a self-contained SQL seed, a checksummed manifest, and the
reproducibility check that regenerates the dataset twice in fresh interpreters and compares checksums.

CSV is the source of truth: LF line endings, UTF-8, header = schema column names, rows sorted by primary key,
timestamps as ``YYYY-MM-DDTHH:MM:SSZ`` (UTC), NULL as an empty field. The manifest carries no timestamps, so
identical inputs give byte-identical files on any OS (D29).
"""
import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Boolean, Integer, Numeric
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app import schema
from app.timeutil import iso_z

GENERATOR = "pam-datagen/1"
BACKEND_DIR = Path(__file__).resolve().parents[2]
GROUPS = [("inputs", schema.INPUT_TABLES), ("ground_truth", schema.GT_TABLES)]


def fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, datetime):           # before date: datetime is a date subclass
        return iso_z(v)
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, Decimal | float):
        return format(v, "f")
    return str(v)


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_dataset(ds, out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    files = {}
    for folder, tables in GROUPS:
        (out_dir / folder).mkdir(parents=True, exist_ok=True)
        source = ds.tables if folder == "inputs" else ds.truth
        for t in tables:
            path = out_dir / folder / f"{t.name}.csv"
            rows = source[t.name]
            with open(path, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f, lineterminator="\n")
                w.writerow([c.name for c in t.columns])
                w.writerows([fmt(v) for v in r] for r in rows)
            files[f"{folder}/{t.name}.csv"] = {"rows": len(rows), "sha256": _sha(path)}
    p = ds.params
    manifest = {"generator": GENERATOR, "seed": p.seed,
                "params": {"users": p.users, "transactions": p.transactions, "year": p.year},
                "timezone": "Asia/Kolkata", "currency": "INR (amounts in paise)", "files": files}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8",
                                           newline="\n")
    return manifest


def _caster(col):
    if isinstance(col.type, Boolean):
        return lambda s: s == "true"
    if isinstance(col.type, Integer):
        return int
    if isinstance(col.type, Numeric):
        return float
    return str


def export_json(out_dir: Path) -> None:
    """One JSON array per table with typed values (numbers, booleans, null), streamed to keep memory flat."""
    out_dir = Path(out_dir)
    (out_dir / "json").mkdir(exist_ok=True)
    for folder, tables in GROUPS:
        for t in tables:
            casts = [(c.name, _caster(c)) for c in t.columns]
            with open(out_dir / folder / f"{t.name}.csv", encoding="utf-8", newline="") as src, \
                    open(out_dir / "json" / f"{t.name}.json", "w", encoding="utf-8", newline="\n") as dst:
                reader = csv.reader(src)
                next(reader)
                dst.write("[")
                for i, row in enumerate(reader):
                    obj = {n: (cast(v) if v != "" else None) for (n, cast), v in zip(casts, row, strict=True)}
                    dst.write(("," if i else "") + "\n" + json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
                dst.write("\n]\n")


def export_sql(out_dir: Path) -> None:
    """``seed.sql``: DDL with every constraint, then ``COPY ... FROM stdin`` blocks. Load with ``psql -f``."""
    out_dir = Path(out_dir)
    dialect = postgresql.dialect()
    with open(out_dir / "seed.sql", "w", encoding="utf-8", newline="\n") as f:
        f.write("-- PAM synthetic dataset seed (generated; see manifest.json for checksums)\n")
        f.write("BEGIN;\nCREATE SCHEMA IF NOT EXISTS gt;\n")
        for _, tables in GROUPS:
            for t in tables:
                f.write(str(CreateTable(t).compile(dialect=dialect)).strip() + ";\n")
                for ix in sorted(t.indexes, key=lambda i: i.name):
                    f.write(str(CreateIndex(ix).compile(dialect=dialect)) + ";\n")
        for folder, tables in GROUPS:
            for t in tables:
                cols = ", ".join(c.name for c in t.columns)
                f.write(f"\nCOPY {t.fullname} ({cols}) FROM stdin WITH (FORMAT csv);\n")
                with open(out_dir / folder / f"{t.name}.csv", encoding="utf-8", newline="") as src:
                    next(src)
                    for line in src:
                        f.write(line)
                f.write("\\.\n")
        f.write("COMMIT;\n")


def export_files(out_dir: Path) -> dict[str, dict]:
    """Rows and checksum of every exported JSON file and of seed.sql (these are deterministic, like the CSVs)."""
    out_dir = Path(out_dir)
    info = {}
    for _, tables in GROUPS:
        for t in tables:
            path = out_dir / "json" / f"{t.name}.json"
            with open(path, "rb") as f:
                lines = sum(1 for _ in f)
            info[f"json/{t.name}.json"] = {"rows": max(lines - 2, 0), "sha256": _sha(path)}       # "[" + rows + "]"
    info["seed.sql"] = {"sha256": _sha(out_dir / "seed.sql")}
    return info


def _git(*args: str) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=BACKEND_DIR, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _source_sha() -> str:
    """One hash over every generator and schema source file, so a data file can be tied to the code that made it."""
    h = hashlib.sha256()
    files = sorted((BACKEND_DIR / "app" / "datagen").glob("*.py")) + [BACKEND_DIR / "app" / "schema.py",
                                                                      BACKEND_DIR / "app" / "ids.py"]
    for p in files:
        h.update(p.name.encode() + b"\0" + p.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()


def write_provenance(out_dir: Path) -> dict:
    """provenance.json: what made this dataset and what each file hashed to. Not part of the reproducibility
    comparison (it records the machine and commit, which legitimately differ); the checksums it carries are."""
    out_dir = Path(out_dir)
    lock = BACKEND_DIR / "uv.lock"
    status = _git("status", "--porcelain", "--", "backend/app", "backend/uv.lock")
    prov = {
        "synthetic_only": True,
        "statement": "Every record is generated by this repository's code from the seed. No real person, account, "
                     "merchant, bank or transaction data was used, copied or scraped.",
        "generator": GENERATOR,
        "generator_source_sha256": _source_sha(),
        "git_commit": _git("rev-parse", "HEAD"),
        "git_tree_clean_for_generator": (status == "") if status is not None else None,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "dependency_lock_sha256": _sha(lock) if lock.exists() else None,
        "command": " ".join(["python -m app.cli", *sys.argv[1:]]),
        "manifest_sha256": _sha(out_dir / "manifest.json"),
        "exports": export_files(out_dir),
        "do_not_edit": "These files are generated artifacts. Fix the generator and regenerate; never edit a file.",
    }
    (out_dir / "provenance.json").write_text(json.dumps(prov, indent=2, sort_keys=True) + "\n", encoding="utf-8",
                                             newline="\n")
    return prov


def repro(params, tmp_root: Path) -> dict:
    """Generate twice, each in a fresh interpreter with a different hash seed, and compare every checksum."""
    tmp_root = Path(tmp_root)
    manifests, exports = [], []
    for run, hash_seed in (("a", "1"), ("b", "2")):
        out = tmp_root / run
        base = [sys.executable, "-m", "app.cli"]
        arg = ["--users", str(params.users), "--transactions", str(params.transactions), "--seed", str(params.seed),
               "--out", str(out)]
        env = {**os.environ, "PYTHONHASHSEED": hash_seed}
        subprocess.run([*base, "generate", *arg], check=True, cwd=BACKEND_DIR, env=env, stdout=subprocess.DEVNULL)
        subprocess.run([*base, "export", *arg], check=True, cwd=BACKEND_DIR, env=env, stdout=subprocess.DEVNULL)
        manifests.append((out / "manifest.json").read_bytes())
        exports.append({k: v["sha256"] for k, v in export_files(out).items()})
    files = json.loads(manifests[0])["files"]
    csv_match = manifests[0] == manifests[1]
    export_match = exports[0] == exports[1]
    return {"match": csv_match and export_match, "csv_match": csv_match, "export_match": export_match,
            "scope": "same locked Python and dependency environment; two fresh interpreters, PYTHONHASHSEED 1 and 2",
            "python": platform.python_version(), "runs": [hashlib.sha256(m).hexdigest() for m in manifests],
            "python_hash_seeds": [1, 2], "files": {k: v["sha256"] for k, v in files.items()},
            "exports": exports[0]}
