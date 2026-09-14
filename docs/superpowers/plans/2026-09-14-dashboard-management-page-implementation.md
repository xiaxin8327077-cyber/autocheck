# 看板管理一期页面与数据来源配置 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在系统管理中交付两个固定金融监管看板的数据区域、字段和数据来源配置页面，支持管理员新增区域、追加字段，以及安全测试一条覆盖区域全部字段的自定义 SQL。

**Architecture:** 先对模块宿主增加通用的“模块导航合并到现有系统管理组”能力，再新增独立 `dashboard_management` 模块。模块自行拥有目录、配置、迁移、API、SQL 预览执行器和前端生命周期；公共平台只负责权限映射和导航挂载，不承载看板业务逻辑。

**Tech Stack:** Python 3.12、SQLAlchemy、MySQL 应用库、psycopg、PyMySQL、原生 JavaScript/CSS、现有 Auto Check 模块宿主与 pytest/Node 静态场景测试。

## Global Constraints

- 固定两个看板：“金融监管报表报送大屏”和“金融监管报送流程大屏”，不允许新建第三个看板。
- Excel 黄色业务字段初始化为 10 个内置数据区域和 21 个内置字段。
- 一个数据区域只配置一条 SQL；SQL 必须一次返回该区域全部启用字段。
- 内置编码、字段别名、字段类型和数据形态不可修改；自定义稳定编码/别名创建后不可修改。
- 给系统数据区域追加自定义字段后，该区域必须切换为自定义 SQL。
- SQL 只允许单条 `SELECT`，或以 `WITH` 开头并最终返回 `SELECT` 结果的查询；测试最多读取 11 行、展示前 10 行。
- API 错误必须脱敏，不回显密码、连接串、完整 SQL、驱动堆栈或本地路径。
- 页面只使用现有亮色活力主题、`--ui-radius` 和固定 Logo 蓝色；不增加主题切换、暗色模式或光晕。
- 平台改动与模块业务改动保持独立差异；普通业务代码不得写入 `server.py`、`index.html`、`app.js` 或 `styles.css`。
- 未经用户明确要求，不提交、不推送、不打包；验证完成后只报告工作区改动和测试结果。

---

### Task 1: 注册平台能力与模块权限映射

**Files:**
- Modify: `src/auto_check/app/capabilities.py`
- Modify: `src/auto_check/app/module_system/permissions.py`
- Test: `tests/test_capabilities.py`
- Test: `tests/module_system/test_collaboration.py`

**Interfaces:**
- Consumes: `capabilities_for_role(role, matrix)` 和 `default_permission_evaluator(current_user, permission)`。
- Produces: `sys.dashboard_management`、`sys.dashboard_management.manage`、`sys.dashboard_management.test_sql` 三个平台能力，以及三个模块权限到平台能力的映射。

- [ ] **Step 1: 写能力默认值失败测试**

```python
def test_dashboard_management_capabilities_are_admin_default_only():
    assert CAPABILITY_DEFINITIONS["sys.dashboard_management"]["type"] == TYPE_MENU
    assert CAPABILITY_DEFINITIONS["sys.dashboard_management.manage"]["type"] == TYPE_FUNCTION
    assert CAPABILITY_DEFINITIONS["sys.dashboard_management.test_sql"]["type"] == TYPE_FUNCTION
    assert DEFAULT_MATRIX["admin"]["sys.dashboard_management"] is True
    assert DEFAULT_MATRIX["user"]["sys.dashboard_management"] is False
    assert CUSTOM_ROLE_DEFAULT_MATRIX["sys.dashboard_management.manage"] is False
```

- [ ] **Step 2: 运行能力测试并确认失败**

Run: `python -m pytest -q tests/test_capabilities.py -k dashboard_management`

Expected: FAIL，三个能力尚未注册。

- [ ] **Step 3: 在中央注册表增加能力**

```python
"sys.dashboard_management": {"label": "看板管理", "type": TYPE_MENU},
"sys.dashboard_management.manage": {"label": "维护看板数据区域、字段与来源", "type": TYPE_FUNCTION},
"sys.dashboard_management.test_sql": {"label": "测试看板自定义 SQL", "type": TYPE_FUNCTION},
```

保持 `_STANDARD_TIER_TRUE` 不包含上述能力，使普通用户和新建角色默认为 False；管理员列通过现有推导自动为 True。

- [ ] **Step 4: 写模块权限映射失败测试**

```python
def test_dashboard_module_permissions_use_platform_capabilities():
    user = {
        "role": "auditor",
        "capabilities": ["sys.dashboard_management", "sys.dashboard_management.test_sql"],
    }
    assert default_permission_evaluator(user, "dashboard_management.view") is True
    assert default_permission_evaluator(user, "dashboard_management.test_sql") is True
    assert default_permission_evaluator(user, "dashboard_management.manage") is False
```

- [ ] **Step 5: 增加显式权限映射并运行测试**

```python
"dashboard_management.view": "sys.dashboard_management",
"dashboard_management.manage": "sys.dashboard_management.manage",
"dashboard_management.test_sql": "sys.dashboard_management.test_sql",
```

Run: `python -m pytest -q tests/test_capabilities.py tests/module_system/test_collaboration.py`

Expected: PASS。

---

### Task 2: 让模块导航合并到现有系统管理组

**Files:**
- Modify: `src/auto_check/web/module_host.js`
- Modify: `src/auto_check/web/module_host.css`
- Test: `tests/module_system/test_frontend_host.py`
- Test: `tests/test_web_static.py`

**Interfaces:**
- Consumes: 模块清单导航的 `group_id`、`group_label`、`group_order`。
- Produces: `renderNavigation()` 对已有 `[data-nav-group="system-management"]` 的通用合并行为；动态节点统一带 `data-module-merged-navigation` 便于清理。

- [ ] **Step 1: 写系统管理组合并场景测试**

构造已有传统导航组与一个模块导航项：

```javascript
const module = makeModule({
  id: "dashboard_management",
  navigation: [{
    id: "dashboard-management",
    label: "看板管理",
    route: "dashboard-management",
    order: 60,
    group_id: "system-management",
    group_label: "系统管理",
    group_order: 90,
  }],
});
await host.initialize(platform);
assert.equal(legacySystemMenu.querySelectorAll('[data-module-route="dashboard-management"]').length, 1);
assert.equal(moduleTopNavigation.querySelectorAll('[data-module-group-toggle="system-management"]').length, 0);
```

再覆盖重复初始化、退出登录清理、模块停用清理、激活后传统父组高亮，以及非匹配组仍在模块挂载点独立渲染。

- [ ] **Step 2: 运行测试确认当前会生成重复系统管理组**

Run: `python -m pytest -q tests/module_system/test_frontend_host.py -k "navigation and system"`

Expected: FAIL，模块入口未进入传统系统管理子菜单。

- [ ] **Step 3: 实现通用合并与清理函数**

在 `module_host.js` 增加以下内部边界：

```javascript
function legacyGroupMenus(groupId) {
  return [...documentRef.querySelectorAll(`[data-nav-group="${groupId}"]`)]
    .map((group) => group.querySelector(".top-nav-submenu, .nav-submenu"))
    .filter(Boolean);
}

function clearMergedNavigation() {
  documentRef.querySelectorAll("[data-module-merged-navigation]")
    .forEach((item) => item.remove());
}

function mergeGroupNavigation(group) {
  const menus = legacyGroupMenus(group.id);
  if (!menus.length) return false;
  menus.forEach((menu) => group.children.forEach((entry) => {
    const item = createNavigationItem(entry, { subitem: true });
    item.dataset.moduleMergedNavigation = group.id;
    menu.appendChild(item);
  }));
  return true;
}
```

`renderNavigation()` 先 `clearMergedNavigation()`；对组调用 `mergeGroupNavigation(item)`，返回 False 时才按原逻辑创建独立模块组。`setModuleNavigationActive()` 同时扫描模块挂载点和合并节点，并将相应传统父组设为 active/open。

- [ ] **Step 4: 扩展事件委托覆盖合并节点**

把模块路由点击监听从单一 `moduleTopNavigation` 扩展到 document 范围，但只接受 `[data-module-route]`，并在 `unload()` 中移除监听，防止影响传统导航。

- [ ] **Step 5: 运行宿主与静态回归测试**

Run: `python -m pytest -q tests/module_system/test_frontend_host.py tests/test_web_static.py -k "module or navigation or system_management"`

Expected: PASS；传统页面顺序和已有模块导航不变。

---

### Task 3: 建立模块清单、内置目录、迁移与仓储

**Files:**
- Create: `src/auto_check/modules/dashboard_management/__init__.py`
- Create: `src/auto_check/modules/dashboard_management/manifest.json`
- Create: `src/auto_check/modules/dashboard_management/module.py`
- Create: `src/auto_check/modules/dashboard_management/catalog.py`
- Create: `src/auto_check/modules/dashboard_management/contracts.py`
- Create: `src/auto_check/modules/dashboard_management/storage.py`
- Create: `src/auto_check/modules/dashboard_management/migrations/001_initial.sql`
- Create: `tests/modules/dashboard_management/__init__.py`
- Create: `tests/modules/dashboard_management/test_manifest_and_migrations.py`
- Create: `tests/modules/dashboard_management/test_catalog.py`
- Create: `tests/modules/dashboard_management/test_storage.py`

**Interfaces:**
- Produces: `BOARD_CATALOG`、`BUILTIN_REGION_SEEDS`、`BUILTIN_FIELD_SEEDS`；`DashboardManagementStorage` 的目录与配置读写接口。
- Consumes: `ModuleContext.application_database`、模块迁移与 schema 注册协议。

- [ ] **Step 1: 写清单和内置目录失败测试**

```python
def test_builtin_catalog_has_two_boards_ten_regions_and_twenty_one_fields():
    assert [board.code for board in BOARD_CATALOG] == ["report_submission", "reporting_process"]
    assert len(BUILTIN_REGION_SEEDS) == 10
    assert len(BUILTIN_FIELD_SEEDS) == 21
    trust = next(item for item in BUILTIN_REGION_SEEDS if item.code == "monthly_trust_projects")
    assert trust.shape == "list"
    assert trust.system_supported is False
```

清单测试断言 `required=false`、API 前缀 `/api/modules/dashboard-management`、导航组 `system-management`、三个模块权限和 schema version 1。

- [ ] **Step 2: 运行目录测试确认失败**

Run: `python -m pytest -q tests/modules/dashboard_management/test_manifest_and_migrations.py tests/modules/dashboard_management/test_catalog.py`

Expected: FAIL，模块尚不存在。

- [ ] **Step 3: 定义不可变内置目录**

`catalog.py` 使用冻结 dataclass：

```python
@dataclass(frozen=True)
class BoardSeed:
    code: str
    name: str
    display_order: int

@dataclass(frozen=True)
class RegionSeed:
    board_code: str
    code: str
    name: str
    shape: Literal["scalar", "list"]
    system_supported: bool
    default_mode: Literal["system", "sql"]
    display_order: int
    description: str

@dataclass(frozen=True)
class FieldSeed:
    region_code: str
    alias: str
    name: str
    value_type: str
    nullable: bool
    display_order: int
    description: str
```

内置字段别名使用稳定 snake_case，例如月度信托区域为 `month`、`single_trust_count`、`collective_trust_count`、`property_trust_count`。

- [ ] **Step 4: 写迁移与 schema 注册测试**

验证三张表及关键列：

```python
expected = {
    "dashboard_management_regions": {"id", "board_code", "region_code", "shape", "built_in", "enabled", "system_supported", "display_order", "row_version"},
    "dashboard_management_fields": {"id", "region_id", "field_alias", "value_type", "nullable", "built_in", "enabled", "display_order", "row_version"},
    "dashboard_management_source_configs": {"region_id", "source_mode", "datasource_id", "sql_text", "tested_signature", "tested_at", "row_version"},
}
```

迁移只创建上述模块前缀表，不触碰核心或其他模块表。

- [ ] **Step 5: 实现仓储接口并写并发测试**

实现以下精确接口：`seed_builtin_catalog() -> None`、`list_regions(board_code, include_disabled=True) -> list[dict[str, Any]]`、`get_region(region_id) -> dict[str, Any] | None`、`create_region(values) -> dict[str, Any]`、`update_region(region_id, values, expected_version) -> dict[str, Any]`、`list_fields(region_id, include_disabled=True) -> list[dict[str, Any]]`、`create_field(region_id, values) -> dict[str, Any]`、`update_field(field_id, values, expected_version) -> dict[str, Any]`、`get_source_config(region_id) -> dict[str, Any] | None`、`save_source_config(region_id, values, expected_version) -> dict[str, Any]`。

所有更新使用 `row_version` 乐观锁。内置目录通过幂等 upsert 补齐但不覆盖管理员可调整的启用状态和排序。

- [ ] **Step 6: 运行模块仓储测试**

Run: `python -m pytest -q tests/modules/dashboard_management/test_manifest_and_migrations.py tests/modules/dashboard_management/test_catalog.py tests/modules/dashboard_management/test_storage.py`

Expected: PASS。

---

### Task 4: 实现数据区域与字段维护服务和 API

**Files:**
- Create: `src/auto_check/modules/dashboard_management/validator.py`
- Create: `src/auto_check/modules/dashboard_management/service.py`
- Create: `src/auto_check/modules/dashboard_management/api.py`
- Modify: `src/auto_check/modules/dashboard_management/module.py`
- Test: `tests/modules/dashboard_management/test_service.py`
- Test: `tests/modules/dashboard_management/test_api.py`
- Test: `tests/modules/dashboard_management/test_validator_and_permissions.py`

**Interfaces:**
- Consumes: Task 3 的仓储方法。
- Produces: 目录读取、区域 CRUD、字段 CRUD、数据源摘要 API；统一 `DomainError` 响应协议。

- [ ] **Step 1: 写验证器失败测试**

覆盖：固定 board code、区域名称 1-100 字、字段别名正则 `^[a-z][a-z0-9_]{0,63}$`、支持的六种类型、显示顺序 0-9999、至少一个启用字段、自定义区域只允许 SQL。

```python
def test_builtin_region_identity_cannot_change(service, admin):
    region = service.catalog("report_submission", admin)["regions"][0]
    with pytest.raises(ValidationError, match="内置数据区域编码不可修改"):
        service.update_region(region["id"], {"region_code": "changed", "row_version": 1}, admin)
```

- [ ] **Step 2: 运行服务测试确认失败**

Run: `python -m pytest -q tests/modules/dashboard_management/test_service.py tests/modules/dashboard_management/test_validator_and_permissions.py`

Expected: FAIL，服务和验证器尚未实现。

- [ ] **Step 3: 实现服务公开方法**

实现以下精确接口：`catalog(board_code, current_user) -> dict[str, Any]`、`create_region(board_code, payload, current_user) -> dict[str, Any]`、`update_region(region_id, payload, current_user) -> dict[str, Any]`、`create_field(region_id, payload, current_user) -> dict[str, Any]`、`update_field(field_id, payload, current_user) -> dict[str, Any]`、`list_datasources() -> list[dict[str, str]]`。

创建自定义区域时由后端生成 `custom_region_<12 hex>`；创建字段时保留用户提交的稳定别名。任何字段集合变化调用仓储清空 `tested_signature/tested_at/tested_by`。

- [ ] **Step 4: 写并实现模块 API**

注册：

```text
GET  /boards
GET  /boards/{board_code}/catalog
POST /boards/{board_code}/regions
PUT  /regions/{region_id}
POST /regions/{region_id}/fields
PUT  /fields/{field_id}
GET  /datasources
```

GET 使用 `dashboard_management.view`；写操作使用 `dashboard_management.manage`。请求体最大 64 KiB，列表接口不返回主机、端口、用户名和密码。

- [ ] **Step 5: 运行服务、权限与 API 测试**

Run: `python -m pytest -q tests/modules/dashboard_management/test_service.py tests/modules/dashboard_management/test_validator_and_permissions.py tests/modules/dashboard_management/test_api.py`

Expected: PASS，401/403/400/409/500 均返回脱敏结构。

---

### Task 5: 实现 SQL 只读测试、字段校验和配置保存

**Files:**
- Create: `src/auto_check/modules/dashboard_management/sql_executor.py`
- Modify: `src/auto_check/modules/dashboard_management/service.py`
- Modify: `src/auto_check/modules/dashboard_management/api.py`
- Test: `tests/modules/dashboard_management/test_sql_executor.py`
- Test: `tests/modules/dashboard_management/test_sql_preview_api.py`

**Interfaces:**
- Consumes: 系统 `load_data_sources()` 返回的 `DataSourceEntry`、当前区域启用字段、Task 3 来源配置仓储。
- Produces: `SqlPreviewExecutor.execute()`、`service.test_sql()`、`service.save_source_config()`。

- [ ] **Step 1: 写 SQL 安全失败测试**

```python
@pytest.mark.parametrize("sql", [
    "DELETE FROM t",
    "SELECT 1; SELECT 2",
    "WITH changed AS (UPDATE t SET x=1 RETURNING *) SELECT * FROM changed",
    "CALL refresh_dashboard()",
])
def test_preview_rejects_non_readonly_sql(sql, executor):
    with pytest.raises(ValidationError, match="只允许单条只读查询"):
        executor.execute(source, sql, fields, shape="list")
```

同时测试重复列名、缺列、标量多行、整数/小数/布尔/日期/日期时间转换、11 行截断、PostgreSQL statement timeout、MySQL read timeout 和异常脱敏。

- [ ] **Step 2: 运行执行器测试确认失败**

Run: `python -m pytest -q tests/modules/dashboard_management/test_sql_executor.py`

Expected: FAIL，执行器尚不存在。

- [ ] **Step 3: 实现预览值对象与执行器**

```python
@dataclass(frozen=True)
class QueryPreview:
    columns: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]
    has_more: bool
    returned_count: int
    tested_signature: str
```

`SqlPreviewExecutor` 的构造签名固定为 `SqlPreviewExecutor(connect_timeout_seconds=5, query_timeout_seconds=10, preview_limit=10)`；公开方法固定为 `execute(source: DataSourceConfig, sql: str, fields: Sequence[FieldSpec], shape: str) -> QueryPreview`。

执行器复用 `ensure_select_only()`，PostgreSQL 连接设置只读事务和 `statement_timeout=10000`，MySQL 使用 `read_timeout=10` 并以只读会话执行；游标只 `fetchmany(11)`。签名使用数据源 ID、规范化 SQL、启用字段别名/类型/空值规则的 SHA-256。

- [ ] **Step 4: 实现测试和保存 API**

```text
POST /regions/{region_id}/source/test
PUT  /regions/{region_id}/source
```

测试请求使用 `dashboard_management.test_sql`；保存使用 `dashboard_management.manage`。保存 SQL 时重新计算签名并要求与最近一次成功测试签名一致，否则返回 409 `sql_retest_required`。

- [ ] **Step 5: 运行 SQL 与 API 测试**

Run: `python -m pytest -q tests/modules/dashboard_management/test_sql_executor.py tests/modules/dashboard_management/test_sql_preview_api.py tests/modules/dashboard_management/test_api.py`

Expected: PASS。

---

### Task 6: 实现两个看板分离的前端页面与目录维护

**Files:**
- Create: `src/auto_check/modules/dashboard_management/web/index.js`
- Create: `src/auto_check/modules/dashboard_management/web/api.js`
- Create: `src/auto_check/modules/dashboard_management/web/state.js`
- Create: `src/auto_check/modules/dashboard_management/web/styles.css`
- Create: `src/auto_check/modules/dashboard_management/web/components/dom.js`
- Create: `src/auto_check/modules/dashboard_management/web/components/dashboard_tabs.js`
- Create: `src/auto_check/modules/dashboard_management/web/components/region_list.js`
- Create: `src/auto_check/modules/dashboard_management/web/components/catalog_dialog.js`
- Create: `src/auto_check/modules/dashboard_management/web/components/source_editor.js`
- Create: `src/auto_check/modules/dashboard_management/web/components/preview_table.js`
- Test: `tests/modules/dashboard_management/test_frontend_static.py`
- Test: `tests/modules/dashboard_management/test_frontend_behavior.py`

**Interfaces:**
- Consumes: Task 4/5 模块 API。
- Produces: `mount(context)`、`activate(route)`、`deactivate()`、`unmount()` 模块生命周期；与效果图一致的双页签配置页面。

- [ ] **Step 1: 写前端静态契约失败测试**

检查所有 CSS 选择器以 `.auto-check-module[data-module="dashboard_management"]` 为顶层作用域；禁止无作用域 `button/input/table/.card`；检查两个固定看板名称、`新增数据区域`、`新增字段`、`测试执行`、`保存配置`、`结果预览（前 10 行）` 和生命周期导出。

- [ ] **Step 2: 写 Node 行为场景失败测试**

覆盖：

```javascript
assert.equal(state.activeBoardCode, "report_submission");
clickTab("reporting_process");
assert.deepEqual(visibleRegionNames(), ["监管报送报表数量", "当月监管报送报表时间", "报表校验统计"]);
assert.equal(
  queryTextFor("report_submission"),
  "SELECT report_type, COUNT(*) AS report_count FROM report_source GROUP BY report_type",
);
```

另测页签状态隔离、区域选择、系统/SQL 切换、系统区域新增字段提示、SQL 修改清除测试状态、最多 10 行预览、未保存离开确认、权限禁用、AbortController 清理。

- [ ] **Step 3: 实现状态与 API 层**

```javascript
export function createState() {
  return {
    activeBoardCode: "report_submission",
    selectedRegionByBoard: new Map(),
    catalogs: new Map(),
    drafts: new Map(),
    previews: new Map(),
    dirtyRegions: new Set(),
    requestController: null,
  };
}
```

`api.js` 只负责路径拼接和 `context.api` 调用，不操作 DOM。

- [ ] **Step 4: 实现页面骨架和双看板页签**

按确认效果图实现：页头与说明、两个一级页签、左侧区域列表、右侧详情。切换页签从 `selectedRegionByBoard` 恢复各自选择，不复用另一看板草稿或预览。

- [ ] **Step 5: 实现区域和字段维护弹窗**

“新增数据区域”弹窗包含名称、单值/列表、说明和首批字段编辑器；“新增字段/管理字段”包含显示名、稳定别名、类型、可空、说明、顺序和启用状态。内置不可变字段禁用相应控件并给出原因。

- [ ] **Step 6: 实现来源编辑、测试与预览**

系统模式显示口径与可用状态；SQL 模式显示数据源选择、输出字段标签、SQL 编辑器、测试执行、保存配置、测试状态和前 10 行预览。主操作“测试执行”使用蓝渐变，其他按钮按语义使用纯色或描边。

- [ ] **Step 7: 运行前端模块测试**

Run: `python -m pytest -q tests/modules/dashboard_management/test_frontend_static.py tests/modules/dashboard_management/test_frontend_behavior.py`

Expected: PASS。

---

### Task 7: 集成、文档、完整验证与交付检查

**Files:**
- Create: `src/auto_check/modules/dashboard_management/README.md`
- Modify: `src/auto_check/modules/dashboard_management/manifest.json`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-09-14-dashboard-management-page-design.md`
- Test: `tests/modules/dashboard_management/test_module_integration.py`
- Test: `tests/module_system/test_packaging.py`

**Interfaces:**
- Consumes: Tasks 1-6 全部接口。
- Produces: 模块启停隔离、发布说明、最终测试证据和用户交付说明。

- [ ] **Step 1: 写模块集成失败测试**

测试真实 `ModuleRuntime` 发现模块、应用迁移、注册路由、公开清单、停用后 404、重新启用恢复、前端静态资源可读取，以及管理员能完整完成“新增区域 → 新增字段 → 测试 SQL → 保存配置”。

- [ ] **Step 2: 运行模块集成测试确认缺口**

Run: `python -m pytest -q tests/modules/dashboard_management/test_module_integration.py tests/module_system/test_packaging.py`

Expected: 首次运行暴露未接通的模块发现、schema 注册或资源清单问题；逐项修复后 PASS。

- [ ] **Step 3: 完成模块说明与更新日志**

`manifest.release_notes.version` 使用当前系统小版本口径，条目只描述模块自身功能，不写“系统优化及BUG修复”。`README.md` 详细说明两个看板分离、10 个内置区域、21 个内置字段、自定义区域/字段、来源模式与 SQL 安全边界。设计文档状态改为“已实施”，只在实现与设计一致后修改。

- [ ] **Step 4: 运行直接相关测试**

Run: `python -m pytest -q tests/modules/dashboard_management tests/module_system/test_frontend_host.py tests/module_system/test_collaboration.py tests/test_capabilities.py`

Expected: PASS。

- [ ] **Step 5: 运行全量测试**

Run: `python -m pytest -q`

Expected: PASS；若出现无关既有失败，保留原改动并单独记录失败用例和证据。

- [ ] **Step 6: 检查差异与空白错误**

Run: `git diff --check`

Expected: 无真实 whitespace error。

Run: `git status --short`

Expected: 仅包含平台导航/权限通用扩展、`dashboard_management` 模块、对应测试和文档；保留用户原有 `.dumate/`、`.zcode/` 等未跟踪内容，不纳入改动。

- [ ] **Step 7: 交付说明**

报告代码、配置/迁移、页面行为、权限、安全限制和实际测试输出。除非用户另行要求，不运行 Windows 打包脚本、不刷新 `dist/auto-check.exe`、不提交、不推送。

- [ ] **Step 8: 核对回滚路径**

通过模块运行时停用 `dashboard_management`，确认入口和模块 API 消失、三张模块配置表及其中数据保留；重新启用后确认目录与来源配置恢复可读。平台导航扩展的单独差异可回滚，且不会改变其他模块原有顶级导航渲染。
