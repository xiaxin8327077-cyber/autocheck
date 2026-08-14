from datetime import date

from auto_check.db_validation.tables import (
    ZG_CODES,
    default_report_date,
    previous_period,
    previous_table_name,
    report_date_token,
)


def test_zg_table_catalog_contains_13_logical_codes_without_physical_names():
    assert len(ZG_CODES) == 13
    assert ZG_CODES[0] == "ZG01"
    assert ZG_CODES[-1] == "ZG13"


def test_default_report_date_is_previous_month_end():
    assert default_report_date(date(2026, 6, 5)).isoformat() == "2026-05-31"


def test_previous_period_and_table_suffix():
    current = date(2026, 5, 31)

    assert previous_period(current).isoformat() == "2026-04-30"
    assert previous_table_name("zgxgzh_projholdinfo_zg04", current) == "zgxgzh_projholdinfo_zg04_2026_04"
    assert report_date_token(current) == "20260531"
