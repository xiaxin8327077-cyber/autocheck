from __future__ import annotations

from contextlib import contextmanager
from datetime import date

import pytest


class _Result:
    def keys(self):
        return ("report_type", "reporting_date")

    def fetchmany(self, size):
        assert size == 11
        return [("1104", date(2026, 9, 20))]

    def fetchall(self):
        return [("1104", date(2026, 9, 20))]


class _Connection:
    def __init__(self):
        self.sql = ""

    def execute(self, statement):
        self.sql = str(statement)
        return _Result()


class _Database:
    class Config:
        database = "autocheck"

    config = Config()

    def __init__(self):
        self.connection = _Connection()

    @contextmanager
    def connect(self):
        yield self.connection


def test_system_query_catalog_explains_all_six_system_sources():
    from auto_check.modules.dashboard_management.system_data import SYSTEM_QUERY_DEFINITIONS

    assert set(SYSTEM_QUERY_DEFINITIONS) == {
        "annual_supplement_completed",
        "monthly_report_validation_remaining",
        "report_reconciliation_completion_time",
        "quarterly_special_processing",
        "monthly_report_submission_time_comparison",
        "monthly_regulatory_report_time",
    }
    assert SYSTEM_QUERY_DEFINITIONS["annual_supplement_completed"].tables == (
        "report_nav_card_snapshots",
    )
    source = SYSTEM_QUERY_DEFINITIONS["annual_supplement_completed"].public_value(_Database())
    assert source["table_details"] == [
        {"name": "report_nav_card_snapshots", "display_name": "报送导航统计卡快照"},
    ]
    assert source["sql"].startswith(
        "-- 数据表：报送导航统计卡快照（report_nav_card_snapshots）"
    )
    assert "-- 字段：完成补录任务数（completed_supplement_count）" in source["sql"]
    assert source["sql"].index("-- 字段：") < source["sql"].index("SELECT completed_count")
    assert SYSTEM_QUERY_DEFINITIONS["report_reconciliation_completion_time"].feature == (
        "核对历史 / 自动对数"
    )
    reconciliation = SYSTEM_QUERY_DEFINITIONS["report_reconciliation_completion_time"]
    assert reconciliation.tables == ("run_headers", "reconcile_runs")
    assert "INNER JOIN reconcile_runs" in reconciliation.sql
    assert "reconcile.total_count = 0" in reconciliation.sql
    assert "MIN(header.run_at) AS reconciliation_completed_at" in reconciliation.sql
    assert "MONTH(CURRENT_DATE) = 1" in reconciliation.sql
    assert "YEAR(header.run_date) = YEAR(CURRENT_DATE) - 1" in reconciliation.sql
    assert "MONTH(header.run_date) = 12" in reconciliation.sql
    assert "MAX(finished_at)" not in reconciliation.sql
    assert "header.status = 'completed'" not in reconciliation.sql
    quarterly = SYSTEM_QUERY_DEFINITIONS["quarterly_special_processing"]
    assert "report_special_processing_records" in quarterly.sql
    assert "report_period" in quarterly.sql
    assert "DATE_FORMAT(report_period, '%Y-%m') AS month" in quarterly.sql
    assert "report_period >= '2026-08-01'" in quarterly.sql
    assert "special_handling_at" not in quarterly.sql
    assert "QUARTER(" not in quarterly.sql
    assert "status = 'completed'" not in quarterly.sql
    assert "status IN ('pending', 'completed')" in quarterly.sql
    assert quarterly.fields == (("month", "报送期月份"), ("special_processing_count", "特殊处理数量"))
    submission_comparison = SYSTEM_QUERY_DEFINITIONS["monthly_report_submission_time_comparison"]
    assert "process.enabled = 1" in submission_comparison.sql
    assert "process.process_code <> 'pbc_central'" in submission_comparison.sql
    assert "process.process_name <> '人行大集中'" not in submission_comparison.sql


def test_system_preview_executes_generated_sql_on_autocheck_database():
    from auto_check.modules.dashboard_management.system_data import SystemDataPreviewExecutor

    database = _Database()
    fields = [
        {
            "field_alias": "report_type",
            "value_type": "string",
            "nullable": False,
            "enabled": True,
        },
        {
            "field_alias": "reporting_date",
            "value_type": "date",
            "nullable": True,
            "enabled": True,
        },
    ]

    result = SystemDataPreviewExecutor().execute(
        database,
        "monthly_regulatory_report_time",
        fields,
        "list",
    )

    assert result.preview.columns == ("report_type", "reporting_date")
    assert result.preview.rows == ({"report_type": "1104", "reporting_date": "2026-09-20"},)
    assert result.source["database"] == "autocheck"
    assert result.source["feature"] == "报送导航 / 月度报送计划"
    assert result.source["table_details"][0]["display_name"] == "报送导航流程配置"
    assert "report_nav_monthly_schedules" in database.connection.sql


def test_system_preview_returns_safe_specific_database_error():
    from auto_check.modules.dashboard_management.system_data import SystemDataPreviewExecutor
    from auto_check.modules.dashboard_management.validator import ValidationError

    class BrokenDatabase(_Database):
        @contextmanager
        def connect(self):
            raise RuntimeError("Unknown column 'missing_field' in 'field list'")
            yield

    fields = [
        {
            "field_alias": "reporting_date",
            "value_type": "date",
            "nullable": True,
            "enabled": True,
        },
    ]
    with pytest.raises(ValidationError, match="查询失败：字段不存在：missing_field"):
        SystemDataPreviewExecutor().execute(
            BrokenDatabase(), "monthly_regulatory_report_time", fields, "list"
        )


def test_unlimited_system_preview_fetches_all_rows() -> None:
    from auto_check.modules.dashboard_management.system_data import SystemDataPreviewExecutor

    class Result:
        def keys(self):
            return ("report_type", "reporting_date")

        def fetchall(self):
            return [
                ("1104", date(2026, 9, 20)),
                ("1105", date(2026, 9, 21)),
            ]

    class Connection(_Connection):
        def execute(self, statement):
            self.sql = str(statement)
            return Result()

    database = _Database()
    database.connection = Connection()
    fields = [
        {
            "field_alias": "report_type",
            "value_type": "string",
            "nullable": False,
            "enabled": True,
        },
        {
            "field_alias": "reporting_date",
            "value_type": "date",
            "nullable": True,
            "enabled": True,
        },
    ]

    result = SystemDataPreviewExecutor(preview_limit=None).execute(
        database,
        "monthly_regulatory_report_time",
        fields,
        "list",
    )

    assert result.preview.has_more is False
    assert result.preview.returned_count == 2
    assert result.preview.rows[-1]["report_type"] == "1105"
