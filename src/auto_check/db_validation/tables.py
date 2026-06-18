from __future__ import annotations

from calendar import monthrange
from datetime import date


ZG_TABLES: dict[str, str] = {
    "ZG01": "zgxgzh_baseinfo_zg01_26",
    "ZG02": "zgxgzh_begraiseinfo_zg02_26",
    "ZG03": "zgxgzh_projendinfo_zg03_26",
    "ZG04": "zgxgzh_projholdinfo_zg04",
    "ZG05": "zgxgzh_projdebt_zg05_2024",
    "ZG06": "zgxgzh_beneficial_zg06",
    "ZG07": "zgxgzh_ioudetail_zg07",
    "ZG08": "zgxgzh_spvdetail_zg08",
    "ZG09": "zgxgzh_debtordate_zg09",
    "ZG10": "zgxgzh_surecinfo_zg10",
    "ZG11": "zgxgzh_industinfo_zg11",
    "ZG12": "zgzgzh_zg12",
    "ZG13": "zgzgzh_zg13",
}

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
