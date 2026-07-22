from pathlib import Path
import re

from auto_check.app.app_database import CURRENT_APP_SCHEMA_VERSION, EXPECTED_APP_SCHEMA


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_SQL = ROOT / "sql" / "app_storage" / "mysql" / "002_report_navigation.sql"
SEED_SQL = ROOT / "sql" / "app_storage" / "mysql" / "003_report_navigation_seed.sql"
OWNER_MIGRATION_SQL = ROOT / "sql" / "app_storage" / "mysql" / "007_report_navigation_schedule_owner.sql"
WORK_CALENDAR_MIGRATION_SQL = ROOT / "sql" / "app_storage" / "mysql" / "008_report_navigation_work_calendar.sql"

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
    "report_nav_card_manual_values",
    "report_nav_card_manual_history",
    "report_nav_monthly_schedules",
    "report_nav_work_calendar",
    "report_nav_stat_runs",
    "report_nav_scheduler_state",
}


def test_report_navigation_schema_only_creates_new_relational_tables():
    sql = SCHEMA_SQL.read_text(encoding="utf-8")

    assert "ALTER TABLE" not in sql.upper()
    assert "DROP TABLE" not in sql.upper()
    assert "TRUNCATE TABLE" not in sql.upper()
    assert " JSON" not in sql.upper()
    assert "FOREIGN KEY" not in sql.upper()
    assert "CONSTRAINT" not in sql.upper()
    for table_name in REPORT_NAV_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS `{table_name}`" in sql


def test_application_schema_keeps_version_one_and_adds_report_navigation_tables():
    assert CURRENT_APP_SCHEMA_VERSION == 1
    assert REPORT_NAV_TABLES <= set(EXPECTED_APP_SCHEMA)
    assert len(EXPECTED_APP_SCHEMA) == 39
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
    assert EXPECTED_APP_SCHEMA["report_nav_card_manual_values"] >= {
        "stat_period",
        "card_code",
        "completed_count",
        "incomplete_count",
        "operator_username",
        "updated_at",
    }


def test_schedule_owner_column_is_declared_and_has_an_idempotent_migration():
    schema_sql = SCHEMA_SQL.read_text(encoding="utf-8")
    migration_sql = OWNER_MIGRATION_SQL.read_text(encoding="utf-8")

    assert "owner_name" in EXPECTED_APP_SCHEMA["report_nav_monthly_schedules"]
    assert "`owner_name` VARCHAR(128) NULL COMMENT '月度负责人'" in schema_sql
    assert "information_schema.columns" in migration_sql
    assert "ADD COLUMN `owner_name` VARCHAR(128) NULL COMMENT ''月度负责人''" in migration_sql


def test_work_calendar_table_and_2026_official_exceptions_are_declared():
    schema_sql = SCHEMA_SQL.read_text(encoding="utf-8")
    migration_sql = WORK_CALENDAR_MIGRATION_SQL.read_text(encoding="utf-8")

    assert EXPECTED_APP_SCHEMA["report_nav_work_calendar"] >= {
        "calendar_date",
        "calendar_year",
        "day_type",
        "day_name",
        "source_document",
        "updated_at",
    }
    assert "CREATE TABLE IF NOT EXISTS `report_nav_work_calendar`" in schema_sql
    assert "ON DUPLICATE KEY UPDATE" in migration_sql
    assert "2026-01-01" in migration_sql
    assert "2026-01-04" in migration_sql
    assert "2026-02-15" in migration_sql
    assert "2026-02-14" in migration_sql
    assert "2026-10-07" in migration_sql
    assert "2026-10-10" in migration_sql


def test_report_navigation_tables_do_not_redefine_schema_version():
    sql = SCHEMA_SQL.read_text(encoding="utf-8")

    assert "app_schema_version" not in sql


def test_pbc_central_step_four_uses_caldate_report_period_mapping():
    sql = SEED_SQL.read_text(encoding="utf-8")

    assert "('pbc_central_4', 'pbc_central', '内部产品资金端客户与资产端交易对手校验一致', 4, 'no_ck_and_report_period'" in sql
    assert "(12, 6, 'period_field', 'caldate')" in sql
    assert "(12, 6, 'time_field', 'tbtime')" not in sql


def test_pbc_process_names_match_report_date_labels():
    sql = SEED_SQL.read_text(encoding="utf-8")

    assert "('pbc_central', '人行大集中报送', 10, 1, 1)" in sql
    assert "('pbc_template', '资管产品模板、逐笔报送', 20, 1, 1)" in sql
    assert "('full_elements', '全要素报送', 40, 1, 1)" in sql
    assert "('east5', 'EAST5.0报送', 60, 1, 1)" in sql
    assert "('east5_1', 'east5', '归档并上传 EAST5.0 报送'" in sql


def test_archive_steps_map_update_and_create_dates_for_completion_time():
    sql = SEED_SQL.read_text(encoding="utf-8")

    for source_id in (13, 14, 18, 19, 20):
        assert re.search(
            rf"\(\d+, {source_id}, 'update_date_field', 'update_date'\)",
            sql,
        )
        assert re.search(
            rf"\(\d+, {source_id}, 'create_date_field', 'create_date'\)",
            sql,
        )


def test_citic_registration_import_step_only_uses_asset_credit_source():
    sql = SEED_SQL.read_text(encoding="utf-8")

    assert "(15, 'citic_registration_2', 'asset_credit', 'zxd', 'zxd_asset_credit_info', 1, 1)" in sql
    assert "(26, 15, 'date_field', 'createdate')" in sql
    assert "result14_xtbzjj_external_data" not in sql
    assert "jsxt_basic_info" not in sql
    assert "source_role` IN ('external_data', 'basic_info')" in sql
    assert "DELETE FROM `report_nav_step_fields`" in sql
    assert "DELETE FROM `report_nav_step_sources`" in sql


def test_report_navigation_schema_has_chinese_comments_for_every_table_and_column():
    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    create_blocks = {
        match.group("table"): match.group("body")
        for match in re.finditer(
            r"CREATE TABLE IF NOT EXISTS `(?P<table>[^`]+)` \((?P<body>.*?)\) "
            r"ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci "
            r"COMMENT='[^']*[\u4e00-\u9fff][^']*';",
            sql,
            re.DOTALL,
        )
    }

    assert set(create_blocks) == REPORT_NAV_TABLES
    for table_name, expected_columns in EXPECTED_APP_SCHEMA.items():
        if table_name not in REPORT_NAV_TABLES:
            continue
        body = create_blocks[table_name]
        for column_name in expected_columns:
            column_line = re.search(
                rf"^\s+`{re.escape(column_name)}`\s+.*$",
                body,
                re.MULTILINE,
            )
            assert column_line is not None, f"{table_name}.{column_name} is missing"
            assert re.search(
                r"\bCOMMENT\s+'[^']*[\u4e00-\u9fff][^']*'",
                column_line.group(0),
            ), f"{table_name}.{column_name} lacks a Chinese comment"
