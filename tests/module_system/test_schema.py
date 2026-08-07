from pathlib import Path
import traceback

import pytest
from sqlalchemy.exc import StatementError

from auto_check.app.app_database import CURRENT_APP_SCHEMA_VERSION, EXPECTED_APP_SCHEMA
from auto_check.app.module_system.contracts import ModuleManifest
from auto_check.app.module_system.schema import (
    ModuleMigration,
    ModuleMigrationError,
    ModuleMigrationRunner,
    ModuleSchemaRegistry,
    load_module_migrations,
)
from auto_check.app.module_system.discovery import load_module_factory


ROOT = Path(__file__).resolve().parents[2]
MODULE_SQL = ROOT / "sql" / "app_storage" / "mysql" / "012_module_system.sql"
FIXTURE_PARENT = ROOT / "tests" / "fixtures"


class _FakeResult:
    def __init__(self, value=None, *, lastrowid: int | None = None):
        self._value = value
        self.lastrowid = lastrowid

    def scalar_one_or_none(self):
        return self._value

    def scalar_one(self):
        return self._value

    def first(self):
        return self._value

    def all(self):
        return self._value or []


class _FakeModuleDatabase:
    def __init__(self):
        self.executed: list[str] = []
        self.schema_versions: dict[str, tuple[int, str]] = {}
        self.completed_migrations: dict[str, list[tuple[int, str]]] = {}
        self._history_id = 0
        self._history_modules: dict[int, str] = {}
        self._history_checksums: dict[int, tuple[int, str]] = {}
        self.history_statuses: dict[int, str] = {}
        self.history_errors: dict[int, str] = {}
        self.statement_error: Exception | None = None
        self.failing_statement = ""
        self.released_locks = 0
        self.info_schema_rows: list[tuple[str, str]] = []
        self.sql: list[str] = []
        self.fail_failed_history_persistence = False
        self.failed_history_error: Exception | None = None
        self.lock_result = 1
        self.release_result = 1
        self.release_error: Exception | None = None
        self.invalidated_connections = 0
        self.invalidate_error: Exception | None = None
        self.closed_connections = 0
        self.close_error: Exception | None = None

    def connect(self):
        return _FakeContext(self)

    def transaction(self):
        return _FakeContext(self)

    def execute(self, statement, parameters=None):
        sql = str(statement)
        parameters = parameters or {}
        self.sql.append(sql)
        if "GET_LOCK" in sql:
            return _FakeResult(self.lock_result)
        if "RELEASE_LOCK" in sql:
            self.released_locks += 1
            if self.release_error is not None:
                raise self.release_error
            return _FakeResult(self.release_result)
        if "SELECT schema_version, checksum" in sql:
            return _FakeResult(self.schema_versions.get(parameters["module_id"]))
        if "SELECT to_version, checksum" in sql:
            return _FakeResult(self.completed_migrations.get(parameters["module_id"], []))
        if "SELECT schema_version FROM app_module_schema_versions" in sql:
            stored = self.schema_versions.get(parameters["module_id"])
            return _FakeResult(stored[0] if stored else None)
        if "INSERT INTO app_module_migration_history" in sql:
            self._history_id += 1
            self._history_modules[self._history_id] = parameters["module_id"]
            self._history_checksums[self._history_id] = (
                parameters["to_version"],
                parameters["checksum"],
            )
            self.history_statuses[self._history_id] = parameters["status"]
            return _FakeResult(lastrowid=self._history_id)
        if "INSERT INTO app_module_schema_versions" in sql:
            self.schema_versions[self._history_modules[parameters["history_id"]]] = (
                parameters["schema_version"],
                parameters["checksum"],
            )
            return _FakeResult()
        if "UPDATE app_module_migration_history" in sql:
            history_id = parameters["history_id"]
            status = parameters["status"]
            if status == "failed" and self.fail_failed_history_persistence:
                raise self.failed_history_error or RuntimeError("fixture audit persistence failure")
            self.history_statuses[history_id] = status
            if status == "completed":
                module_id = self._history_modules[history_id]
                self.completed_migrations.setdefault(module_id, []).append(
                    self._history_checksums[history_id]
                )
            if status == "failed":
                self.history_errors[history_id] = parameters["error"]
            return _FakeResult()
        if "information_schema.columns" in sql:
            return _FakeResult(self.info_schema_rows)
        if sql.lstrip().startswith(("CREATE TABLE", "ALTER TABLE", "CREATE INDEX")):
            self.executed.append(sql.strip())
            if self.failing_statement and self.failing_statement in sql:
                raise self.statement_error or RuntimeError("fixture migration failure")
        return _FakeResult()

    def invalidate(self):
        self.invalidated_connections += 1
        if self.invalidate_error is not None:
            raise self.invalidate_error

    def close(self):
        self.closed_connections += 1
        if self.close_error is not None:
            raise self.close_error


class _FakeContext:
    def __init__(self, database: _FakeModuleDatabase):
        self._database = database

    def __enter__(self):
        return self._database

    def __exit__(self, exc_type, exc_value, traceback):
        return False


@pytest.fixture
def fake_module_database():
    return _FakeModuleDatabase()


@pytest.fixture
def alpha_manifest() -> ModuleManifest:
    return ModuleManifest.from_mapping(
        {
            "id": "alpha",
            "name": "Alpha",
            "version": "1.0.0",
            "platform_api": 1,
            "required": False,
            "backend_entry": "module_packages.alpha.module:create_module",
            "api_prefix": "/api/modules/alpha",
            "frontend_entry": "/module-assets/alpha/index.js",
            "frontend_style": "/module-assets/alpha/styles.css",
            "navigation": [],
            "permissions": ["alpha.view"],
            "dependencies": [],
            "schema_version": 2,
        }
    )


def test_module_system_core_tables_are_part_of_expected_schema():
    assert CURRENT_APP_SCHEMA_VERSION == 1
    assert EXPECTED_APP_SCHEMA["app_modules"] >= {
        "module_id",
        "module_version",
        "enabled",
        "status",
        "last_error",
        "installed_at",
        "updated_at",
    }
    assert EXPECTED_APP_SCHEMA["app_module_schema_versions"] >= {
        "module_id",
        "schema_version",
        "applied_at",
        "checksum",
    }
    assert EXPECTED_APP_SCHEMA["app_module_migration_history"] >= {
        "id",
        "module_id",
        "from_version",
        "to_version",
        "status",
        "checksum",
        "started_at",
        "finished_at",
        "error_message",
    }
    assert len(EXPECTED_APP_SCHEMA) == 45


def test_module_system_sql_is_repeatable_and_does_not_change_core_version():
    sql = MODULE_SQL.read_text(encoding="utf-8")

    assert sql.count("CREATE TABLE IF NOT EXISTS") == 3
    assert "DROP TABLE" not in sql.upper()
    assert "TRUNCATE" not in sql.upper()
    assert "INSERT INTO `app_schema_version`" not in sql


def test_loads_numbered_module_migrations_with_checksums(monkeypatch):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))

    migrations = load_module_migrations("module_packages.alpha")

    assert [item.version for item in migrations] == [1, 2]
    assert all(len(item.checksum) == 64 for item in migrations)
    assert migrations[0].statements == (
        "CREATE TABLE alpha_items (id bigint PRIMARY KEY)",
    )


def test_loader_does_not_split_regular_semicolons_without_the_explicit_marker(
    tmp_path, monkeypatch
):
    package = tmp_path / "semicolon_module"
    migrations = package / "migrations"
    migrations.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (migrations / "001_initial.sql").write_text(
        "CREATE PROCEDURE alpha_proc() BEGIN SELECT 1; SELECT 2; END",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    loaded = load_module_migrations("semicolon_module")

    assert loaded[0].statements == (
        "CREATE PROCEDURE alpha_proc() BEGIN SELECT 1; SELECT 2; END",
    )


def test_loader_splits_non_empty_statements_only_at_the_explicit_marker(tmp_path, monkeypatch):
    package = tmp_path / "marked_module"
    migrations = package / "migrations"
    migrations.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (migrations / "001_initial.sql").write_text(
        "CREATE PROCEDURE alpha_proc() BEGIN SELECT 1; SELECT 2; END\n"
        "-- module-statement-break\n\n"
        "ALTER TABLE alpha_items ADD COLUMN note text NULL",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    loaded = load_module_migrations("marked_module")

    assert loaded[0].statements == (
        "CREATE PROCEDURE alpha_proc() BEGIN SELECT 1; SELECT 2; END",
        "ALTER TABLE alpha_items ADD COLUMN note text NULL",
    )


def test_module_migration_has_the_documented_constructor_shape():
    migration = ModuleMigration(1, "initial", "a" * 64, ("SELECT 1",))

    assert migration.version == 1


def test_runner_applies_only_missing_versions_and_records_checksum(
    fake_module_database, alpha_manifest, monkeypatch
):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    runner = ModuleMigrationRunner(fake_module_database)

    version = runner.run(alpha_manifest, "module_packages.alpha")
    second_version = runner.run(alpha_manifest, "module_packages.alpha")

    assert version == 2
    assert second_version == 2
    assert fake_module_database.executed.count(
        "CREATE TABLE alpha_items (id bigint PRIMARY KEY)"
    ) == 1
    assert fake_module_database.executed.count(
        "ALTER TABLE alpha_items ADD COLUMN note text NULL"
    ) == 1


def test_runner_rejects_changed_applied_checksum(
    fake_module_database, alpha_manifest, monkeypatch
):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    fake_module_database.schema_versions["alpha"] = (1, "different-checksum")

    with pytest.raises(ModuleMigrationError, match="摘要"):
        ModuleMigrationRunner(fake_module_database).run(alpha_manifest, "module_packages.alpha")


def test_runner_rejects_changed_earlier_completed_checksum(
    fake_module_database, alpha_manifest, monkeypatch
):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    migrations = load_module_migrations("module_packages.alpha")
    fake_module_database.schema_versions["alpha"] = (2, migrations[1].checksum)
    fake_module_database.completed_migrations["alpha"] = [
        (1, "different-checksum"),
        (2, migrations[1].checksum),
    ]

    with pytest.raises(ModuleMigrationError, match="摘要"):
        ModuleMigrationRunner(fake_module_database).run(alpha_manifest, "module_packages.alpha")

    assert fake_module_database.released_locks == 1


def test_runner_rejects_completed_history_without_a_schema_version(
    fake_module_database, alpha_manifest, monkeypatch
):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    migrations = load_module_migrations("module_packages.alpha")
    fake_module_database.completed_migrations["alpha"] = [(1, migrations[0].checksum)]

    with pytest.raises(ModuleMigrationError, match="版本"):
        ModuleMigrationRunner(fake_module_database).run(alpha_manifest, "module_packages.alpha")


@pytest.mark.parametrize(
    "history_kind",
    ["empty", "missing_first", "only_second", "duplicate", "out_of_range"],
)
def test_runner_requires_completed_history_to_match_every_applied_version(
    fake_module_database, alpha_manifest, monkeypatch, history_kind
):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    migrations = load_module_migrations("module_packages.alpha")
    checksums = {migration.version: migration.checksum for migration in migrations}
    histories = {
        "empty": [],
        "missing_first": [(2, checksums[2])],
        "only_second": [(2, checksums[2])],
        "duplicate": [(1, checksums[1]), (1, checksums[1]), (2, checksums[2])],
        "out_of_range": [(1, checksums[1]), (2, checksums[2]), (3, "x" * 64)],
    }
    fake_module_database.schema_versions["alpha"] = (2, checksums[2])
    fake_module_database.completed_migrations["alpha"] = histories[history_kind]

    with pytest.raises(ModuleMigrationError, match="版本"):
        ModuleMigrationRunner(fake_module_database).run(alpha_manifest, "module_packages.alpha")


def test_runner_rejects_completed_history_for_schema_version_zero(
    fake_module_database, alpha_manifest, monkeypatch
):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    migration = load_module_migrations("module_packages.alpha")[0]
    fake_module_database.schema_versions["alpha"] = (0, "")
    fake_module_database.completed_migrations["alpha"] = [(1, migration.checksum)]

    with pytest.raises(ModuleMigrationError, match="版本"):
        ModuleMigrationRunner(fake_module_database).run(alpha_manifest, "module_packages.alpha")


def test_runner_records_sanitized_failed_history_and_releases_lock(
    fake_module_database, alpha_manifest, monkeypatch
):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    fake_module_database.failing_statement = "ALTER TABLE"
    fake_module_database.statement_error = StatementError(
        "database rejected statement",
        "ALTER TABLE alpha_items ADD COLUMN secret text",
        {"password": "super-secret"},
        RuntimeError("mysql://user:password@example.test/auto_check"),
    )

    with pytest.raises(ModuleMigrationError) as error:
        ModuleMigrationRunner(fake_module_database).run(alpha_manifest, "module_packages.alpha")

    error_text = str(error.value)
    formatted_traceback = "".join(traceback.format_exception(error.type, error.value, error.tb))
    assert "ALTER TABLE alpha_items" not in error_text
    assert "super-secret" not in error_text
    assert "mysql://" not in error_text
    assert "ALTER TABLE alpha_items" not in formatted_traceback
    assert "super-secret" not in formatted_traceback
    assert "mysql://" not in formatted_traceback
    assert set(fake_module_database.history_statuses.values()) >= {"completed", "failed"}
    assert all(
        "ALTER TABLE alpha_items" not in message
        and "super-secret" not in message
        and "mysql://" not in message
        for message in fake_module_database.history_errors.values()
    )
    assert fake_module_database.released_locks == 1


def test_runner_does_not_release_a_lock_that_was_not_acquired(
    fake_module_database, alpha_manifest, monkeypatch
):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    fake_module_database.lock_result = 0

    with pytest.raises(ModuleMigrationError, match="无法获取模块迁移锁"):
        ModuleMigrationRunner(fake_module_database).run(alpha_manifest, "module_packages.alpha")

    assert fake_module_database.released_locks == 0


@pytest.mark.parametrize("release_mode", ["non_one", "raises"])
def test_runner_invalidates_connection_and_reports_lock_release_failure(
    fake_module_database, alpha_manifest, monkeypatch, release_mode
):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    if release_mode == "non_one":
        fake_module_database.release_result = 0
    else:
        fake_module_database.release_error = RuntimeError(
            "mysql://lock:secret@example.test [SQL: SELECT RELEASE_LOCK(...)]"
        )

    with pytest.raises(ModuleMigrationError, match="锁释放失败") as error:
        ModuleMigrationRunner(fake_module_database).run(alpha_manifest, "module_packages.alpha")

    formatted_traceback = "".join(traceback.format_exception(error.type, error.value, error.tb))
    assert "mysql://" not in formatted_traceback
    assert "SELECT RELEASE_LOCK" not in formatted_traceback
    assert fake_module_database.released_locks == 1
    assert fake_module_database.invalidated_connections == 1


def test_runner_combines_primary_failure_with_lock_release_failure_safely(
    fake_module_database, alpha_manifest, monkeypatch
):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    fake_module_database.failing_statement = "ALTER TABLE"
    fake_module_database.statement_error = StatementError(
        "database rejected statement",
        "ALTER TABLE alpha_items ADD COLUMN secret text",
        {"password": "super-secret"},
        RuntimeError("mysql://user:password@example.test/auto_check"),
    )
    fake_module_database.release_error = RuntimeError(
        "mysql://lock:secret@example.test [SQL: SELECT RELEASE_LOCK(...)]"
    )

    with pytest.raises(ModuleMigrationError, match="锁释放失败") as error:
        ModuleMigrationRunner(fake_module_database).run(alpha_manifest, "module_packages.alpha")

    formatted_traceback = "".join(traceback.format_exception(error.type, error.value, error.tb))
    assert "数据库执行错误" in str(error.value)
    assert "ALTER TABLE alpha_items" not in formatted_traceback
    assert "super-secret" not in formatted_traceback
    assert "mysql://" not in formatted_traceback
    assert fake_module_database.invalidated_connections == 1


def test_runner_reports_invalidation_failure_and_closes_lock_connection(
    fake_module_database, alpha_manifest, monkeypatch
):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    fake_module_database.release_result = 0
    fake_module_database.invalidate_error = RuntimeError(
        "mysql://invalidate:secret@example.test [SQL: INVALIDATE]"
    )

    with pytest.raises(ModuleMigrationError, match="无法使迁移锁连接失效") as error:
        ModuleMigrationRunner(fake_module_database).run(alpha_manifest, "module_packages.alpha")

    formatted_traceback = "".join(traceback.format_exception(error.type, error.value, error.tb))
    assert "mysql://" not in formatted_traceback
    assert "INVALIDATE" not in formatted_traceback
    assert fake_module_database.invalidated_connections == 1
    assert fake_module_database.closed_connections == 1


def test_runner_reports_close_failure_after_invalidation_failure_without_leaking(
    fake_module_database, alpha_manifest, monkeypatch
):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    fake_module_database.release_result = 0
    fake_module_database.invalidate_error = RuntimeError("mysql://invalidate:secret@example.test")
    fake_module_database.close_error = RuntimeError("mysql://close:secret@example.test [SQL: CLOSE]")

    with pytest.raises(ModuleMigrationError, match="无法关闭") as error:
        ModuleMigrationRunner(fake_module_database).run(alpha_manifest, "module_packages.alpha")

    formatted_traceback = "".join(traceback.format_exception(error.type, error.value, error.tb))
    assert "mysql://" not in formatted_traceback
    assert "CLOSE" not in formatted_traceback
    assert fake_module_database.invalidated_connections == 1
    assert fake_module_database.closed_connections == 1


def test_runner_reports_audit_persistence_failure_without_leaking_the_causes(
    fake_module_database, alpha_manifest, monkeypatch
):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    fake_module_database.failing_statement = "ALTER TABLE"
    fake_module_database.statement_error = StatementError(
        "database rejected statement",
        "ALTER TABLE alpha_items ADD COLUMN secret text",
        {"password": "super-secret"},
        RuntimeError("mysql://user:password@example.test/auto_check"),
    )
    fake_module_database.fail_failed_history_persistence = True
    fake_module_database.failed_history_error = RuntimeError(
        "[SQL: UPDATE app_module_migration_history] mysql://audit:secret@example.test"
    )

    with pytest.raises(ModuleMigrationError, match="审计") as error:
        ModuleMigrationRunner(fake_module_database).run(alpha_manifest, "module_packages.alpha")

    formatted_traceback = "".join(traceback.format_exception(error.type, error.value, error.tb))
    assert "ALTER TABLE alpha_items" not in formatted_traceback
    assert "super-secret" not in formatted_traceback
    assert "mysql://" not in formatted_traceback


def test_runner_records_failed_history_when_schema_registry_is_incompatible(
    fake_module_database, alpha_manifest, monkeypatch
):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    fake_module_database.info_schema_rows = [("alpha_items", "id")]
    registry = ModuleSchemaRegistry()
    registry.add("alpha_items", {"id", "note"})

    with pytest.raises(ModuleMigrationError, match="缺少字段"):
        ModuleMigrationRunner(fake_module_database, registry).run(
            alpha_manifest, "module_packages.alpha"
        )

    assert "failed" in fake_module_database.history_statuses.values()
    assert any("information_schema.columns" in sql for sql in fake_module_database.sql)
    assert fake_module_database.released_locks == 1


def test_alpha_fixture_declares_its_migration_target_and_owned_table(monkeypatch):
    monkeypatch.syspath_prepend(str(FIXTURE_PARENT))
    module = load_module_factory("module_packages.alpha.module:create_module")()
    registered: dict[str, set[str]] = {}

    class Registry:
        def add(self, table_name: str, columns: set[str]) -> None:
            registered[table_name] = columns

    module.register_schema(Registry())

    assert module.manifest.schema_version == 2
    assert registered == {"alpha_items": {"id", "note"}}


def test_registry_rejects_core_and_foreign_table_names_and_exposes_read_only_names():
    registry = ModuleSchemaRegistry("alpha")
    registry.add("alpha_items", {"id"})

    assert registry.declared_table_names == frozenset({"alpha_items"})
    with pytest.raises(ValueError, match="核心"):
        registry.add("users", {"id"})
    with pytest.raises(ValueError, match="前缀"):
        registry.add("beta_items", {"id"})


@pytest.mark.parametrize(
    "statement",
    [
        "ALTER TABLE users ADD COLUMN note text",
        "DROP TABLE beta_items",
        "ALTER TABLE alpha_items ADD FOREIGN KEY (id) REFERENCES users(id)",
        "ALTER TABLE auto_check.alpha_items ADD COLUMN note text",
        "ALTER TABLE alpha_items ADD COLUMN note text; DROP TABLE alpha_items",
        "CREATE PROCEDURE alpha_proc() SELECT 1",
        "UPDATE alpha_items JOIN users ON 1 = 1 SET users.username = 'owned'",
        "ALTER TABLE alpha_items RENAME TO beta_items",
        "ALTER TABLE alpha_items EXCHANGE PARTITION p WITH TABLE users",
        "CREATE TABLE alpha_copy LIKE users",
        "CREATE TABLE alpha_copy AS SELECT id FROM users",
        "INSERT INTO alpha_items SELECT id FROM users",
        "UPDATE alpha_items SET id = (SELECT id FROM users LIMIT 1)",
        "DROP TABLE alpha_items, users",
    ],
)
def test_registry_rejects_unsafe_or_out_of_namespace_migration_statements(statement):
    registry = ModuleSchemaRegistry("alpha")
    registry.add("alpha_items", {"id"})

    with pytest.raises(ModuleMigrationError):
        registry.validate_statement(statement)


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE alpha_items (id bigint PRIMARY KEY);",
        "CREATE TABLE IF NOT EXISTS alpha_items (id bigint PRIMARY KEY)",
        "ALTER TABLE alpha_items ADD COLUMN note text",
        "CREATE UNIQUE INDEX alpha_items_name_idx ON alpha_items (id)",
        "DROP INDEX alpha_items_name_idx ON alpha_items",
        "DROP TABLE IF EXISTS alpha_legacy, alpha_archive RESTRICT",
    ],
)
def test_registry_accepts_analyzable_module_owned_ddl(statement):
    registry = ModuleSchemaRegistry("alpha")
    registry.add("alpha_items", {"id"})

    registry.validate_statement(statement)


def test_sql_lexer_accepts_doubled_quote_strings():
    registry = ModuleSchemaRegistry("alpha")
    registry.add("alpha_items", {"id", "note"})

    registry.validate_statement(
        "ALTER TABLE alpha_items ADD CONSTRAINT alpha_note_2 CHECK (note <> 'it''s')"
    )


@pytest.mark.parametrize("quote", ["'", '"'])
def test_sql_lexer_rejects_backslash_quoted_string_that_can_hide_cross_table_reference(
    quote,
):
    registry = ModuleSchemaRegistry("alpha")
    registry.add("alpha_items", {"id"})
    statement = (
        f"CREATE TABLE alpha_items (c varchar(10) DEFAULT {quote}\\{quote}, "
        "x int, FOREIGN KEY (x) REFERENCES users(id) # "
        f"{quote}\n)"
    )

    with pytest.raises(ModuleMigrationError):
        registry.validate_statement(statement)


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE alpha_items (c varchar(10) DEFAULT 'safe')",
        "CREATE TABLE alpha_items (c varchar(10) DEFAULT 'it''s safe')",
        "CREATE TABLE alpha_items (c int DEFAULT 0) -- ordinary comment\n",
    ],
)
def test_sql_lexer_keeps_safe_default_values_and_comments_analyzable(statement):
    registry = ModuleSchemaRegistry("alpha")
    registry.add("alpha_items", {"id"})

    registry.validate_statement(statement)


def test_runner_rejects_cross_namespace_sql_before_database_execution(
    tmp_path, monkeypatch, fake_module_database
):
    package = tmp_path / "unsafe_alpha"
    migrations = package / "migrations"
    migrations.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    unsafe_sql = "DROP TABLE alpha_items, users"
    (migrations / "001_initial.sql").write_text(unsafe_sql, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    manifest = ModuleManifest.from_mapping(
        {
            "id": "alpha",
            "name": "Alpha",
            "version": "1.0.0",
            "platform_api": 1,
            "required": False,
            "backend_entry": "unsafe_alpha.module:create_module",
            "api_prefix": "/api/modules/alpha",
            "frontend_entry": "/module-assets/alpha/index.js",
            "frontend_style": "/module-assets/alpha/styles.css",
            "navigation": [],
            "permissions": ["alpha.view"],
            "dependencies": [],
            "schema_version": 1,
        }
    )
    registry = ModuleSchemaRegistry("alpha")
    registry.add("alpha_items", {"id"})

    with pytest.raises(ModuleMigrationError, match="越界"):
        ModuleMigrationRunner(fake_module_database, registry).run(manifest, "unsafe_alpha")

    assert unsafe_sql not in fake_module_database.sql
