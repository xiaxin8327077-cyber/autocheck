from __future__ import annotations

from calendar import monthrange
from datetime import date


ZG_CODES: tuple[str, ...] = tuple(f"ZG{index:02d}" for index in range(1, 14))

DETAIL_TABLE_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "ZG04": ("ZG03", "ZG05"),
    "ZG05": ("ZG07", "ZG08"),
    "ZG08": ("ZG01",),
    "ZG12": ("ZG01", "ZG05"),
    "ZG13": ("ZG05",),
}


def detail_table_codes_with_dependencies(table_codes: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """Return selected detail tables followed by the tables their rules read directly."""
    result: list[str] = []
    seen: set[str] = set()
    for value in table_codes:
        code = str(value or "").strip().upper()
        if not code:
            continue
        for current in (code, *DETAIL_TABLE_DEPENDENCIES.get(code, ())):
            if current not in seen:
                seen.add(current)
                result.append(current)
    return tuple(result)

def month_end(year: int, month: int) -> date:
    return date(year, month, monthrange(year, month)[1])


def shift_month(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year = month_index // 12
    month = month_index % 12 + 1
    return month_end(year, month)


def default_report_date(today: date) -> date:
    return shift_month(today.replace(day=1), -1)


def previous_period(report_date: date) -> date:
    return shift_month(report_date.replace(day=1), -1)


def previous_suffix(report_date: date) -> str:
    prev = previous_period(report_date)
    return f"_{prev.year:04d}_{prev.month:02d}"


def previous_table_name(base_table: str, report_date: date) -> str:
    return f"{base_table}{previous_suffix(report_date)}"


def report_date_token(report_date: date) -> str:
    return report_date.strftime("%Y%m%d")
