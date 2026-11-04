"""The decision pipeline: categorize → overrides → reversals/refunds → transfer pairing → recurring series →
budgets, insights and the exception queue. Pure function of its input; the job layer persists the output."""
from dataclasses import dataclass, field
from datetime import date

from app import schema
from app.engine.budgets import BudgetIn, income_by_month, resolve_budgets, spend_by_category
from app.engine.categorize import Categorizer, Rule
from app.engine.insights import build_insights
from app.engine.normalize import normalize_descriptor
from app.engine.recurring import detect_recurring
from app.engine.refunds import link_refunds
from app.engine.transfers import match_transfers
from app.engine.types import Category, Enriched, Txn, kind_for
from app.timeutil import local_date, month_end, month_key


@dataclass(slots=True)
class EngineInput:
    txns: list[Txn]
    user_tz: dict[str, str]
    own_vpas: dict[str, set[str]]
    categories: dict[str, Category]
    synonyms: dict[str, str]
    rules: list[Rule]
    merchant_by_vpa: dict[str, str]
    aliases: dict[str, str]
    overrides: dict[str, tuple[str, str]] = field(default_factory=dict)
    budgets: list[BudgetIn] = field(default_factory=list)
    data_end: date = date(2026, 12, 31)
    closed_accounts: dict[str, date] = field(default_factory=dict)
    merchant_names: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ExceptionRow:
    exception_type: str
    entity_type: str
    entity_id: str
    user_id: str | None
    detail: dict


@dataclass(slots=True)
class EngineOutput:
    enriched: list[Enriched]
    series: list
    resolutions: list
    insights: list
    exceptions: list[ExceptionRow]
    stats: dict


def effective_kind(category_kind: str, amount_paise: int) -> str:
    """Kind after a human changes the category (used by the API between runs)."""
    return kind_for(category_kind, amount_paise)


def run_engine(inp: EngineInput) -> EngineOutput:
    cat = Categorizer(inp.rules, inp.merchant_by_vpa, inp.aliases)
    items: list[Enriched] = []
    for t in inp.txns:
        d = local_date(t.posted_at, inp.user_tz.get(t.user_id, "Asia/Kolkata"))      # ★A4: business date
        e = Enriched(t, normalize_descriptor(t.descriptor), d, month_key(d))
        if t.counterparty_vpa and t.counterparty_vpa.lower() in inp.own_vpas.get(t.user_id, ()):
            e.category_code, e.rule_id, e.confidence, e.decision = "SELF_TRANSFER", "SYS-OWNVPA", 0.99, "OWN_VPA"
        else:
            e.merchant_id, rule = cat.categorize(t, e.norm)
            if rule:
                e.category_code, e.rule_id, e.rule_version = rule.category_code, rule.rule_id, rule.version
                e.confidence, e.decision = float(rule.confidence), "RULE"
        if ov := inp.overrides.get(t.txn_id):                                         # E14: humans win
            e.category_code, e.decision, e.locked, e.confidence = ov[0], f"OVERRIDE:{ov[1]}", True, 1.0
            e.rule_id, e.rule_version = None, None
        e.kind = kind_for(inp.categories[e.category_code].kind, t.amount_paise)
        items.append(e)
    stats = {"txns": len(items), "cache_hits": cat.cache_hits}
    stats.update(link_refunds(items, inp.categories))           # reversals first: same account + RRN is certain
    stats["transfer_pairs"] = match_transfers(items, inp.categories)
    series = detect_recurring(items, inp.data_end, closed=inp.closed_accounts)
    stats["series"] = len(series)
    rows = [(e.txn.user_id, e.local_month, e.category_code, e.kind, e.txn.amount_paise) for e in items]
    spend, income = spend_by_category(rows), income_by_month(rows)
    resolutions = resolve_budgets(inp.budgets, inp.categories, inp.synonyms)
    months = sorted({e.local_month for e in items})
    names = {c.code: c.name or c.code for c in inp.categories.values()}
    insights = build_insights(spend, income, resolutions, series, months, names, inp.merchant_names)
    exceptions = _exceptions(items, resolutions, series)
    stats.update(insights=len(insights), exceptions=len(exceptions))
    return EngineOutput(items, series, resolutions, insights, exceptions, stats)


def _exceptions(items: list[Enriched], resolutions, series) -> list[ExceptionRow]:
    out = []
    for e in items:
        if e.locked:
            continue
        if e.kind == "UNKNOWN":
            out.append(ExceptionRow("UNCATEGORIZED", "TXN", e.txn.txn_id, e.txn.user_id,
                                    {"descriptor": e.txn.descriptor, "amount_paise": e.txn.amount_paise}))
        elif e.kind == "TRANSFER" and e.link_txn_id is None:                            # E09
            out.append(ExceptionRow("UNMATCHED_TRANSFER", "TXN", e.txn.txn_id, e.txn.user_id,
                                    {"rule": e.rule_id, "amount_paise": e.txn.amount_paise}))
        elif e.decision == "REFUND_ORPHAN":
            out.append(ExceptionRow("ORPHAN_REFUND", "TXN", e.txn.txn_id, e.txn.user_id,
                                    {"merchant": e.merchant_id, "amount_paise": e.txn.amount_paise}))
    for r in resolutions:
        if r.resolution == "UNMAPPED":
            out.append(ExceptionRow("BUDGET_CATEGORY_UNMAPPED", "BUDGET", r.budget_id, r.user_id,
                                    {"submitted": r.submitted_code, "month": r.month}))
    for s in series:
        if s.status == "MISSED":
            out.append(ExceptionRow("RECURRING_MISSED", "SERIES", "|".join(s.key), s.key[0],
                                    {"next_expected": str(s.next_expected)}))
    return out


def _ix(t) -> dict[str, int]:
    return {c.name: i for i, c in enumerate(t.columns)}


def input_from_rows(tables: dict[str, list[tuple]]) -> EngineInput:
    """Build the engine input from input-table rows (schema column order) — files, the DB or the generator."""
    A, T, U = _ix(schema.account), _ix(schema.txn), _ix(schema.user_profile)
    C, R, M = _ix(schema.category), _ix(schema.category_rule), _ix(schema.merchant)
    B = _ix(schema.budget)
    accounts = {a[A["account_id"]]: a for a in tables["account"]}
    own: dict[str, set[str]] = {}
    for a in accounts.values():
        if a[A["vpa"]]:
            own.setdefault(a[A["user_id"]], set()).add(a[A["vpa"]].lower())
    txns = [Txn(r[T["txn_id"]], r[T["user_id"]], r[T["account_id"]], accounts[r[T["account_id"]]][A["account_type"]],
                r[T["posted_at"]], r[T["amount_paise"]], r[T["channel"]], r[T["descriptor"]],
                r[T["counterparty_vpa"]], r[T["reference_no"]]) for r in tables["txn"]]
    latest: dict[str, tuple] = {}
    for r in tables["category_rule"]:
        if r[R["retired_at"]] is None and (r[R["rule_id"]] not in latest
                                           or r[R["version"]] > latest[r[R["rule_id"]]][R["version"]]):
            latest[r[R["rule_id"]]] = r
    rules = [Rule(r[R["rule_id"]], r[R["version"]], r[R["priority"]], r[R["category_code"]], float(r[R["confidence"]]),
                  r[R["merchant_id"]], r[R["pattern"]], r[R["channel"]], r[R["direction"]], r[R["account_type"]])
             for r in latest.values()]
    last = max((local_date(t.posted_at) for t in txns), default=date(2026, 12, 31))
    return EngineInput(
        txns=txns,
        user_tz={u[U["user_id"]]: u[U["timezone"]] for u in tables["user_profile"]},
        own_vpas=own,
        categories={c[C["category_code"]]: Category(c[C["category_code"]], c[C["kind"]], c[C["effective_from"]],
                                                    c[C["effective_to"]], c[C["replaced_by"]], c[C["name"]])
                    for c in tables["category"]},
        synonyms=dict(tables["category_synonym"]),
        rules=rules,
        merchant_by_vpa={m[M["vpa"]]: m[M["merchant_id"]] for m in tables["merchant"] if m[M["vpa"]]},
        aliases=dict(tables["merchant_alias"]),
        budgets=[BudgetIn(b[B["budget_id"]], b[B["version"]], b[B["user_id"]], b[B["month"]], b[B["category_code"]],
                          b[B["amount_paise"]]) for b in tables["budget"]],
        data_end=month_end(month_key(last)),
        closed_accounts={k: a[A["closed_on"]] for k, a in accounts.items() if a[A["closed_on"]]},
        merchant_names={m[M["merchant_id"]]: m[M["name"]] for m in tables["merchant"]},
    )
