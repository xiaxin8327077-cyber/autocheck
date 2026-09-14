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


def test_service_requires_exact_recent_test_signature_before_sql_save():
    from auto_check.app.config import DataSourceConfig, DataSourceEntry
    from auto_check.modules.dashboard_management.service import DashboardManagementService
    from auto_check.modules.dashboard_management.sql_executor import QueryPreview, SqlPreviewExecutor
    from auto_check.modules.dashboard_management.validator import DomainError

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
            self.config.update(values, row_version=3)
            return dict(self.config)

    class Executor:
        @staticmethod
        def signature_for(source, sql, fields, shape):
            return SqlPreviewExecutor.signature_for(source, sql, fields, shape)

        def execute(self, source, sql, fields, shape):
            return QueryPreview(("value",), ({"value": 1},), False, 1, self.signature_for(source, sql, fields, shape))

    service = DashboardManagementService(Storage(), datasource_loader=lambda: [source], sql_executor=Executor())
    admin = {"username": "admin"}
    tested = service.test_sql(1, {"datasource_id": "safe", "sql_text": "SELECT value"}, admin)
    assert tested["tested_signature"]
    assert tested["row_version"] == 2
    assert "source_config" not in tested and "sql_text" not in tested and "datasource_id" not in tested
    saved = service.save_source_config(1, {
        "source_mode": "sql", "datasource_id": "safe", "sql_text": " SELECT value ", "row_version": 2,
    }, admin)
    assert saved["sql_text"] == " SELECT value "
    with pytest.raises(DomainError) as error:
        service.save_source_config(1, {
            "source_mode": "sql", "datasource_id": "safe", "sql_text": "SELECT changed", "row_version": 3,
        }, admin)
    assert error.value.status == 409 and error.value.code == "sql_retest_required"


def test_service_maps_region_snapshot_conflict_to_sql_retest_required():
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
    assert error.value.status == 409 and error.value.code == "sql_retest_required"
