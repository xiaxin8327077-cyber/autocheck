import json
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
    assert manifest.schema_version == 1
    assert manifest.permissions == (
        "report_special_processing.view",
        "report_special_processing.admin",
    )
    assert [(item.name, item.minimum_version) for item in manifest.service_dependencies] == [
        ("platform.user_directory", 1),
        ("platform.report_navigation", 1),
    ]
    assert manifest.navigation[0].group_id == "data-entry"
    assert manifest.navigation[0].group_label == "数据录入"
    assert manifest.release_notes.items == ("新增报表特殊处理录入与真实统计",)


def test_module_is_discovered_without_central_registration():
    discovered = discover_modules()
    assert "report_special_processing" in {item.manifest.id for item in discovered}


def test_initial_migration_owns_exactly_three_tables_and_never_drops_data():
    migrations = load_module_migrations("auto_check.modules.report_special_processing")
    assert len(migrations) == 1
    assert migrations[0].version == 1
    sql = "\n".join(migrations[0].statements)
    assert sql.count("CREATE TABLE report_special_processing_") == 3
    for table in ("records", "reports", "audit_logs"):
        assert f"report_special_processing_{table}" in sql
    assert "UNIQUE KEY" in sql
    assert "row_version" in sql
    assert "DROP TABLE" not in sql.upper()
    assert "DELETE FROM" not in sql.upper()


def test_module_registers_only_its_three_schema_tables():
    from auto_check.app.module_system.schema import ModuleSchemaRegistry
    from auto_check.modules.report_special_processing.module import create_module

    registry = ModuleSchemaRegistry("report_special_processing")
    create_module().register_schema(registry)
    assert registry.declared_table_names == frozenset(
        {
            "report_special_processing_records",
            "report_special_processing_reports",
            "report_special_processing_audit_logs",
        }
    )
