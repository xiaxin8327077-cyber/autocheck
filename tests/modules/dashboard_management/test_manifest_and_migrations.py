from __future__ import annotations

import json
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[3] / "src" / "auto_check" / "modules" / "dashboard_management"


def test_manifest_declares_optional_dashboard_management_module() -> None:
    payload = json.loads((MODULE_ROOT / "manifest.json").read_text(encoding="utf-8"))

    assert payload["id"] == "dashboard_management"
    assert payload["required"] is False
    assert payload["api_prefix"] == "/api/modules/dashboard-management"
    assert payload["schema_version"] == 2
    assert payload["permissions"] == [
        "dashboard_management.view",
        "dashboard_management.manage",
        "dashboard_management.test_sql",
    ]
    assert payload["navigation"] == [
        {
            "id": "dashboard-management",
            "label": "看板管理",
            "route": "dashboard-management",
            "order": 60,
            "permission": "dashboard_management.view",
            "group_id": "system-management",
            "group_label": "系统管理",
            "group_order": 90,
        }
    ]


def test_initial_migration_creates_only_three_dashboard_management_tables() -> None:
    sql = (MODULE_ROOT / "migrations" / "001_initial.sql").read_text(encoding="utf-8")
    table_names = {
        line.split("(", 1)[0].split()[-1]
        for line in sql.splitlines()
        if line.startswith("CREATE TABLE ")
    }

    assert table_names == {
        "dashboard_management_regions",
        "dashboard_management_fields",
        "dashboard_management_source_configs",
    }
    assert sql.count("CREATE TABLE dashboard_management_") == 3
    assert "FOREIGN KEY (region_id) REFERENCES dashboard_management_regions (id)" in sql
    assert sql.count("FOREIGN KEY (region_id) REFERENCES dashboard_management_regions (id)") == 2


def test_second_migration_creates_year_snapshot_table_with_period_uniqueness() -> None:
    sql = (MODULE_ROOT / "migrations" / "002_year_snapshots.sql").read_text(encoding="utf-8")

    assert sql.count("CREATE TABLE dashboard_management_year_snapshots") == 1
    assert "UNIQUE KEY uq_dashboard_management_year_snapshot_period" in sql
    assert "(region_id, period_year, period_type, period_value)" in sql
    assert (
        "FOREIGN KEY (region_id) REFERENCES dashboard_management_regions (id)"
        in sql
    )
    assert "INSERT " not in sql.upper()


def test_module_registers_schema_for_all_dashboard_management_tables() -> None:
    from auto_check.app.module_system.schema import ModuleSchemaRegistry
    from auto_check.modules.dashboard_management.module import create_module

    registry = ModuleSchemaRegistry("dashboard_management")
    create_module().register_schema(registry)

    expected = {
        "dashboard_management_regions": {
            "id", "board_code", "region_code", "shape", "built_in", "enabled",
            "system_supported", "display_order", "row_version",
        },
        "dashboard_management_fields": {
            "id", "region_id", "field_alias", "value_type", "nullable", "built_in",
            "enabled", "display_order", "row_version",
        },
        "dashboard_management_source_configs": {
            "region_id", "source_mode", "datasource_id", "sql_text", "tested_signature",
            "tested_at", "row_version",
        },
        "dashboard_management_year_snapshots": {
            "id", "region_id", "period_year", "period_type", "period_value", "row_json",
            "source_refreshed_at", "created_at", "updated_at",
        },
    }
    assert registry.declared_table_names == frozenset(expected)
    for table_name, columns in expected.items():
        assert columns <= registry._tables[table_name]
