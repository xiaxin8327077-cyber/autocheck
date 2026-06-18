from datetime import date

from auto_check.db_validation.tables import (
    ZG_TABLES,
    default_report_date,
    previous_period,
    previous_table_name,
    report_date_token,
)


def test_zg_table_mapping_contains_13_tables():
    assert len(ZG_TABLES) == 13
    assert ZG_TABLES["ZG01"] == "zgxgzh_baseinfo_zg01_26"
    assert ZG_TABLES["ZG13"] == "zgzgzh_zg13"


def test_default_report_date_is_previous_month_end():
    assert default_report_date(date(2026, 6, 5)).isoformat() == "2026-05-31"


def test_previous_period_and_table_suffix():
    current = date(2026, 5, 31)

    assert previous_period(current).isoformat() == "2026-04-30"
    assert previous_table_name("zgxgzh_projholdinfo_zg04", current) == "zgxgzh_projholdinfo_zg04_2026_04"
    assert report_date_token(current) == "20260531"
