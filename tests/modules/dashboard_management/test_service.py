from __future__ import annotations

from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, event


class _Database:
    def __init__(self) -> None:
        self._engine = create_engine("sqlite+pysqlite:///:memory:")
        event.listen(
            self._engine,
            "connect",
            lambda dbapi_connection, _: dbapi_connection.execute("PRAGMA foreign_keys=ON"),
        )

    @contextmanager
    def connect(self):
        with self._engine.connect() as connection:
            yield connection

    @contextmanager
    def transaction(self):
        with self._engine.begin() as connection:
            yield connection


@pytest.fixture
def storage():
    from auto_check.modules.dashboard_management.storage import METADATA, DashboardManagementStorage

    database = _Database()
    METADATA.create_all(database._engine)
    instance = DashboardManagementStorage(database)
    instance.seed_builtin_catalog()
    return instance


@pytest.fixture
def service(storage):
    from auto_check.modules.dashboard_management.service import DashboardManagementService

    return DashboardManagementService(storage, datasource_loader=lambda: [
        {"id": "safe", "name": "安全数据源", "db_type": "postgresql", "host": "hidden"},
    ])


@pytest.fixture
def admin():
    return {"id": "1", "username": "admin", "role": "admin"}


def _region_payload(**overrides):
    payload = {
        "name": "自定义区域",
        "shape": "list",
        "description": "自定义说明",
        "display_order": 100,
        "fields": [{
            "field_alias": "initial_value", "name": "初始值", "value_type": "string",
            "nullable": False, "enabled": True, "description": "初始字段", "display_order": 10,
        }],
    }
    payload.update(overrides)
    return payload


def _field_payload(**overrides):
    payload = {
        "field_alias": "custom_value",
        "name": "自定义值",
        "value_type": "decimal",
        "nullable": False,
        "enabled": True,
        "description": "字段说明",
        "display_order": 10,
    }
    payload.update(overrides)
    return payload


def test_catalog_limits_board_codes_and_builtin_region_identity(service, admin):
    from auto_check.modules.dashboard_management.validator import ValidationError

    catalog = service.catalog("report_submission", admin)
    assert [board["code"] for board in catalog["boards"]] == [
        "report_submission", "reporting_process",
    ]
    region = catalog["regions"][0]
    assert region["system_source"]["feature"] == "报送导航 / 补录任务统计"
    assert region["system_source"]["tables"] == ["report_nav_card_snapshots"]
    sql_only = next(item for item in catalog["regions"] if item["region_code"] == "monthly_trust_projects")
    assert sql_only["system_source"] is None
    with pytest.raises(ValidationError, match="内置数据区域编码不可修改"):
        service.update_region(region["id"], {"region_code": "changed", "row_version": 1}, admin)
    with pytest.raises(ValidationError, match="不支持的固定看板编码"):
        service.catalog("third_dashboard", admin)


def test_region_and_field_validation_rules(service, admin):
    from auto_check.modules.dashboard_management.validator import ValidationError

    with pytest.raises(ValidationError, match="数据区域名称"):
        service.create_region("report_submission", _region_payload(name=""), admin)
    with pytest.raises(ValidationError, match="显示顺序"):
        service.create_region("report_submission", _region_payload(display_order=10000), admin)
    with pytest.raises(ValidationError, match="至少需要一个启用字段"):
        service.create_region("report_submission", _region_payload(fields=[]), admin)
    with pytest.raises(ValidationError, match="字段别名"):
        service.create_region("report_submission", _region_payload(fields=[{**_field_payload(), "field_alias": "BadAlias"}]), admin)
    before = len(service.catalog("report_submission", admin)["regions"])
    with pytest.raises(ValidationError, match="首批字段别名不能重复"):
        service.create_region("report_submission", _region_payload(fields=[
            _field_payload(field_alias="duplicate_value"), _field_payload(field_alias="duplicate_value", display_order=20),
        ]), admin)
    assert len(service.catalog("report_submission", admin)["regions"]) == before
    region = service.create_region("report_submission", _region_payload(), admin)
    with pytest.raises(ValidationError, match="字段别名"):
        service.create_field(region["id"], _field_payload(field_alias="BadAlias"), admin)
    with pytest.raises(ValidationError, match="字段类型"):
        service.create_field(region["id"], _field_payload(value_type="json"), admin)


def test_custom_region_and_field_are_stable_and_field_changes_invalidate_tests(service, storage, admin):
    from auto_check.modules.dashboard_management.validator import ValidationError

    region = service.create_region("report_submission", _region_payload(), admin)
    assert region["region_code"].startswith("custom_region_")
    assert region["default_mode"] == "sql"
    assert region["system_supported"] is False

    field = service.create_field(region["id"], _field_payload(), admin)
    source = storage.get_source_config(region["id"])
    assert source["source_mode"] == "sql"
    with pytest.raises(ValidationError, match="字段别名创建后不可修改"):
        service.update_field(field["id"], {"field_alias": "renamed", "row_version": 1}, admin)


def test_system_region_custom_field_switches_sql_and_cannot_disable_last_field(service, storage, admin):
    from auto_check.modules.dashboard_management.validator import ValidationError

    region = service.catalog("report_submission", admin)["regions"][0]
    source = storage.get_source_config(region["id"])
    configured = storage.save_source_config(region["id"], {
        "tested_signature": "a" * 64,
        "tested_at": source["created_at"],
        "tested_by": "admin",
    }, source["row_version"])

    service.create_field(region["id"], _field_payload(field_alias="added_value"), admin)
    updated_source = storage.get_source_config(region["id"])
    assert updated_source["source_mode"] == "sql"
    assert updated_source["tested_signature"] is None
    assert updated_source["row_version"] > configured["row_version"]

    only_region = service.create_region("report_submission", _region_payload(name="单字段区域", fields=[_field_payload(field_alias="only_value")]), admin)
    only_field = storage.list_fields(only_region["id"])[0]
    with pytest.raises(ValidationError, match="至少保留一个启用字段"):
        service.update_field(only_field["id"], {"enabled": False, "row_version": 1}, admin)


def test_service_field_create_rolls_back_when_source_invalidation_fails(service, storage, admin, monkeypatch):
    region = service.catalog("report_submission", admin)["regions"][0]
    before_fields = storage.list_fields(region["id"])
    before_source = storage.get_source_config(region["id"])

    def fail_invalidation(connection, region_id, **kwargs):
        raise RuntimeError("source invalidation failed")

    monkeypatch.setattr(storage, "_invalidate_source_test_with_connection", fail_invalidation)
    with pytest.raises(RuntimeError, match="source invalidation failed"):
        service.create_field(region["id"], _field_payload(field_alias="rollback_from_service"), admin)

    assert storage.list_fields(region["id"]) == before_fields
    assert storage.get_source_config(region["id"]) == before_source


def test_region_create_inserts_all_initial_fields_once(service, storage, admin):
    region = service.create_region("report_submission", _region_payload(fields=[
        _field_payload(field_alias="first_initial", display_order=10),
        _field_payload(field_alias="second_initial", display_order=20),
    ]), admin)
    assert [field["field_alias"] for field in storage.list_fields(region["id"])] == ["first_initial", "second_initial"]
    assert storage.get_source_config(region["id"])["source_mode"] == "sql"


def test_service_deletes_only_custom_regions(service, storage, admin):
    from auto_check.modules.dashboard_management.validator import ValidationError

    custom = service.create_region("report_submission", _region_payload(), admin)
    result = service.delete_region(custom["id"], {"row_version": custom["row_version"]}, admin)
    assert result == {"id": custom["id"], "deleted": True}
    assert storage.get_region(custom["id"]) is None

    builtin = service.catalog("report_submission", admin)["regions"][0]
    with pytest.raises(ValidationError, match="内置数据区域不能删除"):
        service.delete_region(builtin["id"], {"row_version": builtin["row_version"]}, admin)


def test_list_datasources_returns_safe_summary_only(service):
    assert service.list_datasources() == [
        {"id": "safe", "name": "安全数据源", "db_type": "postgresql"},
    ]


def test_board_preview_returns_each_enabled_region_without_one_failure_blocking_others():
    from auto_check.modules.dashboard_management.service import DashboardManagementService
    from auto_check.modules.dashboard_management.sql_executor import QueryPreview

    fields = [{"field_alias": "value", "name": "指标值", "value_type": "integer", "enabled": True}]
    regions = [
        {"id": 1, "region_code": "system_value", "name": "系统指标", "shape": "scalar", "system_supported": True},
        {"id": 2, "region_code": "sql_value", "name": "SQL指标", "shape": "list", "system_supported": False},
        {"id": 3, "region_code": "missing_value", "name": "未配置指标", "shape": "list", "system_supported": False},
    ]

    class Storage:
        database = object()
        def list_regions(self, board_code, include_disabled=True):
            assert board_code == "report_submission" and include_disabled is False
            return regions
        def list_fields(self, region_id, include_disabled=True):
            assert include_disabled is False
            return fields
        def get_source_config(self, region_id):
            return {
                1: {"source_mode": "system"},
                2: {"source_mode": "sql", "datasource_id": "safe", "sql_text": "SELECT 2 AS value", "tested_signature": "valid"},
                3: {"source_mode": "sql", "datasource_id": None, "sql_text": None, "tested_signature": None},
            }[region_id]

    class SystemExecutor:
        def execute(self, database, region_code, active_fields, shape):
            preview = QueryPreview(("value",), ({"value": 1},), False, 1, "")
            return type("Result", (), {"preview": preview})()

    class SqlExecutor:
        def signature_for(self, source, sql, active_fields, shape):
            return "valid"
        def execute(self, source, sql, active_fields, shape):
            return QueryPreview(("value",), ({"value": 2},), False, 1, "valid")

    preview = DashboardManagementService(
        Storage(), datasource_loader=lambda: [{"id": "safe", "config": object()}],
        sql_executor=SqlExecutor(), system_executor=SystemExecutor(),
    ).preview_board_data("report_submission", {})

    assert preview["board"] == {"code": "report_submission", "name": "金融监管报表报送大屏"}
    assert [region["status"] for region in preview["regions"]] == ["success", "success", "error"]
    assert preview["regions"][0]["fields"] == [{"alias": "value", "name": "指标值", "value_type": "integer"}]
    assert preview["regions"][1]["rows"] == ({"value": 2},)
    assert preview["regions"][2]["error"] == {"code": "invalid_request", "message": "自定义 SQL 尚未完成配置"}
