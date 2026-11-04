"""Command line: ``python -m app.cli <command>``. Run from ``backend/``; output paths default to ``../data/<scale>``."""
import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

from app.datagen.generator import SCALES, GenParams, generate
from app.datagen.writer import export_json, export_sql, repro, write_dataset

ROOT = Path(__file__).resolve().parents[2]


def _params(a) -> GenParams:
    users, txns = SCALES[a.scale]
    return GenParams(a.users or users, a.transactions or txns, a.seed)


def _out(a) -> Path:
    if a.out:
        return Path(a.out)
    return ROOT / "data" / (a.scale if not (a.users or a.transactions) else "tmp-custom")


def cmd_generate(a) -> None:
    p, out = _params(a), _out(a)
    t = time.perf_counter()
    m = write_dataset(generate(p), out)
    print(f"generated {m['files']['inputs/txn.csv']['rows']:,} transactions for {p.users:,} households "
          f"(seed {p.seed}) in {time.perf_counter() - t:.1f}s -> {out}")


def cmd_export(a) -> None:
    out = _out(a)
    if not (out / "manifest.json").exists():
        sys.exit(f"no dataset at {out}; run `generate` first")
    export_json(out)
    export_sql(out)
    print(f"wrote {out / 'json'} and {out / 'seed.sql'}")


def cmd_repro(a) -> None:
    with tempfile.TemporaryDirectory(prefix="pam-repro-") as tmp:
        result = repro(_params(a), Path(tmp))
    print(json.dumps(result, indent=2))
    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    if not result["match"]:
        sys.exit(1)


def _reports(a) -> Path:
    return Path(a.reports) if a.reports else ROOT / "reports" / _out(a).name


def cmd_validate_dataset(a) -> None:
    from app.datagen.validate import render_markdown, to_json, validate_dataset
    out, reports = _out(a), _reports(a)
    t = time.perf_counter()
    results = validate_dataset(out)
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "validation_dataset.json").write_text(to_json(results), encoding="utf-8", newline="\n")
    (reports / "validation_dataset.md").write_text(render_markdown(results, f"Dataset validation — {out.name}"),
                                                   encoding="utf-8", newline="\n")
    for r in results:
        print(f"{r.status:4}  {r.name:22} violations={r.violations:<6} labelled={r.labelled}")
    print(f"{time.perf_counter() - t:.1f}s -> {reports}")
    if any(r.status == "FAIL" for r in results):
        sys.exit(1)


def cmd_evaluate(a) -> None:
    """Offline: run the engine on the dataset files and score it against ground truth (no database needed)."""
    from app.datagen.validate import Data
    from app.engine.pipeline import input_from_rows, run_engine
    from app.evaluation import evaluate, from_engine, render_markdown
    out, reports = _out(a), _reports(a)
    t = time.perf_counter()
    d = Data(out)
    result = run_engine(input_from_rows(d.rows))
    decided, events, resolutions, exceptions = from_engine(result)
    m = evaluate(decided, d.rows["txn_label"], d.rows["recurring_truth"], d.rows["anomaly"], events, resolutions,
                 exceptions)
    m["engine_stats"] = result.stats
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "evaluation.json").write_text(json.dumps(m, indent=2, default=str) + "\n", encoding="utf-8",
                                             newline="\n")
    (reports / "evaluation.md").write_text(render_markdown(m, f"Evaluation — {out.name}"), encoding="utf-8",
                                           newline="\n")
    for k, v in m["thresholds"].items():
        print(f"{'PASS' if v['pass'] else 'FAIL'}  {k:28} {v['value']:.4f}  ({v['target']})")
    print(f"{time.perf_counter() - t:.1f}s -> {reports}")
    if not m["all_pass"]:
        sys.exit(1)


def cmd_docs(a) -> None:
    from app.docs_gen import render_data_dictionary
    path = ROOT / "docs" / "data-dictionary.md"
    path.write_text(render_data_dictionary(), encoding="utf-8", newline="\n")
    print(f"wrote {path}")


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):      # Windows consoles default to cp1252, which has no ₹
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="pam", description="PAM data and pipeline commands")
    sub = ap.add_subparsers(dest="command", required=True)
    for name, fn, help_ in [("generate", cmd_generate, "generate the synthetic dataset (CSV + manifest)"),
                            ("export", cmd_export, "write JSON and the SQL seed next to the CSVs"),
                            ("repro", cmd_repro, "generate twice in fresh interpreters and compare checksums"),
                            ("validate-dataset", cmd_validate_dataset, "check keys, joins, dates, arithmetic, labels"),
                            ("evaluate", cmd_evaluate, "run the engine on the files and score it (no DB)"),
                            ("docs", cmd_docs, "regenerate docs/data-dictionary.md from the schema")]:
        s = sub.add_parser(name, help=help_)
        s.set_defaults(fn=fn)
        s.add_argument("--scale", choices=sorted(SCALES), default="starter")
        s.add_argument("--users", type=int)
        s.add_argument("--transactions", type=int)
        s.add_argument("--seed", type=int, default=20261022)
        s.add_argument("--out", help="dataset directory (default ../data/<scale>)")
        s.add_argument("--reports", help="report directory (default ../reports/<scale>)")
        if name == "repro":
            s.add_argument("--report", help="also write the result JSON here")
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
