"""Indian bank working-day rules: Sundays, 2nd and 4th Saturdays (RBI) and national holidays are closed."""
import calendar as _cal
from datetime import date, timedelta

from app.datagen.catalog import HOLIDAYS_2026


def is_bank_working_day(d: date) -> bool:
    if d.weekday() == 6 or d in HOLIDAYS_2026:
        return False
    return not (d.weekday() == 5 and (d.day - 1) // 7 + 1 in (2, 4))


def last_working_day(year: int, month: int) -> date:
    d = date(year, month, _cal.monthrange(year, month)[1])
    while not is_bank_working_day(d):
        d -= timedelta(days=1)
    return d


def next_working_day(d: date) -> date:
    while not is_bank_working_day(d):
        d += timedelta(days=1)
    return d


def clamp_day(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, _cal.monthrange(year, month)[1]))
