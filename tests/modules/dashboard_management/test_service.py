from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

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


def test_fixed_board_returns_each_builtin_region_without_one_failure_blocking_others(storage):
    from auto_check.modules.dashboard_management.service import DashboardManagementService
    from auto_check.modules.dashboard_management.sql_executor import QueryPreview

    class FailingSystemExecutor:
        def execute(self, database, region_code, active_fields, shape):
            if region_code == "monthly_report_validation_remaining":
                raise RuntimeError("database connection lost")
            preview = QueryPreview(
                columns=tuple(field["field_alias"] for field in active_fields),
                rows=tuple({field["field_alias"]: 1 for field in active_fields}),
                has_more=False,
                returned_count=1,
                tested_signature="",
            )
            return type("Result", (), {"preview": preview})()

    result = DashboardManagementService(
        storage,
        system_executor=FailingSystemExecutor(),
        now=lambda: datetime(2026, 9, 15, 10, 30),
    ).preview_board_data("report_submission", {})

    assert result["board"] == {"code": "report_submission", "name": "金融监管报表报送大屏"}
    status_by_code = {region["code"]: region["status"] for region in result["regions"]}
    assert status_by_code["monthly_report_validation_remaining"] == "error"
    assert status_by_code["annual_supplement_completed"] == "success"
    remaining = next(
        region for region in result["regions"]
        if region["code"] == "monthly_report_validation_remaining"
    )
    assert remaining["error"] == {"code": "internal_error", "message": "数据读取失败"}
    supplement = next(
        region for region in result["regions"]
        if region["code"] == "annual_supplement_completed"
    )
    assert supplement["status"] == "success"


def test_external_board_preview_uses_only_fixed_builtin_regions_and_fields(
    storage, admin
):
    from auto_check.modules.dashboard_management.catalog import (
        BUILTIN_FIELD_SEEDS,
        BUILTIN_REGION_SEEDS,
    )
    from auto_check.modules.dashboard_management.service import DashboardManagementService

    service = DashboardManagementService(
        storage,
        datasource_loader=lambda: [
            {"id": "safe", "name": "安全数据源", "db_type": "postgresql"}
        ],
        now=lambda: datetime(2026, 9, 15, 9, 30),
    )
    custom_region = service.create_region(
        "report_submission", _region_payload(name="不得外泄的自定义区域"), admin
    )
    annual_region = next(
        region
        for region in service.catalog("report_submission", admin)["regions"]
        if region["region_code"] == "annual_supplement_completed"
    )
    service.create_field(
        annual_region["id"],
        _field_payload(field_alias="must_not_leak", name="不得外泄的字段"),
        admin,
    )

    external_submission = service.preview_external_board_data("report_submission")
    external_process = service.preview_external_board_data("reporting_process")
    internal_submission = service.preview_board_data("report_submission", admin)

    assert external_submission["generated_at"] == "2026-09-15T09:30:00"
    assert external_submission["status"] == "partial"
    assert [item["code"] for item in external_submission["regions"]] == [
        seed.code
        for seed in BUILTIN_REGION_SEEDS
        if seed.board_code == "report_submission"
    ]
    assert [item["code"] for item in external_process["regions"]] == [
        seed.code
        for seed in BUILTIN_REGION_SEEDS
        if seed.board_code == "reporting_process"
    ]
    annual_external = next(
        item
        for item in external_submission["regions"]
        if item["code"] == "annual_supplement_completed"
    )
    assert [field["alias"] for field in annual_external["fields"]] == [
        seed.alias
        for seed in BUILTIN_FIELD_SEEDS
        if seed.region_code == "annual_supplement_completed"
    ]
    assert "must_not_leak" not in str(external_submission)
    assert custom_region["region_code"] not in str(external_submission)
    assert internal_submission == external_submission
    assert internal_submission["data_year"] == 2026
    assert [item["code"] for item in internal_submission["regions"]] == [
        seed.code
        for seed in BUILTIN_REGION_SEEDS
        if seed.board_code == "report_submission"
    ]
    assert custom_region["region_code"] not in str(internal_submission)
    assert "must_not_leak" not in str(internal_submission)


def test_january_writes_previous_december_but_returns_only_current_data_year(storage, admin):
    from auto_check.modules.dashboard_management.service import DashboardManagementService
    from auto_check.modules.dashboard_management.sql_executor import QueryPreview

    now = datetime(2027, 1, 4, 9, 0)
    completion_region = next(
        row for row in storage.list_regions("report_submission")
        if row["region_code"] == "report_reconciliation_completion_time"
    )

    class SystemExecutor:
        def execute(self, database, region_code, active_fields, shape):
            if region_code != "report_reconciliation_completion_time":
                raise RuntimeError("unrelated system region")
            preview = QueryPreview(
                columns=("month", "reconciliation_completed_at"),
                rows=(
                    {"month": "2026-12", "reconciliation_completed_at": "2027-01-03T01:15:00"},
                    {"month": "2027-01", "reconciliation_completed_at": "2027-01-04T08:30:00"},
                ),
                has_more=False,
                returned_count=2,
                tested_signature="",
            )
            return type("Result", (), {"preview": preview})()

    service = DashboardManagementService(
        storage, system_executor=SystemExecutor(), now=lambda: now
    )
    result = service.preview_external_board_data("report_submission")
    completion = next(
        item for item in result["regions"]
        if item["code"] == "report_reconciliation_completion_time"
    )

    assert result["data_year"] == 2027
    assert [row["month"] for row in completion["rows"]] == ["2027-01"]
    assert storage.list_year_snapshots(completion_region["id"], 2026)[-1]["row"]["month"] == "2026-12"
    assert storage.list_year_snapshots(completion_region["id"], 2027)[0]["row"]["month"] == "2027-01"


def test_january_validation_preview_does_not_leak_2026_baseline_into_2027(storage):
    from auto_check.modules.dashboard_management.service import DashboardManagementService
    from auto_check.modules.dashboard_management.sql_executor import QueryPreview

    validation = next(
        row for row in storage.list_regions("report_submission")
        if row["region_code"] == "report_validation_issue_handling"
    )
    source_config = storage.get_source_config(validation["id"])
    storage.save_source_config(
        validation["id"],
        {
            "source_mode": "sql",
            "datasource_id": "safe",
            "sql_text": "SELECT 2027 validation issue rows",
            "tested_signature": "valid",
            "tested_at": datetime(2027, 1, 4, 8, 0),
            "tested_by": "admin",
        },
        source_config["row_version"],
        expected_region_version=validation["row_version"],
    )

    class SqlExecutor:
        def signature_for(self, source, sql, active_fields, shape):
            return "valid"

        def execute(self, source, sql, active_fields, shape):
            return QueryPreview(
                columns=("month", "validation_issue_count"),
                rows=({"month": "2027-01", "validation_issue_count": 3},),
                has_more=False,
                returned_count=1,
                tested_signature="valid",
            )

    result = DashboardManagementService(
        storage,
        datasource_loader=lambda: [{"id": "safe", "config": object()}],
        sql_executor=SqlExecutor(),
        now=lambda: datetime(2027, 1, 4, 9, 0),
    ).preview_board_data("report_submission", {})
    item = next(
        region for region in result["regions"]
        if region["code"] == "report_validation_issue_handling"
    )

    assert item["status"] == "success"
    assert item["rows"] == ({
        "month": "2027-01",
        "validation_issue_count": 3,
    },)
    assert [
        row["period_value"]
        for row in storage.list_year_snapshots(validation["id"], 2026)
    ] == list(range(1, 10))
    assert [
        row["row"] for row in storage.list_year_snapshots(validation["id"], 2027)
    ] == [{"month": "2027-01", "validation_issue_count": 3}]


def test_external_board_preview_rejects_unknown_board_code(service):
    from auto_check.modules.dashboard_management.validator import NotFoundError

    with pytest.raises(NotFoundError, match="外部看板接口不存在"):
        service.preview_external_board_data("unknown_board")


def test_snapshot_preview_prefers_sql_rows_and_preserves_unreturned_history(storage):
    from auto_check.modules.dashboard_management.service import DashboardManagementService
    from auto_check.modules.dashboard_management.sql_executor import QueryPreview

    trust = next(
        row
        for row in storage.list_regions("report_submission")
        if row["region_code"] == "monthly_trust_projects"
    )
    source_config = storage.get_source_config(trust["id"])
    storage.save_source_config(
        trust["id"],
        {
            "source_mode": "sql",
            "datasource_id": "safe",
            "sql_text": "SELECT snapshot rows",
            "tested_signature": "valid",
            "tested_at": datetime(2026, 9, 15, 8, 0),
            "tested_by": "admin",
        },
        source_config["row_version"],
        expected_region_version=trust["row_version"],
    )

    class SqlExecutor:
        def signature_for(self, source, sql, active_fields, shape):
            return "valid"

        def execute(self, source, sql, active_fields, shape):
            return QueryPreview(
                columns=tuple(field["field_alias"] for field in active_fields),
                rows=(
                    {
                        "month": "6月",
                        "single_trust_count": 400,
                        "collective_trust_count": 500,
                        "property_trust_count": 600,
                    },
                    {
                        "month": "7月",
                        "single_trust_count": 1,
                        "collective_trust_count": 2,
                        "property_trust_count": 3,
                    },
                    {
                        "month": "10月",
                        "single_trust_count": 10,
                        "collective_trust_count": 20,
                        "property_trust_count": 30,
                    },
                ),
                has_more=False,
                returned_count=3,
                tested_signature="valid",
            )

    now = datetime(2026, 9, 15, 10, 30)
    result = DashboardManagementService(
        storage,
        datasource_loader=lambda: [{"id": "safe", "config": object()}],
        sql_executor=SqlExecutor(),
        now=lambda: now,
    ).preview_board_data("report_submission", {})
    item = next(region for region in result["regions"] if region["code"] == trust["region_code"])

    assert item["status"] == "success"
    assert item["snapshot_status"] == "fresh"
    assert item["snapshot_refreshed_at"] == "2026-09-15T10:30:00"
    assert item["returned_count"] == 7
    assert [row["month"] for row in item["rows"]] == [
        "1月", "2月", "3月", "4月", "5月", "6月", "7月",
    ]
    assert item["rows"][0]["single_trust_count"] == 7
    assert item["rows"][5]["single_trust_count"] == 400
    assert item["rows"][6]["single_trust_count"] == 1
    assert [row["period_value"] for row in storage.list_year_snapshots(trust["id"], 2026)] == [
        1, 2, 3, 4, 5, 6, 7,
    ]


def test_validation_sql_preview_refreshes_seeded_2026_september_value(storage):
    from auto_check.modules.dashboard_management.service import DashboardManagementService
    from auto_check.modules.dashboard_management.sql_executor import QueryPreview

    validation = next(
        row for row in storage.list_regions("report_submission")
        if row["region_code"] == "report_validation_issue_handling"
    )
    source_config = storage.get_source_config(validation["id"])
    storage.save_source_config(
        validation["id"],
        {
            "source_mode": "sql",
            "datasource_id": "safe",
            "sql_text": "SELECT validation issue rows",
            "tested_signature": "valid",
            "tested_at": datetime(2026, 9, 21, 8, 0),
            "tested_by": "admin",
        },
        source_config["row_version"],
        expected_region_version=validation["row_version"],
    )

    class SqlExecutor:
        def signature_for(self, source, sql, active_fields, shape):
            return "valid"

        def execute(self, source, sql, active_fields, shape):
            return QueryPreview(
                columns=("month", "validation_issue_count"),
                rows=({"month": "2026-09", "validation_issue_count": 40005},),
                has_more=False,
                returned_count=1,
                tested_signature="valid",
            )

    result = DashboardManagementService(
        storage,
        datasource_loader=lambda: [{"id": "safe", "config": object()}],
        sql_executor=SqlExecutor(),
        now=lambda: datetime(2026, 9, 21, 9, 0),
    ).preview_board_data("report_submission", {})
    item = next(
        region for region in result["regions"]
        if region["code"] == "report_validation_issue_handling"
    )

    assert item["status"] == "success"
    assert [row["month"] for row in item["rows"]] == [
        "2026-01", "2026-02", "2026-03", "2026-04", "2026-05",
        "2026-06", "2026-07", "2026-08", "2026-09",
    ]
    assert item["rows"][-1]["validation_issue_count"] == 40005
    september = next(
        row for row in storage.list_year_snapshots(validation["id"], 2026)
        if row["period_value"] == 9
    )
    assert september["row"]["validation_issue_count"] == 40005


def test_snapshot_preview_falls_back_to_current_year_history_when_live_query_fails(storage):
    from auto_check.modules.dashboard_management.service import DashboardManagementService

    class FailingSystemExecutor:
        def execute(self, database, region_code, active_fields, shape):
            raise RuntimeError("driver leaked details must not be returned")

    result = DashboardManagementService(
        storage,
        system_executor=FailingSystemExecutor(),
        now=lambda: datetime(2026, 9, 15, 10, 30),
    ).preview_board_data("report_submission", {})
    item = next(
        region
        for region in result["regions"]
        if region["code"] == "report_reconciliation_completion_time"
    )

    assert item["status"] == "success"
    assert item["snapshot_status"] == "stale"
    assert item["snapshot_refreshed_at"] is None
    assert item["returned_count"] == 6
    assert [row["month"] for row in item["rows"]] == [
        "2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06",
    ]
    assert "driver" not in str(item)


def test_snapshot_preview_does_not_hide_datetime_contract_error_with_stale_history(storage):
    from auto_check.modules.dashboard_management.service import DashboardManagementService
    from auto_check.modules.dashboard_management.sql_executor import QueryPreview

    class InvalidCompletionExecutor:
        def execute(self, database, region_code, active_fields, shape):
            if region_code != "report_reconciliation_completion_time":
                raise RuntimeError("unrelated system region")
            preview = QueryPreview(
                columns=("month", "reconciliation_completed_at"),
                rows=({
                    "month": "2026-09",
                    "reconciliation_completed_at": "09:30",
                },),
                has_more=False,
                returned_count=1,
                tested_signature="",
            )
            return type("Result", (), {"preview": preview})()

    result = DashboardManagementService(
        storage,
        system_executor=InvalidCompletionExecutor(),
        now=lambda: datetime(2026, 9, 15, 10, 30),
    ).preview_board_data("report_submission", {})
    item = next(
        region
        for region in result["regions"]
        if region["code"] == "report_reconciliation_completion_time"
    )

    assert item["status"] == "error"
    assert item["error"] == {
        "code": "invalid_request",
        "message": "新数据必须提供完整日期时间",
    }
    assert "snapshot_status" not in item
    assert "rows" not in item


def test_data_year_uses_business_timezone_at_calendar_boundary(storage):
    from auto_check.modules.dashboard_management.service import DashboardManagementService

    class FailingSystemExecutor:
        def execute(self, database, region_code, active_fields, shape):
            raise RuntimeError("database failure")

    result = DashboardManagementService(
        storage,
        system_executor=FailingSystemExecutor(),
        now=lambda: datetime(2026, 12, 31, 16, 30, tzinfo=timezone.utc),
    ).preview_board_data("report_submission", {})

    assert result["data_year"] == 2027
    completion = next(
        region
        for region in result["regions"]
        if region["code"] == "report_reconciliation_completion_time"
    )
    assert completion["status"] == "error"
    assert completion["error"]["code"] == "data_not_ready"


def test_monthly_special_processing_snapshot_returns_quarterly_api_rows_without_persisting_future_quarter(storage):
    from auto_check.modules.dashboard_management.service import DashboardManagementService
    from auto_check.modules.dashboard_management.sql_executor import QueryPreview

    quarterly = next(
        row
        for row in storage.list_regions("report_submission")
        if row["region_code"] == "quarterly_special_processing"
    )

    class SystemExecutor:
        def execute(self, database, region_code, active_fields, shape):
            if region_code != "quarterly_special_processing":
                raise RuntimeError("unrelated system region")
            preview = QueryPreview(
                columns=("month", "special_processing_count"),
                rows=({"month": "2026-08", "special_processing_count": 4},),
                has_more=False,
                returned_count=1,
                tested_signature="",
            )
            return type("Result", (), {"preview": preview})()

    result = DashboardManagementService(
        storage,
        system_executor=SystemExecutor(),
        now=lambda: datetime(2026, 9, 15, 10, 30),
    ).preview_board_data("report_submission", {})
    item = next(
        region
        for region in result["regions"]
        if region["code"] == "quarterly_special_processing"
    )

    assert item["status"] == "success"
    assert item["fields"] == [
        {"alias": "quarter", "name": "季度", "value_type": "string"},
        {"alias": "special_processing_count", "name": "特殊处理数量", "value_type": "integer"},
    ]
    assert item["columns"] == ("quarter", "special_processing_count")
    assert item["rows"] == (
        {"quarter": "第1季度", "special_processing_count": 31},
        {"quarter": "第2季度", "special_processing_count": 34},
        {"quarter": "第3季度", "special_processing_count": 12},
        {"quarter": "第4季度", "special_processing_count": 0},
    )
    assert [
        (row["period_type"], row["period_value"])
        for row in storage.list_year_snapshots(quarterly["id"], 2026)
    ] == [("month", month) for month in range(1, 9)]


def test_special_processing_empty_current_reporting_month_overwrites_stale_month_to_zero(storage):
    from auto_check.modules.dashboard_management.service import DashboardManagementService
    from auto_check.modules.dashboard_management.sql_executor import QueryPreview
    from auto_check.modules.dashboard_management.year_snapshots import SnapshotRow

    quarterly = next(
        row for row in storage.list_regions("report_submission")
        if row["region_code"] == "quarterly_special_processing"
    )
    storage.upsert_year_snapshots(
        quarterly["id"],
        (SnapshotRow(2026, "month", 8, {
            "month": "2026-08", "special_processing_count": 4,
        }),),
        datetime(2026, 9, 14, 10, 0),
    )

    class SystemExecutor:
        def execute(self, database, region_code, active_fields, shape):
            if region_code != "quarterly_special_processing":
                raise RuntimeError("unrelated system region")
            return type("Result", (), {"preview": QueryPreview(
                columns=("month", "special_processing_count"),
                rows=({"month": "2026-07", "special_processing_count": 8},),
                has_more=False,
                returned_count=1,
                tested_signature="",
            )})()

    result = DashboardManagementService(
        storage,
        system_executor=SystemExecutor(),
        now=lambda: datetime(2026, 9, 15, 10, 30),
    ).preview_board_data("report_submission", {})
    item = next(
        region for region in result["regions"]
        if region["code"] == "quarterly_special_processing"
    )

    assert item["rows"][2] == {
        "quarter": "第3季度", "special_processing_count": 8,
    }
    august = next(
        row for row in storage.list_year_snapshots(quarterly["id"], 2026)
        if row["period_type"] == "month" and row["period_value"] == 8
    )
    assert august["row"]["special_processing_count"] == 0


def test_special_processing_january_does_not_invent_zero_for_previous_december():
    from auto_check.modules.dashboard_management.service import _with_current_reporting_month_zero

    assert _with_current_reporting_month_zero((), datetime(2027, 1, 15, 10, 30)) == ()


def test_special_processing_invalid_month_does_not_replace_current_reporting_month(storage):
    from auto_check.modules.dashboard_management.service import DashboardManagementService
    from auto_check.modules.dashboard_management.sql_executor import QueryPreview
    from auto_check.modules.dashboard_management.year_snapshots import SnapshotRow

    special = next(
        row for row in storage.list_regions("report_submission")
        if row["region_code"] == "quarterly_special_processing"
    )
    storage.upsert_year_snapshots(
        special["id"],
        (SnapshotRow(2026, "month", 8, {
            "month": "2026-08", "special_processing_count": 4,
        }),),
        datetime(2026, 9, 14, 10, 0),
    )

    class SystemExecutor:
        def execute(self, database, region_code, active_fields, shape):
            if region_code != "quarterly_special_processing":
                raise RuntimeError("unrelated system region")
            return type("Result", (), {"preview": QueryPreview(
                columns=("month", "special_processing_count"),
                rows=({"month": "2026-8", "special_processing_count": 8},),
                has_more=False,
                returned_count=1,
                tested_signature="",
            )})()

    result = DashboardManagementService(
        storage, system_executor=SystemExecutor(),
        now=lambda: datetime(2026, 9, 15, 10, 30),
    ).preview_board_data("report_submission", {})
    item = next(
        region for region in result["regions"]
        if region["code"] == "quarterly_special_processing"
    )

    assert item["status"] == "error"
    august = next(
        row for row in storage.list_year_snapshots(special["id"], 2026)
        if row["period_type"] == "month" and row["period_value"] == 8
    )
    assert august["row"]["special_processing_count"] == 4


def test_special_processing_preserves_confirmed_2026_july_baseline_and_refreshes_august(storage):
    from auto_check.modules.dashboard_management.service import DashboardManagementService
    from auto_check.modules.dashboard_management.sql_executor import QueryPreview

    class SystemExecutor:
        def execute(self, database, region_code, active_fields, shape):
            if region_code != "quarterly_special_processing":
                raise RuntimeError("unrelated system region")
            return type("Result", (), {"preview": QueryPreview(
                columns=("month", "special_processing_count"),
                rows=(
                    {"month": "2026-07", "special_processing_count": 1},
                    {"month": "2026-08", "special_processing_count": 17},
                ),
                has_more=False,
                returned_count=2,
                tested_signature="",
            )})()

    result = DashboardManagementService(
        storage, system_executor=SystemExecutor(),
        now=lambda: datetime(2026, 9, 15, 10, 30),
    ).preview_board_data("report_submission", {})
    item = next(
        region for region in result["regions"]
        if region["code"] == "quarterly_special_processing"
    )
    special = next(
        row for row in storage.list_regions("report_submission")
        if row["region_code"] == "quarterly_special_processing"
    )

    assert item["rows"][2] == {
        "quarter": "第3季度", "special_processing_count": 25,
    }
    values_by_month = {
        row["period_value"]: row["row"]["special_processing_count"]
        for row in storage.list_year_snapshots(special["id"], 2026)
        if row["period_type"] == "month"
    }
    assert values_by_month[7] == 8
    assert values_by_month[8] == 17


def test_special_processing_does_not_zero_confirmed_2026_july_when_august_is_current():
    from auto_check.modules.dashboard_management.service import _with_current_reporting_month_zero

    assert _with_current_reporting_month_zero((), datetime(2026, 8, 15, 10, 30)) == ()


def test_snapshot_preview_without_current_year_history_keeps_existing_error(storage):
    from auto_check.modules.dashboard_management.service import DashboardManagementService

    class FailingSystemExecutor:
        def execute(self, database, region_code, active_fields, shape):
            raise RuntimeError("database failure")

    result = DashboardManagementService(
        storage,
        system_executor=FailingSystemExecutor(),
        now=lambda: datetime(2027, 1, 15, 10, 30),
    ).preview_board_data("report_submission", {})
    item = next(
        region
        for region in result["regions"]
        if region["code"] == "report_reconciliation_completion_time"
    )

    assert item["status"] == "error"
    assert item["error"] == {
        "code": "data_not_ready",
        "message": "当前年度数据尚未准备完成",
    }
    assert result["status"] == "partial"
    assert result["data_year"] == 2027


def test_default_snapshot_executors_can_read_all_twelve_months_without_changing_editor_limit(storage):
    from auto_check.modules.dashboard_management.service import DashboardManagementService

    service = DashboardManagementService(storage)

    assert service._sql_executor.preview_limit == 10
    assert service._system_executor.preview_limit == 10
    assert service._board_sql_executor.preview_limit is None
    assert service._board_system_executor.preview_limit is None


def test_fixed_board_returns_more_than_ten_rows_without_truncation(storage):
    from auto_check.modules.dashboard_management.service import DashboardManagementService
    from auto_check.modules.dashboard_management.sql_executor import QueryPreview

    region = next(
        row for row in storage.list_regions("reporting_process")
        if row["region_code"] == "regulatory_report_count"
    )
    source_config = storage.get_source_config(region["id"])
    storage.save_source_config(
        region["id"],
        {
            "source_mode": "sql",
            "datasource_id": "safe",
            "sql_text": "SELECT report_type, report_count",
            "tested_signature": "valid",
            "tested_at": datetime(2026, 9, 16, 8, 0),
            "tested_by": "admin",
        },
        source_config["row_version"],
        expected_region_version=region["row_version"],
    )
    rows = tuple(
        {"report_type": f"R{index:02d}", "report_count": index}
        for index in range(15)
    )

    class SqlExecutor:
        def signature_for(self, source, sql, active_fields, shape):
            return "valid"

        def execute(self, source, sql, active_fields, shape):
            return QueryPreview(
                columns=("report_type", "report_count"),
                rows=rows,
                has_more=False,
                returned_count=len(rows),
                tested_signature="valid",
            )

    service = DashboardManagementService(
        storage,
        datasource_loader=lambda: [{"id": "safe", "config": object()}],
        sql_executor=SqlExecutor(),
        now=lambda: datetime(2026, 9, 16, 9, 0),
    )
    result = service.preview_external_board_data("reporting_process")
    item = next(
        entry for entry in result["regions"]
        if entry["code"] == "regulatory_report_count"
    )

    assert item["status"] == "success"
    assert item["has_more"] is False
    assert item["returned_count"] == 15
    assert item["rows"] == rows
    for entry in result["regions"]:
        if entry.get("status") == "success" and "rows" in entry:
            assert entry["has_more"] is False
            assert entry["returned_count"] == len(entry["rows"])


def test_snapshot_preview_uses_one_request_time_for_all_regions_and_fallback(storage):
    from auto_check.modules.dashboard_management.service import DashboardManagementService

    calls = []

    def changing_clock():
        calls.append(len(calls))
        return (
            datetime(2026, 12, 31, 23, 59)
            if len(calls) == 1
            else datetime(2027, 1, 1, 0, 0)
        )

    class FailingSystemExecutor:
        def execute(self, database, region_code, active_fields, shape):
            raise RuntimeError("database failure")

    result = DashboardManagementService(
        storage,
        system_executor=FailingSystemExecutor(),
        now=changing_clock,
    ).preview_board_data("report_submission", {})
    completion = next(
        item
        for item in result["regions"]
        if item["code"] == "report_reconciliation_completion_time"
    )

    assert calls == [0]
    assert completion["snapshot_status"] == "stale"
    assert completion["returned_count"] == 6


def test_snapshot_preview_rejects_truncated_live_result_without_overwriting_history(storage):
    from auto_check.modules.dashboard_management.service import DashboardManagementService
    from auto_check.modules.dashboard_management.sql_executor import QueryPreview

    trust = next(
        row
        for row in storage.list_regions("report_submission")
        if row["region_code"] == "monthly_trust_projects"
    )
    source_config = storage.get_source_config(trust["id"])
    storage.save_source_config(
        trust["id"],
        {
            "source_mode": "sql",
            "datasource_id": "safe",
            "sql_text": "SELECT too many snapshot rows",
            "tested_signature": "valid",
            "tested_at": datetime(2026, 9, 15, 8, 0),
            "tested_by": "admin",
        },
        source_config["row_version"],
        expected_region_version=trust["row_version"],
    )

    class TruncatedSqlExecutor:
        def signature_for(self, source, sql, active_fields, shape):
            return "valid"

        def execute(self, source, sql, active_fields, shape):
            return QueryPreview(
                columns=tuple(field["field_alias"] for field in active_fields),
                rows=({"month": "6月", "single_trust_count": 999},),
                has_more=True,
                returned_count=1,
                tested_signature="valid",
            )

    result = DashboardManagementService(
        storage,
        datasource_loader=lambda: [{"id": "safe", "config": object()}],
        sql_executor=TruncatedSqlExecutor(),
        now=lambda: datetime(2026, 9, 15, 10, 30),
    ).preview_board_data("report_submission", {})
    item = next(region for region in result["regions"] if region["code"] == trust["region_code"])

    assert item["status"] == "error"
    assert item["error"] == {
        "code": "truncated_result",
        "message": "数据来源未返回完整结果",
    }
    assert "rows" not in item
    assert storage.list_year_snapshots(trust["id"], 2026)[5]["row"]["single_trust_count"] == 4
    assert result["status"] == "partial"


def test_fixed_board_uses_only_builtin_fields_and_rejects_disabled_builtin(storage):
    from auto_check.modules.dashboard_management.service import DashboardManagementService

    trust = next(
        row
        for row in storage.list_regions("report_submission")
        if row["region_code"] == "monthly_trust_projects"
    )
    property_field = next(
        field
        for field in storage.list_fields(trust["id"])
        if field["field_alias"] == "property_trust_count"
    )
    storage.update_field(
        property_field["id"], {"enabled": False}, property_field["row_version"]
    )
    storage.create_field(trust["id"], {
        "field_alias": "new_metric",
        "name": "新增指标",
        "value_type": "integer",
        "nullable": True,
        "description": "新增后旧快照中尚无值",
        "display_order": 50,
    })

    result = DashboardManagementService(
        storage,
        now=lambda: datetime(2026, 9, 15, 10, 30),
    ).preview_board_data("report_submission", {})
    item = next(region for region in result["regions"] if region["code"] == trust["region_code"])

    assert item["status"] == "error"
    assert item["error"] == {
        "code": "invalid_request",
        "message": "外部接口固定字段配置不完整",
    }
    assert "new_metric" not in str(result)
    assert result["status"] == "partial"


def test_snapshot_region_does_not_fallback_when_required_period_field_is_disabled(storage):
    from auto_check.modules.dashboard_management.service import DashboardManagementService

    completion = next(
        row
        for row in storage.list_regions("report_submission")
        if row["region_code"] == "report_reconciliation_completion_time"
    )
    month_field = next(
        field
        for field in storage.list_fields(completion["id"])
        if field["field_alias"] == "month"
    )
    storage.update_field(month_field["id"], {"enabled": False}, month_field["row_version"])

    result = DashboardManagementService(
        storage,
        now=lambda: datetime(2026, 9, 15, 10, 30),
    ).preview_board_data("report_submission", {})
    item = next(region for region in result["regions"] if region["code"] == completion["region_code"])

    assert item["status"] == "error"
    assert item["error"] == {
        "code": "invalid_request",
        "message": "外部接口固定字段配置不完整",
    }
    assert "snapshot_status" not in item
