from __future__ import annotations

import pytest

from .test_api import Service, _dispatch, _router


class _SourceService(Service):
    def test_sql(self, region_id, payload, current_user):
        return {"region_id": region_id, "tested_signature": "a" * 64, "rows": []}

    def save_source_config(self, region_id, payload, current_user):
        return {"region_id": region_id, "row_version": 3, "source_mode": payload["source_mode"]}


def test_source_test_uses_test_sql_permission_and_source_save_uses_manage():
    router = _router(_SourceService())
    tester = {"role": "user", "capabilities": ["sys.dashboard_management.test_sql"]}
    manager = {"role": "user", "capabilities": ["sys.dashboard_management.manage"]}
    body = {"datasource_id": "safe", "sql_text": "SELECT value"}

    response = _dispatch(router, "POST", "/regions/1/source/test", body=body, user=tester)
    assert response.status == 200 and response.body["data"]["tested_signature"] == "a" * 64
    assert _dispatch(router, "POST", "/regions/1/source/test", body=body, user=manager).status == 403
    assert _dispatch(router, "PUT", "/regions/1/source", body={**body, "source_mode": "sql"}, user=tester).status == 403
    assert _dispatch(router, "PUT", "/regions/1/source", body={**body, "source_mode": "sql"}, user=manager).status == 200


def test_source_save_exposes_sql_retest_conflict_without_sensitive_exception_text():
    from auto_check.modules.dashboard_management.service import SqlRetestRequiredError

    class RetestRequired(_SourceService):
        def save_source_config(self, region_id, payload, current_user):
            raise SqlRetestRequiredError()

    response = _dispatch(_router(RetestRequired()), "PUT", "/regions/1/source", body={"source_mode": "sql"})
    assert response.status == 409
    assert response.body["error"]["code"] == "sql_retest_required"


def test_service_saves_invalid_sql_with_warning_without_requiring_a_successful_test():
    from auto_check.app.config import DataSourceConfig, DataSourceEntry
    from auto_check.modules.dashboard_management.service import DashboardManagementService
    from auto_check.modules.dashboard_management.sql_executor import QueryPreview, SqlPreviewExecutor
    from auto_check.modules.dashboard_management.validator import ValidationError

    source = DataSourceEntry("safe", "安全数据源", DataSourceConfig(
        "postgresql", "hidden", 5432, "db", "public", "reader", "secret",
    ))
    fields = [{"field_alias": "value", "value_type": "integer", "nullable": False, "enabled": True}]

    class Storage:
        def __init__(self):
            self.config = {"row_version": 1, "tested_signature": None, "tested_at": None, "tested_by": None}

        def get_region(self, region_id):
            return {"id": region_id, "shape": "list", "system_supported": True, "row_version": 1}

        def list_fields(self, region_id, include_disabled=False):
            return fields

        def get_source_config(self, region_id):
            return dict(self.config)

        def record_successful_sql_test(self, region_id, signature, username, schema_version):
            assert schema_version == 1
            self.config.update(tested_signature=signature, tested_at="now", tested_by=username, row_version=2)
            return dict(self.config)

        def save_source_config(self, region_id, values, expected_version, *, expected_region_version=None):
            assert expected_version == self.config["row_version"]
            assert expected_region_version == 1
            self.config.update(values, row_version=self.config["row_version"] + 1)
            return dict(self.config)

    class Executor:
        @staticmethod
        def signature_for(source, sql, fields, shape):
            return SqlPreviewExecutor.signature_for(source, sql, fields, shape)

        @staticmethod
        def validate_query(source, sql):
            return SqlPreviewExecutor.validate_query(source, sql)

        def execute(self, source, sql, fields, shape):
            return QueryPreview(("value",), ({"value": 1},), False, 1, self.signature_for(source, sql, fields, shape))

    service = DashboardManagementService(Storage(), datasource_loader=lambda: [source], sql_executor=Executor())
    admin = {"username": "admin"}
    saved = service.save_source_config(1, {
        "source_mode": "sql", "datasource_id": "safe", "sql_text": " SELECT1 value ", "row_version": 1,
    }, admin)
    assert saved["sql_text"] == " SELECT1 value "
    assert saved["tested_signature"] is None
    assert saved["sql_warning"] == "只允许单条只读查询"
    field_mismatch_saved = service.save_source_config(1, {
        "source_mode": "sql", "datasource_id": "safe", "sql_text": "SELECT wrong_alias", "row_version": 2,
    }, admin)
    assert field_mismatch_saved["sql_text"] == "SELECT wrong_alias"
    assert "sql_warning" not in field_mismatch_saved
    with pytest.raises(ValidationError, match="只允许保存查询 SQL"):
        service.save_source_config(1, {
            "source_mode": "sql", "datasource_id": "safe", "sql_text": "DELETE FROM unsafe_table", "row_version": 3,
        }, admin)


def test_service_maps_region_snapshot_conflict_to_version_conflict():
    from auto_check.app.config import DataSourceConfig, DataSourceEntry
    from auto_check.modules.dashboard_management.service import DashboardManagementService
    from auto_check.modules.dashboard_management.sql_executor import SqlPreviewExecutor
    from auto_check.modules.dashboard_management.storage import SchemaVersionConflictError
    from auto_check.modules.dashboard_management.validator import DomainError

    source = DataSourceEntry("safe", "安全数据源", DataSourceConfig(
        "postgresql", "hidden", 5432, "db", "public", "reader", "secret",
    ))
    fields = [{"field_alias": "value", "value_type": "integer", "nullable": False, "enabled": True}]
    signature = SqlPreviewExecutor.signature_for(source, "SELECT value", fields, "list")

    class Storage:
        def get_region(self, region_id):
            return {"id": region_id, "shape": "list", "system_supported": True, "row_version": 7}

        def list_fields(self, region_id, include_disabled=False):
            return fields

        def get_source_config(self, region_id):
            return {"tested_signature": signature, "tested_at": "now", "tested_by": "admin"}

        def save_source_config(self, *args, **kwargs):
            assert kwargs["expected_region_version"] == 7
            raise SchemaVersionConflictError("stale")

    service = DashboardManagementService(Storage(), datasource_loader=lambda: [source])
    with pytest.raises(DomainError) as error:
        service.save_source_config(1, {
            "source_mode": "sql", "datasource_id": "safe", "sql_text": "SELECT value", "row_version": 2,
        }, {"username": "admin"})
    assert error.value.status == 409 and error.value.code == "version_conflict"


def test_reconciliation_sql_test_requires_datetime_and_returns_derived_time():
    from auto_check.modules.dashboard_management.service import DashboardManagementService
    from auto_check.modules.dashboard_management.sql_executor import QueryPreview

    fields = [
        {
            "field_alias": "month",
            "value_type": "string",
            "nullable": False,
            "enabled": True,
        },
        {
            "field_alias": "reconciliation_completed_time",
            "value_type": "string",
            "nullable": False,
            "enabled": True,
        },
        {
            "field_alias": "reconciliation_completed_at",
            "value_type": "datetime",
            "nullable": True,
            "enabled": True,
        },
    ]
    captured_aliases = []

    class Storage:
        def get_region(self, region_id):
            return {
                "id": region_id,
                "region_code": "report_reconciliation_completion_time",
                "shape": "list",
                "system_supported": True,
                "row_version": 1,
            }

        def list_fields(self, region_id, include_disabled=False):
            return fields

        def record_successful_sql_test(
            self, region_id, signature, username, schema_version
        ):
            assert schema_version == 1
            return {"row_version": 2, "tested_signature": signature}

    class Executor:
        def execute(self, source, sql, active_fields, shape):
            captured_aliases.extend(
                field["field_alias"] for field in active_fields
            )
            return QueryPreview(
                columns=("month", "reconciliation_completed_at"),
                rows=({
                    "month": "2026-08",
                    "reconciliation_completed_at": "2026-09-15T09:30:00",
                },),
                has_more=False,
                returned_count=1,
                tested_signature="a" * 64,
            )

    service = DashboardManagementService(
        Storage(),
        datasource_loader=lambda: [{"id": "safe", "config": object()}],
        sql_executor=Executor(),
    )
    response = service.test_sql(
        1,
        {"datasource_id": "safe", "sql_text": "SELECT month, completed_at"},
        {"username": "admin"},
    )

    assert captured_aliases == ["month", "reconciliation_completed_at"]
    assert response["columns"] == (
        "month",
        "reconciliation_completed_time",
        "reconciliation_completed_at",
    )
    assert response["rows"][0] == {
        "month": "2026-08",
        "reconciliation_completed_time": "09:30",
        "reconciliation_completed_at": "2026-09-15T09:30:00",
    }
