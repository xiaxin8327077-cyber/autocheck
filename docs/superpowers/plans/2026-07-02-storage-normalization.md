# 本地存储分表优化实施计划

> **给执行代理的要求：** 实施本计划时按任务逐项推进，建议使用 `superpowers:subagent-driven-development` 或 `superpowers:executing-plans`。每个任务完成后先运行对应测试，再进入下一项。

**目标：** 将当前大量依赖 JSON 的本地持久化改为“结构化热字段 + 兼容快照”的 SQLite 分表模型，优先解决配置、用户和自动对数历史的查询、约束、迁移和膨胀问题。

**架构：** 保留本地 SQLite `auto-check.db`，不引入独立数据库服务。新增 V2 存储层放在现有 `load_store()`、`save_store()`、`AuthManager`、`SqliteHistoryStore` 边界后面，对外 API 和前端返回结构保持兼容。常用查询字段拆到关系表，规则详情、执行快照和旧版兼容数据保留在明确命名的 JSON 快照列中。

**技术栈：** Python 标准库 `sqlite3`、现有 dataclass 配置模型、现有本地 HTTP 服务、pytest、Windows 打包脚本。

---

## 一期范围

一期只做收益最大且风险可控的部分：

- 增加 SQLite 版本化迁移框架。
- 结构化保存数据源、默认设置、人行逐笔校验设置、流程工具设置、对账字段配置和用户。
- 结构化保存自动对数历史：运行头、结果行、差异详情、原因统计、状态统计、增量结果。
- 保留并迁移现有数据：`app_kv.config_store`、`app_kv.auth`、`history_runs`、同目录 `config.json`、旧 `history.json`、旧 `db-validation-history.json`，迁移后不删除旧数据。
- 暂不彻底拆分人行逐笔校验结果行和流程链执行历史，只保证现有功能不回退；它们放到二期继续分表。

## 文件分工

- 新建 `src/auto_check/app/storage_schema.py`：本地库版本号、建表 SQL、迁移入口、备份辅助。
- 新建 `src/auto_check/app/storage_config.py`：配置和用户的结构化读写函数。
- 新建 `src/auto_check/app/storage_history.py`：自动对数历史的结构化读写和旧历史迁移。
- 修改 `src/auto_check/app/local_store.py`：连接 SQLite 时执行 V2 schema，保留旧 KV 和历史接口。
- 修改 `src/auto_check/app/config.py`：`load_store()` / `save_store()` 优先使用结构化表，继续写兼容快照。
- 修改 `src/auto_check/app/security.py`：用户读写改走 `users` 表，同时保留 `auth` 兼容快照。
- 修改 `src/auto_check/app/history.py`：`SqliteHistoryStore(kind='reconcile')` 改走结构化自动对数历史。
- 修改 `README.md`、`docs/check-history-design.zh-CN.md`、`docs/reconcile-execution-flow.zh-CN.md`：同步说明新存储模型。
- 补充 `tests/test_config.py`、`tests/test_security.py`、`tests/test_history.py`、`tests/test_server.py`。

---

## 现有数据迁移原则与来源

迁移必须按“先备份、再建表、再导入、再校验、旧数据保留”的顺序执行。不能因为新表写入成功就删除旧 JSON 或旧表；旧数据至少保留一个版本周期，作为回退和审计依据。

### 迁移来源

需要覆盖这些现有数据来源：

- `auto-check.db.app_kv.config_store`：当前主要配置来源，包含数据源、默认设置、人行逐笔校验设置、流程链设置、对账字段配置。
- `auto-check.db.app_kv.auth`：当前用户列表、密码哈希、角色和启停状态。
- `auto-check.db.history_runs`：当前 SQLite 历史表，按 `kind` 区分 `reconcile`、`db_validation`、`flow_chain`。
- `config.json`：兼容快照；部分用户可能只有这个文件，还没有完整 SQLite 数据。
- `history.json`：早期自动对数历史文件；用户目录中可能仍存在大文件。
- `db-validation-history.json`：早期人行逐笔校验历史文件。
- `reconcile-schema.yaml`：当前对账业务字段清单的 YAML 快照；如果 `config_store.reconcile_schema` 缺失，应作为初始化来源。
- `db-validation-results/`、`pbc-import-uploads/`：文件产物目录不迁入数据库，只保留路径引用，迁移时验证路径存在即可。

### 迁移顺序

1. 定位 `config_path`，计算同目录 `auto-check.db`。
2. 如果 `auto-check.db`、`config.json`、`history.json`、`db-validation-history.json` 存在，先复制到 `backup-before-storage-v2-YYYYMMDD-HHMMSS/`。
3. 创建 V2 schema 和 `storage_migration_runs` 迁移记录表。
4. 配置迁移：优先读 `app_kv.config_store`，不存在时读 `config.json`，写入结构化配置表，并继续写兼容快照。
5. 用户迁移：优先读 `app_kv.auth`，不存在时读 `config.json.auth`，写入 `users`，保留密码哈希不重算。
6. 自动对数历史迁移：优先读 `history_runs(kind='reconcile')`，如果为空再读 `history.json`。
7. 人行逐笔校验和流程链历史：一期仍保留在 `history_runs`，但要补充迁移记录，确保二期能识别来源；如果存在 `db-validation-history.json`，先导入为 `history_runs(kind='db_validation')` 兼容数据。
8. 对账字段配置迁移：优先读 `config_store.reconcile_schema`，缺失时读 `reconcile-schema.yaml` 初始化。
9. 写入迁移报告：记录每类来源导入条数、跳过条数、错误摘要。
10. 校验关键计数：数据源数量、用户数量、自动对数历史数量、自动对数结果行数量不得少于迁移前可解析数量。

### 幂等与回退

- 迁移以 `storage_migration_runs(source_type, source_path, source_key, source_fingerprint)` 判重，同一来源同一指纹重复执行时只能跳过，不能重复插入。
- 自动对数历史以 `run_id` 判重；同一个 `run_id` 已存在时只更新快照和结构化字段，不新增第二份结果。
- 配置迁移每次按当前配置覆盖结构化表，避免旧结构残留。
- 用户迁移以 `username` 和 `id` 约束保护，不允许产生同名重复用户。
- 任一迁移步骤失败时，不删除旧数据；应用继续走旧 `app_kv/history_runs` 回退路径，并在日志和迁移记录中保存错误摘要。
- 回退方式是恢复备份目录中的 `auto-check.db` 和 JSON 文件；不要求用户手工清理半成品表。

---

## 目标表结构

一期新增表：

```sql
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE storage_migration_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    source_path TEXT NOT NULL DEFAULT '',
    source_key TEXT NOT NULL DEFAULT '',
    source_fingerprint TEXT NOT NULL DEFAULT '',
    migrated_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL DEFAULT '',
    UNIQUE(source_type, source_path, source_key, source_fingerprint)
);

CREATE TABLE data_sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    db_type TEXT NOT NULL,
    host TEXT NOT NULL,
    port INTEGER NOT NULL,
    database_name TEXT NOT NULL,
    schema_name TEXT NOT NULL,
    username TEXT NOT NULL,
    password_encrypted TEXT NOT NULL DEFAULT '',
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE app_settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    last_login_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE config_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE run_headers (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    run_date TEXT NOT NULL DEFAULT '',
    run_at TEXT NOT NULL DEFAULT '',
    finished_at TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    executor_id TEXT NOT NULL DEFAULT '',
    executor_username TEXT NOT NULL DEFAULT '',
    executor_name TEXT NOT NULL DEFAULT '',
    config_fingerprint TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT ''
);

CREATE INDEX idx_run_headers_sort
    ON run_headers(kind, run_date DESC, run_at DESC);

CREATE TABLE reconcile_runs (
    id TEXT PRIMARY KEY,
    config_name TEXT NOT NULL DEFAULT '',
    dws_source_name TEXT NOT NULL DEFAULT '',
    rule_version TEXT NOT NULL DEFAULT '',
    baseline_id TEXT NOT NULL DEFAULT '',
    baseline_run_at TEXT NOT NULL DEFAULT '',
    baseline_count INTEGER,
    total_count INTEGER NOT NULL DEFAULT 0,
    added_count INTEGER,
    removed_count INTEGER,
    FOREIGN KEY (id) REFERENCES run_headers(id) ON DELETE CASCADE
);

CREATE TABLE reconcile_run_counts (
    run_id TEXT NOT NULL,
    count_type TEXT NOT NULL,
    label TEXT NOT NULL,
    count_value INTEGER NOT NULL,
    PRIMARY KEY (run_id, count_type, label),
    FOREIGN KEY (run_id) REFERENCES reconcile_runs(id) ON DELETE CASCADE
);

CREATE TABLE reconcile_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    result_order INTEGER NOT NULL,
    project_code TEXT NOT NULL DEFAULT '',
    project_name TEXT NOT NULL DEFAULT '',
    asset_total TEXT NOT NULL DEFAULT '',
    liability_equity_total TEXT NOT NULL DEFAULT '',
    received_trust_balance TEXT NOT NULL DEFAULT '',
    difference TEXT NOT NULL DEFAULT '',
    direction TEXT NOT NULL DEFAULT '',
    difference_reason TEXT NOT NULL DEFAULT '',
    match_status TEXT NOT NULL DEFAULT '',
    valuation_asset_total TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (run_id) REFERENCES reconcile_runs(id) ON DELETE CASCADE
);

CREATE INDEX idx_reconcile_results_run
    ON reconcile_results(run_id, result_order);

CREATE INDEX idx_reconcile_results_project
    ON reconcile_results(project_code);

CREATE INDEX idx_reconcile_results_reason
    ON reconcile_results(difference_reason, match_status);

CREATE TABLE reconcile_result_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id INTEGER NOT NULL,
    detail_order INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT '',
    specific_reason TEXT NOT NULL DEFAULT '',
    data_json TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (result_id) REFERENCES reconcile_results(id) ON DELETE CASCADE
);

CREATE TABLE reconcile_delta_results (
    run_id TEXT NOT NULL,
    delta_type TEXT NOT NULL,
    result_order INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (run_id, delta_type, result_order),
    FOREIGN KEY (run_id) REFERENCES reconcile_runs(id) ON DELETE CASCADE
);
```

继续保留旧表：

```sql
app_kv(key, value, updated_at)
history_runs(kind, id, payload, run_date, run_at, config_fingerprint)
```

旧表只作为兼容快照和迁移来源，不再作为新功能的主要查询入口。

---

## 任务 1：增加版本化 SQLite schema

**涉及文件：**

- 新建：`src/auto_check/app/storage_schema.py`
- 修改：`src/auto_check/app/local_store.py`
- 测试：`tests/test_config.py`

### 步骤

1. 在 `tests/test_config.py` 新增测试 `test_local_store_creates_v2_storage_schema`。

```python
def test_local_store_creates_v2_storage_schema(tmp_path):
    import sqlite3

    from auto_check.app.local_store import db_path_for_config, read_app_value
    from auto_check.app.storage_schema import CURRENT_SCHEMA_VERSION, get_schema_version

    config_path = tmp_path / "config.json"
    read_app_value(config_path, "missing")

    db_path = db_path_for_config(config_path)
    assert db_path.exists()

    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert "schema_migrations" in tables
    assert "storage_migration_runs" in tables
    assert "data_sources" in tables
    assert "users" in tables
    assert "run_headers" in tables
    assert "reconcile_results" in tables
    assert get_schema_version(db_path) == CURRENT_SCHEMA_VERSION
```

2. 运行失败测试。

```powershell
python -m pytest tests/test_config.py::test_local_store_creates_v2_storage_schema -q
```

预期：因为 `storage_schema.py` 尚不存在而失败。

3. 新建 `storage_schema.py`，提供：

- `CURRENT_SCHEMA_VERSION = 2`
- `ensure_storage_schema(connection)`
- `get_schema_version(db_path)`
- `backup_database_if_exists(db_path)`
- `_ensure_legacy_tables(connection)`
- `_migrate_v2(connection)`

4. 修改 `src/auto_check/app/local_store.py`。

```python
from auto_check.app.storage_schema import ensure_storage_schema
```

将 `_ensure_schema()` 改为：

```python
def _ensure_schema(connection: sqlite3.Connection) -> None:
    ensure_storage_schema(connection)
```

5. 运行测试。

```powershell
python -m pytest tests/test_config.py::test_local_store_creates_v2_storage_schema -q
```

预期：通过。

---

## 任务 2：结构化保存配置

**涉及文件：**

- 新建：`src/auto_check/app/storage_config.py`
- 修改：`src/auto_check/app/config.py`
- 测试：`tests/test_config.py`

### 步骤

1. 新增测试 `test_store_persists_data_sources_to_normalized_tables`。

```python
def test_store_persists_data_sources_to_normalized_tables(tmp_path):
    import sqlite3

    from auto_check.app.config import (
        ConfigStore,
        DataSourceConfig,
        DataSourceEntry,
        ReconcileDataSourceSettings,
        load_store,
        save_store,
    )
    from auto_check.app.local_store import db_path_for_config, read_app_value

    config_path = tmp_path / "config.json"
    dws = DataSourceEntry(
        id="source-dws",
        name="DWS",
        config=DataSourceConfig(
            db_type="postgresql",
            host="127.0.0.1",
            port=5432,
            database="dw",
            schema="dws",
            username="u",
            password="Pass123",
        ),
        is_default=True,
    )
    report = DataSourceEntry(
        id="source-report",
        name="Report",
        config=DataSourceConfig(
            db_type="mysql",
            host="10.0.0.2",
            port=3306,
            database="report",
            schema="",
            username="r",
            password="Report123",
        ),
    )

    save_store(
        ConfigStore(
            data_sources=[dws, report],
            default_name="DWS",
            reconcile_data_sources=ReconcileDataSourceSettings(
                dws_source_id="source-dws",
                business_source_id="source-report",
            ),
        ),
        config_path,
    )

    with sqlite3.connect(db_path_for_config(config_path)) as connection:
        rows = connection.execute(
            "SELECT id, name, db_type, host, port, database_name, schema_name, username, password_encrypted "
            "FROM data_sources ORDER BY id"
        ).fetchall()

    assert [row[0] for row in rows] == ["source-dws", "source-report"]
    assert rows[0][8].startswith("aesgcm$")
    assert read_app_value(config_path, "config_store") is not None

    loaded = load_store(config_path)
    assert [entry.id for entry in loaded.data_sources] == ["source-dws", "source-report"]
    assert loaded.data_sources[0].config.password == "Pass123"
    assert loaded.reconcile_data_sources.dws_source_id == "source-dws"
```

2. 运行失败测试。

```powershell
python -m pytest tests/test_config.py::test_store_persists_data_sources_to_normalized_tables -q
```

预期：`data_sources` 未写入而失败。

3. 新建 `storage_config.py`，实现这些函数：

- `has_normalized_config(connection)`
- `save_data_sources(connection, entries)`
- `load_data_sources(connection)`
- `save_setting(connection, key, value)`
- `load_setting(connection, key, default)`

密码继续使用现有 `encrypt_secret()` / `decrypt_secret()`，写入 `password_encrypted`，不保存明文密码。

4. 修改 `config.py`。

在 `load_store()` 中：

- 先尝试从结构化表读取。
- 如果结构化表没有数据，继续走旧 `app_kv.config_store` / `config.json`。
- 旧数据读取成功后调用 `save_store()` 回写结构化表。

在 `save_store()` 中：

- 写入结构化表。
- 继续调用 `save_combined_payload()` 写 `app_kv.config_store` 和 `config.json` 兼容快照。

5. 运行配置测试。

```powershell
python -m pytest tests/test_config.py -q
```

预期：通过。

---

## 任务 3：结构化保存用户

**涉及文件：**

- 修改：`src/auto_check/app/storage_config.py`
- 修改：`src/auto_check/app/security.py`
- 测试：`tests/test_security.py`

### 步骤

1. 新增测试 `test_auth_manager_persists_users_to_normalized_table`。

```python
def test_auth_manager_persists_users_to_normalized_table(tmp_path):
    import sqlite3

    from auto_check.app.local_store import db_path_for_config, read_app_value
    from auto_check.app.security import AuthManager

    config_path = tmp_path / "config.json"
    manager = AuthManager(config_path)
    manager.set_admin_password("Admin123")
    manager.create_user(username="alice", password="Alice123", role="user")

    with sqlite3.connect(db_path_for_config(config_path)) as connection:
        rows = connection.execute(
            "SELECT username, role, enabled FROM users ORDER BY username"
        ).fetchall()

    assert rows == [("admin", "admin", 1), ("alice", "user", 1)]
    assert read_app_value(config_path, "auth")["users"][0]["username"] == "admin"

    reloaded = AuthManager(config_path)
    assert [user["username"] for user in reloaded.list_users()] == ["admin", "alice"]
```

2. 运行失败测试。

```powershell
python -m pytest tests/test_security.py::test_auth_manager_persists_users_to_normalized_table -q
```

预期：`users` 表未写入而失败。

3. 在 `storage_config.py` 增加：

- `load_users(connection)`
- `save_users(connection, users)`

4. 修改 `security.py`。

原则：

- `_auth_payload()` 优先读取 `users` 表。
- 如果 `users` 表为空，再读取旧 `auth.users` 或 `auth.admin_password_hash`。
- 读取旧用户成功后立即回写 `users` 表。
- `_save_users()` 同时写 `users` 表和旧 `auth` 兼容快照。

5. 运行安全测试。

```powershell
python -m pytest tests/test_security.py -q
```

预期：通过。

---

## 任务 4：结构化自动对数历史

**涉及文件：**

- 新建：`src/auto_check/app/storage_history.py`
- 修改：`src/auto_check/app/history.py`
- 测试：`tests/test_history.py`

### 步骤

1. 新增测试 `test_sqlite_history_store_writes_reconcile_results_to_normalized_tables`。

```python
def test_sqlite_history_store_writes_reconcile_results_to_normalized_tables(tmp_path):
    import sqlite3

    from auto_check.app.history import SqliteHistoryStore, build_history_entry
    from auto_check.app.local_store import db_path_for_config

    config_path = tmp_path / "config.json"
    store = SqliteHistoryStore(config_path)
    run = build_history_entry(
        previous_runs=[],
        run_date="2026-06-30",
        config_name="local",
        dws_source_name="dws",
        config=_sample_config(),
        results=[
            {
                "project_code": "P001",
                "project_name": "Project One",
                "asset_total": "100",
                "liability_equity_total": "80",
                "received_trust_balance": "0",
                "difference": "20",
                "direction": "资产大于负债及权益",
                "difference_reason": "资产缺失",
                "match_status": "已解释",
                "valuation_asset_total": "80",
                "details": [
                    {
                        "kind": "asset_gap",
                        "data": {"specific_reason": "特定目的载体资产缺失", "asset_gap": "20"},
                    }
                ],
            }
        ],
    )

    store.save_run(run)

    with sqlite3.connect(db_path_for_config(config_path)) as connection:
        header_count = connection.execute("SELECT COUNT(*) FROM run_headers").fetchone()[0]
        result_row = connection.execute(
            "SELECT project_code, difference_reason, match_status FROM reconcile_results"
        ).fetchone()
        detail_row = connection.execute(
            "SELECT kind, specific_reason FROM reconcile_result_details"
        ).fetchone()

    assert header_count == 1
    assert result_row == ("P001", "资产缺失", "已解释")
    assert detail_row == ("asset_gap", "特定目的载体资产缺失")
    assert store.get_run(run["id"])["results"][0]["project_code"] == "P001"
    assert store.list_runs()[0]["total_count"] == 1
```

2. 运行失败测试。

```powershell
python -m pytest tests/test_history.py::test_sqlite_history_store_writes_reconcile_results_to_normalized_tables -q
```

预期：`reconcile_results` 未写入而失败。

3. 新建 `storage_history.py`，实现：

- `save_reconcile_run(connection, run)`
- `list_reconcile_runs(connection)`
- `get_reconcile_run(connection, run_id)`
- `delete_reconcile_run(connection, run_id)`
- `has_reconcile_runs(connection)`
- `_insert_reconcile_result(connection, run_id, index, result)`
- `_summary(run)`

写入规则：

- `run_headers.payload_json` 保存完整 run 快照。
- `reconcile_runs` 保存运行摘要。
- `reconcile_run_counts` 保存 `status_counts` 和 `reason_counts`。
- `reconcile_results` 保存每条差异的热字段。
- `reconcile_result_details` 保存详情类型、具体原因和详情 JSON。
- `reconcile_delta_results` 保存 `added_results`、`removed_results` 兼容内容。

4. 修改 `history.py` 中的 `SqliteHistoryStore`。

当 `kind == "reconcile"`：

- `save_run()` 写结构化表，同时继续写旧 `history_runs` 兼容快照。
- `list_runs()` 优先读结构化表。
- `get_run()` 优先读 `run_headers.payload_json`。
- `delete_run()` 同时删除结构化表和旧 `history_runs`。

其他 `kind` 暂时继续使用旧 `history_runs`。

5. 运行历史测试。

```powershell
python -m pytest tests/test_history.py -q
```

预期：通过。

---

## 任务 5：迁移现有数据与迁移报告

**涉及文件：**

- 修改：`src/auto_check/app/storage_schema.py`
- 修改：`src/auto_check/app/storage_config.py`
- 修改：`src/auto_check/app/storage_history.py`
- 修改：`src/auto_check/app/config.py`
- 修改：`src/auto_check/app/security.py`
- 修改：`src/auto_check/app/history.py`
- 测试：`tests/test_config.py`
- 测试：`tests/test_security.py`
- 测试：`tests/test_history.py`

### 步骤

1. 新增配置文件迁移测试 `test_store_migrates_from_config_json_when_sqlite_is_empty`。

```python
def test_store_migrates_from_config_json_when_sqlite_is_empty(tmp_path):
    import json
    import sqlite3

    from auto_check.app.config import load_store
    from auto_check.app.local_store import db_path_for_config

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "data_sources": [
                    {
                        "id": "source-json",
                        "name": "JSON 数据源",
                        "db_type": "postgresql",
                        "host": "127.0.0.1",
                        "port": 5432,
                        "database": "json_db",
                        "schema": "dws",
                        "username": "postgres",
                        "password": "Json123",
                        "is_default": True,
                    }
                ],
                "reconcile_data_sources": {
                    "dws_source_id": "source-json",
                    "business_source_id": "source-json",
                },
                "default_settings": {"page_size": 20},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    store = load_store(config_path)

    assert store.data_sources[0].id == "source-json"
    assert store.data_sources[0].config.password == "Json123"
    with sqlite3.connect(db_path_for_config(config_path)) as connection:
        source_count = connection.execute("SELECT COUNT(*) FROM data_sources").fetchone()[0]
        migration = connection.execute(
            "SELECT status, migrated_count FROM storage_migration_runs WHERE source_type = 'config_json'"
        ).fetchone()

    assert source_count == 1
    assert migration == ("completed", 1)
```

2. 新增用户 JSON 迁移测试 `test_auth_migrates_from_config_json_auth_when_users_table_is_empty`。

```python
def test_auth_migrates_from_config_json_auth_when_users_table_is_empty(tmp_path):
    import json
    import sqlite3

    from auto_check.app.local_store import db_path_for_config
    from auto_check.app.security import AuthManager, hash_password

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "auth": {
                    "users": [
                        {
                            "id": "u-admin",
                            "username": "admin",
                            "display_name": "管理员",
                            "role": "admin",
                            "password_hash": hash_password("Admin123"),
                            "enabled": True,
                            "created_at": "2026-07-01 10:00:00",
                            "updated_at": "2026-07-01 10:00:00",
                            "last_login_at": "",
                        }
                    ]
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    manager = AuthManager(config_path)

    assert manager.list_users()[0]["username"] == "admin"
    with sqlite3.connect(db_path_for_config(config_path)) as connection:
        row = connection.execute("SELECT username, role FROM users").fetchone()
        migration = connection.execute(
            "SELECT status, migrated_count FROM storage_migration_runs WHERE source_type = 'auth_json'"
        ).fetchone()

    assert row == ("admin", "admin")
    assert migration == ("completed", 1)
```

3. 新增 SQLite 旧历史表迁移测试 `test_reconcile_history_migrates_from_legacy_history_runs`。

```python
def test_reconcile_history_migrates_from_legacy_history_runs(tmp_path):
    import json
    import sqlite3

    from auto_check.app.history import SqliteHistoryStore, build_history_entry
    from auto_check.app.local_store import db_path_for_config

    config_path = tmp_path / "config.json"
    legacy_run = build_history_entry(
        previous_runs=[],
        run_date="2026-06-30",
        config_name="legacy",
        config=_sample_config(),
        results=[
            {
                "project_code": "P900",
                "project_name": "Legacy Project",
                "asset_total": "10",
                "liability_equity_total": "8",
                "received_trust_balance": "0",
                "difference": "2",
                "direction": "资产大于负债及权益",
                "difference_reason": "资产缺失",
                "match_status": "已解释",
                "details": [],
            }
        ],
    )
    with sqlite3.connect(db_path_for_config(config_path)) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS history_runs (kind TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL, run_date TEXT NOT NULL DEFAULT '', run_at TEXT NOT NULL DEFAULT '', config_fingerprint TEXT NOT NULL DEFAULT '', PRIMARY KEY (kind, id))"
        )
        connection.execute(
            "INSERT INTO history_runs(kind, id, payload, run_date, run_at, config_fingerprint) VALUES (?, ?, ?, ?, ?, ?)",
            (
                "reconcile",
                legacy_run["id"],
                json.dumps(legacy_run, ensure_ascii=False),
                legacy_run["run_date"],
                legacy_run["run_at"],
                legacy_run["config_fingerprint"],
            ),
        )

    store = SqliteHistoryStore(config_path)
    assert store.get_run(legacy_run["id"])["results"][0]["project_code"] == "P900"

    with sqlite3.connect(db_path_for_config(config_path)) as connection:
        count = connection.execute("SELECT COUNT(*) FROM reconcile_results").fetchone()[0]
    assert count == 1
```

4. 新增旧 `history.json` 文件迁移测试 `test_reconcile_history_migrates_from_legacy_history_json_file`。

```python
def test_reconcile_history_migrates_from_legacy_history_json_file(tmp_path):
    import json
    import sqlite3

    from auto_check.app.history import SqliteHistoryStore, build_history_entry
    from auto_check.app.local_store import db_path_for_config

    config_path = tmp_path / "config.json"
    legacy_run = build_history_entry(
        previous_runs=[],
        run_date="2026-06-30",
        config_name="legacy-file",
        config=_sample_config(),
        results=[
            {
                "project_code": "P901",
                "project_name": "Legacy File Project",
                "asset_total": "10",
                "liability_equity_total": "8",
                "received_trust_balance": "0",
                "difference": "2",
                "direction": "资产大于负债及权益",
                "difference_reason": "资产缺失",
                "match_status": "已解释",
                "details": [],
            }
        ],
    )
    config_path.with_name("history.json").write_text(
        json.dumps({"runs": [legacy_run]}, ensure_ascii=False),
        encoding="utf-8",
    )

    store = SqliteHistoryStore(config_path)

    assert store.get_run(legacy_run["id"])["results"][0]["project_code"] == "P901"
    with sqlite3.connect(db_path_for_config(config_path)) as connection:
        result_count = connection.execute("SELECT COUNT(*) FROM reconcile_results").fetchone()[0]
        migration = connection.execute(
            "SELECT status, migrated_count FROM storage_migration_runs WHERE source_type = 'history_json'"
        ).fetchone()

    assert result_count == 1
    assert migration == ("completed", 1)
```

5. 新增旧人行逐笔校验历史文件兼容导入测试 `test_db_validation_history_json_imports_to_legacy_history_runs`。

```python
def test_db_validation_history_json_imports_to_legacy_history_runs(tmp_path):
    import json

    from auto_check.app.history import SqliteHistoryStore

    config_path = tmp_path / "config.json"
    config_path.with_name("db-validation-history.json").write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "id": "dbv-1",
                        "run_at": "2026-07-01 10:00:00",
                        "run_date": "2026-06-30",
                        "report_date": "2026-06-30",
                        "status": "completed",
                        "result_count": 2,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    store = SqliteHistoryStore(config_path, kind="db_validation")

    assert store.get_run("dbv-1")["result_count"] == 2
    assert store.list_runs()[0]["id"] == "dbv-1"
```

6. 运行失败测试。

```powershell
python -m pytest tests/test_config.py::test_store_migrates_from_config_json_when_sqlite_is_empty tests/test_security.py::test_auth_migrates_from_config_json_auth_when_users_table_is_empty tests/test_history.py::test_reconcile_history_migrates_from_legacy_history_runs tests/test_history.py::test_reconcile_history_migrates_from_legacy_history_json_file tests/test_history.py::test_db_validation_history_json_imports_to_legacy_history_runs -q
```

预期：这些测试先失败，说明迁移入口和迁移记录尚未完成。

7. 在 `storage_schema.py` 增加迁移记录函数。

需要实现：

- `fingerprint_text(text: str) -> str`：对来源文本做 SHA-256。
- `migration_completed(connection, source_type, source_path, source_key, source_fingerprint) -> bool`
- `record_migration(connection, source_type, source_path, source_key, source_fingerprint, migrated_count, skipped_count, status, message)`

`status` 只允许使用：

- `completed`
- `skipped`
- `failed`

失败时 `message` 保存首行错误摘要，不能保存密码和完整 SQL。

8. 在 `config.py` 的 `load_store()` 中补齐配置迁移。

规则：

- 如果结构化 `data_sources` 已有数据，直接读取结构化表。
- 如果结构化表为空，优先读取 `app_kv.config_store`。
- 如果 `app_kv.config_store` 为空，再读取 `config.json`。
- 成功解析后调用 `save_store()` 写入结构化表和兼容快照。
- 用 `storage_migration_runs` 记录来源：`config_store` 或 `config_json`。
- 迁移不能改变密码含义：明文密码按现有逻辑加密，已加密密码按现有逻辑解密再加密保存。

9. 在 `security.py` 的 `_auth_payload()` 中补齐用户迁移。

规则：

- 如果 `users` 表已有用户，直接读取。
- 如果为空，优先读取 `app_kv.auth`。
- 如果 `app_kv.auth` 为空，再读取 `config.json.auth`。
- 如果只有旧 `admin_password_hash`，按现有逻辑生成管理员用户后写入 `users`。
- 迁移保留原 `password_hash`，不重置密码。
- 用 `storage_migration_runs` 记录来源：`auth_store` 或 `auth_json`。

10. 在 `storage_history.py` 增加历史迁移函数。

需要实现：

- `migrate_legacy_reconcile_runs(connection, config_path)`
- `migrate_reconcile_history_json(connection, config_path)`
- `migrate_db_validation_history_json_to_legacy_runs(connection, config_path)`

规则：

- 自动对数历史优先迁移 `history_runs(kind='reconcile')`。
- 如果旧 SQLite 没有自动对数历史，再读 `config_path.with_name("history.json")`。
- `history.json` 支持两种格式：顶层列表、或 `{"runs": [...]}`。
- `run_id` 已存在时跳过，不能重复插入。
- `db-validation-history.json` 一期只导入到 `history_runs(kind='db_validation')` 兼容表，不拆到结构化明细表。
- 每个来源都写 `storage_migration_runs`。

11. 在 `SqliteHistoryStore` 入口调用历史迁移。

规则：

- `kind == "reconcile"` 时，在 `list_runs()` 和 `get_run()` 开头调用自动对数历史迁移。
- `kind == "db_validation"` 时，在 `list_runs()` 和 `get_run()` 开头调用 `db-validation-history.json` 兼容导入。
- `kind == "flow_chain"` 暂不从文件导入；只保留旧 `history_runs`。

12. 运行迁移相关测试。

```powershell
python -m pytest tests/test_config.py tests/test_security.py tests/test_history.py -q
```

预期：通过。

---

## 任务 6：保持 API 行为不变

**涉及文件：**

- 修改：`src/auto_check/app/server.py`，仅在测试发现接口行为变化时修改。
- 测试：`tests/test_server.py`

### 步骤

1. 运行关键回归测试。

```powershell
python -m pytest tests/test_server.py::test_api_router_uses_sqlite_history_store_by_default tests/test_server.py::test_post_config_saves_payload tests/test_server.py::test_flow_tool_manual_start_saves_history_with_trigger_type -q
```

预期：通过。

2. 如果 `/api/history` 摘要字段变化，修正 `storage_history._summary()`，确保与现有 `summarize_run()` 等价：

```python
def _summary(run: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in run.items()
        if key not in {"results", "added_results", "removed_results"}
    }
```

3. 运行完整服务测试。

```powershell
python -m pytest tests/test_server.py -q
```

预期：通过。

---

## 任务 7：同步文档

**涉及文件：**

- 修改：`README.md`
- 修改：`docs/check-history-design.zh-CN.md`
- 修改：`docs/reconcile-execution-flow.zh-CN.md`
- 测试：`tests/test_packaging_and_roadmap.py`、`tests/test_web_static.py`

### 步骤

1. 更新 `README.md` 本地持久化说明。

建议文案：

```markdown
- 本地持久化：系统自身配置、用户和历史记录保存到配置目录下的 `auto-check.db`（SQLite）。当前版本使用结构化表保存数据源、用户、系统设置和自动对数历史热字段，并保留 `config.json` 与旧 `app_kv/history_runs` 兼容快照；迁移服务器时需要一并迁移 `auto-check.db`。
```

2. 更新 `docs/check-history-design.zh-CN.md`。

新增说明：

```markdown
## 当前实现

历史记录已从早期 `history.json` 迁移到本地 SQLite。自动对数历史使用 `run_headers`、`reconcile_runs`、`reconcile_results`、`reconcile_result_details`、`reconcile_run_counts` 和 `reconcile_delta_results` 保存常用查询字段，完整历史 payload 保留在 `run_headers.payload_json` 作为兼容快照。

旧版 `history_runs(kind='reconcile')` 会在首次读取自动迁移到结构化表。迁移过程保持幂等，不删除旧数据。
```

3. 更新 `docs/reconcile-execution-flow.zh-CN.md` 的历史/导出章节。

新增说明：

```markdown
自动对数执行完成后，历史摘要字段写入结构化历史表，结果明细和差异详情同时保留结构化热字段与兼容快照。列表页、统计和后续筛选优先读取结构化表；详情页和导出仍可从兼容 payload 还原完整结果，确保旧历史记录迁移后表现一致。
```

4. 运行文档和静态测试。

```powershell
python -m pytest tests/test_packaging_and_roadmap.py tests/test_web_static.py -q
```

预期：通过。若测试校验 README 固定文本，同步更新断言。

---

## 任务 8：全量验证与打包

### 步骤

1. 运行全量测试。

```powershell
python -m pytest -q
```

预期：通过。

2. 检查空白问题。

```powershell
git diff --check
```

预期：没有实际 whitespace error。仓库约定中 CRLF/LF 提示通常不作为失败处理。

3. 如需交付应用，确认没有正在运行的 `dist\auto-check.exe`。

```powershell
Get-Process auto-check -ErrorAction SilentlyContinue
```

如果没有进程占用，运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\package-windows.ps1
```

预期：刷新 `dist\auto-check.exe`。

4. 手工冒烟验证。

```powershell
python -m auto_check --config D:\xiaxin\auto_check\config\local-pg-test-config.json --no-browser
```

检查：

- 设置页能读取数据源。
- 登录和用户管理正常。
- 自动对数执行后能保存历史。
- `/api/history` 返回摘要。
- 历史详情页能显示完整结果和导出详情。
- 旧 `history_runs` 数据首次访问后能迁移到结构化表。

---

## 二期计划

一期稳定后再做：

- 人行逐笔校验结果行结构化：`db_validation_runs`、`db_validation_selected_tables`、`db_validation_warnings`、`db_validation_result_rows`。
- 流程链历史结构化：`flow_chain_runs`、`flow_chain_run_steps`、`flow_chain_run_logs`。
- 存储维护 UI：备份、压缩数据库、导出旧 JSON 快照。
- 迁移完成后的 `VACUUM` 和旧快照清理策略。

## 自查

- 覆盖范围：迁移框架、配置、用户、自动对数历史、旧数据迁移、API 兼容、文档和测试均已覆盖。
- 范围控制：一期不一次性拆完所有历史类型，先处理最大痛点。
- 兼容策略：旧 JSON 不删除，新写路径保留兼容快照，便于回退和审计。
