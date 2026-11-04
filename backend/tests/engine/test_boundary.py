import pathlib
import re


def test_engine_never_touches_ground_truth():
    root = pathlib.Path(__file__).resolve().parents[2] / "app" / "engine"
    for p in root.rglob("*.py"):
        src = p.read_text(encoding="utf-8")
        assert not re.search(r"\bgt[_.]|ground_truth|txn_label|recurring_truth|datagen", src), p
