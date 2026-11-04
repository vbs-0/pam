"""Time helpers. Storage is UTC; business dates/months are in the household's timezone (IST)."""
import calendar
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
IST_OFFSET = timedelta(hours=5, minutes=30)  # IST has no DST; used for fast bulk conversion


@lru_cache(maxsize=16)
def _tz(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def local_date(ts_utc: datetime, tz_name: str = "Asia/Kolkata") -> date:
    if ts_utc.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return ts_utc.astimezone(_tz(tz_name)).date()


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def ist_to_utc(local: datetime) -> datetime:
    """Naive IST wall-clock time -> aware UTC."""
    return (local - IST_OFFSET).replace(tzinfo=UTC)


def utc_to_ist_naive(ts: datetime) -> datetime:
    return ts.astimezone(UTC).replace(tzinfo=None) + IST_OFFSET


def iso_z(ts: datetime) -> str:
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_z(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def month_start(m: str) -> date:
    return date(int(m[:4]), int(m[5:7]), 1)


def month_end(m: str) -> date:
    y, mo = int(m[:4]), int(m[5:7])
    return date(y, mo, calendar.monthrange(y, mo)[1])


def add_months(m: str, k: int) -> str:
    y, mo = divmod(int(m[:4]) * 12 + int(m[5:7]) - 1 + k, 12)
    return f"{y:04d}-{mo + 1:02d}"


def months(year: int) -> list[str]:
    return [f"{year:04d}-{i:02d}" for i in range(1, 13)]
