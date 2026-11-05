"""Dataset validation, run on the written files (what reviewers receive), not on in-memory objects.

Each ``check_*`` returns a CheckResult. FAIL means the data is wrong; WARN means a coverage gap that small
datasets can legitimately have; ``labelled`` counts violations that are deliberate, labelled anomalies.
Keys, joins and enumerations are derived from the schema metadata, so a new column or FK is checked for free.
"""
import csv
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric

from app import ids, schema
from app.timeutil import IST_OFFSET, month_key

TABLES = {t.name: t for t in schema.INPUT_TABLES + schema.GT_TABLES}
FOLDER = {**{t.name: "inputs" for t in schema.INPUT_TABLES}, **{t.name: "ground_truth" for t in schema.GT_TABLES}}
ID_COLUMNS = {("user_profile", "user_id"): "user", ("account", "account_id"): "account", ("txn", "txn_id"): "txn",
              ("budget", "budget_id"): "budget", ("merchant", "merchant_id"): "merchant",
              ("category_rule", "rule_id"): "rule", ("recurring_truth", "truth_series_id"): "truth_series",
              ("anomaly", "anomaly_id"): "anomaly", ("account_event", "event_id"): "account_event"}
DEBIT_PREFIXES = ("UPI/DR/", "ATM WDL", "ACH D-", "IMPS/P2A/", "BBPS/", "POS ", "CC BILL")
CREDIT_PREFIXES = ("UPI/CR/", "UPI/REV/", "NEFT CR", "IMPS/CR/", "INT.PD", "PAYMENT RECEIVED")
QUARTER_ENDS = [date(2026, 3, 31), date(2026, 6, 30), date(2026, 9, 30), date(2026, 12, 31)]
MAX_EXAMPLES = 5


@dataclass
class CheckResult:
    name: str
    status: str                     # PASS | FAIL | WARN
    violations: int
    labelled: int = 0
    examples: list[str] = field(default_factory=list)
    detail: str = ""


class Data:
    """Typed rows per table (tuples in schema column order) plus column index maps."""

    def __init__(self, data_dir: Path):
        self.dir = Path(data_dir)
        self.manifest = json.loads((self.dir / "manifest.json").read_text(encoding="utf-8"))
        self.rows: dict[str, list[tuple]] = {}
        self.ix: dict[str, dict[str, int]] = {}
        self.headers: dict[str, list[str]] = {}
        for name, t in TABLES.items():
            casts = [_caster(c) for c in t.columns]
            with open(self.dir / FOLDER[name] / f"{name}.csv", encoding="utf-8", newline="") as f:
                reader = csv.reader(f)
                header = self.headers[name] = next(reader)
                if header == [c.name for c in t.columns]:
                    self.rows[name] = [tuple(cast(v) if v != "" else None for cast, v in zip(casts, r, strict=True))
                                       for r in reader]
                else:          # column drift: read what matches by name so the other checks still run
                    pos = [header.index(c.name) if c.name in header else None for c in t.columns]
                    self.rows[name] = [tuple(cast(r[i]) if i is not None and r[i] != "" else None
                                             for cast, i in zip(casts, pos, strict=True)) for r in reader]
            self.ix[name] = {c.name: i for i, c in enumerate(t.columns)}

    def col(self, table: str, name: str) -> int:
        return self.ix[table][name]


def _caster(c):
    t = c.type
    if isinstance(t, Boolean):
        return lambda s: s == "true"
    if isinstance(t, Integer):
        return int
    if isinstance(t, Numeric):
        return Decimal
    if isinstance(t, DateTime):
        return datetime.fromisoformat
    if isinstance(t, Date):
        return date.fromisoformat
    return str


def _local(ts: datetime) -> date:
    return (ts + IST_OFFSET).date()


def _result(name: str, bad: list[str], labelled: int = 0, detail: str = "", warn: bool = False) -> CheckResult:
    status = "PASS" if not bad else ("WARN" if warn else "FAIL")
    return CheckResult(name, status, len(bad), labelled, bad[:MAX_EXAMPLES], detail)


# 1. keys -----------------------------------------------------------------------------------------------------------
def check_pk_unique(d: Data) -> CheckResult:
    bad = []
    for name, t in TABLES.items():
        pk = [d.col(name, c.name) for c in t.primary_key]
        counts = Counter(tuple(r[i] for i in pk) for r in d.rows[name])
        bad += [f"{name} {k}" for k, n in counts.items() if n > 1]
    return _result("pk_unique", bad)


# 2. joins ----------------------------------------------------------------------------------------------------------
def check_fk_integrity(d: Data) -> CheckResult:
    bad = []
    for name, t in TABLES.items():
        for fk in t.foreign_key_constraints:
            target = fk.elements[0].column.table.name
            local = [d.col(name, c.name) for c in fk.columns]
            remote = [d.col(target, e.column.name) for e in fk.elements]
            keys = {tuple(r[i] for i in remote) for r in d.rows[target]}
            for r in d.rows[name]:
                k = tuple(r[i] for i in local)
                if None not in k and k not in keys:
                    bad.append(f"{name}.{'+'.join(c.name for c in fk.columns)}={k} not in {target}")
    owner = d.col("account", "user_id")
    bad += [f"account {r[0]} owner {r[owner]} not embedded in id" for r in d.rows["account"] if r[0][4:14] != r[owner]]
    tx_user = d.col("txn", "user_id")
    acc_owner = {r[0]: r[owner] for r in d.rows["account"]}
    bad += [f"txn {r[0]} user {r[tx_user]} != account owner" for r in d.rows["txn"]
            if acc_owner.get(r[1]) != r[tx_user]]
    targets = {"TXN": {r[0] for r in d.rows["txn"]}, "SERIES": {r[0] for r in d.rows["recurring_truth"]},
               "BUDGET": {r[0] for r in d.rows["budget"]}}
    for a in d.rows["anomaly"]:
        if a[3] not in targets[a[2]]:
            bad.append(f"anomaly {a[0]} entity {a[3]} missing")
        bad += [f"anomaly {a[0]} related {x} missing" for x in (a[4] or "").split("|") if x and x not in targets["TXN"]]
    return _result("fk_integrity", bad)


# 3. vocabularies and identifiers -----------------------------------------------------------------------------------
def check_enums(d: Data) -> CheckResult:
    bad = []
    for name, t in TABLES.items():
        for c in t.columns:
            allowed = c.info.get("allowed")
            if allowed:
                i, ok = d.col(name, c.name), set(allowed)
                bad += [f"{name}.{c.name}={r[i]!r}" for r in d.rows[name] if r[i] is not None and r[i] not in ok]
    return _result("enums", bad)


def check_id_formats(d: Data) -> CheckResult:
    bad = []
    for (table, column), kind in ID_COLUMNS.items():
        i, rx = d.col(table, column), ids.ID_PATTERNS[kind]
        bad += [f"{table}.{column}={r[i]}" for r in d.rows[table] if not rx.fullmatch(r[i])]
    return _result("id_formats", bad)


# 4. dates ----------------------------------------------------------------------------------------------------------
def check_date_order(d: Data) -> CheckResult:
    bad = []
    acc = {r[0]: r for r in d.rows["account"]}
    op, cl = d.col("account", "opened_on"), d.col("account", "closed_on")
    posted = d.col("txn", "posted_at")
    year = int(d.manifest["params"]["year"])
    when = {}
    for r in d.rows["txn"]:
        day, a = _local(r[posted]), acc.get(r[1])
        when[r[0]] = r[posted]
        if day.year != year:
            bad.append(f"txn {r[0]} local date {day} outside {year}")
        if a and (day < a[op] or (a[cl] and day > a[cl])):
            bad.append(f"txn {r[0]} on {day} outside account {r[1]} life {a[op]}..{a[cl]}")
    kind, link = d.col("txn_label", "true_kind"), d.col("txn_label", "true_link_txn_id")
    amount = {r[0]: r[d.col("txn", "amount_paise")] for r in d.rows["txn"]}
    for lb in d.rows["txn_label"]:
        if lb[kind] in ("REFUND", "REVERSAL") and lb[link] and amount[lb[0]] > 0 and when[lb[link]] >= when[lb[0]]:
            bad.append(f"{lb[kind].lower()} {lb[0]} not after its original {lb[link]}")
    versions = defaultdict(list)
    for b in d.rows["budget"]:
        versions[b[0]].append((b[1], b[6]))
    for bid, vs in versions.items():
        vs.sort()
        increasing = all(a[1] < b[1] for a, b in zip(vs, vs[1:], strict=False))
        if [v for v, _ in vs] != list(range(1, len(vs) + 1)) or not increasing:
            bad.append(f"budget {bid} versions not consecutive with increasing submitted_at")
    for c in d.rows["category"]:
        if c[5] and c[5] < c[4]:
            bad.append(f"category {c[0]} effective_to before effective_from")
    for a in d.rows["account"]:
        if a[cl] and a[cl] < a[op]:
            bad.append(f"account {a[0]} closed before opening")
    return _result("date_order", bad)


# 5. arithmetic -----------------------------------------------------------------------------------------------------
def _by_account(d: Data) -> dict[str, list[tuple]]:
    out = defaultdict(list)
    for r in d.rows["txn"]:                 # file order = chronological
        out[r[1]].append(r)
    return out


def check_balances(d: Data) -> CheckResult:
    bad = []
    amt = d.col("txn", "amount_paise")
    txns = _by_account(d)
    monthly = defaultdict(list)
    for b in d.rows["account_balance_monthly"]:
        monthly[b[0]].append(b)
        if b[2] + b[3] + b[4] != b[5]:
            bad.append(f"{b[0]} {b[1]} does not reconcile")
    ob, typ, status = d.col("account", "opening_balance_paise"), d.col("account", "account_type"), d.col("account",
                                                                                                         "status")
    for a in d.rows["account"]:
        ms = monthly[a[0]]
        if not ms or ms[0][2] != a[ob]:
            bad.append(f"{a[0]} first month opening != account opening balance")
        bad += [f"{a[0]} {x[1]} closing != {y[1]} opening" for x, y in zip(ms, ms[1:], strict=False) if x[5] != y[2]]
        bal = a[ob]
        flows = defaultdict(lambda: [0, 0])
        for r in txns[a[0]]:
            bal += r[amt]
            flows[month_key(_local(r[3]))][r[amt] < 0] += r[amt]
            if a[typ] == "SAVINGS" and bal < 0:
                bad.append(f"{a[0]} negative after {r[0]}")
                break
        if ms and ms[-1][5] != bal:
            bad.append(f"{a[0]} last monthly closing {ms[-1][5]} != ledger {bal}")
        bad += [f"{a[0]} {m[1]} flows differ from ledger" for m in ms if tuple(flows.get(m[1], (0, 0))) != (m[3], m[4])]
        if a[status] == "CLOSED" and bal != 0:
            bad.append(f"{a[0]} closed with balance {bal}")
    return _result("balances", bad)


def check_cc_payments(d: Data) -> CheckResult:
    bad = []
    amt, ch = d.col("txn", "amount_paise"), d.col("txn", "channel")
    txns = _by_account(d)
    for a in d.rows["account"]:
        if a[2] != "CREDIT_CARD":
            continue
        stmt, paid = defaultdict(int), defaultdict(int)
        for r in txns[a[0]]:
            m = _local(r[3]).month
            if r[ch] == "INTERNAL":
                paid[m] += r[amt]
            else:
                stmt[m] -= r[amt]
        opening = a[d.col("account", "opening_balance_paise")]
        if paid[1] != (-opening if a[7] < date(2026, 1, 1) else 0):
            bad.append(f"{a[0]} January payment {paid[1]} != opening outstanding {-opening}")
        for m in range(1, 12):
            if paid[m + 1] != max(stmt[m], 0):
                bad.append(f"{a[0]} paid {paid[m + 1]} in month {m + 1} for statement {stmt[m]}")
    return _result("cc_payments", bad)


def check_interest_derivation(d: Data) -> CheckResult:
    """Recompute 3% p.a. on the sum of end-of-day balances per quarter (min Rs 1); no interest in the closing
    quarter. The quarter's own interest (posted 20:00 on the quarter end) is excluded from its base."""
    bad = []
    amt, desc = d.col("txn", "amount_paise"), d.col("txn", "descriptor")
    txns = _by_account(d)
    for a in d.rows["account"]:
        if a[2] != "SAVINGS":
            continue
        delta, posted = defaultdict(int), {}
        for r in txns[a[0]]:
            if r[desc].startswith("INT.PD"):
                posted[_local(r[3])] = r[amt]
            else:
                delta[_local(r[3])] += r[amt]
        bal, day = a[d.col("account", "opening_balance_paise")], date(2026, 1, 1)
        closed = a[d.col("account", "closed_on")]
        for qe in QUARTER_ENDS:
            if closed and qe >= closed:
                if qe in posted:
                    bad.append(f"{a[0]} interest after closure on {qe}")
                break
            total = 0
            while day <= qe:
                bal += delta.get(day, 0)
                total += bal
                day += timedelta(days=1)
            expect = max((total * 3 + 18_250) // 36_500, 100)
            if posted.get(qe) != expect:
                bad.append(f"{a[0]} interest {posted.get(qe)} on {qe}, expected {expect}")
            bal += posted.get(qe) or 0
    return _result("interest_derivation", bad)


def check_transfer_pairs_zero(d: Data) -> CheckResult:
    bad = []
    amount = {r[0]: r[d.col("txn", "amount_paise")] for r in d.rows["txn"]}
    kind, link = d.col("txn_label", "true_kind"), d.col("txn_label", "true_link_txn_id")
    back = {lb[0]: lb[link] for lb in d.rows["txn_label"]}
    for lb in d.rows["txn_label"]:
        if lb[kind] in ("TRANSFER", "REVERSAL"):
            other = lb[link]
            if other is None or back.get(other) != lb[0] or amount[lb[0]] + amount[other] != 0:
                bad.append(f"{lb[kind].lower()} {lb[0]} <-> {other} not a balanced mutual pair")
    return _result("transfer_pairs_zero", bad)


# 6. lifecycle ------------------------------------------------------------------------------------------------------
def check_lifecycle(d: Data) -> CheckResult:
    bad = []
    events = defaultdict(list)
    for e in d.rows["account_event"]:
        events[e[1]].append((e[3], e[2]))
    for a in d.rows["account"]:
        seq = sorted(events[a[0]], key=lambda x: (x[0], x[1] != "OPENED"))
        types = [t for _, t in seq]
        if types not in (["OPENED"], ["OPENED", "CLOSED"]):
            bad.append(f"{a[0]} events {types}")
            continue
        closed_event = seq[1][0] if len(seq) == 2 else None
        if seq[0][0] != a[7] or closed_event != a[8] or (a[9] == "CLOSED") != (a[8] is not None):
            bad.append(f"{a[0]} status/dates disagree with its events")
    return _result("lifecycle", bad)


# 7. duplicates -----------------------------------------------------------------------------------------------------
def check_duplicates(d: Data) -> CheckResult:
    i = [d.col("txn", c) for c in ("account_id", "reference_no", "amount_paise", "posted_at")]
    counts = Counter(tuple(r[j] for j in i) for r in d.rows["txn"])
    bad = [f"txn natural key {k}" for k, n in counts.items() if n > 1]
    b = Counter((r[2], r[3], r[4], r[1]) for r in d.rows["budget"])
    bad += [f"budget {k}" for k, n in b.items() if n > 1]
    return _result("duplicates", bad)


# 8. taxonomy -------------------------------------------------------------------------------------------------------
def check_taxonomy_conformance(d: Data) -> CheckResult:
    active = {c[0] for c in d.rows["category"] if c[5] is None}
    off = {b[0] for b in d.rows["budget"] if b[4] not in active}
    labelled = {a[3] for a in d.rows["anomaly"] if a[1] == "BUDGET_CATEGORY_MISMATCH"}
    bad = [f"budget {x} uses a code outside the taxonomy and is not labelled" for x in sorted(off - labelled)]
    bad += [f"budget {x} is labelled but conforms" for x in sorted(labelled - off)]
    return _result("taxonomy_conformance", bad, labelled=len(off & labelled))


def check_columns(d: Data) -> CheckResult:
    bad = [f"{n}: {hs} != schema" for n, hs in d.headers.items() if hs != [c.name for c in TABLES[n].columns]]
    return _result("columns", bad, detail="headers equal the schema column order")


# 9. ground-truth isolation -----------------------------------------------------------------------------------------
def check_truth_isolation(d: Data) -> CheckResult:
    bad = [f"inputs/{n}.csv has {h}" for n, hs in d.headers.items() if FOLDER[n] == "inputs"
           for h in hs if h.startswith("true_")]
    bad += [f"inputs/{p.name} is a ground-truth file" for p in (d.dir / "inputs").glob("*.csv")
            if p.stem in {t.name for t in schema.GT_TABLES}]
    return _result("truth_isolation", bad)


# 10. signs ---------------------------------------------------------------------------------------------------------
def check_sign_convention(d: Data) -> CheckResult:
    amt, desc = d.col("txn", "amount_paise"), d.col("txn", "descriptor")
    bad = [f"{r[0]} {r[amt]} {r[desc][:40]}" for r in d.rows["txn"]
           if r[amt] == 0 or (r[desc].startswith(DEBIT_PREFIXES) and r[amt] > 0)
           or (r[desc].startswith(CREDIT_PREFIXES) and r[amt] < 0)]
    return _result("sign_convention", bad)


# volume, files and coverage ----------------------------------------------------------------------------------------
def check_manifest(d: Data) -> CheckResult:
    bad = []
    for rel, meta in d.manifest["files"].items():
        path = d.dir / rel
        if not path.exists():
            bad.append(f"{rel} missing")
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != meta["sha256"]:
            bad.append(f"{rel} checksum differs from manifest")
        if len(d.rows[path.stem]) != meta["rows"]:
            bad.append(f"{rel} has {len(d.rows[path.stem])} rows, manifest says {meta['rows']}")
    p = d.manifest["params"]
    if len(d.rows["txn"]) != p["transactions"] or len(d.rows["user_profile"]) != p["users"]:
        bad.append("row volume differs from generation parameters")
    months = {lb[d.col("txn_label", "true_local_month")] for lb in d.rows["txn_label"]}
    if len(months) != 12:
        bad.append(f"{len(months)} business months, expected 12")
    return _result("manifest_and_volume", bad)


# structural rules that the schema documents but a CHECK constraint cannot express ---------------------------------
def check_account_rules(d: Data) -> CheckResult:
    """Account id embeds its owner; only credit cards have a limit (and always do); a card has no UPI id."""
    bad = []
    for a in d.rows["account"]:
        if "-".join(a[0].split("-")[1:3]) != a[1]:
            bad.append(f"{a[0]} does not embed its owner {a[1]}")
        card = a[2] == "CREDIT_CARD"
        if card and (a[11] is None or a[11] <= 0):
            bad.append(f"{a[0]} is a card without a positive limit")
        if not card and a[11] is not None:
            bad.append(f"{a[0]} has a credit limit but is not a card")
        if card and a[5] is not None:
            bad.append(f"{a[0]} is a card with a UPI id")
    return _result("account_rules", bad)


def check_holders(d: Data) -> CheckResult:
    """Exactly one PRIMARY holder per account, who is the owner; every holder joins inside the account's life."""
    bad, primary = [], Counter()
    life = {a[0]: (a[7], a[8], a[1]) for a in d.rows["account"]}
    for h in d.rows["account_holder"]:
        opened, closed, owner = life[h[0]]
        if h[2] == "PRIMARY":
            primary[h[0]] += 1
            if h[1] != owner:
                bad.append(f"{h[0]} primary holder {h[1]} is not the owner {owner}")
        if h[3] < opened or (closed is not None and h[3] > closed):
            bad.append(f"{h[0]} holder {h[1]} joins on {h[3]}, outside the account's life")
    bad += [f"{acc} has {primary[acc]} primary holders" for acc in life if primary[acc] != 1]
    return _result("holders", bad)


def check_balance_months(d: Data) -> CheckResult:
    """Monthly balance rows are contiguous per account, chain (opening = last closing) and stay inside its life."""
    bad = []
    life = {a[0]: (a[7], a[8]) for a in d.rows["account"]}
    by = defaultdict(list)
    for r in d.rows["account_balance_monthly"]:
        by[r[0]].append(r)
    for acc, rows in by.items():
        rows.sort(key=lambda r: r[1])
        opened, closed = life[acc]
        if rows[0][1] < month_key(opened) or (closed is not None and rows[-1][1] > month_key(closed)):
            bad.append(f"{acc} has balance months outside its life")
        for prev, cur in zip(rows, rows[1:], strict=False):
            y, m = int(prev[1][:4]), int(prev[1][5:])
            nxt = f"{y + (m == 12)}-{1 if m == 12 else m + 1:02d}"
            if cur[1] != nxt:
                bad.append(f"{acc} jumps from {prev[1]} to {cur[1]}")
            elif cur[2] != prev[5]:
                bad.append(f"{acc} {cur[1]} opens at {cur[2]} but {prev[1]} closed at {prev[5]}")
    return _result("balance_months", bad)


def check_effective_dates(d: Data) -> CheckResult:
    """Rule versions are numbered 1..n with non-decreasing start dates, and a retired version starts first;
    categories do not end before they start."""
    bad = []
    versions = defaultdict(list)
    for r in d.rows["category_rule"]:
        versions[r[0]].append(r)
        if r[11] is not None and r[11] < r[10]:
            bad.append(f"{r[0]} v{r[1]} retired before it started")
    for rid, rows in versions.items():
        rows.sort(key=lambda r: r[1])
        if [r[1] for r in rows] != list(range(1, len(rows) + 1)):
            bad.append(f"{rid} versions are {[r[1] for r in rows]}")
        if any(b[10] < a[10] for a, b in zip(rows, rows[1:], strict=False)):
            bad.append(f"{rid} versions start out of order")
    for c in d.rows["category"]:
        if c[5] is not None and c[5] < c[4]:
            bad.append(f"category {c[0]} ends before it starts")
    return _result("effective_dates", bad)


def _copy_rows(sql: Path) -> dict[str, int]:
    counts, current = {}, None
    with open(sql, encoding="utf-8", newline="") as f:
        for line in f:
            if current is None:
                if line.startswith("COPY "):
                    current = line.split()[1].split(".")[-1]
                    counts[current] = 0
            elif line == "\\.\n":
                current = None
            else:
                counts[current] += 1
    return counts


def check_artifacts(d: Data) -> CheckResult:
    """Exactly the files the manifest lists (none missing, none extra) and, when the exports exist, that the JSON
    and SQL carry the same row counts as the CSVs and match the checksums recorded in provenance.json."""
    bad = []
    listed = set(d.manifest["files"])
    present = {f"{p.parent.name}/{p.name}" for folder in ("inputs", "ground_truth") for p in (d.dir / folder).glob("*")}
    bad += [f"unexpected file {x}" for x in sorted(present - listed)]
    json_dir, sql = d.dir / "json", d.dir / "seed.sql"
    if json_dir.exists() and sql.exists():
        counts = _copy_rows(sql)
        for rel, meta in d.manifest["files"].items():
            name = Path(rel).stem
            jf = json_dir / f"{name}.json"
            if not jf.exists():
                bad.append(f"json/{name}.json missing")
                continue
            with open(jf, "rb") as f:
                json_rows = max(sum(1 for _ in f) - 2, 0)
            if json_rows != meta["rows"]:
                bad.append(f"json/{name}.json has {json_rows} rows, the CSV has {meta['rows']}")
            if counts.get(name) != meta["rows"]:
                bad.append(f"seed.sql loads {counts.get(name)} rows into {name}, the CSV has {meta['rows']}")
        prov = d.dir / "provenance.json"
        if prov.exists():
            p = json.loads(prov.read_text(encoding="utf-8"))
            if p.get("manifest_sha256") != hashlib.sha256((d.dir / "manifest.json").read_bytes()).hexdigest():
                bad.append("manifest.json differs from the checksum in provenance.json")
            for rel, meta in p.get("exports", {}).items():
                path = d.dir / rel
                if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != meta["sha256"]:
                    bad.append(f"{rel} differs from provenance.json")
            if p.get("synthetic_only") is not True:
                bad.append("provenance.json does not declare synthetic_only")
    return _result("artifacts", bad, detail="file set, JSON and SQL row counts, provenance checksums")


def check_coverage(d: Data) -> CheckResult:
    missing = set(schema.ISSUE_TYPES) - {a[1] for a in d.rows["anomaly"]}
    missing |= set(schema.TRUE_KINDS) - {lb[d.col("txn_label", "true_kind")] for lb in d.rows["txn_label"]}
    missing |= {"SALARY", "RENT", "SUBSCRIPTION", "EMI", "UTILITY", "INTEREST"} - {
        r[d.col("recurring_truth", "series_type")] for r in d.rows["recurring_truth"]}
    return _result("coverage", [f"no {m}" for m in sorted(missing)], warn=True,
                   detail="labelled issue types, true kinds and series types present")


CHECKS = [check_columns, check_pk_unique, check_fk_integrity, check_enums, check_id_formats, check_date_order,
          check_balances, check_cc_payments, check_interest_derivation, check_transfer_pairs_zero, check_lifecycle,
          check_duplicates, check_taxonomy_conformance, check_truth_isolation, check_sign_convention, check_manifest,
          check_coverage, check_account_rules, check_holders, check_balance_months, check_effective_dates,
          check_artifacts]


def validate_dataset(data_dir: Path) -> list[CheckResult]:
    d = Data(data_dir)
    return [check(d) for check in CHECKS]


def to_json(results: list[CheckResult]) -> str:
    return json.dumps([r.__dict__ for r in results], indent=2) + "\n"


def render_markdown(results: list[CheckResult], title: str) -> str:
    worst = "FAIL" if any(r.status == "FAIL" for r in results) else (
        "WARN" if any(r.status == "WARN" for r in results) else "PASS")
    out = [f"# {title}", "", f"Overall: **{worst}** ({sum(r.status == 'PASS' for r in results)}/{len(results)} "
           "checks pass)", "", "| Check | Status | Violations | Labelled | Examples |", "|---|---|---|---|---|"]
    for r in results:
        ex = "<br>".join(e.replace("|", "\\|") for e in r.examples) or (r.detail or "")
        out.append(f"| `{r.name}` | {r.status} | {r.violations} | {r.labelled} | {ex} |")
    return "\n".join(out) + "\n"
