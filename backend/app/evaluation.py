"""Score a pipeline run against ground truth. Pure functions; the job layer feeds rows from files or the DB.

This module is the only place ground truth meets decisions — the engine never imports it.
"""
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime

THRESHOLDS = {  # spec §8 acceptance targets (starter dataset)
    "category_accuracy": (">=", 0.85), "transfer_f1": (">=", 0.95), "refund_link_recall": (">=", 0.90),
    "tz_boundary_month_accuracy": ("==", 1.0), "budget_mismatch_handling": ("==", 1.0),
    "series_recall": (">=", 0.85), "missed_precision": (">=", 0.80), "missed_recall": (">=", 0.80),
    "decoy_false_alarm_rate": ("<=", 0.10),
}
NAIVE_INCOME = re.compile(r"salary|pension|int\.pd", re.I)
TOL_DAYS = 7


@dataclass(slots=True, frozen=True)
class Decided:
    txn_id: str
    user_id: str
    local_month: str
    category_code: str
    kind: str
    link_txn_id: str | None
    series_id: str | None
    amount_paise: int
    posted_at: datetime
    descriptor: str


def _utc_month(ts: datetime) -> str:
    u = ts.astimezone(UTC)
    return f"{u.year:04d}-{u.month:02d}"          # 3x faster than strftime over 500k rows


def _r(x: float) -> float:
    return round(x, 4)


def prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": _r(p), "recall": _r(r), "f1": _r(f), "tp": tp, "fp": fp, "fn": fn}


def set_prf(pred: set, truth: set) -> dict:
    return prf(len(pred & truth), len(pred - truth), len(truth - pred))


def classification_report(pairs: list[tuple[str, str]]) -> dict:
    """pairs = (true, predicted). Macro-F1 over classes that occur in the truth."""
    confusion = Counter(f"{t}|{p}" for t, p in pairs)
    true_n, pred_n = Counter(t for t, _ in pairs), Counter(p for _, p in pairs)
    per = {}
    for c in sorted(true_n | pred_n):
        tp = confusion.get(f"{c}|{c}", 0)
        m = prf(tp, pred_n[c] - tp, true_n[c] - tp)
        per[c] = {"precision": m["precision"], "recall": m["recall"], "f1": m["f1"], "support": true_n[c]}
    supported = [v["f1"] for v in per.values() if v["support"]]
    return {"accuracy": _r(sum(t == p for t, p in pairs) / len(pairs)) if pairs else 0.0,
            "macro_f1": _r(sum(supported) / len(supported)) if supported else 0.0,
            "per_class": per, "confusion": dict(sorted(confusion.items()))}


def match_series(pred: dict[str, set[str]], truth: dict[str, set[str]]) -> dict[str, str]:
    """truth id -> predicted id whose members cover >= 50% of the truth members (best overlap wins)."""
    owner = {t: s for s, members in pred.items() for t in members}
    out = {}
    for tid, members in truth.items():
        votes = Counter(owner[t] for t in members if t in owner)
        if votes:
            sid, n = min(votes.items(), key=lambda kv: (-kv[1], kv[0]))
            if n >= 0.5 * len(members):
                out[tid] = sid
    return out


def missed_event_eval(pred_events: list[tuple[str, date]], skips: list[tuple[str, date]],
                      decoys: list[tuple[str, date]], truth_to_pred: dict[str, str], tol_days: int = TOL_DAYS) -> dict:
    """An event is a hit if it belongs to the series matched to a labelled skip and lies within ±tol days."""
    by_series = defaultdict(list)
    for sid, d in pred_events:
        by_series[sid].append(d)

    def near(tid: str, d: date) -> list[date]:
        sid = truth_to_pred.get(tid)
        return [x for x in by_series.get(sid, []) if abs((x - d).days) <= tol_days] if sid else []

    hit_events = {(truth_to_pred[t], x) for t, d in skips for x in near(t, d)}
    caught = sum(1 for t, d in skips if near(t, d))
    alarms = sum(1 for t, d in decoys if near(t, d))
    return {"precision": _r(len(hit_events) / len(pred_events)) if pred_events else 0.0,
            "recall": _r(caught / len(skips)) if skips else 0.0,
            "decoy_false_alarm_rate": _r(alarms / len(decoys)) if decoys else 0.0,
            "predicted_events": len(pred_events), "skips": len(skips), "decoys": len(decoys)}


def naive_spend(rows: list[Decided]) -> dict[tuple[str, str], int]:
    """What a naive ledger reports: every debit and every non-salary credit is spending, bucketed by UTC month."""
    out: dict[tuple[str, str], int] = defaultdict(int)
    for d in rows:
        if d.amount_paise < 0 or not NAIVE_INCOME.search(d.descriptor):
            out[(d.user_id, _utc_month(d.posted_at))] += abs(d.amount_paise)
    return dict(out)


def _spend(rows) -> dict[tuple[str, str, str], int]:
    out: dict[tuple[str, str, str], int] = defaultdict(int)
    for user, month, cat, kind, amt in rows:
        if kind in ("EXPENSE", "REFUND") or (kind == "UNKNOWN" and amt < 0):
            out[(user, month, cat)] -= amt
    return out


def evaluate(decided: list[Decided], labels: list[tuple], truth_series: list[tuple], anomalies: list[tuple],
             series_events: list[tuple[str, str, date]], resolutions: dict[str, tuple[str | None, str]],
             exceptions: set[tuple[str, str]]) -> dict:
    """labels / truth_series / anomalies are ground-truth rows in schema column order."""
    d = {x.txn_id: x for x in decided}
    lab = {lb[0]: lb for lb in labels}                     # txn_id, merchant, category, kind, link, series, month

    cat = classification_report([(lab[t][2], x.category_code) for t, x in d.items()])
    kind = classification_report([(lab[t][3], x.kind) for t, x in d.items()])
    coverage = _r(sum(x.category_code != "UNCATEGORIZED" for x in decided) / len(decided)) if decided else 0.0

    def links(source, kinds, pair):
        out = set()
        for t, link, k in source:
            if k in kinds and link:
                out.add(frozenset((t, link)) if pair else (t, link))
        return out
    truth_l = [(t, lb[4], lb[3]) for t, lb in lab.items()]
    pred_l = [(x.txn_id, x.link_txn_id, x.kind) for x in decided]
    transfers = set_prf(links(pred_l, {"TRANSFER"}, True), links(truth_l, {"TRANSFER"}, True))
    refunds = set_prf(links(pred_l, {"REFUND"}, False), links(truth_l, {"REFUND"}, False))
    reversals = set_prf(links(pred_l, {"REVERSAL"}, True), links(truth_l, {"REVERSAL"}, True))

    pred_members: dict[str, set[str]] = defaultdict(set)
    for x in decided:
        if x.series_id:
            pred_members[x.series_id].add(x.txn_id)
    truth_members: dict[str, set[str]] = defaultdict(set)
    for t, lb in lab.items():
        if lb[5]:
            truth_members[lb[5]].add(t)
    t2p = match_series(pred_members, truth_members)
    series = {"series": prf(len(set(t2p.values())), len(pred_members) - len(set(t2p.values())),
                            len(truth_members) - len(t2p)),
              "members": set_prf({t for m in pred_members.values() for t in m},
                                 {t for m in truth_members.values() for t in m}),
              "by_type": {}}
    for st in sorted({r[3] for r in truth_series}):
        ids = [r[0] for r in truth_series if r[3] == st]
        series["by_type"][st] = {"truth": len(ids), "matched": sum(i in t2p for i in ids)}
    pred_missed = [(s, dt) for s, et, dt in series_events if et == "MISSED"]
    skips = [(a[3], a[6]) for a in anomalies if a[1] == "RECURRING_SKIP"]
    decoys = [(a[3], a[6]) for a in anomalies if a[1] == "RECURRING_NOT_SKIP"]
    missed = missed_event_eval(pred_missed, skips, decoys, t2p)

    tz_ids = [a[3] for a in anomalies if a[1] == "TZ_BOUNDARY"]
    tz = {"month_accuracy": _r(sum(x.local_month == lab[t][6] for t, x in d.items()) / len(d)) if d else 0.0,
          "naive_utc_month_accuracy": _r(sum(_utc_month(x.posted_at) == lab[t][6]
                                             for t, x in d.items()) / len(d)) if d else 0.0,
          "tz_boundary_month_accuracy": _r(sum(d[t].local_month == lab[t][6] for t in tz_ids) / len(tz_ids))
          if tz_ids else 0.0, "tz_boundary_cases": len(tz_ids)}

    truth_spend = _spend((x.user_id, lab[t][6], lab[t][2], lab[t][3], x.amount_paise) for t, x in d.items())
    pred_spend = _spend((x.user_id, x.local_month, x.category_code, x.kind, x.amount_paise) for x in decided)
    keys = set(truth_spend) | set(pred_spend)
    mae = sum(abs(truth_spend.get(k, 0) - pred_spend.get(k, 0)) for k in keys) / len(keys) if keys else 0.0
    naive = naive_spend(decided)
    totals = {"truth": sum(truth_spend.values()), "system": sum(pred_spend.values()), "naive": sum(naive.values())}

    outcomes = anomaly_outcomes(anomalies, d, t2p, pred_missed, resolutions, exceptions)
    by_issue: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for o in outcomes:
        by_issue[o["issue_type"]][0] += o["outcome"] == "CAUGHT"
        by_issue[o["issue_type"]][1] += 1
    recall_by_issue = {k: {"caught": c, "total": n, "recall": _r(c / n)} for k, (c, n) in sorted(by_issue.items())}
    mismatch = recall_by_issue.get("BUDGET_CATEGORY_MISMATCH", {"recall": 0.0})["recall"]

    headline = {"category_accuracy": cat["accuracy"], "transfer_f1": transfers["f1"],
                "refund_link_recall": refunds["recall"], "tz_boundary_month_accuracy": tz["tz_boundary_month_accuracy"],
                "budget_mismatch_handling": mismatch, "series_recall": series["series"]["recall"],
                "missed_precision": missed["precision"], "missed_recall": missed["recall"],
                "decoy_false_alarm_rate": missed["decoy_false_alarm_rate"]}
    checks = {k: {"value": v, "target": f"{THRESHOLDS[k][0]} {THRESHOLDS[k][1]}", "pass": _meets(v, *THRESHOLDS[k])}
              for k, v in headline.items()}
    return {
        "headline": headline, "thresholds": checks, "all_pass": all(c["pass"] for c in checks.values()),
        "categorization": {**cat, "coverage": coverage}, "kind": kind,
        "transfers": transfers, "refund_links": refunds, "reversals": reversals,
        "recurring": {**series, "missed_events": missed}, "timezone": tz,
        "budgets": {"spend_mae_paise": round(mae), "user_month_category_cells": len(keys)},
        "naive_baseline": {"totals_paise": totals,
                           "naive_overstatement": _r(totals["naive"] / totals["truth"] - 1) if totals["truth"] else 0.0,
                           "system_error": _r(totals["system"] / totals["truth"] - 1) if totals["truth"] else 0.0},
        "anomalies": recall_by_issue, "anomaly_outcomes": outcomes,
    }


def _meets(v: float, op: str, target: float) -> bool:
    return v >= target if op == ">=" else v <= target if op == "<=" else v == target


def anomaly_outcomes(anomalies: list[tuple], d: dict[str, Decided], t2p: dict[str, str],
                     pred_missed: list[tuple[str, date]], resolutions: dict[str, tuple[str | None, str]],
                     exceptions: set[tuple[str, str]]) -> list[dict]:
    missed_by_series = defaultdict(list)
    for s, dt in pred_missed:
        missed_by_series[s].append(dt)
    out = []
    for a in anomalies:
        aid, issue, _etype, ent, related, expected, exp_date = a[:7]
        if issue == "TRANSFER_DOUBLE_COUNT":
            legs = [d[ent], d[related]]
            ok = all(x.kind == "TRANSFER" for x in legs)
            seen = f"debit {legs[0].kind}/{legs[0].category_code}, credit {legs[1].kind}/{legs[1].category_code}"
        elif issue == "REFUND_AS_EXPENSE":
            x = d[ent]
            ok = x.kind == "REFUND" and x.link_txn_id == related
            seen = f"{x.kind} linked to {x.link_txn_id or 'nothing'} as {x.category_code}"
        elif issue in ("RECURRING_SKIP", "RECURRING_NOT_SKIP"):
            sid = t2p.get(ent)
            near = [x for x in missed_by_series.get(sid, []) if abs((x - exp_date).days) <= TOL_DAYS] if sid else []
            ok = bool(near) if issue == "RECURRING_SKIP" else not near
            seen = (f"series {sid}: MISSED on {near[0]}" if near else
                    f"series {sid}: no MISSED event near {exp_date}" if sid else "series not detected")
        elif issue == "TZ_BOUNDARY":
            x = d[ent]
            ok = f"MONTH:{x.local_month}" == expected
            seen = f"booked in {x.local_month}"
        else:                                              # BUDGET_CATEGORY_MISMATCH
            code, how = resolutions.get(ent, (None, "MISSING"))
            if expected.startswith("REMAP_TO:"):
                ok = code == expected.split(":", 1)[1]
            else:
                ok = how == "UNMAPPED" and ("BUDGET_CATEGORY_UNMAPPED", ent) in exceptions
            seen = f"{how} -> {code}"
        out.append({"anomaly_id": aid, "issue_type": issue, "outcome": "CAUGHT" if ok else "MISSED", "observed": seen})
    return out


def from_engine(out) -> tuple[list[Decided], list[tuple[str, str, date]], dict, set]:
    """Adapt an EngineOutput (series ids = natural keys) for evaluate()."""
    decided = [Decided(e.txn.txn_id, e.txn.user_id, e.local_month, e.category_code, e.kind, e.link_txn_id,
                       "|".join(e.series_key) if e.series_key else None, e.txn.amount_paise, e.txn.posted_at,
                       e.txn.descriptor) for e in out.enriched]
    events = [("|".join(s.key), et, dt) for s in out.series for et, dt, _ in s.events]
    resolutions = {r.budget_id: (r.resolved_code, r.resolution) for r in out.resolutions}
    exceptions = {(x.exception_type, x.entity_id) for x in out.exceptions}
    return decided, events, resolutions, exceptions


def render_markdown(m: dict, title: str) -> str:
    from app.money import fmt_inr

    def pct(x: float) -> str:
        return f"{x:.2%}"

    out = [f"# {title}", "", f"All acceptance targets met: **{'yes' if m['all_pass'] else 'no'}**", "",
           "| Metric | Value | Target | Pass |", "|---|---|---|---|"]
    out += [f"| {k} | {v['value']:.4f} | {v['target']} | {'✅' if v['pass'] else '❌'} |"
            for k, v in m["thresholds"].items()]
    out += ["", "## Labelled anomalies", "", "| Issue | Caught | Total | Recall |", "|---|---|---|---|"]
    out += [f"| {k} | {v['caught']} | {v['total']} | {pct(v['recall'])} |" for k, v in m["anomalies"].items()]
    c, nb = m["categorization"], m["naive_baseline"]
    out += ["", "## Categorization", "",
            f"Accuracy {pct(c['accuracy'])} · macro-F1 {c['macro_f1']:.4f} · coverage {pct(c['coverage'])} · "
            f"kind accuracy {pct(m['kind']['accuracy'])}", "",
            "| Category | Precision | Recall | F1 | Support |", "|---|---|---|---|---|"]
    out += [f"| {k} | {v['precision']:.3f} | {v['recall']:.3f} | {v['f1']:.3f} | {v['support']} |"
            for k, v in c["per_class"].items() if v["support"]]
    out += ["", "## Links", "", "| Link | Precision | Recall | F1 |", "|---|---|---|---|"]
    out += [f"| {name} | {m[k]['precision']:.4f} | {m[k]['recall']:.4f} | {m[k]['f1']:.4f} |"
            for name, k in (("Transfer pairs", "transfers"), ("Refund → purchase", "refund_links"),
                            ("Reversal pairs", "reversals"))]
    r, me = m["recurring"], m["recurring"]["missed_events"]
    out += ["", "## Recurring payments", "",
            f"Series precision {r['series']['precision']:.4f}, recall {r['series']['recall']:.4f}; member F1 "
            f"{r['members']['f1']:.4f}. MISSED events: precision {me['precision']:.4f}, recall {me['recall']:.4f} "
            f"({me['skips']} labelled skips), decoy false-alarm rate {me['decoy_false_alarm_rate']:.4f} "
            f"({me['decoys']} decoys).", "", "| Type | Truth series | Matched |", "|---|---|---|"]
    out += [f"| {k} | {v['truth']} | {v['matched']} |" for k, v in r["by_type"].items()]
    tz = m["timezone"]
    out += ["", "## Time zone and budgets", "",
            f"IST month accuracy {pct(tz['month_accuracy'])} vs naive UTC {pct(tz['naive_utc_month_accuracy'])}; "
            f"TZ-boundary cases {tz['tz_boundary_cases']} at {pct(tz['tz_boundary_month_accuracy'])}. Spend MAE per "
            f"user-month-category {fmt_inr(m['budgets']['spend_mae_paise'])} over "
            f"{m['budgets']['user_month_category_cells']} cells.", "", "## Naive ledger baseline", "",
            "| Ledger | Total spend |", "|---|---|",
            f"| Ground truth | {fmt_inr(nb['totals_paise']['truth'])} |",
            f"| PAM | {fmt_inr(nb['totals_paise']['system'])} ({nb['system_error']:+.2%}) |",
            f"| Naive (all debits + non-salary credits, UTC months) | {fmt_inr(nb['totals_paise']['naive'])} "
            f"({nb['naive_overstatement']:+.2%}) |"]
    return "\n".join(out) + "\n"
