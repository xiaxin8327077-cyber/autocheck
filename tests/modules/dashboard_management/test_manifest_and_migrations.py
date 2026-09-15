from __future__ import annotations

import json
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[3] / "src" / "auto_check" / "modules" / "dashboard_management"
ROOT = Path(__file__).resolve().parents[3]
EXTERNAL_API_DOC = ROOT / "docs" / "dashboard-management-external-api.zh-CN.md"
MODULE_README = MODULE_ROOT / "README.md"


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
    assert any("外部只读" in item for item in payload["release_notes"]["items"])


def test_external_api_document_covers_security_examples_and_all_fixed_fields() -> None:
    content = EXTERNAL_API_DOC.read_text(encoding="utf-8")

    for fragment in [
        "/api/external/v1/dashboard-management/boards/report_submission/preview",
        "/api/external/v1/dashboard-management/boards/reporting_process/preview",
        "AUTO_CHECK_EXTERNAL_API_TOKEN",
        "Authorization: Bearer",
        "WWW-Authenticate: Bearer",
        "Cache-Control: no-store",
        "curl",
        "HTTP 401",
        "HTTP 404",
        "HTTP 503",
        '"status": "success"',
        '"status": "partial"',
        "连接 3 秒",
        "总超时 10 秒",
        "不对 401 重试",
        "最近一次成功",
        "request_id",
        "浏览器大屏",
        "对方系统后端适配接口",
        "AutoCheck 外部接口",
        "一个且仅一个",
        "v1 不定义查询参数",
        "请求体",
        "HTTP 405",
        "Allow: GET",
        "成功区域",
        "并非所有平台级错误",
        "联调检查清单",
    ]:
        assert fragment in content

    for region_code in [
        "annual_supplement_completed",
        "monthly_report_validation_remaining",
        "monthly_trust_projects",
        "report_reconciliation_completion_time",
        "report_validation_issue_handling",
        "quarterly_special_processing",
        "monthly_report_submission_time_comparison",
        "regulatory_report_count",
        "monthly_regulatory_report_time",
        "report_validation_statistics",
    ]:
        assert region_code in content

    for field_alias in [
        "completed_supplement_count",
        "remaining_validation_count",
        "month",
        "single_trust_count",
        "collective_trust_count",
        "property_trust_count",
        "reconciliation_completed_at",
        "validation_issue_count",
        "quarter",
        "special_processing_count",
        "report_type",
        "actual_report_generated_at",
        "required_submission_at",
        "report_count",
        "reporting_date",
        "validation_count",
    ]:
        assert field_alias in content

    assert "1月～12月" in content
    assert content.count("YYYY-MM") >= 2
    assert "YYYY-MM-DD" in content
    assert "ISO 8601" in content


def test_module_readme_links_to_external_api_document_from_module_directory() -> None:
    content = MODULE_README.read_text(encoding="utf-8")

    assert "../../../../docs/dashboard-management-external-api.zh-CN.md" in content


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
