from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest

from auto_check.app.module_system.contracts import ModuleBootstrapContext, ModuleManifest
from auto_check.app.module_system.runtime import ModuleRuntime


FIXTURE_PARENT = Path(__file__).resolve().parents[1] / "fixtures"


class _DropinStateStore:
    def __init__(self, database):
        self.enabled: dict[str, bool] = {}

    def save_discovered(self, manifest):
        self.enabled.setdefault(manifest.id, True)

    def load_enabled(self, module_id):
        return self.enabled.get(module_id)

    def set_enabled(self, module_id, enabled):
        self.enabled[module_id] = enabled

    def set_status(self, module_id, status, error=""):
        return None


class _DropinResult:
    def __init__(self, value=None, *, lastrowid: int | None = None):
        self._value = value
        self.lastrowid = lastrowid

    def scalar_one(self):
        return self._value

    def scalar_one_or_none(self):
        return self._value

    def first(self):
        return self._value

    def all(self):
        return self._value or []


class _DropinMigrationDatabase:
    """Execute the fixture DDL and expose its resulting information schema."""

    _CREATE_TABLE = re.compile(
        r"CREATE\s+TABLE\s+(?P<table>[A-Za-z_][A-Za-z0-9_]*)\s*\((?P<body>.*)\)\s*ENGINE",
        re.IGNORECASE | re.DOTALL,
    )

    def __init__(self):
        self.tables: dict[str, set[str]] = {}
        self.schema_versions: dict[str, int] = {}
        self.completed_migrations: dict[str, list[int]] = {}
        self._checksums: dict[str, str] = {}
        self._history: dict[int, tuple[str, int, str]] = {}
        self._history_id = 0

    @contextmanager
    def connect(self):
        yield self

    @contextmanager
    def transaction(self):
        yield self

    def execute(self, statement, parameters=None):
        sql = str(statement)
        parameters = parameters or {}
        if "GET_LOCK" in sql or "RELEASE_LOCK" in sql:
            return _DropinResult(1)
        if "information_schema.columns" in sql:
            return _DropinResult(
                [(table_name, column) for table_name, columns in self.tables.items() for column in columns]
            )
        if "SELECT schema_version, checksum" in sql:
            module_id = parameters["module_id"]
            version = self.schema_versions.get(module_id)
            return _DropinResult(None if version is None else (version, self._checksums[module_id]))
        if "SELECT to_version, checksum" in sql:
            module_id = parameters["module_id"]
            completed = self.completed_migrations.get(module_id, [])
            return _DropinResult([(version, self._checksums[module_id]) for version in completed])
        if "SELECT schema_version FROM app_module_schema_versions" in sql:
            return _DropinResult(self.schema_versions.get(parameters["module_id"]))
        if "INSERT INTO app_module_migration_history" in sql:
            self._history_id += 1
            self._history[self._history_id] = (
                parameters["module_id"],
                parameters["to_version"],
                parameters["checksum"],
            )
            return _DropinResult(lastrowid=self._history_id)
        if "INSERT INTO app_module_schema_versions" in sql:
            module_id, _, _ = self._history[parameters["history_id"]]
            self.schema_versions[module_id] = parameters["schema_version"]
            self._checksums[module_id] = parameters["checksum"]
            return _DropinResult()
        if "UPDATE app_module_migration_history" in sql:
            if parameters["status"] == "completed":
                module_id, version, _ = self._history[parameters["history_id"]]
                self.completed_migrations.setdefault(module_id, []).append(version)
            return _DropinResult()
        if match := self._CREATE_TABLE.search(sql):
            columns = {
                column_match.group(1)
                for column_match in re.finditer(
                    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s+[A-Za-z]", match.group("body"), re.MULTILINE
                )
                if column_match.group(1).upper() not in {"PRIMARY", "UNIQUE", "KEY"}
            }
            self.tables[match.group("table")] = columns
            return _DropinResult()
        raise AssertionError(f"unexpected fixture SQL: {sql}")


@pytest.fixture
def dropin_runtime(monkeypatch, tmp_path):
    """Build a runtime from the fixture package without any application registration."""
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    import auto_check.app.module_system.runtime as runtime_module
    import dropin_modules.report_demo.module as report_demo_module

    monkeypatch.setattr(runtime_module, "ModuleStateStore", _DropinStateStore)

    def create():
        report_demo_module.reset_fixture_state()
        database = _DropinMigrationDatabase()
        runtime = ModuleRuntime.build(
            ModuleBootstrapContext(
                application_database=database,
                config_path=tmp_path / "config.json",
                temp_root=tmp_path / "module-data",
                now=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            package_name="dropin_modules",
        )
        create.database = database
        create.task_started = report_demo_module.TASK_STATE.started
        create.task_release = report_demo_module.TASK_STATE.release
        create.stop_entered = report_demo_module.TASK_STATE.stop_entered
        create.task_state = report_demo_module.TASK_STATE
        return runtime

    create.lifecycle_calls = report_demo_module.CALLS
    return create


@pytest.fixture
def valid_manifest() -> ModuleManifest:
    return ModuleManifest.from_mapping(
        {
            "id": "custom_reports",
            "name": "自定义报表",
            "version": "1.0.0",
            "platform_api": 1,
            "required": False,
            "backend_entry": "auto_check.modules.custom_reports.module:create_module",
            "api_prefix": "/api/modules/custom-reports",
            "frontend_entry": "/module-assets/custom_reports/index.js",
            "frontend_style": "/module-assets/custom_reports/styles.css",
            "navigation": [
                {
                    "id": "custom-reports",
                    "label": "自定义报表",
                    "route": "custom-reports",
                    "order": 60,
                    "permission": "custom_reports.view",
                }
            ],
            "permissions": ["custom_reports.view", "custom_reports.publish"],
            "dependencies": [],
            "schema_version": 0,
        }
    )
