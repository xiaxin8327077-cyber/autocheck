# AutoCheck External Read-only Dashboard API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. The user explicitly requires inline execution and forbids subagents/DSH. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为两个固定监管看板提供带 Bearer Token 的外部只读接口，同时保持内部模块预览接口兼容。

**Architecture:** 平台为模块路由增加显式 `external=True` 的 GET-only 协议、独立 external preflight/dispatch 和通用 Token 认证入口；看板模块单独登记预览路由并在服务层固定内置区域白名单。平台不知道看板业务，模块不能借此外露管理路由。

**Tech Stack:** Python 3.12、`http.server`、现有模块运行时、pytest、Markdown。

## Global Constraints

- 只修改 `D:\xiaxin\auto_check`，不得修改 `D:\xiaxin\kanban`。
- 保留当前工作区既有看板修改和原型目录用户改动。
- 使用 `apply_patch` 修改文件，使用 `rg` 搜索，PowerShell 使用 `pwsh -NoLogo -NoProfile`。
- 新生产行为先写失败测试并观察预期失败。
- 不开放 CORS；Token 不进入浏览器代码。
- 不修改顶栏大版本号。
- 不打包、不提交、不推送。

---

### Task 1: 扩展模块外部只读路由协议

**Files:**

- Modify: `tests/module_system/test_routing.py`
- Modify: `tests/module_system/test_runtime.py`
- Modify: `src/auto_check/app/module_system/routing.py`
- Modify: `src/auto_check/app/module_system/runtime.py`

**Interfaces:**

- Produces: `ModuleRouter.add(..., external: bool = False)`
- Produces: `ModuleRouter.external_preflight(method, path)`
- Produces: `ModuleRouter.dispatch_external(request)`
- Produces: `ModuleRuntime.external_preflight(method, path)`
- Produces: `ModuleRuntime.dispatch_external(method, path, query)`

- [ ] **Step 1: 写失败测试**

测试显式外部 GET 可通过 `/api/external/v1/custom-reports/...` 分发；普通 GET 在外部路径返回 404；`external=True` 的 POST 登记抛出 `ValueError`；内部路径仍执行权限判断。

- [ ] **Step 2: 验证 RED**

Run:

```powershell
python -m pytest tests/module_system/test_routing.py tests/module_system/test_runtime.py -q
```

Expected: 新测试因缺少 external 参数或方法失败。

- [ ] **Step 3: 最小实现**

给 `_ModuleRoute` 增加 `external: bool`。登记时校验 `external` 必须为布尔值且只允许 GET。external preflight/dispatch 只选择 `route.external`，并把 `/api/external/v1/<module-prefix>` 映射为模块相对路径；外部分发不调用 permission evaluator。运行时只枚举 enabled 且非 transitioning 的模块路由。

- [ ] **Step 4: 验证 GREEN**

Run 同 Step 2，Expected: PASS。

---

### Task 2: 接入通用 HTTP Bearer Token 认证

**Files:**

- Modify: `tests/module_system/test_server_integration.py`
- Modify: `src/auto_check/app/server.py`

**Interfaces:**

- Consumes: `AUTO_CHECK_EXTERNAL_API_TOKEN`
- Produces: `/api/external/v1/<module-prefix>/<relative-path>`

- [ ] **Step 1: 写失败测试**

在 alpha 测试模块显式登记 `/external`。测试 Token 未配置为 503；缺失/错误为 401 且有 `WWW-Authenticate: Bearer`；正确 Token 为 200；普通内部路由在 external 命名空间为 404；POST 为 405；所有响应 `Cache-Control: no-store`；内部会话接口不变。

- [ ] **Step 2: 验证 RED**

Run:

```powershell
python -m pytest tests/module_system/test_server_integration.py -q
```

Expected: 外部路径尚未绕过 Session 并返回目标状态。

- [ ] **Step 3: 最小实现**

在 `_handle_api()` 的网页登录检查前委派 `_handle_external_module_api()`。按“Token 配置 → Authorization 格式和值 → external preflight → external dispatch”顺序处理；使用 `secrets.compare_digest()`；401 增加 challenge；所有出口加 `Cache-Control: no-store`。平台代码不得出现 board code。

- [ ] **Step 4: 验证 GREEN**

Run 同 Step 2，Expected: PASS。

---

### Task 3: 实现两个固定看板的稳定外部响应

**Files:**

- Modify: `tests/modules/dashboard_management/test_api.py`
- Modify: `tests/modules/dashboard_management/test_service.py`
- Modify: `tests/modules/dashboard_management/test_module_integration.py`
- Modify: `src/auto_check/modules/dashboard_management/api.py`
- Modify: `src/auto_check/modules/dashboard_management/service.py`

**Interfaces:**

- Produces: `DashboardManagementService.preview_external_board_data(board_code)`
- Produces: 外部 `GET /api/external/v1/dashboard-management/boards/{board_code}/preview`

- [ ] **Step 1: 写失败测试**

测试两个 board code 可访问；非法 code 为 404；外部区域严格等于 `BUILTIN_REGION_SEEDS` 的固定顺序；自定义区域不出现；结果包含顶层 `status`、`generated_at` 和 `meta.request_id`；单区域失败为 HTTP 200 + `partial`；内部 `preview_board_data()` 仍包含启用自定义区域。

- [ ] **Step 2: 验证 RED**

Run:

```powershell
python -m pytest tests/modules/dashboard_management/test_api.py tests/modules/dashboard_management/test_service.py tests/modules/dashboard_management/test_module_integration.py -q
```

Expected: 缺少外部服务和路由响应契约。

- [ ] **Step 3: 最小实现**

从 `BUILTIN_REGION_SEEDS` 计算每个看板固定编码；重用一个私有预览实现，并让外部调用传入固定编码过滤器和 `built_in` 检查。外部 API 使用一次请求时间生成 `generated_at`，根据区域错误计算 `success/partial`，保持日期和 datetime 的 ISO 8601 序列化。

- [ ] **Step 4: 验证 GREEN**

Run 同 Step 2，Expected: PASS。

---

### Task 4: 完成接口与对接文档、模块说明和版本记录

**Files:**

- Create: `docs/dashboard-management-external-api.zh-CN.md`
- Modify: `src/auto_check/modules/dashboard_management/README.md`
- Modify: `src/auto_check/modules/dashboard_management/manifest.json`
- Modify: `README.md`
- Modify: `docs/module-development-guide.zh-CN.md`
- Modify: `tests/modules/dashboard_management/test_manifest_and_migrations.py`
- Modify: `tests/module_system/test_documentation.py`

- [ ] **Step 1: 写失败文档契约测试**

检查文档包含两个 URL、环境变量、curl、成功/partial/401/404/503 示例、10 个区域完整字段表、逐区域 month 格式、后端适配架构、超时/重试/缓存/request_id 建议；manifest release notes 包含外部接口说明。

- [ ] **Step 2: 验证 RED**

Run:

```powershell
python -m pytest tests/modules/dashboard_management/test_manifest_and_migrations.py tests/module_system/test_documentation.py -q
```

Expected: 文档或 release note 断言失败。

- [ ] **Step 3: 编写文档**

完整记录响应结构、字段类型和日期格式，不写真实 Token、密码、连接串或 `D:\xiaxin\kanban` 的实现细节。README 只增加入口和关键安全说明；模块清单保持 `1.2.27`，新增一条不重复的模块更新项。

- [ ] **Step 4: 验证 GREEN**

Run 同 Step 2，Expected: PASS。

---

### Task 5: 回归、全量验证和开发环境重启

- [ ] **Step 1: 运行模块相关测试**

```powershell
python -m pytest tests/module_system tests/modules/dashboard_management -q
```

- [ ] **Step 2: 运行全量测试**

```powershell
python -m pytest -q
```

Expected: 全部 PASS，跳过数无异常增长。

- [ ] **Step 3: 检查差异**

```powershell
git diff --check
git status --short
```

确认没有修改 `D:\xiaxin\kanban` 和已标注的原型目录文件。

- [ ] **Step 4: 重启与 HTTP 冒烟**

识别 8765 当前监听进程和启动命令，只终止属于本工作区的 AutoCheck 开发进程；用原配置和临时 `AUTO_CHECK_EXTERNAL_API_TOKEN` 重启。验证端口 8765、无 Token 401、错误 Token 401、正确 Token 调用两个看板为 200。另用隔离的短时测试进程验证环境变量未配置时 503，避免破坏最终运行实例。

- [ ] **Step 5: 交付检查**

不运行打包脚本，不创建 commit，不推送远端；汇总代码、配置、文档、行为变化及所有实际测试证据。
