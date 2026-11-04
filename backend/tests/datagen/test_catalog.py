import re

from app.datagen import catalog
from app.engine.normalize import normalize_descriptor


def test_codes_unique_and_references_valid():
    codes = [c.code for c in catalog.CATEGORIES]
    assert len(codes) == len(set(codes))
    active = {c.code for c in catalog.CATEGORIES if c.effective_to is None}
    for m in catalog.MERCHANTS:
        assert m.category in active and set(m.extra_categories) <= active
    for syn, code in catalog.SYNONYMS.items():
        assert syn == syn.upper() and code in active
    for c in catalog.CATEGORIES:
        if c.replaced_by:
            assert c.replaced_by in active and c.effective_to is not None
    for canonical, variants in catalog.REMAP_VARIANTS.items():
        assert canonical in active and not set(variants) & active


def test_merchant_ids_and_vpas_unique():
    ids = [m.merchant_id for m in catalog.MERCHANTS]
    vpas = [m.vpa for m in catalog.MERCHANTS if m.vpa]
    assert len(ids) == len(set(ids)) and len(vpas) == len(set(vpas))
    assert all(v.split("@")[0].endswith("-mrch") for v in vpas)


def test_aliases_normalized_and_unique():
    seen = set()
    for m in catalog.MERCHANTS:
        assert len(m.aliases) >= 2, m.name
        for a in m.aliases:
            assert normalize_descriptor(a) == a, a
            assert a not in seen, a
            seen.add(a)


def test_ambiguous_merchants_exist():
    assert sum(1 for m in catalog.MERCHANTS if m.extra_categories) >= 4


def test_rules_valid_and_ordered_ids():
    rules = catalog.seed_rules()
    ids = [r["rule_id"] for r in rules]
    assert len(ids) == len(set(ids)) and ids[0] == "RUL-0001"
    merchants = {m.merchant_id for m in catalog.MERCHANTS}
    codes = {c.code for c in catalog.CATEGORIES if c.effective_to is None}
    for r in rules:
        assert r["category_code"] in codes
        assert r["merchant_id"] is None or r["merchant_id"] in merchants
        if r["pattern"]:
            re.compile(r["pattern"])
            assert len(r["pattern"]) <= 200
        assert any(r[k] for k in ("merchant_id", "pattern", "channel", "account_type"))


def test_subscriptions_and_utilities_reference_real_merchants():
    ids = {m.merchant_id for m in catalog.MERCHANTS}
    assert {s[0] for s in catalog.SUBSCRIPTIONS} <= ids
    assert set(catalog.UTILITY_BY_STATE.values()) | {catalog.DEFAULT_UTILITY, catalog.DTH} <= ids
    assert set(catalog.BROADBAND) | {m[0] for m in catalog.MOBILE} | set(catalog.LENDERS) <= ids


def test_seasonality_and_persona_weights_shape():
    assert all(len(v) == 12 for v in catalog.SEASONALITY.values())
    assert catalog.SEASONALITY["SHOPPING"][9] > 1.4 and catalog.SEASONALITY["SHOPPING"][10] > 1.4
    for w in catalog.PERSONA_WEIGHTS.values():
        assert abs(sum(w.values()) - 1.0) < 1e-9
