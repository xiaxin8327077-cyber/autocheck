from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

from auto_check.app.module_system.contracts import ModuleBootstrapContext
from auto_check.app.module_system.runtime import ModuleAssetNotFound, ModuleRuntime


class _Database:
    def __init__(self) -> None:
        self._engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        event.listen(
            self._engine,
            "connect",
            lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"),
        )

    @contextmanager
    def connect(self):
        with self._engine.connect() as connection:
            yield connection

    @contextmanager
    def transaction(self):
        with self._engine.begin() as connection:
            yield connection


class _StateStore:
    def __init__(self, database) -> None:
        self.enabled: dict[str, bool] = {}

    def save_discovered(self, manifest) -> None:
        self.enabled.setdefault(manifest.id, True)

    def load_enabled(self, module_id):
        return self.enabled.get(module_id)

    def set_enabled(self, module_id, enabled) -> None:
        self.enabled[module_id] = enabled

    def set_status(self, module_id, status, error="") -> None:
        return None


class _MigrationRunner:
    calls: list[tuple[str, int]] = []

    def __init__(self, database, schema_registry=None) -> None:
        self.schema_registry = schema_registry

    def run(self, manifest, package_name):
        self.calls.append((manifest.id, manifest.schema_version))
        return manifest.schema_version


class _SafeSqlExecutor:
    signature = "a" * 64

    def signature_for(self, source, sql, fields, shape):
        assert source["id"] == "safe"
        assert sql == "SELECT 'ok' AS initial_value"
        assert shape == "list"
        return self.signature

    def execute(self, source, sql, fields, shape):
        from auto_check.modules.dashboard_management.sql_executor import QueryPreview

        assert [field["field_alias"] for field in fields] == ["initial_value"]
        return QueryPreview(
            columns=("initial_value",),
            rows=({"initial_value": "ok"},),
            has_more=False,
            returned_count=1,
            tested_signature=self.signature,
        )


def _dispatch(runtime, method, suffix, *, body=None):
    return runtime.dispatch(
        method=method,
        path="/api/modules/dashboard-management" + suffix,
        query={},
        body=body,
        current_user={"id": "1", "username": "admin", "role": "admin"},
    )


def test_module_runtime_discovers_migrates_routes_assets_and_restores_dashboard_workflow(
    monkeypatch, tmp_path
):
    """Exercise the dashboard module through the public runtime lifecycle."""
    import auto_check.app.module_system.runtime as runtime_module
    from auto_check.modules.dashboard_management.service import DashboardManagementService
    from auto_check.modules.dashboard_management.storage import METADATA

    database = _Database()
    METADATA.create_all(database._engine)
    _MigrationRunner.calls = []
    monkeypatch.setattr(runtime_module, "ModuleStateStore", _StateStore)
    monkeypatch.setattr(runtime_module, "ModuleMigrationRunner", _MigrationRunner)
    runtime = ModuleRuntime.build(
        ModuleBootstrapContext(
            application_database=database,
            config_path=tmp_path / "config.json",
            temp_root=tmp_path / "module-data",
            now=lambda: datetime(2026, 9, 14, tzinfo=timezone.utc),
        )
    )
    runtime._loaded = [
        loaded
        for loaded in runtime._loaded
        if loaded.discovered.manifest.id == "dashboard_management"
    ]
    runtime.start()
    try:
        assert _MigrationRunner.calls == [("dashboard_management", 2)]
        modules = runtime.public_modules({"role": "admin"})
        assert modules[0]["navigation"][0]["group_id"] == "system-management"
        assert runtime.read_asset("dashboard_management", "index.js").content
        assert runtime.read_asset("dashboard_management", "styles.css").content

        report_catalog = _dispatch(runtime, "GET", "/boards/report_submission/catalog")
        process_catalog = _dispatch(runtime, "GET", "/boards/reporting_process/catalog")
        assert report_catalog.status == process_catalog.status == 200
        assert len(report_catalog.body["data"]["regions"]) == 7
        assert len(process_catalog.body["data"]["regions"]) == 3

        created = _dispatch(runtime, "POST", "/boards/report_submission/regions", body={
            "name": "集成验收区域",
            "shape": "list",
            "description": "运行时集成验收",
            "display_order": 999,
            "fields": [{
                "field_alias": "initial_value",
                "name": "首批字段",
                "value_type": "string",
                "nullable": False,
                "enabled": True,
                "description": "测试字段",
                "display_order": 10,
            }],
        })
        assert created.status == 201
        region_id = created.body["data"]["id"]

        external_submission = runtime.dispatch_external(
            method="GET",
            path=(
                "/api/external/v1/dashboard-management/boards/"
                "report_submission/preview"
            ),
            query={},
        )
        external_process = runtime.dispatch_external(
            method="GET",
            path=(
                "/api/external/v1/dashboard-management/boards/"
                "reporting_process/preview"
            ),
            query={},
        )
        assert external_submission.status == external_process.status == 200
        assert external_submission.body["status"] == "partial"
        assert external_submission.body["generated_at"]
        assert external_submission.body["meta"]["request_id"].startswith("req-")
        assert [
            region["code"] for region in external_submission.body["data"]["regions"]
        ] == [
            "annual_supplement_completed",
            "monthly_report_validation_remaining",
            "monthly_trust_projects",
            "report_reconciliation_completion_time",
            "report_validation_issue_handling",
            "quarterly_special_processing",
            "monthly_report_submission_time_comparison",
        ]
        assert [
            region["code"] for region in external_process.body["data"]["regions"]
        ] == [
            "regulatory_report_count",
            "monthly_regulatory_report_time",
            "report_validation_statistics",
        ]
        assert created.body["data"]["region_code"] not in {
            region["code"]
            for region in external_submission.body["data"]["regions"]
        }

        module = runtime._find("dashboard_management").instance
        module._service = DashboardManagementService(
            module._storage,
            datasource_loader=lambda: [{
                "id": "safe", "name": "安全替身", "db_type": "postgresql", "config": object(),
            }],
            sql_executor=_SafeSqlExecutor(),
        )
        tested = _dispatch(runtime, "POST", f"/regions/{region_id}/source/test", body={
            "datasource_id": "safe", "sql_text": "SELECT 'ok' AS initial_value",
        })
        assert tested.status == 200
        saved = _dispatch(runtime, "PUT", f"/regions/{region_id}/source", body={
            "source_mode": "sql",
            "datasource_id": "safe",
            "sql_text": "SELECT 'ok' AS initial_value",
            "row_version": tested.body["data"]["row_version"],
        })
        assert saved.status == 200

        runtime.set_enabled("dashboard_management", False, {"role": "admin"})
        assert _dispatch(runtime, "GET", "/boards").status == 404
        assert runtime.public_modules({"role": "admin"}) == []
        with pytest.raises(ModuleAssetNotFound):
            runtime.read_asset("dashboard_management", "index.js")

        runtime.set_enabled("dashboard_management", True, {"role": "admin"})
        restored = _dispatch(runtime, "GET", "/boards/report_submission/catalog")
        assert any(region["id"] == region_id for region in restored.body["data"]["regions"])

        runtime.stop()
        runtime.start()
        restarted = _dispatch(runtime, "GET", "/boards/report_submission/catalog")
        assert any(region["id"] == region_id for region in restarted.body["data"]["regions"])
    finally:
        runtime.stop()
