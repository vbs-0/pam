"""Deterministic, immutable identifiers (formats fixed by the brief)."""
import re


def seq(prefix: str, n: int, width: int = 6) -> str:
    return f"{prefix}-{n:0{width}d}"


def user_id(n: int) -> str:
    return seq("USR", n)


def account_id(user: str, n: int) -> str:
    return f"ACC-{user}-{n:02d}"


def txn_id(year: int, n: int) -> str:
    return f"TXN-{year}-{n:08d}"


def budget_id(user: str, month: str, code: str) -> str:
    return f"BUD-{user}-{month}-{code}"


def series_id(n: int) -> str:
    return seq("REC", n)


def seq_number(identifier: str) -> int:
    """Trailing counter of an id like 'EXC-000042' -> 42."""
    return int(identifier.rsplit("-", 1)[1])


ID_PATTERNS = {k: re.compile(v) for k, v in {
    "user": r"USR-\d{6}", "account": r"ACC-USR-\d{6}-\d{2}", "txn": r"TXN-\d{4}-\d{8}",
    "budget": r"BUD-USR-\d{6}-\d{4}-\d{2}-[A-Za-z_]+", "series": r"REC-\d{6}", "merchant": r"MER-\d{4}",
    "rule": r"RUL-\d{4}", "truth_series": r"TRS-\d{6}", "anomaly": r"ANM-\d{6}",
    "account_event": r"AEV-\d{6}",
}.items()}
