# User Interface Radius Preferences Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为每个登录用户提供服务端同步的全局界面圆角设置，在系统设置中通过 1–15px 单滑块所见即所得预览并显式保存，默认 4px，且除 `border-radius` 显示外不改变任何系统功能、数据、权限或交互。

**Architecture:** 新增 MySQL 第 36 张表 `user_interface_preferences` 和独立 SQLAlchemy 仓储；认证后的 `GET/POST /api/settings/interface` 只读写当前会话用户。前端在解除 `auth-pending` 前加载偏好，用根变量 `--ui-radius` 驱动集中式明确选择器覆盖层；拖动只更新草稿和 CSS，保存成功才更新服务端基线，离开设置页撤销未保存预览。

**Tech Stack:** Python 3.12、SQLAlchemy Core、MySQL 8、原生 HTML/CSS/JavaScript、pytest、PyInstaller、PowerShell

---

## 实施边界与执行约束

- 本计划的权威需求来自 `docs/superpowers/specs/2026-07-17-user-interface-radius-design.md`。
- 只修改圆角显示及新增的“界面设置”卡片；不修改业务请求体、表单值、事件绑定、权限判断、页面切换、弹窗开关、尺寸、定位、层级和点击区域。
- 登录页不加载 `styles.css`，仍需在圆角覆盖测试中明确禁止登录页选择器和本地存储权威来源。
- `001_init_schema.sql`、`002_report_navigation.sql`、`003_report_navigation_seed.sql` 不改；仅新增 `004_user_interface_preferences.sql`。
- `CURRENT_APP_SCHEMA_VERSION` 保持 `1`，期望表数由 35 调整为 36。
- 不在代码实现阶段连接或写入用户提供的正式 MySQL。正式库执行 `004`、启动新程序和双账号验收必须在代码交付后再次取得明确上线授权。
- 每个任务遵循红—绿—重构：先写最小失败测试并确认失败原因，再写实现，再跑相关回归后提交。

## 文件结构映射

### 新增文件

- `sql/app_storage/mysql/004_user_interface_preferences.sql`：偏好表增量 DDL。
- `src/auto_check/app/storage_user_interface_preferences.py`：读取、保存、孤儿清理仓储。
- `tests/test_user_interface_preferences.py`：DDL、仓储、隔离、upsert 和清理测试。

### 修改文件

- `src/auto_check/app/app_database.py`：加入第 36 张表的结构契约。
- `src/auto_check/app/security.py`：用户整体替换事务内清理孤儿偏好。
- `src/auto_check/app/server.py`：当前用户偏好 GET/POST API。
- `src/auto_check/web/index.html`：系统设置新增普通用户可见的界面设置卡片。
- `src/auto_check/web/app.js`：启动加载、草稿/保存基线、预览/保存/恢复/离页撤销。
- `src/auto_check/web/styles.css`：根变量、界面设置布局、语义化圆角覆盖层和普通用户网格。
- `scripts/export_sqlite_to_mysql.py`：生成迁移报告时提示后续还需执行 `004`，但不从 SQLite 导出偏好数据。
- `tests/mysql_config_test_support.py`：内存 MySQL 契约执行器支持新表、`user_id` 和 `NOT IN` 清理。
- `tests/test_app_database.py`、`tests/test_report_navigation_schema.py`：期望表数更新为 36。
- `tests/test_sqlite_to_mysql_export.py`：后续 SQL 资产顺序包含 `004`。
- `tests/test_server.py`：路由层当前用户隔离和严格值校验。
- `tests/test_security.py`：真实 HTTP 登录、CSRF、普通用户访问和删用户清理回归。
- `tests/test_web_static.py`：卡片、启动顺序、状态模型、覆盖范围与显示-only 契约。
- `tests/test_deployment_assets.py`：部署文档和 `004` 资产一致性。
- `README.md`：功能、表数、SQL 顺序、版本说明。
- `docs/mysql-application-storage.zh-CN.md`、`docs/deployment.zh-CN.md`、`docs/intranet-production-deployment.zh-CN.md`：第 36 张表和升级顺序。
- `dist/auto-check.exe`：所有测试通过后重新打包刷新。

## Task 1: 增量 DDL、结构契约和 SQL 资产顺序

**Files:**

- Create: `sql/app_storage/mysql/004_user_interface_preferences.sql`
- Modify: `src/auto_check/app/app_database.py`
- Modify: `scripts/export_sqlite_to_mysql.py`
- Create: `tests/test_user_interface_preferences.py`
- Modify: `tests/test_app_database.py`
- Modify: `tests/test_report_navigation_schema.py`
- Modify: `tests/test_sqlite_to_mysql_export.py`

- [ ] **Step 1: 先写 DDL 和结构契约失败测试**

在 `tests/test_user_interface_preferences.py` 写入：

```python
from pathlib import Path

from auto_check.app.app_database import CURRENT_APP_SCHEMA_VERSION, EXPECTED_APP_SCHEMA


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_SQL = ROOT / "sql" / "app_storage" / "mysql" / "004_user_interface_preferences.sql"


def test_user_interface_preferences_incremental_schema_is_safe_and_documented():
    sql = SCHEMA_SQL.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS `user_interface_preferences`" in sql
    assert "`user_id` VARCHAR(64) NOT NULL COMMENT '用户 ID'" in sql
    assert "`radius_px` TINYINT UNSIGNED NOT NULL DEFAULT 4" in sql
    assert "`updated_at` DATETIME(6) NOT NULL" in sql
    assert "PRIMARY KEY (`user_id`)" in sql
    assert "CHECK (`radius_px` BETWEEN 1 AND 15)" in sql
    assert "COMMENT='用户界面偏好表：保存每个用户的界面圆角设置。'" in sql
    assert "FOREIGN KEY" not in sql.upper()
    assert "DROP TABLE" not in sql.upper()
    assert "TRUNCATE TABLE" not in sql.upper()
    assert "ALTER TABLE" not in sql.upper()
    assert "app_schema_version" not in sql


def test_application_schema_keeps_version_one_and_adds_interface_preferences():
    assert CURRENT_APP_SCHEMA_VERSION == 1
    assert EXPECTED_APP_SCHEMA["user_interface_preferences"] == frozenset(
        {"user_id", "radius_px", "updated_at"}
    )
    assert len(EXPECTED_APP_SCHEMA) == 36
```

同时更新原有数量断言：

```python
# tests/test_app_database.py
def test_expected_schema_is_immutable_and_contains_35_business_tables():
    assert len(EXPECTED_APP_SCHEMA) == 36

# tests/test_report_navigation_schema.py
assert len(EXPECTED_APP_SCHEMA) == 36
```

将测试函数名同步改成不写死旧的“34 business tables”，例如：

```python
def test_expected_schema_is_immutable_and_contains_all_application_tables():
```

- [ ] **Step 2: 写 SQL 资产顺序失败测试**

更新 `tests/test_sqlite_to_mysql_export.py`：

```python
assert report["post_migration_schema_scripts"] == [
    "sql/app_storage/mysql/002_report_navigation.sql",
    "sql/app_storage/mysql/003_report_navigation_seed.sql",
    "sql/app_storage/mysql/004_user_interface_preferences.sql",
]
```

- [ ] **Step 3: 运行失败测试并确认只因功能缺失失败**

Run:

```powershell
python -m pytest -q tests/test_user_interface_preferences.py tests/test_app_database.py tests/test_report_navigation_schema.py tests/test_sqlite_to_mysql_export.py
```

Expected: FAIL；失败原因包括 `004_user_interface_preferences.sql` 不存在、`EXPECTED_APP_SCHEMA` 缺少新表、表数仍为 35、后续 SQL 列表缺少 `004`。不得接受导入错误或无关测试失败。

- [ ] **Step 4: 新增最小 DDL**

创建 `sql/app_storage/mysql/004_user_interface_preferences.sql`：

```sql
CREATE TABLE IF NOT EXISTS `user_interface_preferences` (
  `user_id` VARCHAR(64) NOT NULL COMMENT '用户 ID',
  `radius_px` TINYINT UNSIGNED NOT NULL DEFAULT 4 COMMENT '界面圆角像素值，范围 1 至 15',
  `updated_at` DATETIME(6) NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`user_id`),
  CONSTRAINT `chk_user_interface_radius_px` CHECK (`radius_px` BETWEEN 1 AND 15)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='用户界面偏好表：保存每个用户的界面圆角设置。';
```

- [ ] **Step 5: 更新应用结构契约**

在 `src/auto_check/app/app_database.py` 的 `users` 附近加入：

```python
"user_interface_preferences": _columns("user_id", "radius_px", "updated_at"),
```

保持：

```python
CURRENT_APP_SCHEMA_VERSION = 1
```

- [ ] **Step 6: 更新离线导出后的 SQL 提示，不增加 SQLite 数据映射**

在 `scripts/export_sqlite_to_mysql.py` 中：

```python
POST_MIGRATION_SCHEMA_SCRIPTS = [
    "sql/app_storage/mysql/002_report_navigation.sql",
    "sql/app_storage/mysql/003_report_navigation_seed.sql",
    "sql/app_storage/mysql/004_user_interface_preferences.sql",
]
```

保持 `MIGRATION_TARGET_TABLE_ORDER` 不包含新表，因为旧 SQLite 没有用户界面偏好来源。

- [ ] **Step 7: 运行目标测试至绿色**

Run:

```powershell
python -m pytest -q tests/test_user_interface_preferences.py tests/test_app_database.py tests/test_report_navigation_schema.py tests/test_sqlite_to_mysql_export.py
```

Expected: PASS。

- [ ] **Step 8: 提交数据库契约**

```powershell
git add sql/app_storage/mysql/004_user_interface_preferences.sql src/auto_check/app/app_database.py scripts/export_sqlite_to_mysql.py tests/test_user_interface_preferences.py tests/test_app_database.py tests/test_report_navigation_schema.py tests/test_sqlite_to_mysql_export.py
git commit -m "feat: add user interface preference schema"
```

## Task 2: 偏好仓储、MySQL 契约桩和孤儿清理

**Files:**

- Create: `src/auto_check/app/storage_user_interface_preferences.py`
- Modify: `src/auto_check/app/security.py`
- Modify: `tests/mysql_config_test_support.py`
- Modify: `tests/test_user_interface_preferences.py`
- Modify: `tests/test_security.py`

- [ ] **Step 1: 先写仓储行为失败测试**

在 `tests/test_user_interface_preferences.py` 增加：

```python
from mysql_config_test_support import MySqlContractConnection
from auto_check.app.storage_user_interface_preferences import (
    load_user_interface_preferences,
    prune_user_interface_preferences,
    save_user_interface_preferences,
)


def test_missing_or_invalid_interface_radius_uses_default_four():
    connection = MySqlContractConnection()
    assert load_user_interface_preferences(connection, "user-a") == 4

    connection.tables["user_interface_preferences"].append(
        {"user_id": "user-a", "radius_px": 99, "updated_at": None}
    )
    assert load_user_interface_preferences(connection, "user-a") == 4


def test_interface_preferences_upsert_and_isolate_users():
    connection = MySqlContractConnection()

    assert save_user_interface_preferences(connection, "user-a", 1) == 1
    assert save_user_interface_preferences(connection, "user-a", 15) == 15
    assert save_user_interface_preferences(connection, "user-b", 7) == 7

    assert load_user_interface_preferences(connection, "user-a") == 15
    assert load_user_interface_preferences(connection, "user-b") == 7
    assert len(connection.tables["user_interface_preferences"]) == 2


def test_prune_interface_preferences_keeps_only_active_users():
    connection = MySqlContractConnection()
    save_user_interface_preferences(connection, "active", 6)
    save_user_interface_preferences(connection, "deleted", 12)

    prune_user_interface_preferences(connection, ["active"])

    assert [row["user_id"] for row in connection.tables["user_interface_preferences"]] == ["active"]
    assert load_user_interface_preferences(connection, "active") == 6
    assert load_user_interface_preferences(connection, "deleted") == 4
```

- [ ] **Step 2: 写用户删除事务清理失败测试**

在 `tests/test_security.py` 增加集成测试：

```python
def test_deleting_user_prunes_interface_preferences_in_same_user_transaction(
    tmp_path, shared_application_database
):
    from auto_check.app.storage_user_interface_preferences import save_user_interface_preferences

    manager = AuthManager(tmp_path / "config.json")
    manager.set_admin_password("Admin123")
    admin = manager.list_users()[0]
    operator = manager.create_user("operator", "Operator123", "user")

    with shared_application_database.transaction() as connection:
        save_user_interface_preferences(connection, admin["id"], 4)
        save_user_interface_preferences(connection, operator["id"], 12)

    manager.delete_user(operator["id"], current_user_id=admin["id"])

    rows = shared_application_database.connection.tables["user_interface_preferences"]
    assert [(row["user_id"], row["radius_px"]) for row in rows] == [(admin["id"], 4)]
```

- [ ] **Step 3: 运行失败测试**

Run:

```powershell
python -m pytest -q tests/test_user_interface_preferences.py tests/test_security.py -k "interface_preferences or prunes_interface"
```

Expected: FAIL；新仓储模块不存在或内存契约桩缺少新表，且用户删除尚未清理偏好。

- [ ] **Step 4: 实现独立仓储**

创建 `src/auto_check/app/storage_user_interface_preferences.py`，核心实现为：

```python
from __future__ import annotations

from datetime import UTC, datetime
from typing import Iterable

from sqlalchemy import Column, MetaData, SmallInteger, String, Table, delete, select
from sqlalchemy.dialects.mysql import DATETIME, insert as mysql_insert
from sqlalchemy.engine import Connection


DEFAULT_INTERFACE_RADIUS_PX = 4
MIN_INTERFACE_RADIUS_PX = 1
MAX_INTERFACE_RADIUS_PX = 15

_METADATA = MetaData()
USER_INTERFACE_PREFERENCES = Table(
    "user_interface_preferences",
    _METADATA,
    Column("user_id", String(64), primary_key=True),
    Column("radius_px", SmallInteger, nullable=False),
    Column("updated_at", DATETIME(fsp=6), nullable=False),
)


def load_user_interface_preferences(connection: Connection, user_id: str) -> int:
    row = connection.execute(
        select(USER_INTERFACE_PREFERENCES.c.radius_px).where(
            USER_INTERFACE_PREFERENCES.c.user_id == str(user_id)
        )
    ).mappings().first()
    value = row["radius_px"] if row is not None else None
    if type(value) is not int or not MIN_INTERFACE_RADIUS_PX <= value <= MAX_INTERFACE_RADIUS_PX:
        return DEFAULT_INTERFACE_RADIUS_PX
    return value


def save_user_interface_preferences(connection: Connection, user_id: str, radius_px: int) -> int:
    radius_px = _validate_radius(radius_px)
    statement = mysql_insert(USER_INTERFACE_PREFERENCES).values(
        user_id=str(user_id),
        radius_px=radius_px,
        updated_at=datetime.now(UTC).replace(tzinfo=None),
    )
    connection.execute(
        statement.on_duplicate_key_update(
            radius_px=statement.inserted.radius_px,
            updated_at=statement.inserted.updated_at,
        )
    )
    return radius_px


def prune_user_interface_preferences(connection: Connection, active_user_ids: Iterable[str]) -> None:
    active_ids = sorted({str(user_id) for user_id in active_user_ids if str(user_id)})
    statement = delete(USER_INTERFACE_PREFERENCES)
    if active_ids:
        statement = statement.where(USER_INTERFACE_PREFERENCES.c.user_id.not_in(active_ids))
    connection.execute(statement)


def _validate_radius(value: int) -> int:
    if type(value) is not int or not MIN_INTERFACE_RADIUS_PX <= value <= MAX_INTERFACE_RADIUS_PX:
        raise ValueError("radius_px must be an integer between 1 and 15")
    return value
```

保持使用 SQLAlchemy 和 `MemoryResult` 都支持的 `.mappings().first()`，不要让测试桩驱动生产代码采用异常写法。

- [ ] **Step 5: 扩展 MySQL 契约桩**

在 `tests/mysql_config_test_support.py`：

```python
self.tables["user_interface_preferences"] = []
```

将 `user_id` 加入 select/delete 过滤字段列表，并把主键映射补成：

```python
if table_name == "user_interface_preferences":
    return ("user_id",)
```

在 delete 分支先处理 `NOT IN`：

```python
if " NOT IN " in sql.upper():
    active_ids = {str(value) for value in next(
        (value for value in params.values() if isinstance(value, list)), []
    )}
    self.tables[table_name] = [
        row for row in self.tables[table_name]
        if str(row.get("user_id")) in active_ids
    ]
```

该分支必须位于普通 `" IN "` 判断之前。

- [ ] **Step 6: 在用户保存事务内清理偏好**

修改 `AuthManager._save_users()`：

```python
def _save_users(self, users: list[dict[str, Any]]) -> None:
    from auto_check.app.storage_user_interface_preferences import prune_user_interface_preferences
    from auto_check.app.storage_users import replace_users

    normalized_users = [_normalize_user(user) for user in users]
    with self.database.transaction() as connection:
        replace_users(connection, normalized_users)
        prune_user_interface_preferences(
            connection,
            [str(user["id"]) for user in normalized_users],
        )
```

不改变 `AuthSession`、公开用户字段或现有用户写入方式。

- [ ] **Step 7: 运行仓储和认证回归**

Run:

```powershell
python -m pytest -q tests/test_user_interface_preferences.py tests/test_security.py
```

Expected: PASS；现有登录、用户写入和用户管理测试也保持绿色。

- [ ] **Step 8: 提交仓储层**

```powershell
git add src/auto_check/app/storage_user_interface_preferences.py src/auto_check/app/security.py tests/mysql_config_test_support.py tests/test_user_interface_preferences.py tests/test_security.py
git commit -m "feat: persist per-user interface radius"
```

## Task 3: 当前用户 API、严格校验和 CSRF 回归

**Files:**

- Modify: `src/auto_check/app/server.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_security.py`

- [ ] **Step 1: 写路由层隔离和边界失败测试**

在 `tests/test_server.py` 增加：

```python
def test_interface_settings_api_defaults_upserts_and_isolates_current_user(
    tmp_path, shared_application_database
):
    router = ApiRouter(config_path=tmp_path / "config.json")
    user_a = {"id": "user-a", "username": "a", "role": "user"}
    user_b = {"id": "user-b", "username": "b", "role": "user"}

    assert router.handle("GET", "/api/settings/interface", None, current_user=user_a) == (
        200,
        {"settings": {"radius_px": 4}},
    )
    assert router.handle(
        "POST",
        "/api/settings/interface",
        {"radius_px": 15, "user_id": "user-b"},
        current_user=user_a,
    ) == (200, {"settings": {"radius_px": 15}})
    assert router.handle("GET", "/api/settings/interface", None, current_user=user_b) == (
        200,
        {"settings": {"radius_px": 4}},
    )
```

在同文件增加严格校验参数化测试：

```python
@pytest.mark.parametrize("value", [0, 16, 1.5, True, False, None, "4", "bad"])
def test_interface_settings_api_rejects_non_integer_or_out_of_range_radius(
    tmp_path, value
):
    router = ApiRouter(config_path=tmp_path / "config.json")
    status, payload = router.handle(
        "POST",
        "/api/settings/interface",
        {"radius_px": value},
        current_user={"id": "user-a", "username": "a", "role": "user"},
    )
    assert status == 400
    assert payload["error"] == "radius_px must be an integer between 1 and 15"


@pytest.mark.parametrize("value", [1, 15])
def test_interface_settings_api_accepts_boundary_values(tmp_path, value):
    router = ApiRouter(config_path=tmp_path / "config.json")
    status, payload = router.handle(
        "POST",
        "/api/settings/interface",
        {"radius_px": value},
        current_user={"id": "user-a", "username": "a", "role": "user"},
    )
    assert (status, payload) == (200, {"settings": {"radius_px": value}})
```

另加 `current_user=None` 返回 401 的直接路由测试，防止内部调用绕过会话边界。

- [ ] **Step 2: 写 HTTP 认证和 CSRF 失败测试**

在 `tests/test_security.py` 使用现有 `_start_auth_test_server`、`_encrypted_password`、`_json_request`：

```python
def test_interface_settings_http_requires_login_and_csrf_but_allows_regular_user(tmp_path):
    server = _start_auth_test_server(tmp_path / "config.json")
    try:
        status, payload, _ = _json_request(server, "GET", "/api/settings/interface")
        assert status == 401
        assert payload["error"] == "login required"

        status, setup_payload, setup_headers = _json_request(
            server,
            "POST",
            "/api/auth/setup",
            {"password_encrypted": _encrypted_password(server, "AdminPass123")},
        )
        assert status == 200
        admin_headers = {
            "Cookie": setup_headers["set-cookie"].split(";", 1)[0],
            "X-CSRF-Token": setup_payload["csrf_token"],
        }
        status, _, _ = _json_request(
            server,
            "POST",
            "/api/users",
            {
                "username": "operator",
                "role": "user",
                "password_encrypted": _encrypted_password(server, "Operator123"),
                "enabled": True,
            },
            admin_headers,
        )
        assert status == 200

        status, login_payload, login_headers = _json_request(
            server,
            "POST",
            "/api/auth/login",
            {
                "username": "operator",
                "password_encrypted": _encrypted_password(server, "Operator123"),
            },
        )
        assert status == 200
        user_cookie = login_headers["set-cookie"].split(";", 1)[0]

        status, payload, _ = _json_request(
            server,
            "GET",
            "/api/settings/interface",
            None,
            {"Cookie": user_cookie},
        )
        assert (status, payload) == (200, {"settings": {"radius_px": 4}})

        status, payload, _ = _json_request(
            server,
            "POST",
            "/api/settings/interface",
            {"radius_px": 12},
            {"Cookie": user_cookie},
        )
        assert status == 403
        assert payload["error"] == "invalid csrf token"

        status, payload, _ = _json_request(
            server,
            "POST",
            "/api/settings/interface",
            {"radius_px": 12},
            {
                "Cookie": user_cookie,
                "X-CSRF-Token": login_payload["csrf_token"],
            },
        )
        assert (status, payload) == (200, {"settings": {"radius_px": 12}})
    finally:
        server.shutdown()
        server.server_close()
```

实现完整测试，不复制新的 HTTP 服务器帮助函数。

- [ ] **Step 3: 运行失败测试**

Run:

```powershell
python -m pytest -q tests/test_server.py tests/test_security.py -k "interface_settings"
```

Expected: FAIL；接口路由尚不存在，HTTP POST 仍会落到 404，但现有登录/CSRF 基础设施正常。

- [ ] **Step 4: 实现当前用户 GET/POST 路由**

在 `src/auto_check/app/server.py` 导入仓储常量和函数，并在 `ApiRouter.handle()` 业务分支前部加入：

```python
if path == "/api/settings/interface":
    user_id = str((current_user or {}).get("id") or "")
    if not user_id:
        return 401, {"error": "login required"}

    if method == "GET":
        with self.application_database.connect() as connection:
            radius_px = load_user_interface_preferences(connection, user_id)
        return 200, {"settings": {"radius_px": radius_px}}

    if method == "POST":
        radius_px = (body or {}).get("radius_px")
        if type(radius_px) is not int or not 1 <= radius_px <= 15:
            raise ValueError("radius_px must be an integer between 1 and 15")
        with self.application_database.transaction() as connection:
            saved_radius = save_user_interface_preferences(connection, user_id, radius_px)
        return 200, {"settings": {"radius_px": saved_radius}}
```

请求中的 `user_id` 永远不读取。POST 的 CSRF 继续由 `AutoCheckRequestHandler._handle_api()` 在进入路由前统一校验，不新增第二套 token 逻辑。

- [ ] **Step 5: 运行路由和认证回归**

Run:

```powershell
python -m pytest -q tests/test_server.py tests/test_security.py
```

Expected: PASS。

- [ ] **Step 6: 提交 API**

```powershell
git add src/auto_check/app/server.py tests/test_server.py tests/test_security.py
git commit -m "feat: expose current user interface settings api"
```

## Task 4: 系统设置卡片和前端草稿状态机

**Files:**

- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/app.js`
- Modify: `tests/test_web_static.py`

- [ ] **Step 1: 写卡片结构和普通用户可见性失败测试**

在 `tests/test_web_static.py` 增加：

```python
def test_interface_settings_card_is_user_visible_and_has_one_exact_slider():
    html = INDEX_HTML.read_text(encoding="utf-8")
    settings_html = html.split('id="page-settings"', 1)[1]
    card = re.search(
        r'<section class="card settings-dashboard-card card-interface">(?P<body>.*?)</section>',
        settings_html,
        re.S,
    )
    assert card is not None
    body = card.group("body")
    assert 'id="interfaceRadiusSlider" type="range" min="1" max="15" step="1" value="4"' in body
    assert 'id="interfaceRadiusValue"' in body
    assert 'id="saveInterfaceSettingsBtn"' in body
    assert 'id="resetInterfaceSettingsBtn"' in body
    assert "admin-only" not in card.group(0)

    system_pos = settings_html.index("card-system-info")
    interface_pos = settings_html.index("card-interface")
    data_pos = settings_html.index("card-data admin-only")
    assert system_pos < interface_pos < data_pos
```

- [ ] **Step 2: 写前端状态和启动顺序失败测试**

继续在 `tests/test_web_static.py` 增加或扩展现有认证启动测试：

```python
def test_interface_radius_loads_before_authenticated_app_is_revealed():
    app_js = APP_JS.read_text(encoding="utf-8")
    match = re.search(
        r"async function ensureAuthenticated\(\) \{(?P<body>.*?)\n\}",
        app_js,
        re.S,
    )
    assert match is not None
    ensure = match.group("body")
    assert 'await loadInterfaceRadiusPreference({ silent: true })' in ensure
    assert ensure.index("await loadInterfaceRadiusPreference") < ensure.index("revealAuthenticatedApp()")
    assert 'localStorage.setItem("autoCheckRadius' not in app_js


def test_interface_radius_draft_only_posts_on_explicit_save_and_reverts_on_leave():
    app_js = APP_JS.read_text(encoding="utf-8")
    assert "savedRadiusPx" in app_js
    assert "draftRadiusPx" in app_js
    assert 'interfaceRadiusSlider?.addEventListener("input"' in app_js
    match = re.search(
        r'interfaceRadiusSlider\?\.addEventListener\("input", \(\) => \{(?P<body>.*?)\n\}\);',
        app_js,
        re.S,
    )
    assert match is not None
    slider_handler = match.group("body")
    assert "applyInterfaceRadius" in slider_handler
    assert '/api/settings/interface' not in slider_handler
    assert 'api("/api/settings/interface", {' in app_js
    assert 'method: "POST"' in app_js
    assert "discardUnsavedInterfaceRadius" in app_js
    assert 'previousPage === "settings"' in app_js
```

- [ ] **Step 3: 运行失败测试**

Run:

```powershell
python -m pytest -q tests/test_web_static.py -k "interface_radius or interface_settings_card"
```

Expected: FAIL；卡片和状态函数尚不存在。

- [ ] **Step 4: 在系统信息后加入界面设置卡片**

在 `src/auto_check/web/index.html` 的 `card-system-info` 后加入：

```html
<!-- 界面设置 -->
<section class="card settings-dashboard-card card-interface">
  <div class="card-header">
    <div class="card-icon card-icon-purple" aria-hidden="true">◫</div>
    <div class="card-title">
      <h3>界面设置</h3>
      <p>自定义当前账号的系统圆角</p>
    </div>
  </div>
  <div class="card-body">
    <label class="interface-radius-control" for="interfaceRadiusSlider">
      <span class="setting-label">全局圆角</span>
      <span class="interface-radius-value" id="interfaceRadiusValue">4px</span>
      <input id="interfaceRadiusSlider" type="range" min="1" max="15" step="1" value="4" />
      <span class="setting-hint">导航、卡片、弹窗、矩形按钮和输入/选择控件统一使用该值</span>
    </label>
    <div id="interfaceSettingsStatus" class="interface-settings-status" role="status">已保存</div>
    <div class="settings-actions">
      <button id="saveInterfaceSettingsBtn" type="button" class="btn-primary btn-sm">保存界面设置</button>
      <button id="resetInterfaceSettingsBtn" type="button" class="btn-outline btn-sm">恢复默认</button>
    </div>
  </div>
</section>
```

滑块是唯一圆角值输入；不增加组件分类开关。

- [ ] **Step 5: 实现前端状态模型和规范化函数**

在 `src/auto_check/web/app.js` 的全局状态附近加入：

```javascript
const DEFAULT_INTERFACE_RADIUS_PX = 4;
const MIN_INTERFACE_RADIUS_PX = 1;
const MAX_INTERFACE_RADIUS_PX = 15;
const interfaceRadiusState = {
  savedRadiusPx: DEFAULT_INTERFACE_RADIUS_PX,
  draftRadiusPx: DEFAULT_INTERFACE_RADIUS_PX,
  loaded: false,
  loadFailed: false,
  saving: false,
  statusText: "已保存",
};

function normalizeInterfaceRadius(value) {
  return Number.isInteger(value) && value >= MIN_INTERFACE_RADIUS_PX && value <= MAX_INTERFACE_RADIUS_PX
    ? value
    : DEFAULT_INTERFACE_RADIUS_PX;
}

function applyInterfaceRadius(value) {
  const radiusPx = normalizeInterfaceRadius(value);
  document.documentElement.style.setProperty("--ui-radius", `${radiusPx}px`);
  return radiusPx;
}
```

缓存 `interfaceRadiusSlider`、`interfaceRadiusValue`、`interfaceSettingsStatus` 和两个按钮，增加 `renderInterfaceRadiusSettings(statusText = "")`。传入非空状态时先写入 `interfaceRadiusState.statusText`，无参数重绘时保留已有成功/失败文案；该函数只同步显示值、状态和保存按钮 loading/disabled，不操作任何业务控件。默认状态按 `draftRadiusPx === savedRadiusPx` 显示“已保存”，否则显示“正在预览，尚未保存”。

- [ ] **Step 6: 实现启动加载和失败回退**

```javascript
async function loadInterfaceRadiusPreference({ silent = false } = {}) {
  try {
    const payload = await api("/api/settings/interface");
    const radiusPx = normalizeInterfaceRadius(payload.settings?.radius_px);
    interfaceRadiusState.savedRadiusPx = radiusPx;
    interfaceRadiusState.draftRadiusPx = radiusPx;
    interfaceRadiusState.loaded = true;
    interfaceRadiusState.loadFailed = false;
    applyInterfaceRadius(radiusPx);
    renderInterfaceRadiusSettings("已保存");
    return true;
  } catch (error) {
    if (!interfaceRadiusState.loaded) {
      interfaceRadiusState.savedRadiusPx = DEFAULT_INTERFACE_RADIUS_PX;
      interfaceRadiusState.draftRadiusPx = DEFAULT_INTERFACE_RADIUS_PX;
      applyInterfaceRadius(DEFAULT_INTERFACE_RADIUS_PX);
    }
    interfaceRadiusState.loadFailed = true;
    renderInterfaceRadiusSettings("加载失败，当前使用默认 4px");
    if (!silent) showToast("界面设置加载失败，可稍后重试", "warning");
    return false;
  }
}
```

修改 `ensureAuthenticated()` 顺序：

```javascript
authState.csrfToken = payload.csrf_token || "";
authState.user = payload.user || null;
document.documentElement.dataset.role = authState.user?.role === "admin" ? "admin" : "user";
await loadInterfaceRadiusPreference({ silent: true });
activateThemeUserStorage();
applySavedUserTheme();
updateCurrentUsername();
applyRoleAccess();
revealAuthenticatedApp();
```

偏好 GET 失败必须被函数内部捕获，不能阻止 `revealAuthenticatedApp()`。

- [ ] **Step 7: 实现预览、保存、恢复默认和离页撤销**

```javascript
interfaceRadiusSlider?.addEventListener("input", () => {
  interfaceRadiusState.draftRadiusPx = normalizeInterfaceRadius(Number(interfaceRadiusSlider.value));
  applyInterfaceRadius(interfaceRadiusState.draftRadiusPx);
  renderInterfaceRadiusSettings("正在预览，尚未保存");
});

resetInterfaceSettingsBtn?.addEventListener("click", () => {
  interfaceRadiusState.draftRadiusPx = DEFAULT_INTERFACE_RADIUS_PX;
  applyInterfaceRadius(interfaceRadiusState.draftRadiusPx);
  renderInterfaceRadiusSettings("正在预览，尚未保存");
});

saveInterfaceSettingsBtn?.addEventListener("click", async () => {
  interfaceRadiusState.saving = true;
  renderInterfaceRadiusSettings("正在保存…");
  try {
    const payload = await api("/api/settings/interface", {
      method: "POST",
      body: JSON.stringify({ radius_px: interfaceRadiusState.draftRadiusPx }),
    });
    const radiusPx = normalizeInterfaceRadius(payload.settings?.radius_px);
    interfaceRadiusState.savedRadiusPx = radiusPx;
    interfaceRadiusState.draftRadiusPx = radiusPx;
    applyInterfaceRadius(radiusPx);
    renderInterfaceRadiusSettings("保存成功");
  } catch (error) {
    renderInterfaceRadiusSettings("保存失败，当前预览尚未保存");
    showToast(error.message, "error");
  } finally {
    interfaceRadiusState.saving = false;
    renderInterfaceRadiusSettings();
  }
});

function discardUnsavedInterfaceRadius() {
  if (interfaceRadiusState.draftRadiusPx === interfaceRadiusState.savedRadiusPx) return;
  interfaceRadiusState.draftRadiusPx = interfaceRadiusState.savedRadiusPx;
  applyInterfaceRadius(interfaceRadiusState.savedRadiusPx);
  renderInterfaceRadiusSettings("已保存");
}
```

在 `switchPage()` 设置新页面前加入：

```javascript
if (previousPage === "settings" && name !== "settings") {
  discardUnsavedInterfaceRadius();
}
```

在 `loadSettingsPageData()` 中加入界面偏好刷新；若重复打开设置页，从服务端重新读取最后一次成功保存值，以满足多设备最后写入生效：

```javascript
loadPageSection("界面设置", () => loadInterfaceRadiusPreference({ silent: false })),
```

- [ ] **Step 8: 运行前端静态测试**

Run:

```powershell
python -m pytest -q tests/test_web_static.py
```

Expected: PASS；特别确认现有设置页 loader 断言仍允许非阻塞加载，不把整个页面切换改成等待所有管理配置。

- [ ] **Step 9: 提交前端状态和标记**

```powershell
git add src/auto_check/web/index.html src/auto_check/web/app.js tests/test_web_static.py
git commit -m "feat: add interface radius settings controls"
```

## Task 5: 集中式圆角覆盖和 display-only 契约

**Files:**

- Modify: `src/auto_check/web/styles.css`
- Modify: `tests/test_web_static.py`

- [ ] **Step 1: 写覆盖层范围和属性限制失败测试**

在 `tests/test_web_static.py` 增加：

```python
def test_user_radius_override_is_semantic_and_border_radius_only():
    css = STYLES_CSS.read_text(encoding="utf-8")
    override = css.split("/* User interface radius preference: start */", 1)[1].split(
        "/* User interface radius preference: end */", 1
    )[0]

    for selector in (
        ".nav-item",
        ".top-nav",
        ".card",
        ".tool-card",
        ".settings-dashboard-card",
        ".modal",
        ".pbc-modal",
        ".user-modal",
        ".btn-primary",
        ".btn-outline",
        ".btn-confirm-primary",
        ".pbc-btn",
        ".setting-input",
        ".prompt-input",
        ".filter-select",
        ".custom-select-dropdown",
        ".custom-date-dropdown",
    ):
        assert selector in override

    for forbidden_selector in (
        ".login-card",
        ".user-initial-avatar",
        ".status-dot",
        ".report-nav-refresh-btn",
        ".tool-card-badge",
        ".progress-bar",
        ".progress-fill",
        ".checkbox",
        ".radio",
        ".range-track",
        ".range-thumb",
        "svg",
        "[class*=card]",
    ):
        assert forbidden_selector not in override

    declarations = re.findall(r"\{(?P<body>[^{}]+)\}", override, re.S)
    assert declarations
    for body in declarations:
        properties = {
            line.split(":", 1)[0].strip()
            for line in body.split(";")
            if ":" in line
        }
        assert properties == {"border-radius"}
```

另加根变量和普通用户三卡布局断言：

```python
assert "--ui-radius: 4px;" in css
assert '[data-role="user"] #page-settings .card-interface' in css
```

- [ ] **Step 2: 写代表性功能标记未被圆角代码接管的回归测试**

在现有 modal/custom input/nav 测试旁增加：

```python
def test_interface_radius_code_does_not_change_business_events_or_payloads():
    app_js = APP_JS.read_text(encoding="utf-8")
    radius_section = app_js[app_js.index("const DEFAULT_INTERFACE_RADIUS_PX"):]
    assert "addEventListener(\"click\"" in radius_section  # 仅保存/恢复按钮
    for business_path in (
        "/api/run/start",
        "/api/report-navigation/refresh",
        "/api/tools/pbc-import/start",
        "/api/tools/db-validation/start",
        "/api/tools/flow/start",
    ):
        assert business_path not in radius_section.split("// Interface radius end", 1)[0]
```

实现时给圆角 JS 逻辑添加 `// Interface radius start/end` 标记，让测试只检查该段；不要用“文件中恰好没出现”代替边界测试。

- [ ] **Step 3: 运行失败测试**

Run:

```powershell
python -m pytest -q tests/test_web_static.py -k "user_radius_override or interface_radius_code or regular_user_settings"
```

Expected: FAIL；根变量、覆盖层和普通用户三卡规则尚不存在。

- [ ] **Step 4: 增加界面设置卡片自身布局**

在 `styles.css` 的设置页样式附近增加 `.card-interface`、`.interface-radius-control`、`.interface-radius-value`、`.interface-settings-status` 的布局、颜色和间距。该布局可以设置 `display`、`gap` 等，但不得修改现有业务组件；滑块轨道/手柄保持组件自身形态，不读取 `--ui-radius`。

把普通用户规则从系统信息/关于系统两卡扩展为系统信息/界面设置/关于系统三卡：

```css
[data-role="user"] #page-settings .card-system-info,
[data-role="user"] #page-settings .card-interface,
[data-role="user"] #page-settings .card-about {
  display: block;
}
```

同步调整普通用户网格跨度和卡片高度规则，但不改变管理员 `admin-only` 权限选择器。

- [ ] **Step 5: 增加根变量和集中式明确选择器覆盖层**

在 `:root` 加入：

```css
--ui-radius: 4px;
```

在 `styles.css` 文件末尾按以下清单加入标记和明确选择器，覆盖层内唯一属性必须是 `border-radius`：

```css
/* User interface radius preference: start */
.nav-item,
.nav-group-toggle,
.nav-submenu,
[data-theme="space-tech"] .top-nav,
[data-theme="space-tech"] .top-nav-item,
[data-theme="space-tech"] .top-nav-group-toggle,
[data-theme="space-tech"] .top-nav-submenu,
[data-theme="space-tech"] .top-nav-subitem,
.card,
.home-stat-card,
.home-analysis-card,
#page-home .glass-card,
#page-home .glass-stat-card,
.tool-card,
.run-log-panel,
#page-report-navigation .report-nav-stat-card,
#page-report-navigation .report-nav-card,
#page-settings .settings-dashboard-card,
#page-users .user-stat-card,
#page-users .user-filter-bar,
#page-users .user-table-card,
.reconcile-settings-panel,
.db-validation-panel,
.flow-run-panel,
.flow-step-builder-panel,
#page-local-storage .local-storage-metric,
#page-local-storage .local-storage-table-panel,
#page-local-storage .local-storage-detail-panel,
.modal,
.pbc-modal,
.user-modal,
.btn-primary,
.btn-outline,
.btn-danger,
.btn-stop,
.btn-confirm-primary,
.btn-close,
.page-btn,
.trend-quick-btn,
.pbc-btn,
.user-menu-trigger,
.user-menu-panel,
.user-menu-logout,
.pbc-modal-close,
.filter-input,
.filter-select,
.chart-date-select,
.setting-input,
.prompt-input,
.user-form-control,
.main-content input:not([type="checkbox"]):not([type="radio"]):not([type="range"]):not([type="file"]):not([type="hidden"]),
.main-content select,
.main-content textarea,
.modal-field input:not([type="checkbox"]):not([type="radio"]):not([type="range"]),
.modal-field select,
.modal input:not([type="checkbox"]):not([type="radio"]):not([type="range"]):not([type="file"]):not([type="hidden"]),
.modal select,
.modal textarea,
.custom-input-shell,
.custom-select-shell,
.custom-select-trigger,
.custom-select-dropdown,
.custom-date-shell,
.custom-date-dropdown {
  border-radius: var(--ui-radius) !important;
}
/* User interface radius preference: end */
```

以上选择器清单是本功能的实现清单；实施时用 `rg` 核对类名没有被并行改动。若当前 DOM 类名已变化，只允许一对一替换为等价的明确选择器，不扩大为全局匹配。禁止使用全局 `button`、无 `.main-content`/`.modal` 作用域的全局 `input`、`[class*=card]` 或 `*`；禁止纳入 `.user-initial-avatar`、`.status-dot`、图表点、`.report-nav-refresh-btn`、badge/tag、progress、checkbox/radio/range、SVG 和遮罩层。

- [ ] **Step 6: 运行前端全量静态回归**

Run:

```powershell
python -m pytest -q tests/test_web_static.py
```

Expected: PASS；现有主题、暗色、导航、弹窗、日期框、自定义下拉框和普通用户权限断言全部不变。

- [ ] **Step 7: 检查 CSS 差异只影响显示**

Run:

```powershell
git diff -- src/auto_check/web/styles.css src/auto_check/web/app.js src/auto_check/web/index.html
```

Expected: 圆角覆盖层只有 `border-radius`；其他新增 CSS 只用于界面设置卡片布局；JS 仅调用偏好 API 和根 CSS 变量，不触碰业务 API 或业务 DOM 值。

- [ ] **Step 8: 提交样式覆盖**

```powershell
git add src/auto_check/web/styles.css tests/test_web_static.py
git commit -m "feat: apply one radius across interface surfaces"
```

## Task 6: README、部署说明和应用内更新日志

**Files:**

- Modify: `README.md`
- Modify: `docs/mysql-application-storage.zh-CN.md`
- Modify: `docs/deployment.zh-CN.md`
- Modify: `docs/intranet-production-deployment.zh-CN.md`
- Modify: `src/auto_check/web/app.js`
- Modify: `tests/test_deployment_assets.py`
- Modify: `tests/test_web_static.py`

- [ ] **Step 1: 先写文档和更新日志失败测试**

在 `tests/test_deployment_assets.py` 增加：

```python
def test_deployment_docs_require_interface_preferences_incremental_sql():
    paths = [
        ROOT / "README.md",
        ROOT / "docs" / "mysql-application-storage.zh-CN.md",
        ROOT / "docs" / "deployment.zh-CN.md",
        ROOT / "docs" / "intranet-production-deployment.zh-CN.md",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "004_user_interface_preferences.sql" in text
        assert "36 张" in text
```

在 `tests/test_web_static.py` 的 v2.1 更新日志测试中加入：

```python
assert "新增用户级界面圆角设置" in app_js
assert "系统优化及BUG修复" in app_js
```

- [ ] **Step 2: 运行失败测试**

Run:

```powershell
python -m pytest -q tests/test_deployment_assets.py tests/test_web_static.py -k "deployment_docs_require_interface or changelog"
```

Expected: FAIL；文档和更新日志尚未记录新功能。

- [ ] **Step 3: 更新 README 详细说明**

在 `README.md`：

- 应用存储执行顺序增加 `004_user_interface_preferences.sql`。
- 完整应用结构由 35 张改为 36 张，说明新增表无外键且由应用清理孤儿偏好。
- “系统设置”增加用户级 1–15px 全局圆角、默认 4px、预览/显式保存、跨设备同步和普通用户可见。
- “用户管理”把“普通用户仅保留关于系统和系统信息”更新为包含界面设置。
- v2.1 详细变更记录列出覆盖导航、卡片、弹窗、矩形按钮、输入/选择控件；明确仅影响显示，不改变功能。

不修改应用界面版本号和 favicon 版本参数。

- [ ] **Step 4: 更新 MySQL 与部署文档**

在三个部署文档中统一写明：

1. `001` 创建原 20 张表。
2. `002` 新增 15 张报送导航表。
3. `003` 写入报送导航种子。
4. `004` 新增 1 张用户界面偏好表。
5. 完整结构 36 张表，schema version 仍为 1。
6. 应用不会自动执行 DDL，升级必须先备份、执行 `004`，再部署新程序。

不要把用户提供的主机、用户名或密码写入文档。

- [ ] **Step 5: 更新应用内 v2.1 精简日志**

在 `src/auto_check/web/app.js` 的 v2.1 列表增加一条具体新增功能：

```html
<li>新增用户级界面圆角设置，支持统一预览、保存和跨设备同步。</li>
```

其他样式细节不展开，保留现有：

```html
<li>系统优化及BUG修复。</li>
```

- [ ] **Step 6: 运行文档和前端测试**

Run:

```powershell
python -m pytest -q tests/test_deployment_assets.py tests/test_web_static.py
```

Expected: PASS。

- [ ] **Step 7: 提交文档与日志**

```powershell
git add README.md docs/mysql-application-storage.zh-CN.md docs/deployment.zh-CN.md docs/intranet-production-deployment.zh-CN.md src/auto_check/web/app.js tests/test_deployment_assets.py tests/test_web_static.py
git commit -m "docs: document interface preference rollout"
```

## Task 7: 全量回归、构建和交付前审计

**Files:**

- Verify: all modified source, tests, SQL and docs
- Modify: `dist/auto-check.exe`

- [ ] **Step 1: 运行聚焦测试组**

Run:

```powershell
python -m pytest -q tests/test_user_interface_preferences.py tests/test_app_database.py tests/test_report_navigation_schema.py tests/test_sqlite_to_mysql_export.py tests/test_server.py tests/test_security.py tests/test_web_static.py tests/test_deployment_assets.py
```

Expected: PASS。

- [ ] **Step 2: 运行仓库全量测试**

Run:

```powershell
python -m pytest -q
```

Expected: 全部测试 PASS，无 error、failure 或 skip 数异常增长。记录最终通过数量和耗时作为交付证据。

- [ ] **Step 3: 运行显示-only 静态审计**

Run:

```powershell
rg -n "User interface radius preference|--ui-radius|interfaceRadius" src/auto_check/web/styles.css src/auto_check/web/app.js src/auto_check/web/index.html
rg -n "api/settings/interface|user_interface_preferences" src tests sql README.md docs
git diff --check
git status --short
```

Expected:

- 圆角覆盖层仅有 `border-radius`。
- 只有偏好 API 使用 `radius_px`，业务 API 请求参数未变化。
- 没有 `autoCheckRadius` 等 localStorage 权威来源。
- `git diff --check` 无真实 whitespace error。
- 工作区只包含本功能相关文件和打包产物。

- [ ] **Step 4: 确认打包产物未被进程占用**

Run:

```powershell
Get-Process auto-check -ErrorAction SilentlyContinue
```

Expected: 无输出。若有进程，停止并向用户说明后再打包；不得直接覆盖被占用文件。

- [ ] **Step 5: 刷新 Windows 可执行文件**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\package-windows.ps1
```

Expected: 打包成功，`dist\auto-check.exe` 更新时间刷新且脚本退出码为 0。

- [ ] **Step 6: 打包后再次跑关键测试和差异检查**

Run:

```powershell
python -m pytest -q tests/test_user_interface_preferences.py tests/test_server.py tests/test_security.py tests/test_web_static.py
git diff --check
Get-Item dist\auto-check.exe | Select-Object FullName, Length, LastWriteTime
```

Expected: PASS；exe 存在且非空。

- [ ] **Step 7: 提交打包产物**

仅当 `dist/auto-check.exe` 是当前仓库跟踪的交付物且确有变化时执行：

```powershell
git add dist/auto-check.exe
git commit -m "build: refresh Windows executable"
```

若仓库策略显示该文件未跟踪，则不强行添加，只报告本地打包路径。

- [ ] **Step 8: 进行提交范围复核**

Run:

```powershell
git log --oneline -7
git status --short
git diff HEAD~6 --stat
```

Expected: 提交按数据库、仓储、API、前端、样式、文档、构建聚焦拆分；没有无关文件或用户原有改动被覆盖。

## Task 8: 正式库升级与浏览器验收（需单独明确授权）

**Files:**

- Execute after approval: `sql/app_storage/mysql/004_user_interface_preferences.sql`
- Verify after deployment: running application and MySQL schema

- [ ] **Step 1: 停止并请求上线授权**

在此检查点停止自动执行，向用户提供：测试结果、exe 路径、`004` 内容摘要、风险和回滚说明。必须得到“可以执行正式库 004 并部署”的明确授权后才能继续。此前提供过连接信息不等同于本次写库授权。

- [ ] **Step 2: 备份并执行增量 SQL**

由获授权的运维流程使用安全凭据文件或交互式密码提示完成备份和 `004` 执行。不得把数据库密码放入命令历史、计划文档、提交或工具输出。执行后核验：

```sql
SHOW CREATE TABLE user_interface_preferences;
SELECT COUNT(*) AS table_count
FROM information_schema.tables
WHERE table_schema = DATABASE();
```

Expected: 表定义含主键、默认 4、1–15 CHECK、无外键；应用库表数为 36。

- [ ] **Step 3: 启动新程序并检查启动结构校验**

Expected: 应用启动成功，不再报告缺少 `user_interface_preferences`；认证、系统信息和原业务页面仍可加载。

- [ ] **Step 4: 三主题、三圆角浏览器验收**

对 1px、4px、15px 分别检查活力浅色、活力暗色、沉稳主题：

- 导航、内容卡片、弹窗外壳、矩形按钮、输入框/数字框/日期框/原生选择框、自定义下拉面板完全使用同一值。
- 头像、状态点、图表点、圆形刷新按钮、badge/tag、progress、checkbox/radio/range 和 SVG 形状保持原样。
- 拖动时即时预览且 Network 中没有 POST；保存按钮才 POST。
- 恢复默认预览 4px 但刷新前不落库；未保存离页恢复已保存值。
- 保存失败模拟时保留草稿，其他页面仍能使用。

- [ ] **Step 5: 双账号和跨浏览器同步验收**

账号 A 保存 1px，账号 B 保存 15px；分别刷新、退出登录、换浏览器验证：

- A 始终读取 1px，B 始终读取 15px。
- 一个账号保存不改变另一个账号。
- 同账号后一次成功保存覆盖前一次，符合 last-successful-write-wins。

- [ ] **Step 6: 业务无影响抽样**

在 1px 和 15px 下各完成一次：页面切换、主题切换、暗色切换、确认/输入/用户/导入弹窗开关、日期与下拉选择，并检查自动对数、报送导航刷新、历史查看、PBC 导入入口、逐笔校验入口、流程工具入口的请求路径和请求体与改动前一致。

Expected: 除圆角显示和界面设置卡片外，无业务行为、数据、权限、流程或接口参数变化。

## 最终验收清单

- [ ] 默认 4px，滑块范围 1–15px、步长 1，仅一个全局值。
- [ ] 管理员和普通用户都能看到界面设置卡片。
- [ ] 导航、卡片、弹窗、矩形按钮、输入/选择控件完全统一。
- [ ] 弹窗内部按钮、输入、数字、日期和下拉控件已覆盖。
- [ ] 拖动只预览；保存才写库；恢复默认仍需保存；未保存离页撤销。
- [ ] 当前用户服务端保存、跨设备同步、双账号隔离、最后成功保存生效。
- [ ] 启动 GET 发生在解除 `auth-pending` 前；失败回退 4px 且不阻塞应用。
- [ ] POST 严格拒绝 bool、float、空值、字符串和越界整数，CSRF 保持生效。
- [ ] 新表无外键；用户删除在同一事务清理孤儿偏好。
- [ ] 圆形、胶囊、进度、选择控件原生形状和图标内部形状不受影响。
- [ ] 圆角覆盖层只修改 `border-radius`，业务 API 和事件不变。
- [ ] MySQL 期望结构为 36 张表，schema version 仍为 1，`004` 必须人工先执行。
- [ ] README、应用内精简日志和部署文档同步更新。
- [ ] 全量 pytest、`git diff --check`、必要打包和授权后的浏览器验收全部通过。
