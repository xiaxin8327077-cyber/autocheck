import json
import re
from pathlib import Path

from auto_check.app.module_system.contracts import ModuleManifest
from auto_check.app.module_system.discovery import discover_modules
from auto_check.app.module_system.schema import load_module_migrations


ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "src/auto_check/modules/report_special_processing"


def test_manifest_declares_an_optional_grouped_module_and_platform_services():
    manifest = ModuleManifest.from_mapping(json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8")))
    assert manifest.id == "report_special_processing"
    assert manifest.required is False
    assert manifest.api_prefix == "/api/modules/report-special-processing"
    assert manifest.schema_version == 5
    assert manifest.permissions == (
        "report_special_processing.view",
        "report_special_processing.detail",
        "report_special_processing.create",
        "report_special_processing.edit",
        "report_special_processing.confirm",
        "report_special_processing.reopen",
        "report_special_processing.void",
        "report_special_processing.delete",
    )
    assert [(item.name, item.minimum_version) for item in manifest.service_dependencies] == [
        ("platform.user_directory", 1),
        ("platform.report_navigation", 1),
        ("platform.notification", 1),
    ]
    assert manifest.navigation[0].group_id == "data-entry"
    assert manifest.navigation[0].group_label == "数据录入"
    assert manifest.version == "1.2.12"
    assert manifest.release_notes.version == "1.2.12"
    assert manifest.release_notes.items == (
        "数据治理负责人可按所属维度自动带出后，改选任意启用用户",
    )


def test_module_is_discovered_without_central_registration():
    discovered = discover_modules()
    assert "report_special_processing" in {item.manifest.id for item in discovered}


def test_initial_migration_owns_exactly_three_tables_and_never_drops_data():
    migrations = load_module_migrations("auto_check.modules.report_special_processing")
    assert len(migrations) == 5
    assert [item.version for item in migrations] == [1, 2, 3, 4, 5]
    sql = "\n".join(migrations[0].statements)
    assert sql.count("CREATE TABLE report_special_processing_") == 3
    for table in ("records", "reports", "audit_logs"):
        assert f"report_special_processing_{table}" in sql
    assert "UNIQUE KEY" in sql
    assert "row_version" in sql
    assert "DROP TABLE" not in sql.upper()
    assert "DELETE FROM" not in sql.upper()
    second = "\n".join(migrations[1].statements)
    assert "report_special_processing_processes" in second
    assert "INSERT INTO" not in second.upper()
    assert "DROP TABLE" not in second.upper()


def test_migration_003_adds_dimension_governance_columns():
    migrations = load_module_migrations("auto_check.modules.report_special_processing")
    assert len(migrations) == 5
    assert migrations[2].version == 3
    sql = "\n".join(migrations[2].statements).upper()
    for col in (
        "DIMENSION",
        "GOVERNANCE_OWNER_USER_ID",
        "TABLE_NAME",
        "FIELD_NAME",
        "VALUE_BEFORE",
        "VALUE_AFTER",
    ):
        assert col in sql


def test_migration_005_adds_confirm_attachment_table():
    migrations = load_module_migrations("auto_check.modules.report_special_processing")
    assert migrations[4].version == 5
    sql = "\n".join(migrations[4].statements)
    assert "report_special_processing_confirm_attachments" in sql
    assert "LONGBLOB" in sql.upper()
    assert "uq_rsp_confirm_att_audit_seq" in sql
    assert "DROP TABLE" not in sql.upper()
    assert "DELETE FROM" not in sql.upper()
    create_pattern = re.compile(
        r"CREATE TABLE (?P<table>report_special_processing_confirm_attachments) \("
        r"(?P<body>.*?)\) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 "
        r"COMMENT='(?P<comment>[^']+)'",
        re.DOTALL,
    )
    match = create_pattern.search(sql)
    assert match is not None
    assert re.search(r"[\u4e00-\u9fff]", match.group("comment"))
    column_lines = re.findall(
        r"(?m)^\s{4}(?!PRIMARY\b|UNIQUE\b|KEY\b)"
        r"(?P<column>[a-z][a-z0-9_]*)\s+.*$",
        match.group("body"),
    )
    assert column_lines
    for column_name in column_lines:
        column_line = re.search(
            rf"(?m)^\s{{4}}{re.escape(column_name)}\s+.*$",
            match.group("body"),
        ).group(0)
        assert re.search(
            r"\bCOMMENT\s+'[^']*[\u4e00-\u9fff][^']*'",
            column_line,
        ), f"confirm_attachments.{column_name} lacks a Chinese comment"


def test_migration_004_widens_audit_json_to_longtext():
    migrations = load_module_migrations("auto_check.modules.report_special_processing")
    assert migrations[3].version == 4
    sql = "\n".join(migrations[3].statements).upper()
    assert "REPORT_SPECIAL_PROCESSING_AUDIT_LOGS" in sql
    assert "CHANGED_FIELDS_JSON" in sql
    assert "LONGTEXT" in sql
    assert "DROP TABLE" not in sql
    assert "DELETE FROM" not in sql


def test_initial_migration_has_chinese_comments_for_every_table_and_column():
    sql = (PACKAGE / "migrations/001_initial.sql").read_text(encoding="utf-8")
    create_pattern = re.compile(
        r"CREATE TABLE (?P<table>report_special_processing_[a-z_]+) \("
        r"(?P<body>.*?)\) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 "
        r"COMMENT='(?P<comment>[^']+)'",
        re.DOTALL,
    )
    matches = list(create_pattern.finditer(sql))

    assert len(matches) == 3
    for match in matches:
        table_name = match.group("table")
        assert re.search(r"[\u4e00-\u9fff]", match.group("comment")), (
            f"{table_name} lacks a Chinese table comment"
        )
        column_lines = re.findall(
            r"(?m)^\s{4}(?!PRIMARY\b|UNIQUE\b|KEY\b)"
            r"(?P<column>[a-z][a-z0-9_]*)\s+.*$",
            match.group("body"),
        )
        assert column_lines, f"{table_name} has no columns"
        for column_name in column_lines:
            column_line = re.search(
                rf"(?m)^\s{{4}}{re.escape(column_name)}\s+.*$",
                match.group("body"),
            ).group(0)
            assert re.search(
                r"\bCOMMENT\s+'[^']*[\u4e00-\u9fff][^']*'",
                column_line,
            ), f"{table_name}.{column_name} lacks a Chinese comment"

    process_sql = (PACKAGE / "migrations/002_multi_report_processes.sql").read_text(encoding="utf-8")
    process_match = re.search(
        r"CREATE TABLE(?: IF NOT EXISTS)? (?P<table>report_special_processing_processes) \("
        r"(?P<body>.*?)\) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 "
        r"COMMENT='(?P<comment>[^']+)'",
        process_sql,
        re.DOTALL,
    )
    assert process_match is not None
    assert re.search(r"[\u4e00-\u9fff]", process_match.group("comment"))
    column_lines = re.findall(
        r"(?m)^\s{4}(?!PRIMARY\b|UNIQUE\b|KEY\b)"
        r"(?P<column>[a-z][a-z0-9_]*)\s+.*$",
        process_match.group("body"),
    )
    assert column_lines
    for column_name in column_lines:
        column_line = re.search(
            rf"(?m)^\s{{4}}{re.escape(column_name)}\s+.*$",
            process_match.group("body"),
        ).group(0)
        assert re.search(
            r"\bCOMMENT\s+'[^']*[\u4e00-\u9fff][^']*'",
            column_line,
        ), f"processes.{column_name} lacks a Chinese comment"


def test_module_registers_only_its_schema_tables():
    from auto_check.app.module_system.schema import ModuleSchemaRegistry
    from auto_check.modules.report_special_processing.module import create_module

    registry = ModuleSchemaRegistry("report_special_processing")
    create_module().register_schema(registry)
    assert registry.declared_table_names == frozenset(
        {
            "report_special_processing_records",
            "report_special_processing_reports",
            "report_special_processing_processes",
            "report_special_processing_audit_logs",
            "report_special_processing_confirm_attachments",
        }
    )
