from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo


BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def beijing_now() -> datetime:
    return datetime.now(BEIJING_TZ).replace(tzinfo=None)


def beijing_today() -> date:
    return beijing_now().date()


def beijing_timestamp() -> str:
    return beijing_now().isoformat(timespec="seconds")


def beijing_datetime_text() -> str:
    return beijing_now().strftime("%Y-%m-%d %H:%M:%S")


def beijing_time_text() -> str:
    return beijing_now().strftime("%H:%M:%S")
