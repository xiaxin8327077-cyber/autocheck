# 看板外部接口监控 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 AutoCheck 看板管理模块内增加外部接口状态、近 24 小时统计和保留 30 天的认证后调用记录，并支持查看完整调用方 IP 和无损返回看板管理界面。

**Architecture:** 平台继续负责 Bearer Token 认证，并通过版本化只读服务只暴露“Token 是否已配置”；TCP 对端 IP 通过通用 `ModuleRequest.client_ip` 传入模块。看板模块拥有调用记录表、统计/分页、内部管理 API 和监控子页面，401、503、错误方法及未命中路由的请求不入库。

**Tech Stack:** Python 3.12、`BaseHTTPRequestHandler`、SQLAlchemy、MySQL 模块迁移、原生 ES Modules/DOM/CSS、pytest、Node.js 前端行为测试。

## Global Constraints

- 工作目录固定为 `D:\xiaxin\auto_check`，当前分支固定为 `feature/auto-check`。
- 只修改 AutoCheck；不得修改 `D:\xiaxin\kanban` 的任何文件或数据。
- 当前工作区已有外部接口和看板管理未提交改动；不得 reset、checkout、覆盖或回退这些改动。
- 不修改 `docs/prototypes/regulatory-reporting-workbench/` 下的用户改动，不处理 `.dumate/`、`.zcode/`。
- 开始前完整阅读仓库 `AGENTS.md`、`docs/ai-modular-development-rules.zh-CN.md`、已确认设计和现有外部接口设计；长文档分段读到 EOF。
- 使用 `apply_patch` 编辑，使用 `rg` 搜索，PowerShell 使用 `pwsh -NoLogo -NoProfile`。
- 严格 TDD：先写失败测试并看到预期失败，再写最小实现，再运行目标测试。
- 不使用 DSH 或子代理；直接在一个主会话中按任务顺序实施。
- 不提交、不推送、不打包 `dist\auto-check.exe`；不要修改展示用大版本号。
- 401、503、错误方法、未命中路由及内部预览不记录；认证通过并命中外部看板预览路由后的 200/404/500 要记录。
- 调用方 IP 取规范化的 TCP 对端地址，忽略 `X-Forwarded-For` 和 `Forwarded`。
- 明文 Token、Token 摘要、Authorization、SQL、数据源配置和响应数据不得进入调用记录或监控响应。
- 留存期固定为滚动 30 天；列表默认每页 10 条、最大 100 条，不新增专用设置。
- 页面必须符合“系统管理 / 角色权限”管理列表规范，详细验收见“页面显示与交互验收规范”。

---

## Current State and Baseline

- 两个外部路径和 Bearer 认证已经在当前未提交改动中实现。
- 外部路由由 `ModuleRouter.add(..., external=True)` 显式发布，`server.py` 只做通用认证和分发。
- 当前模块 manifest `schema_version` 为 2，已有迁移 `001_initial.sql`、`002_year_snapshots.sql`。
- 当前模块更新项 19 条；manifest 合同最多允许 20 条，本功能只能再追加 1 条并避免重复。
- 外部接口功能加入前的全量基线是 `2121 passed, 11 skipped`；当前实现已增加测试，因此最终数量以本次实际输出为准。
- 已确认设计：`docs/superpowers/specs/2026-09-15-dashboard-external-api-monitoring-design.md`。

## File Map

### Create

- `src/auto_check/app/external_api.py`：外部接口 Token 的单一读取函数和 `platform.external_api_status` v1 只读服务。
- `src/auto_check/modules/dashboard_management/external_api_monitoring.py`：调用记录表、查询对象、仓储和监控领域服务。
- `src/auto_check/modules/dashboard_management/migrations/003_external_api_call_logs.sql`：调用记录表及索引。
- `src/auto_check/modules/dashboard_management/web/components/external_api_monitor.js`：监控页 DOM、状态卡、指标卡、筛选、表格和分页。
- `tests/modules/dashboard_management/test_external_api_monitoring.py`：监控仓储、服务、留存、统计、分页和参数测试。

### Modify

- `src/auto_check/app/server.py`：复用 Token 读取函数、注册平台状态服务、传递 TCP 对端 IP。
- `src/auto_check/app/module_system/contracts.py`：为 `ModuleRequest` 增加 `client_ip`。
- `src/auto_check/app/module_system/routing.py`：外部分发接受并传递 `client_ip`。
- `src/auto_check/app/module_system/runtime.py`：外部分发接受并传递 `client_ip`。
- `src/auto_check/app/platform_services.py`：若外部状态服务放入独立文件，只更新导出或保持不变；不要复制实现。
- `src/auto_check/app/capabilities.py`：登记监控能力和默认角色矩阵。
- `src/auto_check/app/module_system/permissions.py`：模块权限映射到平台能力。
- `src/auto_check/modules/dashboard_management/module.py`：登记新表、解析平台服务并构建监控服务。
- `src/auto_check/modules/dashboard_management/api.py`：记录外部调用并增加两个内部监控 API。
- `src/auto_check/modules/dashboard_management/manifest.json`：schema、权限、平台服务依赖和一条更新项。
- `src/auto_check/modules/dashboard_management/web/api.js`：summary/calls 请求。
- `src/auto_check/modules/dashboard_management/web/state.js`：监控视图、筛选、分页和返回状态。
- `src/auto_check/modules/dashboard_management/web/index.js`：权限入口、监控加载、视图切换和返回。
- `src/auto_check/modules/dashboard_management/web/components/dashboard_tabs.js`：标题栏“接口监控”次要按钮。
- `src/auto_check/modules/dashboard_management/web/styles.css`：监控页满高布局和组件样式。
- `tests/test_platform_services.py`、`tests/test_server.py`：平台服务注册和启动装配。
- `tests/module_system/test_contracts.py`、`test_routing.py`、`test_runtime.py`、`test_server_integration.py`：IP 请求元数据和外部 HTTP 行为。
- `tests/modules/dashboard_management/test_api.py`、`test_module_integration.py`：调用记录和监控 API。
- `tests/modules/dashboard_management/test_manifest_and_migrations.py`：迁移、schema、权限、依赖和更新项。
- `tests/modules/dashboard_management/test_frontend_behavior.py`、`test_frontend_static.py`：状态机、返回恢复、分页和显示结构。
- `tests/test_capabilities.py`、`tests/test_web_static.py`：平台能力树和前端角色权限树。
- `docs/dashboard-management-external-api.zh-CN.md`、模块 `README.md`、根 `README.md`：记录范围、IP、30 天留存和入口。

## Page Display and Interaction Acceptance Specification

以下条目是实现与测试必须同时满足的页面验收标准：

1. 入口位于看板管理顶部 Tabs/标题栏右侧，文案为“接口监控”，使用空心次要按钮；仅 `sys.dashboard_management.external_api_monitor` 可见。
2. 点击入口后仍处于“系统管理 → 看板管理”导航，不打开弹窗、不新增全局菜单；根容器切换为独立监控子页面。
3. 监控页标题栏左侧显示“返回看板管理”，点击后恢复进入前的当前看板、当前区域、未保存草稿、SQL 测试状态、预览结果和可恢复的滚动位置，不弹出放弃修改确认。
4. 页面根节点采用纵向 flex，`height: 100%`、`min-height: 0`；整页只有一个 `.dm-management-card` 同源外框，内部严格按“标题栏 → 状态区 → 五项统计条 → 筛选栏 → 表格 → 底部分页”排列。
5. 外框复用看板管理/角色权限管理的边框、背景、圆角和裁切；内部各区只用分隔线组织，不得拆成漂浮卡片、卡片瀑布或多套外框。
6. 状态区显示“接口已启用/未启用”“Token 已配置/未配置”“记录保留 30 天”和两个完整相对路径；桌面端两个接口同一行并列展示，窄屏再收敛为单列；绝不显示 Token、长度、摘要或 Authorization。
7. 指标区固定五项：近 24 小时调用、成功、部分成功、失败、平均耗时；桌面宽度下五项等宽等高、标签和值基线一致，仅用统一分隔线组织；无调用时计数为 0，平均耗时显示 `-`。
8. 筛选区依次为看板、结果状态、调用方 IP、开始日期、结束日期、“查询”“重置”；日期复用系统日期选择组件，开始日期覆盖当天起始时刻，结束日期覆盖当天结束时刻；查询与重置均使用统一空心按钮，重置后所有筛选归零并回到第 1 页。
9. 表格列顺序固定为：调用时间、调用方 IP、看板、HTTP 状态、业务状态、失败区域数、耗时、`request_id`、错误摘要。
10. IP 和 `request_id` 使用等宽字体展示，不提供单独复制按钮。
11. `success` 使用成功语义色，`partial` 使用警告语义色，`error` 使用危险语义色；HTTP 状态与业务状态必须分别显示。
12. 错误摘要为空显示 `-`；长文本在单元格内截断并通过 `title` 查看完整安全摘要，不撑破表格。
13. 分页必须使用 `.pagination`、`.pagination-info`、`.pagination-controls`、`.page-btn`、`.page-current`、`.pagination-jump`；上一页/下一页使用系统标准左右箭头和 `aria-label`，避免按钮文字竖排；分页固定在列表卡底部，空数据和单页也显示。
14. 分页文案：有数据为“共 N 条，第 P / T 页”，空数据为“暂无数据”；当前页空数据显示 `-`，否则只显示页码 P。
15. 筛选变化、查询、清除后回第 1 页；上一页、下一页、跳页正确，越界页收敛到有效范围；请求过程中禁用重复翻页。
16. 首次加载显示骨架或明确的“正在加载接口监控…”；查询失败保留筛选并显示安全错误和“重新加载”，不能把失败伪装成空数据。
17. 视口较窄时统计项从五列收敛为两列/一列，筛选项换行；表格使用自身横向滚动，不让整页横向溢出；响应式只改变排列，不改变视觉语言与内容顺序。
18. 仅使用当前亮色活力主题、Logo 蓝渐变 `#3466D9` 到 `#6AA4FF`、现有语义色和全局变量。渐变只用于实心主操作；返回、筛选等次要操作使用纯色。
19. 卡片、按钮、输入框、选择框、日期控件、状态标签统一使用 `--ui-radius`；悬浮反馈使用纯色描边，不使用主题光晕，不因 hover 位移内部布局。
20. 所有按钮带 `type="button"`，分页按钮有 `aria-label`，状态信息不只依赖颜色表达。
21. 标题栏高度、内容内边距、筛选控件高度、表头/行高、状态标签、按钮尺寸和间距以“系统管理 / 角色权限”现有实现为准，不另造页面密度；同类控件必须齐线。
22. 表头与所有内容列统一居中；同一行的标签和文字垂直居中，不得高低错位。
23. 禁止巨型圆角、彩色投影、玻璃拟态、悬浮卡片、胶囊式导航、超大指标数字和新的独立图标语言，确保页面与系统其他管理页整齐划一。

---

### Task 1: 建立外部接口配置单一来源与只读状态服务

**Files:**
- Create: `src/auto_check/app/external_api.py`
- Modify: `src/auto_check/app/server.py`
- Test: `tests/test_platform_services.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Produces: `read_external_api_token(environ: Mapping[str, str] | None = None) -> str`
- Produces: `ExternalApiStatusSnapshot(token_configured: bool)`
- Produces: `create_external_api_status_service(token_reader: Callable[[], str] = read_external_api_token) -> PlatformServiceSpec`
- Produces: service name `platform.external_api_status`, version `1`, facade method `get_status() -> ExternalApiStatusSnapshot`

- [ ] **Step 1: 写平台服务失败测试**

在 `tests/test_platform_services.py` 增加以下行为断言：

```python
def test_external_api_status_service_exposes_only_configuration_boolean():
    registry = ServiceRegistry()
    registry.register_platform(create_external_api_status_service(lambda: "secret"))
    services = registry.for_module(
        "dashboard_management",
        service_dependencies={"platform.external_api_status": 1},
    )
    facade = services.resolve("platform.external_api_status", 1)
    assert facade.get_status() == ExternalApiStatusSnapshot(token_configured=True)
    assert not hasattr(facade.get_status(), "token")
    services.close()
    with pytest.raises(RuntimeError, match="closed"):
        facade.get_status()


def test_external_api_status_service_reports_blank_token_as_unconfigured():
    spec = create_external_api_status_service(lambda: "   ")
    registry = ServiceRegistry()
    registry.register_platform(spec)
    services = registry.for_module(
        "dashboard_management",
        service_dependencies={"platform.external_api_status": 1},
    )
    assert services.resolve("platform.external_api_status", 1).get_status().token_configured is False
```

- [ ] **Step 2: 运行测试确认因缺少服务失败**

Run: `python -m pytest tests/test_platform_services.py -q`

Expected: FAIL，导入 `create_external_api_status_service` 或 `ExternalApiStatusSnapshot` 失败。

- [ ] **Step 3: 实现最小安全服务**

`src/auto_check/app/external_api.py` 使用以下公开结构；facade 必须使用 `RLock` 和关闭检查，风格与 `platform.user_directory` 一致：

```python
EXTERNAL_API_STATUS_SERVICE = "platform.external_api_status"
EXTERNAL_API_STATUS_VERSION = 1


def read_external_api_token(environ=None) -> str:
    source = os.environ if environ is None else environ
    return str(source.get("AUTO_CHECK_EXTERNAL_API_TOKEN", "")).strip()


@dataclass(frozen=True)
class ExternalApiStatusSnapshot:
    token_configured: bool


class _ExternalApiStatusFacade:
    def get_status(self) -> ExternalApiStatusSnapshot:
        with self._lock:
            if self._closed:
                raise RuntimeError("platform service facade is closed")
            return ExternalApiStatusSnapshot(bool(self._token_reader()))


def create_external_api_status_service(token_reader=read_external_api_token) -> PlatformServiceSpec:
    def bind(_owner: str) -> BoundService:
        facade = _ExternalApiStatusFacade(token_reader)
        return BoundService(value=facade, close=facade._close)
    return PlatformServiceSpec(EXTERNAL_API_STATUS_SERVICE, EXTERNAL_API_STATUS_VERSION, bind)
```

将 `server.py` 的直接 `os.environ.get(...)` 替换为 `read_external_api_token()`，并在 `ModuleRuntime.build(... platform_services=(...))` 注册 `create_external_api_status_service()`。删除不再需要的 `os` 导入（仅当该文件没有其他用途）。同步 `tests/test_server.py` 中启动装配的 monkeypatch 工厂，断言新服务工厂被调用一次。

- [ ] **Step 4: 运行目标测试**

Run: `python -m pytest tests/test_platform_services.py tests/test_server.py -q`

Expected: PASS。

- [ ] **Step 5: 检查敏感字段**

Run: `rg -n "token|Authorization" src/auto_check/app/external_api.py`

Expected: 只有配置读取和布尔判断，没有 Token 返回字段、打印、日志或摘要。

### Task 2: 把 TCP 对端 IP 作为通用外部模块请求元数据传递

**Files:**
- Modify: `src/auto_check/app/module_system/contracts.py`
- Modify: `src/auto_check/app/module_system/routing.py`
- Modify: `src/auto_check/app/module_system/runtime.py`
- Modify: `src/auto_check/app/server.py`
- Test: `tests/module_system/test_contracts.py`
- Test: `tests/module_system/test_routing.py`
- Test: `tests/module_system/test_runtime.py`
- Test: `tests/module_system/test_server_integration.py`

**Interfaces:**
- Produces: `ModuleRequest.client_ip: str`
- Produces: `ModuleRouter.dispatch_external(method, path, query, *, client_ip) -> ModuleHttpResponse | None`
- Produces: `ModuleRuntime.dispatch_external(method, path, query, *, client_ip) -> ModuleHttpResponse`
- Produces: `_normalize_peer_ip(value: object) -> str`，返回规范 IPv4/IPv6 或安全兜底 `unknown`

- [ ] **Step 1: 写外部分发 IP 失败测试**

在路由测试中注册捕获请求的 external GET handler，并断言：

```python
response = router.dispatch_external(
    "GET", "/boards/report_submission/preview", {}, client_ip="2001:db8::7"
)
assert response.status == 200
assert captured_request.client_ip == "2001:db8::7"
```

在 server integration 测试 handler 中回显 `request.client_ip`，启动真实本地 HTTP 服务后断言 `127.0.0.1` 或 `::1`；请求同时发送 `X-Forwarded-For: 203.0.113.9`，断言回显值不是 `203.0.113.9`。

- [ ] **Step 2: 运行测试确认签名失败**

Run: `python -m pytest tests/module_system/test_contracts.py tests/module_system/test_routing.py tests/module_system/test_runtime.py tests/module_system/test_server_integration.py -q`

Expected: FAIL，`dispatch_external` 不接受 `client_ip` 或 `ModuleRequest` 缺少字段。

- [ ] **Step 3: 实现请求元数据传播**

在 `ModuleRequest` 最后增加有默认值的字段以保持内部构造兼容：

```python
@dataclass(frozen=True)
class ModuleRequest:
    method: str
    path: str
    path_params: Mapping[str, str]
    query: Mapping[str, str]
    body: Mapping[str, Any] | None
    current_user: Mapping[str, Any]
    client_ip: str = ""
```

路由和运行时的 `dispatch_external` 使用仅关键字参数 `client_ip`，构造请求时设置该字段；内部 `dispatch` 保持现有行为并得到空字符串。

在 `server.py` 增加纯函数：

```python
def _normalize_peer_ip(value: object) -> str:
    host = str(value or "").strip().split("%", 1)[0]
    try:
        return ipaddress.ip_address(host).compressed
    except ValueError:
        return "unknown"
```

调用值只能来自 `self.client_address[0]`，不要读取任何转发头：

```python
client_ip = _normalize_peer_ip(self.client_address[0] if self.client_address else "")
response = self.router.module_runtime.dispatch_external(
    method=method,
    path=path,
    query=query,
    client_ip=client_ip,
)
```

- [ ] **Step 4: 运行目标测试**

Run: `python -m pytest tests/module_system/test_contracts.py tests/module_system/test_routing.py tests/module_system/test_runtime.py tests/module_system/test_server_integration.py -q`

Expected: PASS；现有 401/503/405/404/Cache-Control 测试继续通过。

### Task 3: 新增调用记录迁移和仓储

**Files:**
- Create: `src/auto_check/modules/dashboard_management/migrations/003_external_api_call_logs.sql`
- Create: `src/auto_check/modules/dashboard_management/external_api_monitoring.py`
- Modify: `src/auto_check/modules/dashboard_management/module.py`
- Test: `tests/modules/dashboard_management/test_manifest_and_migrations.py`
- Test: `tests/modules/dashboard_management/test_external_api_monitoring.py`

**Interfaces:**
- Produces: `ExternalApiCallRecord`
- Produces: `ExternalApiCallQuery`
- Produces: `ExternalApiMonitoringStore.record_and_cleanup(record, cutoff) -> None`
- Produces: `ExternalApiMonitoringStore.summary(since, cutoff) -> Mapping[str, Any]`
- Produces: `ExternalApiMonitoringStore.list_calls(query, cutoff) -> Mapping[str, Any]`

- [ ] **Step 1: 写迁移和仓储失败测试**

迁移测试必须断言 schema version 3、新表只创建一次、字段和索引存在、无 INSERT：

```python
assert payload["schema_version"] == 3
sql = (MODULE_ROOT / "migrations" / "003_external_api_call_logs.sql").read_text("utf-8")
for fragment in [
    "CREATE TABLE dashboard_management_external_api_calls",
    "caller_ip VARCHAR(45) NOT NULL",
    "request_id VARCHAR(64) NOT NULL",
    "UNIQUE KEY uq_dashboard_management_external_api_calls_request_id",
    "KEY ix_dashboard_management_external_api_calls_called_at",
]:
    assert fragment in sql
assert "INSERT " not in sql.upper()
```

仓储测试使用现有测试数据库夹具，插入 success、partial、error、31 天前记录，断言清理、统计、IP 精确筛选、稳定倒序、总数和分页。

- [ ] **Step 2: 运行测试确认缺少迁移和类型**

Run: `python -m pytest tests/modules/dashboard_management/test_manifest_and_migrations.py tests/modules/dashboard_management/test_external_api_monitoring.py -q`

Expected: FAIL，新迁移或 `external_api_monitoring` 模块不存在。

- [ ] **Step 3: 写 MySQL 迁移**

迁移必须使用模块现有 MySQL 风格：

```sql
CREATE TABLE dashboard_management_external_api_calls (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '外部接口调用记录主键',
    called_at DATETIME(6) NOT NULL COMMENT 'UTC 调用开始时间',
    board_code VARCHAR(64) NOT NULL COMMENT '固定看板编码',
    http_status INT NOT NULL COMMENT '最终 HTTP 状态码',
    result_status VARCHAR(16) NOT NULL COMMENT 'success partial 或 error',
    failed_region_count INT NOT NULL DEFAULT 0 COMMENT '失败区域数量',
    duration_ms BIGINT NOT NULL COMMENT '调用耗时毫秒',
    request_id VARCHAR(64) NOT NULL COMMENT '接口请求追踪号',
    caller_ip VARCHAR(45) NOT NULL COMMENT 'TCP 对端 IPv4 或 IPv6',
    error_code VARCHAR(64) NULL COMMENT '安全错误码',
    error_message VARCHAR(500) NULL COMMENT '安全错误摘要',
    PRIMARY KEY (id),
    UNIQUE KEY uq_dashboard_management_external_api_calls_request_id (request_id),
    KEY ix_dashboard_management_external_api_calls_called_at (called_at),
    KEY ix_dashboard_management_external_api_calls_board_time (board_code, called_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='看板外部接口调用记录';
```

- [ ] **Step 4: 实现跨数据库 SQLAlchemy 表和仓储**

在新文件中复用 `storage.py` 的 `METADATA`、`IDENTIFIER_TYPE`、`_row/_rows` 风格。公开数据类型保持以下签名：

```python
@dataclass(frozen=True)
class ExternalApiCallRecord:
    called_at: datetime
    board_code: str
    http_status: int
    result_status: str
    failed_region_count: int
    duration_ms: int
    request_id: str
    caller_ip: str
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class ExternalApiCallQuery:
    page: int = 1
    page_size: int = 10
    board_code: str = ""
    result_status: str = ""
    caller_ip: str = ""
    started_at: datetime | None = None
    ended_at: datetime | None = None
```

`record_and_cleanup` 在一个 transaction 中先删除 `called_at < cutoff`，再插入；`summary` 和 `list_calls` 在查询前清理。summary 返回 `total/success/partial/failed/average_duration_ms/last_called_at/last_success_at`。分页排序固定 `called_at DESC, id DESC`，越界收敛到最后有效页，空数据返回 `page=1,total_pages=1`。

- [ ] **Step 5: 登记模块 schema 并运行测试**

在 `module.py.register_schema()` 登记新表及全部字段。Run: `python -m pytest tests/modules/dashboard_management/test_manifest_and_migrations.py tests/modules/dashboard_management/test_external_api_monitoring.py -q`

Expected: PASS。

### Task 4: 实现监控领域服务、30 天留存和安全归类

**Files:**
- Modify: `src/auto_check/modules/dashboard_management/external_api_monitoring.py`
- Modify: `src/auto_check/modules/dashboard_management/module.py`
- Test: `tests/modules/dashboard_management/test_external_api_monitoring.py`

**Interfaces:**
- Produces: `ExternalApiCallTrace`
- Produces: `ExternalApiMonitoringService.begin_call(board_code, caller_ip, request_id) -> ExternalApiCallTrace`
- Produces: `ExternalApiMonitoringService.finish_call(trace, response) -> None`
- Produces: `ExternalApiMonitoringService.monitor_summary() -> Mapping[str, Any]`
- Produces: `ExternalApiMonitoringService.list_calls(query: Mapping[str, str]) -> Mapping[str, Any]`
- Constructor clock contract: `utc_now: Callable[[], datetime]` 返回有 UTC 时区的时间，`monotonic_now: Callable[[], float]` 只用于耗时。

- [ ] **Step 1: 写归类、留存和容错失败测试**

测试使用注入的 wall clock、monotonic clock、status facade 和 fake store：

```python
trace = service.begin_call("report_submission", "203.0.113.8", "req-1")
service.finish_call(trace, ModuleHttpResponse.json(200, {
    "status": "partial",
    "data": {"regions": [{"status": "success"}, {"status": "error"}]},
    "meta": {"request_id": "req-1"},
}))
record = store.records[0]
assert record.result_status == "partial"
assert record.failed_region_count == 1
assert record.caller_ip == "203.0.113.8"
assert record.duration_ms >= 0
```

另测 404/500 为 error、对外安全错误摘要、store 抛异常时 `finish_call` 不抛出、summary token 未配置、日期/IP/状态/页码参数错误为 `ValidationError`。

- [ ] **Step 2: 运行测试确认服务不存在**

Run: `python -m pytest tests/modules/dashboard_management/test_external_api_monitoring.py -q`

Expected: FAIL，缺少 `ExternalApiMonitoringService` 或方法。

- [ ] **Step 3: 实现领域服务**

使用以下固定规则：

```python
RETENTION_DAYS = 30
SUMMARY_HOURS = 24
ALLOWED_RESULTS = frozenset({"success", "partial", "error"})

def _classify(response):
    body = response.body if isinstance(response.body, Mapping) else {}
    if response.status == 200 and body.get("status") in {"success", "partial"}:
        result = str(body["status"])
        regions = body.get("data", {}).get("regions", [])
        failed = sum(1 for region in regions if region.get("status") == "error")
        return result, failed, None, None
    error = body.get("error", {}) if isinstance(body.get("error"), Mapping) else {}
    return "error", 0, str(error.get("code") or "internal_error"), str(error.get("message") or "系统暂时无法处理该请求")
```

`duration_ms` 用 `(monotonic_now - trace.started_tick) * 1000` 向上取整并限制为非负数。wall clock 默认使用 `datetime.now(timezone.utc)`，写入数据库前转为 naive UTC，API 输出时恢复为带 `+00:00` 的 ISO 8601，前端再按浏览器本地时区显示。`finish_call` 捕获所有仓储异常并通过注入的模块 logger 记录，不改变业务响应。monitor summary 组合平台 `token_configured`、固定 endpoints、30 天留存和仓储统计；`enabled == token_configured`。

- [ ] **Step 4: 在模块生命周期装配服务**

`DashboardManagementModule.start()` 必须解析声明依赖并构造 `_monitoring_service`：

```python
status_facade = context.services.resolve("platform.external_api_status", 1)
monitor_store = ExternalApiMonitoringStore(context.application_database)
self._monitoring_service = ExternalApiMonitoringService(
    monitor_store,
    status_facade=status_facade,
    logger=context.logger,
)
```

领域服务的默认 `utc_now` 必须是 `lambda: datetime.now(timezone.utc)`，测试直接注入固定时钟，不复用可能为本地 naive 时间的 `context.now`。`stop()` 清空服务引用；`health()` 需同时确认业务服务和监控服务存在。所有直接启动模块的测试上下文都要登记 `platform.external_api_status` v1，不能绕过 manifest 依赖检查。

- [ ] **Step 5: 运行测试**

Run: `python -m pytest tests/modules/dashboard_management/test_external_api_monitoring.py tests/modules/dashboard_management/test_module_integration.py -q`

Expected: PASS。

### Task 5: 对认证通过并命中路由的外部预览写一次记录

**Files:**
- Modify: `src/auto_check/modules/dashboard_management/api.py`
- Modify: `src/auto_check/modules/dashboard_management/module.py`
- Test: `tests/modules/dashboard_management/test_api.py`
- Test: `tests/modules/dashboard_management/test_module_integration.py`

**Interfaces:**
- Consumes: Task 2 的 `request.client_ip`
- Consumes: Task 4 的 `begin_call` / `finish_call`
- Produces: `register_routes(router, service_provider, monitoring_provider)`

- [ ] **Step 1: 写调用记录边界失败测试**

构造 fake monitoring service 并断言：

```python
external = dispatch_external("/boards/report_submission/preview", client_ip="198.51.100.4")
assert external.status == 200
assert monitor.calls == [
    ("report_submission", "198.51.100.4", external.body["meta"]["request_id"], 200)
]

internal = dispatch_internal("/boards/report_submission/preview")
assert internal.status == 200
assert len(monitor.calls) == 1
```

增加 invalid board 404 和业务异常 500，各自恰好记录一次且 request_id 与响应一致；monitor `finish_call` 抛错时外部响应仍保持原状态和 body。

- [ ] **Step 2: 运行测试确认监控未接入**

Run: `python -m pytest tests/modules/dashboard_management/test_api.py tests/modules/dashboard_management/test_module_integration.py -q`

Expected: FAIL，monitor 没有收到调用。

- [ ] **Step 3: 重构外部 preview 分支为单出口**

保留内部响应结构不变；外部分支必须先创建 request_id 和 trace，再将 success/DomainError/Exception 都转换成 `response`，最后记录并返回：

```python
def board_preview(request: ModuleRequest) -> ModuleHttpResponse:
    request_id = _request_id()
    if not request.path.startswith("/api/external/v1/"):
        return internal_board_preview(request, request_id)
    monitor = monitoring_provider()
    board_code = request.path_params["board_code"]
    trace = monitor.begin_call(board_code, request.client_ip, request_id)
    try:
        response = _external_success(
            service_provider().preview_external_board_data(board_code), request_id
        )
    except DomainError as error:
        response = _error(error, request_id)
    except Exception:
        response = _internal_error(request_id)
    monitor.finish_call(trace, response)
    return response
```

`finish_call` 自身吞掉仓储异常；API 层不要记录 Token、query 或响应数据。

- [ ] **Step 4: 运行目标和外部 HTTP 回归**

Run: `python -m pytest tests/modules/dashboard_management/test_api.py tests/modules/dashboard_management/test_module_integration.py tests/module_system/test_server_integration.py -q`

Expected: PASS。

### Task 6: 增加监控权限、summary 和 calls 内部 API

**Files:**
- Modify: `src/auto_check/app/capabilities.py`
- Modify: `src/auto_check/app/module_system/permissions.py`
- Modify: `src/auto_check/web/app.js`
- Modify: `src/auto_check/modules/dashboard_management/api.py`
- Modify: `src/auto_check/modules/dashboard_management/manifest.json`
- Test: `tests/test_capabilities.py`
- Test: `tests/test_web_static.py`
- Test: `tests/modules/dashboard_management/test_api.py`

**Interfaces:**
- Produces: module permission `dashboard_management.external_api_monitor`
- Produces: platform capability `sys.dashboard_management.external_api_monitor`
- Produces: `GET /external-api/monitor/summary`
- Produces: `GET /external-api/monitor/calls`

- [ ] **Step 1: 写权限和 API 失败测试**

测试管理员/已授权普通角色为 200，未授权角色为 403：

```python
authorized = {"role": "user", "capabilities": ["sys.dashboard_management.external_api_monitor"]}
assert dispatch("GET", "/external-api/monitor/summary", user=authorized).status == 200
assert dispatch("GET", "/external-api/monitor/calls", user=authorized).status == 200
assert dispatch("GET", "/external-api/monitor/summary", user={"role": "user", "capabilities": []).status == 403
```

能力测试断言定义类型为 `TYPE_FUNCTION`、admin 默认 true、user/custom role 默认 false；`app.js` 角色权限树出现完全一致的能力码和“查看外部接口监控”标签。

- [ ] **Step 2: 运行测试确认能力和路由缺失**

Run: `python -m pytest tests/test_capabilities.py tests/test_web_static.py tests/modules/dashboard_management/test_api.py -q`

Expected: FAIL，能力码或监控路由不存在。

- [ ] **Step 3: 登记能力和权限映射**

增加：

```python
"sys.dashboard_management.external_api_monitor": {
    "label": "查看看板外部接口监控",
    "type": TYPE_FUNCTION,
}
```

管理员默认值由锁定管理员规则保持 true，标准 user 和自定义角色默认 false。模块权限映射增加：

```python
"dashboard_management.external_api_monitor": "sys.dashboard_management.external_api_monitor"
```

`app.js` 角色权限树看板管理节点增加同码功能项。

- [ ] **Step 4: 注册两个只读内部路由**

使用 permission `dashboard_management.external_api_monitor`、`max_body_bytes=0`：

```python
router.add(
    "GET", "/external-api/monitor/summary",
    handle(lambda _service, request: monitoring_provider().monitor_summary()),
    permission=monitor_permission, max_body_bytes=0,
)
router.add(
    "GET", "/external-api/monitor/calls",
    handle(lambda _service, request: monitoring_provider().list_calls(request.query)),
    permission=monitor_permission, max_body_bytes=0,
)
```

无效 `page/page_size/board_code/result_status/caller_ip/started_at/ended_at` 返回 400 字段错误；平台 Session/CSRF 行为保持现有内部 GET 规则。

- [ ] **Step 5: 运行目标测试**

Run: `python -m pytest tests/test_capabilities.py tests/test_web_static.py tests/modules/dashboard_management/test_api.py -q`

Expected: PASS。

### Task 7: 增加前端监控状态机、API 和无损返回

**Files:**
- Modify: `src/auto_check/modules/dashboard_management/web/api.js`
- Modify: `src/auto_check/modules/dashboard_management/web/state.js`
- Modify: `src/auto_check/modules/dashboard_management/web/index.js`
- Test: `tests/modules/dashboard_management/test_frontend_behavior.py`

**Interfaces:**
- Produces: `api.monitorSummary()`、`api.monitorCalls(filters)`
- Produces: `enterMonitorView(state, scrollTop)`、`leaveMonitorView(state)`
- Produces: state fields `viewMode`、`managementScrollTop`、`monitorSummary`、`monitorCalls`、`monitorFilters`、`monitorPage`、`monitorLoading`、`monitorError`

- [ ] **Step 1: 扩充 Node 行为场景为失败测试**

在现有 scenario 中先创建未保存草稿，然后进入/退出监控：

```javascript
markSqlChanged(state, "SELECT unsaved before monitor");
const before = currentDraft(state);
enterMonitorView(state, 128);
assert.equal(state.viewMode, "monitor");
leaveMonitorView(state);
assert.equal(state.viewMode, "management");
assert.equal(currentDraft(state), before);
assert.equal(currentDraft(state).sql_text, "SELECT unsaved before monitor");
assert.equal(state.managementScrollTop, 128);
```

测试筛选变化/清除回第一页、页码收敛、监控请求参数编码，以及 `stopRequests` 会中止监控请求。

- [ ] **Step 2: 运行行为测试确认导出缺失**

Run: `python -m pytest tests/modules/dashboard_management/test_frontend_behavior.py -q`

Expected: FAIL，状态函数或 API 方法不存在。

- [ ] **Step 3: 实现前端状态和 API**

保持现有 `catalogs/drafts/serverSnapshots/previews` Map 引用不变，视图切换只改变 `viewMode`：

```javascript
export function enterMonitorView(state, scrollTop = 0) {
  state.managementScrollTop = Math.max(0, Number(scrollTop) || 0);
  state.viewMode = "monitor";
}
export function leaveMonitorView(state) {
  state.viewMode = "management";
}
export function resetMonitorFilters(state) {
  state.monitorFilters = { board_code: "", result_status: "", caller_ip: "", started_at: "", ended_at: "" };
  state.monitorPage = 1;
}
```

API 查询使用 `URLSearchParams`，只发送非空筛选，始终发送 `page` 和 `page_size=10`。进入监控时并行加载 summary 和 calls；列表翻页只刷新 calls；所有响应写回前检查 lifecycle generation。

- [ ] **Step 4: 运行行为测试**

Run: `python -m pytest tests/modules/dashboard_management/test_frontend_behavior.py -q`

Expected: PASS。

### Task 8: 实现符合统一管理页规范的监控页面

**Files:**
- Create: `src/auto_check/modules/dashboard_management/web/components/external_api_monitor.js`
- Modify: `src/auto_check/modules/dashboard_management/web/components/dashboard_tabs.js`
- Modify: `src/auto_check/modules/dashboard_management/web/index.js`
- Modify: `src/auto_check/modules/dashboard_management/web/styles.css`
- Test: `tests/modules/dashboard_management/test_frontend_static.py`
- Test: `tests/modules/dashboard_management/test_frontend_behavior.py`

**Interfaces:**
- Produces: `renderExternalApiMonitor(options) -> HTMLElement`
- Consumes: `onBack`、`onFilterChange`、`onSearch`、`onClear`、`onPageChange`、`onRetry`

- [ ] **Step 1: 写完整页面结构失败测试**

静态测试必须逐项断言“页面显示与交互验收规范”的核心结构，包括：

```python
component = _read("components/external_api_monitor.js")
css = _read("styles.css")
for class_name in [
    "dm-monitor-page", "dm-monitor-header", "dm-monitor-status-section",
    "dm-monitor-metrics", "dm-management-card", "dm-monitor-filters",
    "dm-monitor-table-wrap", "pagination", "pagination-info",
    "pagination-controls", "page-btn", "page-current", "pagination-jump",
]:
    assert class_name in component or class_name in css
for text in [
    "返回看板管理", "调用方 IP", "近 24 小时调用", "部分成功",
    "平均耗时", "记录保留 30 天", "暂无数据", "跳至",
]:
    assert text in component
assert "height: 100%" in css
assert "min-height: 0" in css
assert "flex: 1" in css
assert "var(--ui-radius)" in css
assert "box-shadow: 0 0" not in css
```

行为测试覆盖返回不清空草稿、查询/清除、分页、加载/错误/空状态和重试。

- [ ] **Step 2: 运行前端测试确认组件缺失**

Run: `python -m pytest tests/modules/dashboard_management/test_frontend_static.py tests/modules/dashboard_management/test_frontend_behavior.py -q`

Expected: FAIL，监控组件或入口不存在。

- [ ] **Step 3: 实现语义化 DOM**

组件根结构固定为：

```html
<section class="dm-monitor-page">
  <section class="dm-management-card dm-monitor-card">
    <header class="dm-monitor-header">返回按钮、标题、刷新按钮</header>
    <section class="dm-monitor-status-section">状态与接口路径</section>
    <section class="dm-monitor-metrics">五个等宽统计项</section>
    <div class="dm-monitor-filters">五个筛选项、查询、清除</div>
    <div class="dm-monitor-table-wrap"><table class="result-table management-list-table dm-monitor-table"></table></div>
    <div class="pagination">统一分页结构</div>
  </section>
</section>
```

所有动态内容用 `textContent`/`node(..., {text})`，不拼接不可信 HTML。状态标签同时写中文文本和语义 class。时间按当前项目前端规则显示 `YYYY-MM-DD HH:mm:ss`，后端仍返回 ISO 8601。

- [ ] **Step 4: 实现布局和视觉规则**

CSS 至少满足：

```css
.auto-check-module[data-module="dashboard_management"] .dm-monitor-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
}
.auto-check-module[data-module="dashboard_management"] .dm-monitor-card {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--outline-variant);
  border-radius: var(--ui-radius);
  background: var(--surface-container-lowest);
}
.auto-check-module[data-module="dashboard_management"] .dm-monitor-table-wrap {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
}
```

不要为监控页重定义公共 `.pagination`、表头或数据行密度；仅允许作用域内补充 flex 定位和分隔线。标题栏、筛选控件、表格行、标签和按钮必须复用角色权限管理的尺寸与间距。断点下统计列数收敛，筛选换行，表格容器横向滚动。禁止暗色模式、主题开关、光晕、悬浮卡片、夸张指标字号和新图标体系。

- [ ] **Step 5: 集成入口和返回**

`dashboard_tabs.js` 接收 `canMonitor/onMonitor` 并在右侧显示空心按钮。`index.js` 用 `hasPermission(user, "dashboard_management.external_api_monitor")` 控制；返回时 render 原管理视图，并在下一帧恢复 `managementScrollTop`。没有能力时不请求监控 API。

- [ ] **Step 6: 运行前端测试**

Run: `python -m pytest tests/modules/dashboard_management/test_frontend_static.py tests/modules/dashboard_management/test_frontend_behavior.py -q`

Expected: PASS。

### Task 9: 完成 manifest、文档、更新日志和模块回归

**Files:**
- Modify: `src/auto_check/modules/dashboard_management/manifest.json`
- Modify: `src/auto_check/modules/dashboard_management/README.md`
- Modify: `docs/dashboard-management-external-api.zh-CN.md`
- Modify: `README.md`
- Modify: related tests listed below

**Interfaces:**
- Manifest: schema version 3，新增 permission 和 `service_dependencies`
- Release note: 恰好新增一条模块功能项，总数不超过 20

- [ ] **Step 1: 写文档与 manifest 失败测试**

在 manifest 测试中断言：

```python
assert payload["schema_version"] == 3
assert "dashboard_management.external_api_monitor" in payload["permissions"]
assert payload["service_dependencies"] == [
    {"name": "platform.external_api_status", "minimum_version": 1}
]
assert len(payload["release_notes"]["items"]) <= 20
assert any("外部接口监控" in item and "30 天" in item for item in payload["release_notes"]["items"])
```

文档测试断言“认证通过并命中路由才记录”“401/503 不记录”“TCP 对端 IP”“不信任 X-Forwarded-For”“30 天”“接口监控”“返回看板管理”均出现。

- [ ] **Step 2: 运行文档测试确认失败**

Run: `python -m pytest tests/modules/dashboard_management/test_manifest_and_migrations.py tests/module_system/test_documentation.py -q`

Expected: FAIL，manifest 或文档缺少监控说明。

- [ ] **Step 3: 更新 manifest 和说明文档**

manifest 追加：

```json
"permissions": [
  "dashboard_management.view",
  "dashboard_management.manage",
  "dashboard_management.test_sql",
  "dashboard_management.external_api_monitor"
],
"service_dependencies": [
  {"name": "platform.external_api_status", "minimum_version": 1}
],
"schema_version": 3
```

更新项使用一条：`看板管理模块：新增外部接口监控，展示接口状态、近 24 小时统计及含调用方 IP 的 30 天认证后调用记录`。不要在 `app.js` 静态 v1.2.27 列表重复写功能；现有模块 release notes 会动态并入当前版本，`app.js` 只需在 Task 6 更新权限树。

README 详细说明行为变化；外部接口文档明确记录边界和 IP 来源，不改变现有字段契约和 Kanban 后端适配建议。

- [ ] **Step 4: 运行看板和模块系统回归**

Run: `python -m pytest tests/modules/dashboard_management tests/module_system tests/test_platform_services.py tests/test_capabilities.py tests/test_web_static.py tests/test_server.py -q`

Expected: PASS。

### Task 10: 全量验证、开发环境重启和真实页面验收

**Files:**
- Verify only; do not create package or commit.

**Interfaces:**
- Produces: 测试输出、8765 监听证据、HTTP 行为证据和页面验收结果。

- [ ] **Step 1: 运行完整测试**

Run: `python -m pytest -q`

Expected: 所有测试通过；只允许仓库既有 skipped，不允许 failed/error。

- [ ] **Step 2: 检查差异和敏感信息**

Run:

```powershell
git diff --check
rg -n "Authorization|AUTO_CHECK_EXTERNAL_API_TOKEN" src/auto_check/modules/dashboard_management
git status --short
```

Expected: `git diff --check` 没有实际 whitespace error；模块代码不读取或保存 Token；无关原型改动仍原样存在且未被本功能修改。

- [ ] **Step 3: 安全识别并重启当前工作区开发进程**

先读取监听进程，不对未确认目标执行终止：

```powershell
$listener = Get-NetTCPConnection -State Listen -LocalPort 8765 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
  $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
  $processInfo | Select-Object ProcessId, ExecutablePath, CommandLine | Format-List
}
```

只有 `CommandLine` 明确指向 `D:\xiaxin\auto_check` 的源码 AutoCheck 进程时才停止，并使用已验证的 PID：

```powershell
$workspacePath = [IO.Path]::GetFullPath('D:\xiaxin\auto_check')
if (-not $listener -or -not $processInfo.CommandLine -or -not $processInfo.CommandLine.Contains($workspacePath, [StringComparison]::OrdinalIgnoreCase)) {
  throw '8765 监听进程不是当前工作区源码服务，停止重启并人工核对'
}
$verifiedProcessId = [int]$listener.OwningProcess
Stop-Process -Id $verifiedProcessId
Wait-Process -Id $verifiedProcessId -ErrorAction SilentlyContinue
```

复用原进程已经确认的 Python、`--config`、host 等参数并设置临时测试 Token，使用隐藏窗口启动。若原命令未带这些可选参数，则使用项目默认源码命令：

```powershell
$env:AUTO_CHECK_EXTERNAL_API_TOKEN = "<test-token-from-secure-config>"
$process = Start-Process -FilePath "python" -ArgumentList "-m", "auto_check", "--no-browser", "--port", "8765" -WorkingDirectory "D:\xiaxin\auto_check" -WindowStyle Hidden -PassThru
```

如果原进程有 `--config` 或不同 Python 路径，必须逐项复用已确认值，不猜测。轮询 `http://127.0.0.1:8765/` 直至就绪，最长 30 秒。

- [ ] **Step 4: 验证外部 HTTP 和新增记录**

用 `Invoke-WebRequest -SkipHttpErrorCheck` 验证：无 Token 401、错误 Token 401、正确 Token 调用两个 board 为 200、响应 `Cache-Control: no-store`。登录 AutoCheck 后调用 summary/calls，确认两次正确 Token 调用新增记录且 `caller_ip` 为本地 TCP 对端地址；401 不增加记录。

503 使用隔离的短时源码进程和不同端口验证，避免破坏最终 8765 实例：清除当前 PowerShell 进程中的测试 Token，在 18765 启动相同源码/配置，验证外部请求为 503 后停止该已确认 PID。不要终止任何未确认进程。

- [ ] **Step 5: 按页面规范逐项验收**

用有监控权限的管理员打开“系统管理 → 看板管理”：

1. 确认“接口监控”入口位置、样式和权限显隐。
2. 确认状态、五个指标、两个端点、30 天说明正确。
3. 确认 IP/状态/时间筛选、查询、清除和分页行为。
4. 确认空数据、单页、加载、错误重试、窄窗口横向表格滚动。
5. 在看板管理制造未保存 SQL 草稿，进入监控再点击“返回看板管理”，确认看板、区域、草稿、测试状态和预览未丢失且无放弃提示。
6. 确认没有暗色模式、光晕、硬编码新圆角或语义颜色错误。

- [ ] **Step 6: 最终报告**

报告必须分为：代码/配置与文档改动、可见行为变化、测试命令与实际结果、8765/401/503/两个 200/调用记录/IP/返回恢复的实测结果、未执行打包/提交/推送。不要只写“已完成”。

### Task 11: 统一监控页信息层级与管理列表风格

**Files:**
- Modify: `src/auto_check/modules/dashboard_management/web/components/external_api_monitor.js`
- Modify: `src/auto_check/modules/dashboard_management/web/styles.css`
- Modify: `tests/modules/dashboard_management/test_frontend_static.py`
- Modify: `src/auto_check/modules/dashboard_management/README.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: 现有 `renderExternalApiMonitor(options)` 的状态、筛选、分页和返回回调。
- Produces: 保持原有行为的结构化状态区、带标签筛选区和语义状态表格。

- [ ] **Step 1: 增加失败的前端结构测试**

断言 `dm-monitor-status-overview`、`dm-monitor-endpoint-list`、`dm-monitor-filter-field`、`management-list-status`、粘性表头和不含复制按钮。

- [ ] **Step 2: 运行单个静态测试确认失败**

Run: `python -m pytest tests/modules/dashboard_management/test_frontend_static.py::test_external_api_monitor_uses_management_list_layout -q`

Expected: FAIL，因为新结构类名尚未实现。

- [ ] **Step 3: 重组监控页 DOM 和作用域 CSS**

只在 `dashboard_management` 模块内增加状态标识、接口清单、带标签筛选、语义状态和粘性表头；保留一个外框和公共分页。

- [ ] **Step 4: 同步模块与根 README**

记录状态区、筛选标签、语义标签、去除复制按钮和统一管理页布局。

- [ ] **Step 5: 运行相关、模块及全量回归**

Run: `python -m pytest tests/modules/dashboard_management/test_frontend_static.py tests/modules/dashboard_management/test_frontend_behavior.py -q`

Run: `python -m pytest tests/modules/dashboard_management -q`

Run: `python -m pytest -q`

Run: `git diff --check`

Expected: 全部 PASS，无真实 whitespace error；不打包、不提交、不推送。
