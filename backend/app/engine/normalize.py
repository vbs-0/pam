import re

_CARD = re.compile(r"\b\d{4,6}x+\d{4}\b")
_IFSC = re.compile(r"\b[a-z]{4}0[a-z0-9]{6}\b")
_REF = re.compile(r"\b\d{6,}\b")
_NON = re.compile(r"[^a-z0-9@.]+")
_MONTHS = re.compile(r"\b(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|"
                     r"sep|sept|september|oct|october|nov|november|dec|december)\b")
_DIGITS = re.compile(r"\d+")


def normalize_descriptor(s: str) -> str:
    """Lower-case narration with card masks, IFSC codes, reference numbers and punctuation removed."""
    s = s.lower()
    s = _CARD.sub(" ", s)
    s = _IFSC.sub(" ", s)
    s = _REF.sub(" ", s)
    s = _NON.sub(" ", s)
    return " ".join(s.split())


def strip_variable(norm: str) -> str:
    """Drop tokens that change every occurrence (month names, years, numbers) so occurrences group."""
    return " ".join(_DIGITS.sub(" ", _MONTHS.sub(" ", norm)).split())
