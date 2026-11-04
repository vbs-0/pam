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


def repro(params, tmp_root: Path) -> dict:
    """Generate twice, each in a fresh interpreter with a different hash seed, and compare every checksum."""
    tmp_root = Path(tmp_root)
    manifests = []
    for run, hash_seed in (("a", "1"), ("b", "2")):
        out = tmp_root / run
        subprocess.run([sys.executable, "-m", "app.cli", "generate", "--users", str(params.users),
                        "--transactions", str(params.transactions), "--seed", str(params.seed), "--out", str(out)],
                       check=True, cwd=BACKEND_DIR, env={**os.environ, "PYTHONHASHSEED": hash_seed},
                       stdout=subprocess.DEVNULL)
        manifests.append((out / "manifest.json").read_bytes())
    files = json.loads(manifests[0])["files"]
    return {"match": manifests[0] == manifests[1], "runs": [hashlib.sha256(m).hexdigest() for m in manifests],
            "python_hash_seeds": [1, 2], "files": {k: v["sha256"] for k, v in files.items()}}
