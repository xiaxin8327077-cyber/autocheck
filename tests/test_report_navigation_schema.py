from pathlib import Path

from auto_check.app.app_database import CURRENT_APP_SCHEMA_VERSION, EXPECTED_APP_SCHEMA


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_SQL = ROOT / "sql" / "app_storage" / "mysql" / "002_report_navigation.sql"

REPORT_NAV_TABLES = {
    "report_nav_processes",
    "report_nav_process_months",
    "report_nav_steps",
    "report_nav_step_dependencies",
    "report_nav_step_sources",
    "report_nav_step_fields",
    "report_nav_step_values",
    "report_nav_step_overrides",
    "report_nav_step_snapshots",
    "report_nav_process_snapshots",
    "report_nav_card_snapshots",
    "report_nav_monthly_schedules",
    "report_nav_stat_runs",
    "report_nav_scheduler_state",
}


def test_report_navigation_schema_only_creates_new_relational_tables():
    sql = SCHEMA_SQL.read_text(encoding="utf-8")

    assert "ALTER TABLE" not in sql.upper()
    assert "DROP TABLE" not in sql.upper()
    assert "TRUNCATE TABLE" not in sql.upper()
    assert " JSON" not in sql.upper()
    for table_name in REPORT_NAV_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS `{table_name}`" in sql


def test_application_schema_keeps_version_one_and_adds_report_navigation_tables():
    assert CURRENT_APP_SCHEMA_VERSION == 1
    assert REPORT_NAV_TABLES <= set(EXPECTED_APP_SCHEMA)
    assert len(EXPECTED_APP_SCHEMA) == 34
    assert EXPECTED_APP_SCHEMA["report_nav_steps"] >= {
        "step_code",
        "process_code",
        "evaluator_key",
        "default_completed",
    }
    assert EXPECTED_APP_SCHEMA["report_nav_card_snapshots"] >= {
        "stat_period",
        "card_code",
        "total_count",
        "completed_count",
        "incomplete_count",
    }


def test_report_navigation_tables_do_not_redefine_schema_version():
    sql = SCHEMA_SQL.read_text(encoding="utf-8")

    assert "app_schema_version" not in sql

