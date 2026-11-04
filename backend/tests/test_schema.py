import pytest
from sqlalchemy import CheckConstraint, inspect

from app import schema
from app.docs_gen import render_data_dictionary


def test_every_column_documented_and_enums_checked():
    for t in schema.metadata.sorted_tables:
        assert t.comment, f"{t.fullname} lacks a table comment"
        checks = {c.name for c in t.constraints if isinstance(c, CheckConstraint)}
        for c in t.columns:
            assert c.info.get("desc"), f"{t.fullname}.{c.name} lacks description"
            if c.info.get("allowed"):
                assert any(n.endswith(f"{c.name}_allowed") for n in checks), f"{t.fullname}.{c.name} lacks enum check"


def test_every_table_has_primary_key():
    for t in schema.metadata.sorted_tables:
        assert t.primary_key.columns, t.fullname


def test_table_groups_cover_core_entities():
    names = {t.fullname for t in schema.INPUT_TABLES + schema.GT_TABLES + schema.OUTPUT_TABLES}
    for core in ["user_profile", "account", "merchant", "txn", "category", "category_rule", "budget",
                 "recurring_series", "insight", "account_holder", "merchant_category", "gt.txn_label",
                 "gt.anomaly", "gt.recurring_truth"]:
        assert core in names


def test_load_order_parents_first():
    order = [t.fullname for t in schema.INPUT_TABLES + schema.GT_TABLES]
    for t in schema.INPUT_TABLES + schema.GT_TABLES:
        for fk in t.foreign_keys:
            parent = fk.column.table.fullname
            if parent in order and parent != t.fullname:
                assert order.index(parent) < order.index(t.fullname), (t.fullname, parent)


def test_inputs_never_contain_truth_columns():
    for t in schema.INPUT_TABLES:
        assert not any(c.name.startswith("true_") for c in t.columns), t.name


def test_data_dictionary_mentions_every_table():
    md = render_data_dictionary()
    for t in schema.metadata.sorted_tables:
        assert f"`{t.fullname}`" in md
    assert "| Column | Type | Required | Allowed values | Unit | Unique | Validation | Description |" in md
    assert "N:M" in md


@pytest.mark.db
def test_migration_creates_all_tables(db_engine):
    insp = inspect(db_engine)
    public = set(insp.get_table_names())
    gt = set(insp.get_table_names(schema="gt"))
    assert {t.name for t in schema.metadata.sorted_tables if t.schema is None} <= public
    assert {"txn_label", "anomaly", "recurring_truth"} <= gt
