# System Notification Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建设 MySQL 持久化、SSE 实时推送的通用系统通知中心，并让报表特殊处理的新待确认事项成为首个通知来源。

**Architecture:** 先在平台层增加独立的 `notifications` 功能包、核心数据表、HTTP/SSE 接口和顶栏界面，再通过版本化 `platform.notification` 服务让业务模块发布通知。通知主体与用户收件状态持久化到 MySQL，进程内有界 SSE Hub 只承担实时分发，断线补偿以数据库查询为准。

**Tech Stack:** Python 3.12、SQLAlchemy Core、MySQL、`ThreadingHTTPServer`、原生 JavaScript/CSS、浏览器 `EventSource`、pytest。

## Global Constraints

- 开始实现前完整阅读 `AGENTS.md`、`docs/ai-modular-development-rules.zh-CN.md` 和 `docs/superpowers/specs/2026-08-25-system-notification-center-design.md`。
- 当前用户已明确不使用隔离工作区；在当前工作区实施，并保留所有已有、无关和未提交改动。
- 本功能是平台协议变更和业务模块接入的组合；先完成平台任务，再完成模块任务，差异与审查必须分层。
- 通知中心必须保持通用，不得在平台包中出现 `report_special_processing`、`pending` 或“待确认”等业务判断。
- 生产环境为无外网 Linux x86_64 单文件可执行程序，用户通过 `http://服务器IP:8765` 访问。
- 不引入 Redis、消息队列、外部推送服务或新的第三方依赖。
- 不实现浏览器或 Windows 桌面通知。
- 通知保留 30 天；历史待办不补发；打开通知面板不自动已读。
- 铃铛显示准确未读数：`1..99` 显示数字，超过 99 显示 `99+`，0 隐藏。
- 平台服务固定为 `platform.notification` version 1，来源模块由绑定门面注入。
- 所有修改类接口执行登录、CSRF、当前用户数据隔离和请求大小校验。
- 顶栏通知属于所有登录用户的基础能力，不新增角色能力码；未来人工发布入口另行设计权限。
- 前端保持亮色活力主题，使用现有圆角和主题变量；铃铛不用渐变，语义颜色不只靠颜色表达。
- 不修改展示用大版本号；更新日志并入当前版本。
- 不自动打包 Linux 或 Windows 可执行文件。
- 未经用户明确授权不提交、不推送、不创建 Pull Request；任务中的提交检查点只用于审查差异范围。

---

## File Structure

### 新增平台文件

| 文件 | 职责 |
|---|---|
| `src/auto_check/app/notifications/__init__.py` | 只导出稳定平台类型和工厂 |
| `src/auto_check/app/notifications/contracts.py` | 发布、展示、动作、分页契约与纯校验 |
| `src/auto_check/app/notifications/storage.py` | 通知主体、收件状态、列表、已读、清理 SQLAlchemy 仓储 |
| `src/auto_check/app/notifications/stream.py` | 有界、按用户隔离的进程内 SSE Hub |
| `src/auto_check/app/notifications/service.py` | 发布、幂等、查询、已读、清理和提交后分发 |
| `src/auto_check/app/notifications/platform.py` | `platform.notification` v1 可撤销模块门面 |
| `src/auto_check/app/notifications/http_api.py` | 核心通知 HTTP 参数解析与状态码映射，不直接写 Socket |
| `src/auto_check/web/notification_center.js` | 通知面板状态、API、SSE、降级轮询、弹窗和交互 |
| `src/auto_check/web/notification_center.css` | 仅通知中心的核心界面样式 |
| `sql/app_storage/mysql/018_system_notifications.sql` | 两张核心通知表的增量 SQL |

### 新增测试文件

| 文件 | 职责 |
|---|---|
| `tests/notifications/test_schema.py` | 核心通知表、索引和全局 schema 版本契约 |
| `tests/notifications/test_contracts.py` | 发布契约、动作、分页游标校验 |
| `tests/notifications/test_storage.py` | 仓储、用户隔离、已读、幂等与清理 |
| `tests/notifications/test_service.py` | 服务编排和提交后推送 |
| `tests/notifications/test_platform.py` | 模块门面来源绑定、版本和撤销 |
| `tests/notifications/test_stream.py` | SSE Hub 隔离、容量、溢出与关闭 |
| `tests/notifications/test_http.py` | 登录、CSRF、列表、已读及 SSE HTTP 集成 |
| `tests/notifications/test_frontend_static.py` | 前端结构、未读上限、生命周期和资源引用 |

### 修改文件

| 文件 | 修改目的 |
|---|---|
| `src/auto_check/app/app_database.py` | 将两张平台表加入预期 schema；保持 schema version 1 |
| `src/auto_check/app/server.py` | 创建通知服务、注册平台服务、委派通知 API/SSE、按序停止 |
| `src/auto_check/web/index.html` | 增加铃铛、面板、弹窗区域及独立资源引用 |
| `src/auto_check/web/app.js` | 登录后启动通知中心、注销前停止、复用受控业务导航、更新日志 |
| `tests/mysql_config_test_support.py` | 测试数据库模拟器识别通知表与仓储语句 |
| `tests/test_app_database.py` | 核心 schema 契约 |
| `tests/test_deployment_docs.py` | SQL 和部署文档契约 |
| `tests/test_server.py` / `tests/test_security.py` | 服务装配和现有鉴权回归，按现有夹具最小修改 |
| `tests/test_web_static.py` | 核心资源顺序与全局页面回归 |
| `src/auto_check/modules/report_special_processing/manifest.json` | 声明通知服务依赖并更新模块补丁版本与说明 |
| `src/auto_check/modules/report_special_processing/module.py` | 解析通知服务并注入业务服务 |
| `src/auto_check/modules/report_special_processing/service.py` | 在四类新待办提交成功后调用通用发布器 |
| `tests/modules/report_special_processing/test_service.py` | 待办触发矩阵与幂等键测试 |
| `tests/modules/report_special_processing/test_manifest_and_migrations.py` | 服务依赖和版本契约 |
| `README.md` | 详细说明系统通知能力、部署约束和使用行为 |
| `docs/deployment.zh-CN.md` | 增量 SQL、SSE、systemd 和内网说明 |
| `src/auto_check/modules/report_special_processing/README.md` | 说明模块产生待确认通知的条件 |

---

### Task 1: 建立通知核心表和 schema 契约

**Files:**
- Create: `sql/app_storage/mysql/018_system_notifications.sql`
- Create: `tests/notifications/test_schema.py`
- Modify: `src/auto_check/app/app_database.py`
- Modify: `tests/test_app_database.py`
- Modify: `tests/mysql_config_test_support.py`
- Modify: `tests/test_deployment_docs.py`

**Interfaces:**
- Produces: `system_notifications` 和 `system_notification_recipients` 两张核心表。
- Produces: `EXPECTED_APP_SCHEMA` 中对应字段集合。
- Preserves: `CURRENT_APP_SCHEMA_VERSION == 1`。

- [ ] **Step 1: 写 schema 失败测试**

在 `tests/notifications/test_schema.py` 固定以下关键契约：

```python
from pathlib import Path

from auto_check.app.app_database import CURRENT_APP_SCHEMA_VERSION, EXPECTED_APP_SCHEMA

ROOT = Path(__file__).resolve().parents[2]


def test_notification_tables_are_core_application_schema():
    assert CURRENT_APP_SCHEMA_VERSION == 1
    assert EXPECTED_APP_SCHEMA["system_notifications"] == frozenset({
        "id", "source_module", "event_type", "category", "level", "title",
        "content", "action_json", "dedupe_key", "dedupe_hash", "created_at",
        "expires_at",
    })
    assert EXPECTED_APP_SCHEMA["system_notification_recipients"] == frozenset({
        "notification_id", "user_id", "received_at", "read_at",
    })


def test_notification_migration_has_required_keys_and_does_not_bump_global_version():
    sql = (ROOT / "sql/app_storage/mysql/018_system_notifications.sql").read_text("utf-8")
    assert "CREATE TABLE IF NOT EXISTS `system_notifications`" in sql
    assert "UNIQUE KEY `uk_system_notifications_source_event`" in sql
    assert "KEY `ix_system_notifications_expires`" in sql
    assert "CREATE TABLE IF NOT EXISTS `system_notification_recipients`" in sql
    assert "PRIMARY KEY (`notification_id`, `user_id`)" in sql
    assert "ON DELETE CASCADE" in sql
    assert "INSERT INTO `app_schema_version`" not in sql
    assert "UPDATE `app_schema_version`" not in sql
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m pytest tests/notifications/test_schema.py tests/test_app_database.py -q
```

Expected: FAIL，提示迁移文件或通知表 schema 不存在。

- [ ] **Step 3: 编写精确增量 SQL**

`018_system_notifications.sql` 使用以下结构：

```sql
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `auto_check`;

CREATE TABLE IF NOT EXISTS `system_notifications` (
  `id` CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `source_module` VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `event_type` VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `category` VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `level` VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `title` VARCHAR(191) NOT NULL,
  `content` TEXT NOT NULL,
  `action_json` JSON NULL,
  `dedupe_key` VARCHAR(191) NOT NULL,
  `dedupe_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `created_at` DATETIME(6) NOT NULL,
  `expires_at` DATETIME(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_system_notifications_source_event`
    (`source_module`, `event_type`, `dedupe_hash`),
  KEY `ix_system_notifications_expires` (`expires_at`, `id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='通用系统通知主体';

CREATE TABLE IF NOT EXISTS `system_notification_recipients` (
  `notification_id` CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `user_id` VARCHAR(64) NOT NULL,
  `received_at` DATETIME(6) NOT NULL,
  `read_at` DATETIME(6) NULL,
  PRIMARY KEY (`notification_id`, `user_id`),
  KEY `ix_system_notification_recipients_user_list`
    (`user_id`, `received_at`, `notification_id`),
  KEY `ix_system_notification_recipients_user_unread`
    (`user_id`, `read_at`, `received_at`),
  CONSTRAINT `fk_system_notification_recipients_notification`
    FOREIGN KEY (`notification_id`) REFERENCES `system_notifications` (`id`)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='系统通知用户收件与已读状态';
```

- [ ] **Step 4: 同步 schema 与 MySQL 测试桩**

在 `EXPECTED_APP_SCHEMA` 中加入精确字段集合；不要修改 `CURRENT_APP_SCHEMA_VERSION`。扩展 `tests/mysql_config_test_support.py` 的表名、字段和主键模拟，使后续仓储测试能够执行插入、联查、更新和删除。

- [ ] **Step 5: 运行 schema 测试**

Run:

```powershell
python -m pytest tests/notifications/test_schema.py tests/test_app_database.py tests/test_deployment_docs.py -q
```

Expected: PASS。

- [ ] **Step 6: 检查本任务差异**

Run:

```powershell
git diff --check -- sql/app_storage/mysql/018_system_notifications.sql src/auto_check/app/app_database.py tests/notifications/test_schema.py tests/test_app_database.py tests/mysql_config_test_support.py tests/test_deployment_docs.py
```

Expected: 无真实 whitespace error。未经明确授权不提交。

---

### Task 2: 实现通知契约和仓储

**Files:**
- Create: `src/auto_check/app/notifications/__init__.py`
- Create: `src/auto_check/app/notifications/contracts.py`
- Create: `src/auto_check/app/notifications/storage.py`
- Create: `tests/notifications/test_contracts.py`
- Create: `tests/notifications/test_storage.py`

**Interfaces:**
- Produces: `NotificationAction`、`NotificationPublishRequest`、`NotificationPublishResult`、`NotificationItem`、`NotificationStreamPublisher`。
- Produces: `NotificationStorage.create_or_get()`、`list_for_user()`、`unread_count()`、`mark_read()`、`mark_all_read()`、`delete_expired_batch()`。
- Consumes: Task 1 的两张表。

- [ ] **Step 1: 写契约和仓储失败测试**

测试至少覆盖：

```python
def test_publish_request_normalizes_recipients_and_internal_action():
    request = validate_publish_request(NotificationPublishRequest(
        event_type="pending_confirmation_created",
        dedupe_key="rsp-pending:12:3:u1",
        recipient_user_ids=("u1", "u1", " u2 "),
        category="todo",
        level="info",
        title=" 报表特殊处理待确认 ",
        content="项目端 · 字段名",
        action=NotificationAction("navigate", "report-special-processing", {"record_id": "12"}),
    ))
    assert request.recipient_user_ids == ("u1", "u2")
    assert request.title == "报表特殊处理待确认"


def test_storage_isolates_unread_state_by_user(notification_storage):
    created = notification_storage.create_or_get(
        source_module="alpha",
        request=sample_request(recipients=("u1", "u2")),
        now=aware_beijing_datetime(),
    )
    notification_storage.mark_read("u1", created.notification_id, aware_beijing_datetime())
    assert notification_storage.unread_count("u1", aware_beijing_datetime()) == 0
    assert notification_storage.unread_count("u2", aware_beijing_datetime()) == 1


def test_storage_returns_existing_notification_for_same_dedupe_key(notification_storage):
    first = notification_storage.create_or_get("alpha", sample_request(), aware_beijing_datetime())
    second = notification_storage.create_or_get("alpha", sample_request(), aware_beijing_datetime())
    assert second.notification_id == first.notification_id
    assert second.created is False
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m pytest tests/notifications/test_contracts.py tests/notifications/test_storage.py -q
```

Expected: FAIL，通知类型和仓储尚不存在。

- [ ] **Step 3: 实现不可变契约和校验**

在 `contracts.py` 使用冻结 dataclass，并实现这些精确入口：`validate_publish_request(value: NotificationPublishRequest) -> NotificationPublishRequest`、`validate_source_module(value: str) -> str`、`encode_cursor(received_at: datetime, notification_id: str) -> str`、`decode_cursor(value: str) -> tuple[datetime, str]`、`action_to_json(value: NotificationAction | None) -> dict[str, object] | None`、`action_from_json(value: object) -> NotificationAction | None`。

同时定义服务可依赖的小接口：

```python
@dataclass(frozen=True)
class NotificationStreamEvent:
    type: Literal["notification", "resync", "close"]
    notification: NotificationItem | None
    unread_count: int | None


class NotificationStreamPublisher(Protocol):
    def publish(self, user_id: str, event: NotificationStreamEvent) -> None:
        """将已提交的通知事件发送给当前进程内目标用户订阅。"""
```

游标内容为紧凑 JSON 的 URL-safe base64，解码时严格检查时区时间和 32 位十六进制通知 ID；任何错误映射为统一 `NotificationValidationError`。

- [ ] **Step 4: 实现参数化仓储**

`storage.py` 使用 SQLAlchemy Core Table 声明现有表，不执行运行时建表。`create_or_get()` 必须在一个 `application_database.transaction()` 中插入通知主体与所有收件人；唯一键冲突后查询并返回已有 ID，不再次插入或分发。

仓储公开签名固定为：

- `create_or_get(source_module: str, request: NotificationPublishRequest, now: datetime) -> NotificationPublishResult`
- `get_for_user(user_id: str, notification_id: str, now: datetime) -> NotificationItem | None`
- `list_for_user(user_id: str, *, unread_only: bool, limit: int, cursor: tuple[datetime, str] | None, now: datetime) -> NotificationPage`
- `unread_count(user_id: str, now: datetime) -> int`
- `mark_read(user_id: str, notification_id: str, read_at: datetime) -> NotificationItem | None`
- `mark_all_read(user_id: str, read_at: datetime) -> int`
- `delete_expired_batch(now: datetime, limit: int = 1000) -> int`

列表条件必须同时包含：

```python
RECIPIENTS.c.user_id == user_id
NOTIFICATIONS.c.expires_at > now
```

游标条件：

```python
or_(
    RECIPIENTS.c.received_at < cursor_time,
    and_(
        RECIPIENTS.c.received_at == cursor_time,
        RECIPIENTS.c.notification_id < cursor_id,
    ),
)
```

列表先取 `limit + 1` 行以判断 `next_cursor`。`mark_read()` 和 `mark_all_read()` 只更新当前 `user_id`；`delete_expired_batch()` 先查询最多 1,000 个 ID，再在同一事务删除。

- [ ] **Step 5: 运行契约和仓储测试**

Run:

```powershell
python -m pytest tests/notifications/test_contracts.py tests/notifications/test_storage.py -q
```

Expected: PASS。

---

### Task 3: 实现通知服务和 `platform.notification` v1

**Files:**
- Create: `src/auto_check/app/notifications/service.py`
- Create: `src/auto_check/app/notifications/platform.py`
- Create: `tests/notifications/test_service.py`
- Create: `tests/notifications/test_platform.py`
- Modify: `src/auto_check/app/notifications/__init__.py`

**Interfaces:**
- Consumes: `NotificationStorage`。
- Consumes: Task 2 的 `NotificationStreamPublisher` 小接口，服务测试使用记录调用的 fake，不依赖具体 Hub。
- Produces: `NotificationService.publish(source_module, request)`。
- Produces: `create_notification_platform_service(service) -> PlatformServiceSpec`。
- Produces: 模块门面 `publish(request) -> NotificationPublishResult`，来源自动绑定。

- [ ] **Step 1: 写服务和门面失败测试**

核心断言：

```python
def test_platform_facade_injects_bound_module_owner(notification_service):
    spec = create_notification_platform_service(notification_service)
    bound = spec.binder("report_special_processing")
    bound.value.publish(sample_request())
    assert notification_service.published_sources == ["report_special_processing"]


def test_duplicate_publish_does_not_emit_second_live_event(service, hub):
    first = service.publish("alpha", sample_request())
    second = service.publish("alpha", sample_request())
    assert first.created is True
    assert second.created is False
    assert hub.publish_count == 1


def test_closed_platform_facade_rejects_publish(notification_service):
    bound = create_notification_platform_service(notification_service).binder("alpha")
    bound.close()
    with pytest.raises(RuntimeError, match="closed"):
        bound.value.publish(sample_request())
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m pytest tests/notifications/test_service.py tests/notifications/test_platform.py -q
```

Expected: FAIL，服务和平台工厂尚不存在。

- [ ] **Step 3: 实现服务编排**

服务构造签名固定为 `NotificationService(storage: NotificationStorage, user_directory: Callable[[str], object | None], stream_publisher: NotificationStreamPublisher, *, now: Callable[[], datetime])`；发布入口固定为 `publish(source_module: str, request: NotificationPublishRequest) -> NotificationPublishResult`。

`publish()` 顺序固定为：校验来源和请求、确认接收人为启用用户、仓储事务提交、若 `created=true` 再计算每位接收人的准确未读数并发布实时事件。任何 SSE 分发错误只记录并隔离，不能把已经持久化的通知改为失败。

服务同时提供 `start_cleanup()` 和 `stop()`：前者只允许启动一个可中断的清理线程，后者设置停止事件并在有限时间内等待线程退出；重复调用必须幂等。

- [ ] **Step 4: 实现可撤销平台门面**

`platform.py` 定义常量 `NOTIFICATION_SERVICE = "platform.notification"`、`NOTIFICATION_SERVICE_VERSION = 1`，并提供 `create_notification_platform_service(service: NotificationService) -> PlatformServiceSpec`。

门面仅暴露 `publish()`，不暴露仓储、查询、SSE Hub、用户目录或数据库连接。门面锁定绑定 owner，并在 `close()` 后拒绝调用。

- [ ] **Step 5: 运行服务测试**

Run:

```powershell
python -m pytest tests/notifications/test_service.py tests/notifications/test_platform.py tests/module_system/test_collaboration.py tests/test_platform_services.py -q
```

Expected: PASS。

---

### Task 4: 实现有界 SSE Hub

**Files:**
- Create: `src/auto_check/app/notifications/stream.py`
- Create: `tests/notifications/test_stream.py`

**Interfaces:**
- Produces: `NotificationStreamHub.subscribe(user_id) -> NotificationSubscription`。
- Produces: `NotificationStreamHub.publish(user_id, event)`。
- Produces: `NotificationSubscription.next(timeout_seconds)`、`close()`。
- Enforces: 每用户 5、全局 200、队列容量 100。

- [ ] **Step 1: 写隔离、限制和溢出失败测试**

```python
def test_hub_delivers_only_to_target_user():
    hub = NotificationStreamHub(max_per_user=5, max_total=200, queue_size=100)
    u1 = hub.subscribe("u1")
    u2 = hub.subscribe("u2")
    hub.publish("u1", sample_event("n1"))
    assert u1.next(0.01).notification.id == "n1"
    assert u2.next(0.01) is None


def test_queue_overflow_requires_resync_without_unbounded_growth():
    hub = NotificationStreamHub(max_per_user=5, max_total=200, queue_size=1)
    subscription = hub.subscribe("u1")
    hub.publish("u1", sample_event("n1"))
    hub.publish("u1", sample_event("n2"))
    assert subscription.next(0.01).type == "resync"


def test_hub_enforces_per_user_and_global_limits():
    hub = NotificationStreamHub(max_per_user=1, max_total=1, queue_size=100)
    hub.subscribe("u1")
    with pytest.raises(NotificationStreamLimitError):
        hub.subscribe("u1")
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m pytest tests/notifications/test_stream.py -q
```

Expected: FAIL。

- [ ] **Step 3: 实现线程安全 Hub**

使用 `RLock`、按用户订阅集合和 `queue.Queue(maxsize=100)`。订阅关闭必须幂等；Hub 关闭时向所有订阅发关闭哨兵并拒绝新订阅。队列满时清空该订阅当前积压并只放一个 `resync` 事件，不能阻塞业务发布线程。

- [ ] **Step 4: 运行 Hub 测试和线程泄漏检查**

Run:

```powershell
python -m pytest tests/notifications/test_stream.py -q
```

Expected: PASS，测试退出后没有未关闭订阅。

---

### Task 5: 增加通知 HTTP API、SSE 端点和服务生命周期

**Files:**
- Create: `src/auto_check/app/notifications/http_api.py`
- Create: `tests/notifications/test_http.py`
- Modify: `src/auto_check/app/server.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_security.py`

**Interfaces:**
- Consumes: `NotificationService` 和 `NotificationStreamHub`。
- Produces: `GET /api/notifications`。
- Produces: `POST /api/notifications/{id}/read`。
- Produces: `POST /api/notifications/read-all`。
- Produces: `GET /api/notifications/stream`。

- [ ] **Step 1: 写 HTTP 登录、隔离、CSRF 和 SSE 失败测试**

测试必须按现有 `_json_request` 和真实 HTTP Server 夹具实现以下精确断言：

- `test_notification_list_requires_login`：无会话 GET 返回 401 和 `login required`。
- `test_notification_list_returns_only_current_user`：为 u1/u2 分别造数，u1 响应只含 u1 项。
- `test_mark_read_requires_csrf`：缺少或错误 CSRF 的 POST 返回 403。
- `test_marking_another_users_notification_returns_404`：u1 标记 u2 项返回 404。
- `test_read_all_updates_only_current_user`：u1 全部已读后 u1 为 0、u2 数量不变。
- `test_sse_requires_login_and_has_stream_headers`：无会话返回 401；有会话返回 `text/event-stream`、`no-cache`、`X-Accel-Buffering: no`。
- `test_sse_emits_notification_for_target_user`：u1 流读取到目标事件，u2 流在同一时间窗只收到心跳。
- `test_sse_limit_returns_429`：达到用户或全局限制后新连接返回 429。

- [ ] **Step 2: 运行 HTTP 测试确认失败**

Run:

```powershell
python -m pytest tests/notifications/test_http.py -q
```

Expected: FAIL，接口返回 404 或属性不存在。

- [ ] **Step 3: 实现纯 HTTP 参数控制器**

`NotificationHttpApi` 只解析 `filter`、`limit`、`cursor`、通知 ID并调用服务。错误映射固定为：

- 参数无效：400，例如 `{"error":"invalid notification request","error_id":"NOTIF-A1B2C3"}`
- 不存在或不属于当前用户：404，`{"error":"notification not found"}`
- 未登录：由核心 Handler 返回 401。
- CSRF 失败：由核心 Handler 返回 403。
- 未知异常：500，脱敏错误和可追踪编号。

动作路由只接受 `[a-z][a-z0-9-]{0,63}`；HTTP、HTTPS、`//`、`/api/` 和未知动作类型在发布校验阶段拒绝。路由是否存在由点击时的现有核心页面/模块宿主解析，解析失败只显示错误，不进行外部跳转。

- [ ] **Step 4: 在 Handler 中做最小路由委派**

在 `_handle_api()` 完成会话和 CSRF 校验后、模块路由前加入：

```python
if path == "/api/notifications" or path.startswith("/api/notifications/"):
    self._handle_notifications(method, path, session)
    return
```

`_handle_notifications()` 将普通接口交给 `NotificationHttpApi`。SSE 分支直接写响应头并循环：

```python
while self._authenticated_session() is not None:
    event = subscription.next(timeout_seconds=20.0)
    payload = format_sse_event(event) if event else b": ping\n\n"
    if not self._write_response_body(payload):
        break
    self.wfile.flush()
```

必须在 `finally` 调用 `subscription.close()`。SSE 响应不发送 `Content-Length`，设置 `close_connection=False`，并捕获已存在的客户端断开错误类型。

- [ ] **Step 5: 装配服务与关闭顺序**

在 `run_server()`：

1. 数据库验证成功后创建 `NotificationStorage`、`NotificationStreamHub`、`NotificationService`。
2. 启动通知清理线程。
3. 在 `platform_services` 中追加 `create_notification_platform_service(notification_service)`。
4. 赋值 `Handler.notification_http_api`、`Handler.notification_stream_hub`。
5. `finally` 中先停止通知服务和关闭 Hub，再关闭 Server 和应用数据库。

清理线程启动后立即清理一次，之后每 6 小时执行 `delete_expired_batch(limit=1000)` 直到不足一批；使用 `threading.Event.wait(21600)`，不得使用不可中断 `sleep()`。

- [ ] **Step 6: 运行 HTTP、服务装配和安全测试**

Run:

```powershell
python -m pytest tests/notifications/test_http.py tests/notifications/test_service.py tests/test_server.py tests/test_security.py -q
```

Expected: PASS。

---

### Task 6: 实现顶栏通知中心前端

**Files:**
- Create: `src/auto_check/web/notification_center.js`
- Create: `src/auto_check/web/notification_center.css`
- Create: `tests/notifications/test_frontend_static.py`
- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/app.js`
- Modify: `tests/test_web_static.py`

**Interfaces:**
- Produces: `window.AutoCheckNotificationCenter.start(options)` 和 `.stop()`。
- Consumes: `api`、`authState`、`handleReportNavTodoAction`、`showToast` 回调。
- Consumes: Task 5 的 API 和 SSE。

- [ ] **Step 1: 写前端静态失败测试**

测试精确检查：

```python
def test_notification_resources_and_topbar_mount_are_present():
    assert '<link rel="stylesheet" href="/notification_center.css"' in INDEX_HTML
    assert '<script src="/notification_center.js"' in INDEX_HTML
    assert 'data-notification-bell' in INDEX_HTML
    assert 'data-notification-badge' in INDEX_HTML
    assert 'data-notification-panel' in INDEX_HTML
    assert 'data-notification-toast-region' in INDEX_HTML


def test_badge_caps_visual_value_at_99_plus():
    assert 'count > 99 ? "99+" : String(count)' in NOTIFICATION_JS


def test_opening_panel_does_not_call_mark_read():
    open_panel = extract_function(NOTIFICATION_JS, "openPanel")
    assert "/read" not in open_panel


def test_notification_center_stops_event_source_and_polling():
    stop = extract_function(NOTIFICATION_JS, "stop")
    assert ".close()" in stop
    assert "clearInterval" in stop
```

- [ ] **Step 2: 运行前端测试确认失败**

Run:

```powershell
python -m pytest tests/notifications/test_frontend_static.py tests/test_web_static.py -q
```

Expected: FAIL，资源和挂载点不存在。

- [ ] **Step 3: 增加语义化顶栏结构**

在 `.top-nav-actions`、顶部用户菜单之前插入：

```html
<div class="notification-center" data-notification-center>
  <button class="notification-bell" type="button" data-notification-bell
          aria-label="通知" aria-haspopup="true" aria-expanded="false">
    <span class="notification-bell-icon" aria-hidden="true"></span>
    <span class="notification-badge" data-notification-badge hidden></span>
  </button>
  <section class="notification-panel" data-notification-panel hidden
           aria-label="系统通知">
    <header class="notification-panel-header">
      <h2>通知 <span data-notification-unread-text></span></h2>
      <button type="button" data-notification-read-all>全部已读</button>
    </header>
    <div class="notification-filters" role="tablist" aria-label="通知筛选">
      <button type="button" role="tab" data-notification-filter="all" aria-selected="true">全部</button>
      <button type="button" role="tab" data-notification-filter="unread" aria-selected="false">未读</button>
    </div>
    <div class="notification-list" data-notification-list></div>
    <p class="notification-empty" data-notification-empty hidden>暂无通知</p>
    <button type="button" class="notification-load-more" data-notification-load-more hidden>加载更多</button>
    <p class="notification-error" data-notification-error hidden>
      通知加载失败
      <button type="button" data-notification-retry>重新加载</button>
    </p>
  </section>
</div>
<div class="notification-toast-region" data-notification-toast-region
     aria-live="polite" aria-atomic="false"></div>
```

实际提交沿用上述完整节点，并为铃铛图标提供现有图标体系一致的可见实现。

- [ ] **Step 4: 实现独立通知中心状态机**

`notification_center.js` 使用 IIFE，内部状态至少包含：

```javascript
const state = {
  started: false,
  userId: "",
  csrfToken: "",
  filter: "all",
  items: [],
  unreadCount: 0,
  nextCursor: null,
  loading: false,
  eventSource: null,
  reconnectFailures: 0,
  pollTimer: null,
  liveToastIds: new Set(),
  visibleToasts: [],
};
```

公开入口：

```javascript
window.AutoCheckNotificationCenter = Object.freeze({
  start: async ({ user, csrfToken, api, handleAction, notify }) => { /* 完整初始化 */ },
  stop: () => { /* 关闭 EventSource、轮询、监听器和临时弹窗 */ },
});
```

所有标题、正文和属性使用 `textContent` 或统一转义，禁止把服务端内容直接拼进 `innerHTML`。

- [ ] **Step 5: 实现列表、已读和数量规则**

`renderBadge(count)` 必须：

```javascript
const normalized = Math.max(0, Number(count) || 0);
badge.hidden = normalized === 0;
badge.textContent = normalized > 99 ? "99+" : String(normalized);
bell.setAttribute("aria-label", normalized ? `通知，${normalized}条未读` : "通知，无未读");
```

点击通知调用单条已读接口后用响应中的准确 `unread_count` 覆盖本地值。失败时保留未读显示、调用 `notify("通知状态更新失败", "error")`，随后仍允许执行受控查看动作。“全部已读”成功后把当前所有缓存项设为已读并使用服务端返回数量。

- [ ] **Step 6: 实现 SSE、重连同步和降级轮询**

`EventSource("/api/notifications/stream")` 收到 `notification` 时：

1. 校验 JSON 形状。
2. 用服务端 `unread_count` 更新角标。
3. 若当前列表没有该 ID，则插到顶部。
4. 仅当前连接实时事件调用 `showLiveToast()`。

`open` 事件触发静默 `reloadFirstPage()` 并停止 60 秒轮询；连续错误达到 3 次后启动轮询。列表初始化和重连同步不得调用 `showLiveToast()`。

- [ ] **Step 7: 实现弹窗上限和清理**

每条实时弹窗 6 秒自动关闭，最多保留 3 条。第四条及以后只更新角标和列表。关闭按钮只移除弹窗；“查看”执行已读和动作。定时器句柄随弹窗保存，`stop()` 清除全部句柄。

- [ ] **Step 8: 接入应用登录和注销生命周期**

在初始加载中，模块宿主初始化完成后调用：

```javascript
await window.AutoCheckNotificationCenter.start({
  user: Object.assign({}, authState.user),
  csrfToken: authState.csrfToken,
  api,
  handleAction: handleReportNavTodoAction,
  notify: showToast,
});
```

`logout()` 发请求前调用 `window.AutoCheckNotificationCenter.stop()`；若退出失败则重新启动，避免用户仍停留页面却没有通知连接。页面 `beforeunload` 时也调用 `stop()`。

- [ ] **Step 9: 完成独立作用域样式**

所有选择器以 `.notification-center` 或 `.notification-toast-region` 为根，不定义通用 `button`、`.panel`、`.item`。使用 `--ui-radius`、主题蓝和现有语义色；通知面板宽 400px、最大高 520px，小屏幕使用 `min(400px, calc(100vw - 24px))`。未读同时包含浅蓝背景、圆点和可读文字。

- [ ] **Step 10: 运行前端验证**

Run:

```powershell
python -m pytest tests/notifications/test_frontend_static.py tests/test_web_static.py -q
node --check src/auto_check/web/notification_center.js
node --check src/auto_check/web/app.js
```

Expected: 全部 PASS，两个 JS 文件语法检查无输出。

---

### Task 7: 接入报表特殊处理的新待确认事件

**Files:**
- Modify: `src/auto_check/modules/report_special_processing/manifest.json`
- Modify: `src/auto_check/modules/report_special_processing/module.py`
- Modify: `src/auto_check/modules/report_special_processing/service.py`
- Modify: `tests/modules/report_special_processing/test_service.py`
- Modify: `tests/modules/report_special_processing/test_manifest_and_migrations.py`

**Interfaces:**
- Consumes: `platform.notification` version 1。
- Produces: `SpecialProcessingService` 在四类新待确认关系提交后发布通用通知。
- Preserves: `PendingConfirmTodoProvider` 继续只负责查询，不创建通知。

- [ ] **Step 1: 写待办触发矩阵失败测试**

为服务注入记录调用的 `FakeNotificationPublisher`，测试：

```python
@pytest.mark.parametrize("operation", [
    "create_formal",
    "submit_draft",
    "reopen_completed",
    "reassign_pending",
])
def test_new_pending_relationship_publishes_one_notification(operation, service_factory):
    publisher = FakeNotificationPublisher()
    service = service_factory(notification_publisher=publisher)
    changed = run_operation(service, operation)
    assert len(publisher.requests) == 1
    request = publisher.requests[0]
    assert request.recipient_user_ids == (changed["governance_owner_user_id"],)
    assert request.category == "todo"
    assert request.level == "info"
    assert request.title == "报表特殊处理待确认"
    assert request.dedupe_key == (
        f"rsp-pending:{changed['id']}:{changed['row_version']}:"
        f"{changed['governance_owner_user_id']}"
    )


@pytest.mark.parametrize("operation", [
    "save_draft",
    "edit_pending_without_reassignment",
    "complete",
    "void",
    "delete",
    "list_todos",
])
def test_non_creation_operations_do_not_publish(operation, service_factory):
    publisher = FakeNotificationPublisher()
    service = service_factory(notification_publisher=publisher)
    run_operation(service, operation)
    assert publisher.requests == []
```

- [ ] **Step 2: 运行模块测试确认失败**

Run:

```powershell
python -m pytest tests/modules/report_special_processing/test_service.py tests/modules/report_special_processing/test_manifest_and_migrations.py -q
```

Expected: FAIL，业务服务尚无通知发布器。

- [ ] **Step 3: 声明服务依赖并注入**

将清单中的 `service_dependencies` 扩展为：

```json
[
  {"name": "platform.user_directory", "minimum_version": 1},
  {"name": "platform.report_navigation", "minimum_version": 1},
  {"name": "platform.notification", "minimum_version": 1}
]
```

模块版本从当前 `1.2.7` 升为 `1.2.8`，模块说明增加“待确认事项接入系统通知”。`module.py` 在 `start()` 中解析服务并以构造参数 `notification_publisher` 注入 `SpecialProcessingService`。

- [ ] **Step 4: 集中实现一个发布辅助方法**

在 `SpecialProcessingService` 增加私有方法，所有触发点复用：

```python
def _publish_pending_notification(self, record: Mapping[str, Any]) -> None:
    owner_id = str(record.get("governance_owner_user_id") or "").strip()
    if not owner_id:
        return
    dimension = str(record.get("dimension") or "").strip()
    dimension_label = DIMENSION_LABELS.get(dimension, dimension or "未分维度")
    field_name = str(record.get("field_name") or "").strip() or "未填字段"
    record_id = int(record["id"])
    row_version = int(record["row_version"])
    self._notifications.publish(NotificationPublishRequest(
        event_type="pending_confirmation_created",
        dedupe_key=f"rsp-pending:{record_id}:{row_version}:{owner_id}",
        recipient_user_ids=(owner_id,),
        category="todo",
        level="info",
        title="报表特殊处理待确认",
        content=f"{dimension_label} · {field_name}",
        action=NotificationAction(
            type="navigate",
            route="report-special-processing",
            query={"record_id": str(record_id), "highlight": "1", "open": "confirm"},
        ),
    ))
```

若发布失败，捕获异常并使用模块日志器记录来源、记录 ID、`row_version`、接收人和 `request_id`，不记录完整正文，不改变已经成功的业务响应。

- [ ] **Step 5: 在精确触发点调用**

仅在仓储方法返回已提交的新记录后调用：

- `create()`：`status == pending`。
- `update()`：旧状态 `draft` 且新状态 `pending`，或旧状态 `pending` 且治理负责人发生变化。
- `reopen()`：成功返回的新状态为 `pending`。

不得在 `PendingConfirmTodoProvider.list_todos()`、查询、统计刷新、完成、作废和删除中调用。

- [ ] **Step 6: 运行模块测试**

Run:

```powershell
python -m pytest tests/modules/report_special_processing/test_service.py tests/modules/report_special_processing/test_manifest_and_migrations.py tests/modules/report_special_processing/test_todos.py -q
```

Expected: PASS。

---

### Task 8: 完成清理、重连和边界集成验收

**Files:**
- Modify: `tests/notifications/test_service.py`
- Modify: `tests/notifications/test_http.py`
- Modify: `tests/notifications/test_frontend_static.py`
- Modify: `tests/modules/report_special_processing/test_service.py`

**Interfaces:**
- Verifies: 30 天保留、断线补偿、重复抑制、关闭顺序和历史待办不补发。

- [ ] **Step 1: 补齐跨层失败测试**

增加以下具名验收用例和精确断言：

- `test_notification_is_visible_until_exact_expiry_boundary`：`now < expires_at` 可见，`now == expires_at` 不可见。
- `test_cleanup_deletes_at_most_one_thousand_per_batch`：造 1,005 条过期数据，首批返回 1,000，第二批返回 5。
- `test_service_startup_cleanup_does_not_create_notifications`：启动清理前后主体数量只减少、不增加。
- `test_reconnect_uses_database_list_without_replaying_live_event`：重连触发列表 GET，但不调用实时弹窗函数。
- `test_business_success_is_preserved_when_notification_publish_fails`：仓储业务记录已提交，业务响应仍成功，日志含记录 ID 和请求号。
- `test_same_record_version_and_recipient_is_idempotent`：两次发布只存在一个主体和一个收件行。
- `test_existing_pending_records_are_not_published_on_module_start`：模块启动只注册 Provider，不调用通知发布器。

- [ ] **Step 2: 运行用例并修正真实缺口**

Run:

```powershell
python -m pytest tests/notifications tests/modules/report_special_processing -q
```

Expected: 首次运行可能暴露边界失败；只修改对应职责文件，不把修复移入公共大文件。

- [ ] **Step 3: 再次运行通知和模块全集**

Run:

```powershell
python -m pytest tests/notifications tests/modules/report_special_processing -q
```

Expected: PASS。

---

### Task 9: 同步用户、部署和更新日志文档

**Files:**
- Modify: `README.md`
- Modify: `docs/deployment.zh-CN.md`
- Modify: `src/auto_check/modules/report_special_processing/README.md`
- Modify: `src/auto_check/web/app.js`
- Modify: `tests/test_deployment_docs.py`
- Modify: `tests/test_web_static.py`

**Interfaces:**
- Documents: 用户行为、30 天保留、SSE、无外网、HTTP、增量 SQL、回滚。
- Preserves: 展示大版本 `V1.2`，不自行跨大版本。

- [ ] **Step 1: 写文档契约失败测试**

`tests/test_deployment_docs.py` 至少检查：

```python
def test_deployment_docs_explain_intranet_sse_notifications():
    assert "018_system_notifications.sql" in DEPLOYMENT_DOC
    assert "SSE" in DEPLOYMENT_DOC
    assert "http://服务器IP:8765" in DEPLOYMENT_DOC
    assert "不依赖外网" in DEPLOYMENT_DOC
    assert "30 天" in DEPLOYMENT_DOC
```

应用内更新日志测试检查最新版本存在一条具体新功能说明，且同一版本“系统优化及BUG修复”最多一条。

- [ ] **Step 2: 更新详细文档**

`README.md` 说明：铃铛准确未读数量、全部/未读列表、单条/全部已读、右上角一次弹窗、30 天保留、SSE 实时、浏览器页面必须打开、断线数据库补偿、无外网可运行。

`docs/deployment.zh-CN.md` 说明升级顺序：备份数据库、执行 `018_system_notifications.sql`、替换 Linux 单文件、重启 systemd、检查 `/api/notifications` 和 SSE 响应头；回滚时先回滚代码，默认保留通知表。

模块 README 只描述四类触发场景和非触发场景，不重复平台实现细节。

- [ ] **Step 3: 更新应用内日志**

在当前最新系统版本条目增加：

```html
<li>新增系统通知中心，支持未读数量、通知列表和实时提醒。</li>
```

模块更新点通过 `manifest.release_notes` 聚合，不在系统日志手工重复“报表特殊处理录入模块”条目。

- [ ] **Step 4: 运行文档和静态测试**

Run:

```powershell
python -m pytest tests/test_deployment_docs.py tests/test_web_static.py tests/notifications/test_frontend_static.py -q
```

Expected: PASS。

---

### Task 10: 全量验证和交付检查

**Files:**
- Verify only: all changed files listed above.

**Interfaces:**
- Verifies: 设计文档第 15 节全部验收标准。

- [ ] **Step 1: 运行通知与模块重点测试**

Run:

```powershell
python -m pytest tests/notifications tests/modules/report_special_processing tests/module_system -q
```

Expected: PASS。

- [ ] **Step 2: 运行核心服务和前端回归**

Run:

```powershell
python -m pytest tests/test_app_database.py tests/test_server.py tests/test_security.py tests/test_web_static.py tests/test_deployment_docs.py -q
```

Expected: PASS。

- [ ] **Step 3: 运行全量测试**

按用户的稳定偏好，将该耗时验证交给后台子代理执行；主会话检查完整输出并处理失败。

Run:

```powershell
python -m pytest -q
```

Expected: PASS，退出码 0。

- [ ] **Step 4: 检查 JavaScript 语法**

Run:

```powershell
node --check src/auto_check/web/notification_center.js
node --check src/auto_check/web/app.js
node --check src/auto_check/modules/report_special_processing/web/index.js
```

Expected: 均无输出，退出码 0。

- [ ] **Step 5: 检查差异和模块边界**

Run:

```powershell
git diff --check
git status --short
rg -n "report_special_processing|pending_confirmation|报表特殊处理待确认" src/auto_check/app/notifications
rg -n "platform.notification" src/auto_check/modules/report_special_processing/manifest.json src/auto_check/modules/report_special_processing/module.py
```

Expected:

- `git diff --check` 无真实 whitespace error；CRLF/LF 提示单独判断。
- 通知平台目录的业务词检索无结果。
- 模块只通过清单和平台门面接入通知。
- 没有无关文件被回退或覆盖。

- [ ] **Step 6: 手工浏览器验收**

在本地开发服务创建两个登录用户并使用两个浏览器会话验证：

1. 用户 A 新建正式特殊处理记录并把数据治理负责人设为用户 B。
2. 用户 B 在任意页面 1 秒内看到铃铛数量增加和一次右上角弹窗。
3. 用户 A 不收到该通知。
4. 用户 B 打开铃铛，未读数不变化；点击通知后数量减 1 并打开确认界面。
5. 再创建 100 条测试通知，角标显示 `99+`，API 返回准确数量。
6. 断开网络后创建通知，恢复网络后列表与数量出现该项但不补弹窗。
7. 完成待办后通知仍存在。
8. 将测试通知时间调整到 30 天边界并运行清理，过期项消失。

- [ ] **Step 7: 给用户报告交付状态**

报告必须分别说明：

- 平台代码：数据表、服务、API、SSE、前端。
- 模块代码：哪些业务操作产生通知。
- 配置与部署：增量 SQL、端口、外网和 HTTPS 需求。
- 文档：README、部署和模块说明。
- 行为变化：未读数、列表、弹窗、已读和保留期。
- 验证证据：重点测试、全量测试、JS 检查和差异检查的实际输出。
- 未执行事项：没有打包、提交或推送，除非用户另行授权。

---

## Execution Order and Review Gates

1. Task 1 至 Task 6 构成通用通知平台。Task 6 通过后先审查平台目录中是否出现业务专用名称。
2. Task 7 才允许修改报表特殊处理模块；不得提前把模块依赖加入一个尚未注册的平台服务。
3. Task 8 验证跨层边界，Task 9 同步文档，Task 10 做最终证据检查。
4. 如果平台服务、SSE 或核心顶栏需要超出本计划的公共协议修改，停止实施并更新设计，不在业务模块任务中临时绕过。

## Rollback Order

1. 停止业务模块发布：移除 `platform.notification` 依赖和三个业务调用位置。
2. 回滚前端启动和资源引用，使铃铛入口消失。
3. 回滚通知 API、SSE 和平台服务装配。
4. 默认保留通知表；确认备份后才人工按“收件表 → 主体表”的顺序删除。
5. 重启服务并验证原有报表特殊处理待办查询仍正常。
