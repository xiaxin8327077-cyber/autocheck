# MySQL Application Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Auto Check runtime SQLite persistence with a manually provisioned MySQL `auto_check` database while preserving configuration, authentication, and history behavior and hiding the local-database UI.

**Architecture:** A new `ApplicationDatabase` reads the existing `config.json`, owns one SQLAlchemy MySQL engine, validates the manually installed schema, and provides explicit transactions to existing storage modules. Runtime repositories use MySQL only; SQLite remains available solely to a manually invoked export script.

**Tech Stack:** Python 3.12, SQLAlchemy Core 2.x, PyMySQL, MySQL 5.7.8+/8.x, pytest, PyInstaller

---

### Task 1: Add the MySQL application-database foundation

**Files:**
- Create: `src/auto_check/app/app_database.py`
- Modify: `pyproject.toml`
- Modify: `scripts/package-windows.ps1`
- Modify: `scripts/package-linux.sh`
- Test: `tests/test_app_database.py`

- [ ] **Step 1: Write failing configuration and schema-validation tests**

Cover a valid `app_database` node, missing node, non-MySQL backend, invalid port/pool values, SQLAlchemy URL construction without password interpolation, successful `SELECT 1`, schema version mismatch, missing table, and missing column. Tests must assert that validation emits no DDL.

```python
def test_load_application_database_config_requires_mysql(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"app_database":{"backend":"postgresql"}}', encoding="utf-8")
    with pytest.raises(ValueError, match="仅支持 mysql"):
        load_application_database_config(path)

def test_validate_schema_rejects_missing_table(fake_database):
    fake_database.tables.remove("users")
    with pytest.raises(ApplicationSchemaError, match="users"):
        validate_application_schema(fake_database.connection)
    assert fake_database.executed_ddl == []
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `python -m pytest tests/test_app_database.py -q`

Expected: collection/import failure because `auto_check.app.app_database` does not exist.

- [ ] **Step 3: Implement the application database object**

Implement these stable interfaces:

```python
@dataclass(frozen=True)
class ApplicationDatabaseConfig:
    host: str
    port: int
    database: str
    username: str
    password: str
    charset: str = "utf8mb4"
    connect_timeout: int = 10
    pool_size: int = 5
    pool_max_overflow: int = 5
    ssl: bool = False

class ApplicationDatabase:
    @classmethod
    def from_config_path(cls, config_path: str | Path) -> "ApplicationDatabase": ...
    def test_connection(self) -> None: ...
    def validate_schema(self) -> None: ...
    @contextmanager
    def connect(self) -> Iterator[Connection]: ...
    @contextmanager
    def transaction(self) -> Iterator[Connection]: ...
    def close(self) -> None: ...
```

Use `sqlalchemy.URL.create("mysql+pymysql", ...)`, `create_engine(pool_pre_ping=True, pool_recycle=1800)`, `text("SELECT 1")`, `information_schema.tables`, `information_schema.columns`, and `SELECT MAX(version) FROM app_schema_version`. Define `CURRENT_APP_SCHEMA_VERSION = 1` and the expected 19 source tables plus `app_schema_version` in one immutable mapping.

- [ ] **Step 4: Add runtime and packaging dependencies**

Add `SQLAlchemy>=2.0,<3.0` to project dependencies and PyInstaller hidden imports for `sqlalchemy.dialects.mysql` and `sqlalchemy.dialects.mysql.pymysql` in Windows and Linux packaging scripts.

- [ ] **Step 5: Run focused tests**

Run: `python -m pytest tests/test_app_database.py -q`

Expected: all tests pass.

### Task 2: Convert configuration persistence to MySQL

**Files:**
- Modify: `src/auto_check/app/storage_config.py`
- Modify: `src/auto_check/app/config.py`
- Modify: `src/auto_check/app/local_store.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Replace SQLite-specific tests with MySQL repository contract tests**

Add tests for loading/saving `data_sources`, `app_settings`, and config snapshots through a transaction. Assert native datetime values are accepted and data-source passwords remain encrypted. Assert `save_store()` does not rewrite `config.json`.

```python
def test_save_store_does_not_overwrite_bootstrap_config(app_database, config_path):
    before = config_path.read_text(encoding="utf-8")
    save_store(sample_store(), config_path, database=app_database)
    assert config_path.read_text(encoding="utf-8") == before
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `python -m pytest tests/test_config.py -q`

Expected: failures show SQLite path creation and old connection assumptions.

- [ ] **Step 3: Rewrite storage configuration DML with SQLAlchemy Core**

Use MySQL upsert via `sqlalchemy.dialects.mysql.insert(table).on_duplicate_key_update(...)`. Replace `rowid` ordering with explicit `updated_at`, `name`, or primary key ordering. Keep JSON serialization deterministic and return the same `DataSourceEntry` and `ConfigStore` models.

- [ ] **Step 4: Make MySQL the only runtime configuration source**

Change `load_store`, `save_store`, `load_config`, and `save_config` to receive or resolve `ApplicationDatabase`. Read `app_database` from the file before database access; after connection succeeds, ignore legacy dynamic JSON and never call SQLite compatibility snapshot writers. Reduce `local_store.py` to legacy JSON-reading helpers used by the offline exporter or remove it after all callers migrate.

- [ ] **Step 5: Run focused tests**

Run: `python -m pytest tests/test_config.py tests/test_db.py -q`

Expected: all focused tests pass and no test expects `auto-check.db` creation.

### Task 3: Convert authentication and user persistence to MySQL

**Files:**
- Modify: `src/auto_check/app/security.py`
- Modify: `tests/test_security.py`

- [ ] **Step 1: Write failing MySQL user-store tests**

Cover initial administrator creation when `users` is empty, imported users remaining valid, new password validation (six characters and at least one letter), login timestamp persistence, user CRUD, and unchanged `AUTO_CHECK_SECRET_KEY` encryption/decryption behavior.

```python
def test_successful_login_updates_mysql_last_login(app_database, auth_service):
    token = auth_service.login("admin", "admin123")
    assert token
    row = app_database.fetch_user("admin")
    assert row["last_login_at"] is not None
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_security.py -q`

Expected: failures identify SQLite `_connect` and `app_kv` usage.

- [ ] **Step 3: Inject ApplicationDatabase into AuthManager**

Change construction to `AuthManager(config_path, database=application_database)`. Load/save only the normalized `users` table. Preserve in-memory sessions because the approved deployment is single-instance. Do not import users from JSON or SQLite during normal startup.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_security.py -q`

Expected: all authentication and password-rule tests pass.

### Task 4: Convert all structured history repositories to MySQL

**Files:**
- Modify: `src/auto_check/app/storage_history.py`
- Modify: `src/auto_check/app/history.py`
- Modify: `src/auto_check/app/history_migration.py`
- Test: `tests/test_history.py`

- [ ] **Step 1: Write failing repository tests for all three history kinds**

Cover save/list/get/delete for reconcile, db-validation, and flow-chain runs; native `Decimal`, `date`, `datetime`, and `time`; JSON restoration; child replacement; generated IDs; ordering; cascade deletion; and transaction rollback.

```python
@pytest.mark.parametrize("kind", ["reconcile", "db_validation", "flow_chain"])
def test_database_history_store_round_trip(kind, app_database, sample_runs):
    store = DatabaseHistoryStore(app_database, kind=kind)
    store.save_run(sample_runs[kind])
    assert store.get_run(sample_runs[kind]["id"]) == sample_runs[kind]
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_history.py -q`

Expected: failures identify SQLite connections, `?` placeholders, `lastrowid`, and legacy migration scans.

- [ ] **Step 3: Implement SQLAlchemy history DML**

Use MySQL upserts for run headers and run-specific parents, delete/reinsert owned child rows inside one transaction, use SQLAlchemy inserted primary keys for detail records, and normalize MySQL native values back to the existing API JSON shape. Preserve `ON DELETE CASCADE` behavior and current list ordering.

- [ ] **Step 4: Remove runtime legacy migration behavior**

Replace `SqliteHistoryStore` with `DatabaseHistoryStore`. Remove `history_migration.py` from server imports and normal runtime. Keep no endpoint or startup action that reads old SQLite/JSON history.

- [ ] **Step 5: Run focused tests**

Run: `python -m pytest tests/test_history.py -q`

Expected: all three history suites pass.

### Task 5: Wire MySQL through the server and hide the local-database UI

**Files:**
- Modify: `src/auto_check/app/server.py`
- Modify: `src/auto_check/app/storage_admin.py`
- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/app.js`
- Modify: `src/auto_check/web/styles.css`
- Modify: `tests/test_server.py`
- Modify: `tests/test_storage_admin.py`
- Modify: `tests/test_web_static.py`

- [ ] **Step 1: Write failing startup and UI tests**

Assert the server constructs one `ApplicationDatabase`, validates it before creating the HTTP server, injects it into router/auth/history stores, closes it on shutdown, and refuses to start on schema mismatch. Static tests must assert the local-storage navigation/page markup is hidden and related JavaScript does not auto-load it.

```python
def test_local_database_page_is_hidden(web_html, web_js):
    assert 'data-page="local-storage"' not in web_html
    assert 'loadLocalStorageOverview()' not in web_js
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_server.py tests/test_storage_admin.py tests/test_web_static.py -q`

Expected: failures show default `SqliteHistoryStore`, SQLite admin APIs, and visible page markup.

- [ ] **Step 3: Inject the database at process startup**

In `run_server`, resolve the existing config path, build/test/validate `ApplicationDatabase`, pass it to `ApiRouter` and `AuthManager`, and close it in `finally`. Make background jobs reuse the engine but open their own transaction/connection.

- [ ] **Step 4: Disable storage-admin runtime endpoints**

Remove SQLite imports and file operations from the active server route. Preserve route matching only if needed for compatibility, returning HTTP 404 or a stable disabled-feature response without accessing a database. Remove server imports of backup and legacy migration helpers.

- [ ] **Step 5: Hide the page and all entry points**

Remove or hidden-render the navigation item and page section, remove event bindings and automatic data loads, and delete now-unused local-storage styles only when static tests confirm no remaining selector use. Do not add a replacement MySQL management page.

- [ ] **Step 6: Run focused tests**

Run: `python -m pytest tests/test_server.py tests/test_storage_admin.py tests/test_web_static.py -q`

Expected: focused tests pass in both theme-oriented static assertions and server behavior.

### Task 6: Add manual schema and offline SQLite export assets

**Files:**
- Create: `sql/app_storage/mysql/001_init_schema.sql`
- Create: `scripts/export_sqlite_to_mysql.py`
- Test: `tests/test_sqlite_to_mysql_export.py`

- [ ] **Step 1: Write failing export tests**

Build a temporary SQLite V2 fixture and assert the exporter emits `USE auto_check`, 20 commented MySQL tables, all normalized INSERT rows, native date/time/decimal literals, an end-of-transaction `app_schema_version` row, checksums, and no `CREATE DATABASE`, `DROP`, `TRUNCATE`, legacy-table DDL, or plaintext value output to stdout.

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_sqlite_to_mysql_export.py -q`

Expected: failure because the exporter and checked-in MySQL schema do not exist.

- [ ] **Step 3: Add the generic schema SQL**

Base it on the verified production schema at `D:\xiaxin\download\auto_check_mysql_schema.sql`. Retain `DATE`, `DATETIME(6)`, `TIME(6)`, `DECIMAL(38,12)`, JSON, indexes, cascades, 20 Chinese table comments, and 155 Chinese field comments. The generic schema must not contain production data or secrets.

- [ ] **Step 4: Implement the manual exporter CLI**

Provide:

```text
python scripts/export_sqlite_to_mysql.py \
  --source "D:\path\auto-check.db" \
  --database auto_check \
  --schema-output "D:\output\auto_check_mysql_schema.sql" \
  --data-output "D:\output\auto_check_mysql_data.sql" \
  --report-output "D:\output\auto_check_mysql_migration_report.json"
```

Open SQLite with `mode=ro`, require `integrity_check=ok` and zero foreign-key issues, exclude `app_kv/history_runs/schema_migrations/sqlite_sequence`, validate every typed value, write UTF-8-safe literals, and never connect to MySQL.

- [ ] **Step 5: Run exporter tests**

Run: `python -m pytest tests/test_sqlite_to_mysql_export.py -q`

Expected: all tests pass.

### Task 7: Update documentation and release notes

**Files:**
- Modify: `README.md`
- Modify: `src/auto_check/web/app.js`
- Modify: `docs/deployment.zh-CN.md`
- Modify: `docs/intranet-production-deployment.zh-CN.md`
- Modify: `docs/check-history-design.zh-CN.md`
- Modify: `docs/flow-bg-execution-design.zh-CN.md`
- Modify: `docs/local-sqlite-database-design.zh-CN.md`
- Modify: `docs/production-sqlite-storage-migration.zh-CN.md`
- Create: `docs/mysql-application-storage.zh-CN.md`
- Test: `tests/test_web_static.py`
- Test: `tests/test_deployment_assets.py`

- [ ] **Step 1: Write failing documentation assertions**

Assert README and deployment docs describe MySQL application storage, existing `config.json`, manual schema/data execution, unchanged `AUTO_CHECK_SECRET_KEY`, backup/rollback, and hidden local-database UI. Assert the in-app changelog contains only the concise entry `系统优化及BUG修复` for this migration.

- [ ] **Step 2: Run documentation tests and verify failure**

Run: `python -m pytest tests/test_web_static.py tests/test_deployment_assets.py -q`

Expected: old SQLite wording causes failures.

- [ ] **Step 3: Update all affected documentation**

Mark SQLite documents as legacy/rollback references rather than current architecture. Document exact MySQL execution order and config example. Keep README detailed; keep the in-app changelog concise as required by AGENTS.md.

- [ ] **Step 4: Run documentation tests**

Run: `python -m pytest tests/test_web_static.py tests/test_deployment_assets.py -q`

Expected: all documentation/static tests pass.

### Task 8: Full regression, real-MySQL check, and Windows package

**Files:**
- Modify only files required by failures attributable to this migration.
- Refresh: `dist/auto-check.exe`

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest -q`

Expected: all tests pass; record the exact count.

- [ ] **Step 2: Run a real MySQL integration check when credentials are available**

Set `AUTO_CHECK_TEST_MYSQL_DSN` to an isolated MySQL database/schema, execute the checked-in schema manually, then run MySQL-marked repository tests. If credentials are unavailable, report this verification gap explicitly and do not claim runtime MySQL execution.

- [ ] **Step 3: Check whitespace and runtime SQLite references**

Run:

```powershell
git diff --check
rg -n "sqlite3|auto-check\.db|SqliteHistoryStore|PRAGMA|sqlite_master" src/auto_check/app src/auto_check/web
```

Expected: no whitespace errors and no SQLite reference in the active runtime path.

- [ ] **Step 4: Confirm the executable is not running**

Run: `Get-Process | Where-Object { $_.Path -eq (Resolve-Path 'dist\auto-check.exe') }`

Expected: no process result.

- [ ] **Step 5: Build the Windows executable**

Run: `powershell -ExecutionPolicy Bypass -File scripts\package-windows.ps1`

Expected: exit code 0 and refreshed `dist\auto-check.exe`.

- [ ] **Step 6: Run final smoke checks**

Run `dist\auto-check.exe --help` and verify the package starts far enough to report a clear missing/invalid MySQL bootstrap configuration rather than creating SQLite when run against a temporary config without `app_database`.
