from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.module import MANIFEST
from tests.modules.data_validation.support import Metadata, loan_definition, service, user

ROOT = Path(__file__).resolve().parents[3] / "src" / "auto_check" / "modules" / "data_validation"


def test_migrations_pass_the_module_ddl_safety_gate() -> None:
    from auto_check.app.module_system.schema import ModuleSchemaRegistry, load_module_migrations
    from auto_check.modules.data_validation.module import create_module

    registry = ModuleSchemaRegistry("data_validation")
    create_module().register_schema(registry)
    migrations = load_module_migrations("auto_check.modules.data_validation")
    assert [item.version for item in migrations] == list(range(1, MANIFEST.schema_version + 1))
    for migration in migrations:
        for statement in migration.statements:
            registry.validate_statement(statement)


def test_manifest_and_initial_migration() -> None:
    assert MANIFEST.required is False
    assert MANIFEST.api_prefix == "/api/modules/data-validation"
    assert MANIFEST.table_prefix == "data_validation_"
    assert MANIFEST.navigation[0].route == "data-validation"
    assert [item.route for item in MANIFEST.navigation] == [
        "data-validation", "data-validation-results", "data-validation-settings",
    ]
    assert MANIFEST.navigation[1].label == "校验结果"
    assert MANIFEST.navigation[1].permission == "data_validation.view_results"
    assert MANIFEST.navigation[2].label == "校验设置"
    assert MANIFEST.navigation[2].permission == "data_validation.admin"
    sql = (ROOT / "migrations" / "001_initial.sql").read_text(encoding="utf-8")
    for name in (
        "data_validation_rules",
        "data_validation_rule_versions",
        "data_validation_settings",
        "data_validation_audit_logs",
    ):
        assert f"CREATE TABLE {name}" in sql
    assert "data_validation_tasks" not in sql
    assert "rule_code" in sql and "current_version_id" in sql and "content_sha256" in sql


def test_save_draft_with_unresolved_null_policy() -> None:
    _database, rules = service()
    saved = rules.save_draft(user(), loan_definition(null_policy="unresolved", equality_policy="unresolved"))
    assert saved["status"] == "draft"
    assert saved["rule_code"] == "DV000001"


def test_list_rules_filters_on_the_server() -> None:
    database, rules = service()
    owner = user()
    for index in range(60):
        rules.save_draft(owner, loan_definition(name=f"期限{index}", description="期限"))
    page = rules.list_rules(owner, {"page": "2", "page_size": "50", "status": "draft", "keyword": "期限"})
    assert page["total"] == 60
    assert len(page["items"]) == 10
    assert [item["id"] for item in page["items"]] == sorted((item["id"] for item in page["items"]), reverse=True)
    listed = [sql for sql in database.sql if "data_validation_rules" in sql and "ORDER BY" in sql.upper()]
    assert listed
    assert "LIMIT" in listed[-1].upper()


def test_rule_stats_follow_the_same_scope() -> None:
    _database, rules = service()
    owner = user("7")
    rules.save_draft(owner, loan_definition(name="草稿一"))
    rules.save_draft(owner, loan_definition(name="草稿二"))
    enabled = rules.save_draft(owner, loan_definition(name="已启用"))
    version = rules.storage.latest_version(enabled["id"])
    rules.storage.set_status(enabled["id"], "enabled", int(version["id"]))
    assert rules.rule_stats(owner) == {
        "total": 3, "enabled": 1, "disabled": 0, "draft": 2,
        "categories": [], "unclassified": {"total": 3, "enabled": 1, "disabled": 0, "draft": 2},
    }
    assert rules.rule_stats(user("8")) == {
        "total": 0, "enabled": 0, "disabled": 0, "draft": 0,
        "categories": [], "unclassified": {"total": 0, "enabled": 0, "disabled": 0, "draft": 0},
    }


def test_copy_starts_a_new_draft() -> None:
    _database, rules = service()
    saved = rules.save_draft(user("1"), loan_definition())
    copied = rules.copy_rule(user("2", "admin"), saved["id"])
    assert copied["creator_user_id"] == "2"
    assert copied["status"] == "draft"
    assert copied["version_no"] == 1
    assert copied["current_version_id"] is None


def test_other_user_cannot_edit_or_disable_draft() -> None:
    _database, rules = service()
    saved = rules.save_draft(user("1"), loan_definition())
    with pytest.raises(AppError) as edit_error:
        rules.save_draft(user("2"), loan_definition(name="改"), saved["id"])
    with pytest.raises(AppError) as disable_error:
        rules.disable_rule(user("2"), saved["id"])
    assert edit_error.value.code == "FORBIDDEN"
    assert disable_error.value.code == "FORBIDDEN"
    assert rules.storage.get_rule(saved["id"])["status"] == "draft"
    assert rules.storage.latest_audit(saved["id"])["action_code"] == "access_denied"


def test_five_thousand_rules_are_paged() -> None:
    database, rules = service()
    owner = user()
    for index in range(5000):
        rules.storage.create_rule(
            creator_user_id="1", name=f"规则{index}", description="", definition=loan_definition(name=f"规则{index}"),
            sql_text="", mapping_version="", content_sha256="a" * 64, generation_mode="manual",
        )
    database.sql.clear()
    page = rules.list_rules(owner, {"page": 1, "page_size": 50})
    assert len(page["items"]) == 50
    assert page["total"] == 5000
    assert any("LIMIT" in sql.upper() for sql in database.sql)


class _Processes:
    def list_report_processes(self):
        from types import SimpleNamespace
        return [
            SimpleNamespace(code="pbc_central", name="人行大集中报送", order=1, active=True),
            SimpleNamespace(code="east5", name="East5报送", order=2, active=True),
            SimpleNamespace(code="disabled_process", name="停用分类", order=3, active=False),
        ]


def test_rule_category_is_stored_filtered_and_grouped_by_report_processes() -> None:
    _database, rules = service(report_navigation=_Processes())
    owner = user("7")
    rules.save_draft(owner, loan_definition(name="人行规则一", report_category="pbc_central"))
    enabled = rules.save_draft(owner, loan_definition(name="人行规则二", report_category="pbc_central"))
    rules.save_draft(owner, loan_definition(name="East 规则", report_category="east5"))
    rules.save_draft(owner, loan_definition(name="历史未分类"))
    rules.save_draft(owner, loan_definition(name="未知分类", report_category="legacy_code"))
    version = rules.storage.latest_version(enabled["id"])
    rules.storage.set_status(enabled["id"], "enabled", int(version["id"]))

    # 分类写入规则行并可筛选
    assert rules.storage.get_rule(enabled["id"])["report_category"] == "pbc_central"
    listed = rules.list_rules(owner, {"report_category": "pbc_central"})
    assert listed["total"] == 2
    assert {item["report_category"] for item in listed["items"]} == {"pbc_central"}

    # 卡片统计按报送导航分类合并；停用分类不展示；未分类与未知分类归入 unclassified
    categories = {item["code"]: item for item in rules.list_report_categories()}
    assert "disabled_process" not in categories
    stats = rules.rule_stats(owner)
    by_code = {item["code"]: item for item in stats["categories"]}
    assert by_code["group:pbc"]["total"] == 2 and by_code["group:pbc"]["enabled"] == 1
    assert "pbc_central" not in by_code and "pbc_template" not in by_code
    assert by_code["east5"]["total"] == 1
    assert stats["total"] == 5
    assert stats["unclassified"] == {"total": 2, "enabled": 0, "draft": 2, "disabled": 0}


def test_selectable_sources_are_limited_to_regulatory_marts() -> None:
    """模块创建规则的下拉临时只开放监管报送集市与监管报表，系统配置与其他数据源不受影响。"""
    from types import SimpleNamespace
    metadata = Metadata(sources=[
        SimpleNamespace(id="market", name="监管报送集市", dialect="postgresql"),
        SimpleNamespace(id="report", name="监管报表", dialect="mysql"),
        SimpleNamespace(id="other", name="1104", dialect="mysql"),
    ])
    _database, rules = service(metadata=metadata)
    assert [item["id"] for item in rules.list_selectable_sources()] == ["market", "report"]
    assert [item["id"] for item in rules.list_sources()] == ["market", "report", "other"]
