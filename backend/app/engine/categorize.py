"""Rule-based categorization with merchant resolution (VPA first, then longest alias) and a decision cache.

Rules are evaluated in (priority, rule_id) order; every non-null condition must hold. Decisions are cached on
the normalized descriptor plus the other rule inputs, so the same merchant with a different RRN is a cache hit.
"""
import re
from dataclasses import dataclass

from app.engine.types import Txn


@dataclass(slots=True, frozen=True)
class Rule:
    rule_id: str
    version: int
    priority: int
    category_code: str
    confidence: float
    merchant_id: str | None = None
    pattern: str | None = None
    channel: str | None = None
    direction: str = "ANY"
    account_type: str | None = None


class Categorizer:
    def __init__(self, rules: list[Rule], merchant_by_vpa: dict[str, str], aliases: dict[str, str]):
        self.rules = sorted(rules, key=lambda r: (r.priority, r.rule_id))
        self._rx = {(r.rule_id, r.version): re.compile(r.pattern) for r in self.rules if r.pattern}
        self.vpa = {k.lower(): v for k, v in merchant_by_vpa.items()}
        self.alias = {k.lower(): v for k, v in aliases.items()}
        alts = sorted(self.alias, key=len, reverse=True)   # longest first: "amazon fresh" beats "amazon" (E01)
        self._alias_rx = (re.compile(r"(?<![a-z0-9])(" + "|".join(map(re.escape, alts)) + r")(?![a-z0-9])")
                          if alts else None)
        self._cache: dict[tuple, tuple[str | None, Rule | None]] = {}
        self.cache_hits = 0

    def resolve_merchant(self, norm: str, vpa: str | None) -> str | None:
        if vpa and vpa.lower() in self.vpa:                 # a registered VPA beats any text (E02)
            return self.vpa[vpa.lower()]
        if self._alias_rx and (m := self._alias_rx.search(norm)):
            return self.alias[m.group(1)]
        return None

    def categorize(self, t: Txn, norm: str) -> tuple[str | None, Rule | None]:
        direction = "DR" if t.amount_paise < 0 else "CR"
        key = (norm, t.counterparty_vpa, t.channel, direction, t.account_type)
        hit = self._cache.get(key)
        if hit is not None:
            self.cache_hits += 1
            return hit
        merchant = self.resolve_merchant(norm, t.counterparty_vpa)
        found = None
        for r in self.rules:
            if r.merchant_id and r.merchant_id != merchant:
                continue
            if r.channel and r.channel != t.channel:
                continue
            if r.direction != "ANY" and r.direction != direction:
                continue
            if r.account_type and r.account_type != t.account_type:
                continue
            if r.pattern and not self._rx[(r.rule_id, r.version)].search(norm):
                continue
            found = r
            break
        self._cache[key] = (merchant, found)
        return merchant, found
