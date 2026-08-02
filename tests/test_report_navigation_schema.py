from pathlib import Path
import re

from auto_check.app.app_database import CURRENT_APP_SCHEMA_VERSION, EXPECTED_APP_SCHEMA


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_SQL = ROOT / "sql" / "app_storage" / "mysql" / "002_report_navigation.sql"
SEED_SQL = ROOT / "sql" / "app_storage" / "mysql" / "003_report_navigation_seed.sql"
OWNER_MIGRATION_SQL = ROOT / "sql" / "app_storage" / "mysql" / "007_report_navigation_schedule_owner.sql"
WORK_CALENDAR_MIGRATION_SQL = ROOT / "sql" / "app_storage" / "mysql" / "008_report_navigation_work_calendar.sql"
MANUAL_STEP_PERMISSIONS_SQL = ROOT / "sql" / "app_storage" / "mysql" / "009_report_navigation_manual_step_permissions.sql"
PBC_TEMPLATE_STEP_SEVEN_DISPLAY_ONLY_SQL = ROOT / "sql" / "app_storage" / "mysql" / "010_pbc_template_step_seven_display_only.sql"
COMPLETION_TIME_SOURCES_SQL = ROOT / "sql" / "app_storage" / "mysql" / "011_report_navigation_completion_time_sources.sql"
PROVIDER_STATES_SQL = ROOT / "sql" / "app_storage" / "mysql" / "013_report_navigation_provider_states.sql"

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
    "report_nav_card_provider_states",
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
    assert len(EXPECTED_APP_SCHEMA) == 43
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
    assert EXPECTED_APP_SCHEMA["report_nav_card_provider_states"] >= {
        "card_code",
        "owner",
        "semantics_version",
        "provider_active",
        "stale",
        "last_attempt_at",
        "last_success_at",
        "last_success_period_key",
        "last_error",
        "updated_at",
    }


def test_card_provider_state_has_an_idempotent_migration():
    migration_sql = PROVIDER_STATES_SQL.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS `report_nav_card_provider_states`" in migration_sql
    assert "DROP TABLE" not in migration_sql.upper()


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


def test_manual_step_permission_migration_only_enables_current_confirmable_step():
    migration_sql = MANUAL_STEP_PERMISSIONS_SQL.read_text(encoding="utf-8")

    assert "UPDATE `report_nav_steps`" in migration_sql
    assert "WHEN `step_code` = 'pbc_template_7' THEN 1" in migration_sql
    assert "ELSE 0" in migration_sql
    assert "DROP " not in migration_sql.upper()


def test_pbc_template_step_seven_is_display_only_and_step_six_is_final():
    seed_sql = SEED_SQL.read_text(encoding="utf-8")
    migration_sql = PBC_TEMPLATE_STEP_SEVEN_DISPLAY_ONLY_SQL.read_text(encoding="utf-8")

    assert (
        "('pbc_template_7', 'pbc_template', "
        "'归档后制表人填写数据调整情况说明（如有）', 7, 'display_only', 1, 0, 0)"
        in seed_sql
    )
    assert "(50, 11, 'create_date_field', 'create_date')" in seed_sql
    assert "INSERT INTO `report_nav_steps`" in migration_sql
    assert "'归档后制表人填写数据调整情况说明（如有）'" in migration_sql
    assert "'display_only'" in migration_sql
    assert "'create_date_field', 'create_date'" in migration_sql
    assert "DROP " not in migration_sql.upper()
    assert "TRUNCATE " not in migration_sql.upper()


def test_report_navigation_tables_do_not_redefine_schema_version():
    sql = SCHEMA_SQL.read_text(encoding="utf-8")

    assert "app_schema_version" not in sql


def test_pbc_central_step_four_uses_caldate_report_period_mapping():
    sql = SEED_SQL.read_text(encoding="utf-8")

    assert "('pbc_central_4', 'pbc_central', '内部产品资金端客户与资产端交易对手校验一致', 4, 'no_ck_and_report_period'" in sql
    assert "(12, 6, 'period_field', 'caldate')" in sql
    assert "(12, 6, 'time_field', 'tbtime')" not in sql
    assert "(22, 'pbc_central_4', 'completion_time', 'currency_report_24', 'currency_report_duration', 3, 1)" in sql
    assert "(51, 22, 'period_field', 'caldate')" in sql
    assert "(52, 22, 'create_date_field', 'create_date')" in sql


def test_pbc_process_names_match_report_date_labels():
    sql = SEED_SQL.read_text(encoding="utf-8")

    assert "('pbc_central', '人行大集中报送', 10, 1, 1)" in sql
    assert "('pbc_template', '资管产品模板、逐笔报送', 20, 1, 1)" in sql
    assert "('full_elements', '全要素报送', 40, 1, 1)" in sql
    assert "('east5', 'EAST5.0报送', 60, 1, 1)" in sql
    assert "('east5_1', 'east5', '归档并上传 EAST5.0 报送'" in sql


def test_archive_steps_map_create_date_only_for_completion_time():
    sql = SEED_SQL.read_text(encoding="utf-8")

    for source_id in (11, 13, 14, 18, 19, 20):
        assert re.search(
            rf"\(\d+, {source_id}, 'create_date_field', 'create_date'\)",
            sql,
        )
        assert not re.search(
            rf"\(\d+, {source_id}, 'update_date_field', 'update_date'\)",
            sql,
        )


def test_completion_time_migration_configures_create_date_only():
    sql = COMPLETION_TIME_SOURCES_SQL.read_text(encoding="utf-8")

    assert "'pbc_central_4', 'completion_time', 'currency_report_24'," in sql
    assert "'currency_report_duration', 3, 1" in sql
    assert "'period_field', 'caldate'" in sql
    assert "'create_date_field', 'create_date'" in sql
    assert "`field_role` = 'update_date_field'" in sql
    assert "DROP " not in sql.upper()
    assert "TRUNCATE " not in sql.upper()


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


def test_all_mysql_create_tables_have_clean_chinese_table_and_column_comments():
    ddl_dir = ROOT / "sql" / "app_storage" / "mysql"
    create_pattern = re.compile(
        r"CREATE TABLE(?: IF NOT EXISTS)? `(?P<table>[^`]+)` \((?P<body>.*?)\) "
        r"ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
        r"\s+COMMENT='(?P<comment>[^']+)';",
        re.DOTALL,
    )
    create_count = 0

    for sql_path in sorted(ddl_dir.glob("*.sql")):
        sql = sql_path.read_text(encoding="utf-8")
        declared_count = len(re.findall(r"(?im)^CREATE TABLE(?: IF NOT EXISTS)? `", sql))
        matches = list(create_pattern.finditer(sql))
        assert len(matches) == declared_count, f"{sql_path.name} has an unparsed CREATE TABLE"
        create_count += declared_count

        for match in matches:
            table_name = match.group("table")
            table_comment = match.group("comment")
            assert re.search(r"[\u4e00-\u9fff]", table_comment), (
                f"{sql_path.name}:{table_name} lacks a Chinese table comment"
            )
            assert "?" not in table_comment, (
                f"{sql_path.name}:{table_name} has a damaged table comment"
            )

            column_lines = re.findall(r"(?m)^\s+`[^`]+`\s+.*$", match.group("body"))
            assert column_lines, f"{sql_path.name}:{table_name} has no columns"
            for column_line in column_lines:
                column_name = re.match(r"\s+`([^`]+)`", column_line).group(1)
                column_comment = re.search(
                    r"\bCOMMENT\s+'(?P<comment>[^']*[\u4e00-\u9fff][^']*)'",
                    column_line,
                )
                assert column_comment is not None, (
                    f"{sql_path.name}:{table_name}.{column_name} lacks a Chinese comment"
                )
                assert "?" not in column_comment.group("comment"), (
                    f"{sql_path.name}:{table_name}.{column_name} has a damaged comment"
                )

    assert create_count > 0
