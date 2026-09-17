# 两个监管看板接口专属 Token 管理实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task with review checkpoints.

日期：2026-09-16
依据：[看板外部接口专属 Token 管理设计](../specs/2026-09-16-dashboard-scoped-token-management-design.md)
状态：待实施

## 目标

让 AutoCheck 管理员在现有“系统管理 → 看板管理 → 接口监控”页面生成或轮换一个一次性展示的 Bearer Token。该 Token 只能认证以下两个精确 GET 路由：

- `/api/external/v1/dashboard-management/boards/report_submission/preview`
- `/api/external/v1/dashboard-management/boards/reporting_process/preview`

不允许该 Token 访问第三个看板、动态看板路由、其他外部接口、内部模块接口、监控接口、Token 管理接口、登录接口或其他功能。

## 实施约束

- 严格限定在平台通用外部路由认证能力和看板管理模块，不改变两个目标看板之外的业务行为。
- 先写失败测试，再写最小实现；每个任务完成后做代码审查检查点。
- 明文 Token 只在成功生成响应和当前一次性弹窗中短暂存在；数据库、日志、调用记录、浏览器存储均不得保存明文。
- 数据库管理 Token 优先；只有尚未生成数据库 Token 时，才兼容 `AUTO_CHECK_EXTERNAL_API_TOKEN`。
- 管理端不提供“录入已有 Token”。生产部署后由生产管理员重新生成。
- 不自动打包 `dist\auto-check.exe`，不提交、不推送。
- 工作区已有大量未提交改动，实施时只增量修改列明文件，禁止回退或格式化无关文件。

## 任务 1：为外部路由增加通用、逐路由认证契约

**文件**

- 修改：`src/auto_check/app/module_system/routing.py`
- 修改：`src/auto_check/app/module_system/runtime.py`
- 测试：`tests/module_system/test_routing.py`
- 测试：`tests/module_system/test_runtime.py`

### 1.1 先补失败测试

在 `test_routing.py` 覆盖：

1. `external=True` 的路由必须显式登记认证器。
2. 内部路由不得登记外部认证器。
3. `external_preflight()` 返回命中的认证器，但不调用认证器。
4. 未知路径返回 `None`；路径存在但方法不允许时仍保留 `Allow` 信息。
5. 两条外部路由登记不同认证器时，各自只返回自己的认证器。

在 `test_runtime.py` 覆盖运行时向 HTTP 层透传认证器，不改变内部路由分发、权限判断和模块生命周期。

先运行：

```powershell
python -m pytest tests/module_system/test_routing.py tests/module_system/test_runtime.py -q
```

预期：新增断言失败，证明当前平台还不支持逐路由认证器。

### 1.2 实现最小通用契约

在 `routing.py` 增加不可变结果类型：

```python
@dataclass(frozen=True)
class ExternalAuthDecision:
    configured: bool
    authenticated: bool


ExternalRouteAuthenticator = Callable[[str], ExternalAuthDecision]
```

扩展 `_ModuleRoute` 和 `ModuleRoutePreflight`：

```python
external_authenticator: ExternalRouteAuthenticator | None
```

扩展 `ModuleRouter.add()`：

```python
def add(
    self,
    method: str,
    path: str,
    handler: ModuleHandler,
    *,
    permission: str,
    max_body_bytes: int = 0,
    external: bool = False,
    external_authenticator: ExternalRouteAuthenticator | None = None,
) -> None:
```

注册规则：

- `external=True`：仅允许 GET，且必须提供可调用认证器。
- `external=False`：`external_authenticator` 必须为 `None`。
- 认证器只作为元数据返回，路由匹配、预检和分发阶段不主动执行。

运行时只透传 `ModuleRoutePreflight`，不得引入看板编码、环境变量或 Token 逻辑。

### 1.3 验证与检查点

重新运行 1.1 命令，确认通过；审查 `routing.py` 和 `runtime.py` 中不得出现 `dashboard_management`、`report_submission`、`reporting_process`。

## 任务 2：调整 HTTP 外部入口，并升级兼容环境变量服务

**文件**

- 修改：`src/auto_check/app/external_api.py`
- 修改：`src/auto_check/app/server.py`
- 测试：`tests/test_platform_services.py`
- 测试：`tests/test_server.py`
- 测试：`tests/module_system/test_server_integration.py`

### 2.1 先补失败测试

平台服务测试覆盖：

- `platform.external_api_status` v2 仍可返回是否配置环境变量。
- 新增 `verify_candidate(candidate: str) -> bool`，使用恒定时间比较。
- 空值和错误值失败，正确值成功；服务永不返回原始 Token。

HTTP 入口测试覆盖以下顺序：

1. 先做精确路由预检；未知路由返回 404，不调用任何认证器。
2. 路径存在但方法错误返回 405 和 `Allow`，不调用认证器。
3. 已匹配路由未配置凭据时返回 503 `external_api_disabled`。
4. 缺失、重复、非 Bearer、空 Bearer 或错误 Token 返回 401，并包含 `WWW-Authenticate: Bearer`。
5. 正确 Token 才进入模块 handler。
6. 一个认证器通过，不代表其他认证器或其他路由通过。
7. 401、404、405、503 不产生看板业务调用记录。

先运行：

```powershell
python -m pytest tests/test_platform_services.py tests/test_server.py tests/module_system/test_server_integration.py -q
```

### 2.2 实现平台服务 v2

保持 `read_external_api_token()` 作为兼容读取器，为 facade 增加：

```python
class ExternalApiStatusFacade:
    def get_status(self) -> ExternalApiStatusSnapshot: ...
    def verify_candidate(self, candidate: str) -> bool: ...
```

`verify_candidate()` 内部每次读取当前环境变量，使用 `secrets.compare_digest()` 比较，不暴露值、长度或摘要。`server.py` 不再直接导入或读取 `read_external_api_token()`。

平台启动注册该服务的版本由 1 升至 2；保留 v1 所需的 `get_status()` 行为，避免现有调用方失效。

### 2.3 重排 HTTP 入口认证顺序

`_handle_external_module_api()` 必须按以下顺序执行：

```text
external_preflight
  ├─ 无路径匹配 -> 404
  ├─ 有路径但方法不匹配 -> 405 + Allow
  └─ 精确路由命中 -> 解析 Authorization
                          -> 调用该路由认证器
                          -> 503 / 401 / dispatch_external
```

只向认证器传递解析后的候选 Token 字符串；不传会话、请求体、查询参数或完整请求头。异常统一脱敏为 503，不回显内部异常。

### 2.4 验证与检查点

运行 2.1 命令并审查：

- `server.py` 没有看板业务硬编码。
- 外部路由未命中时不会先暴露 Token 配置状态。
- 旧的全局 Token 检查已删除，未来外部路由必须自带认证器。

## 任务 3：实现看板模块专属凭据表、仓储与服务

**文件**

- 新增：`src/auto_check/modules/dashboard_management/migrations/004_external_api_credentials.sql`
- 新增：`src/auto_check/modules/dashboard_management/external_api_credentials.py`
- 新增：`tests/modules/dashboard_management/test_external_api_credentials.py`
- 修改：`tests/modules/dashboard_management/test_manifest_and_migrations.py`

### 3.1 先补失败测试

新测试覆盖：

- 无数据库凭据且无环境变量时，状态为 `configured=False, source="none"`。
- 无数据库凭据但环境变量存在时，状态为 `configured=True, source="environment"`。
- 首次生成返回 URL-safe 明文、`rotated=False`，仓储只收到 SHA-256 十六进制摘要和短指纹。
- 已有数据库凭据再生成返回 `rotated=True`，旧摘要被单事务替换。
- 数据库写入失败时不返回候选 Token，旧摘要保持不变。
- `authenticate()` 对数据库摘要使用 `secrets.compare_digest`；数据库凭据存在时不再接受环境变量。
- 无数据库凭据时，环境变量验证只通过 v2 facade 的 `verify_candidate()`。
- 状态和异常文本不包含明文、摘要、长度或候选值。

迁移测试覆盖 schema 版本 4、文件连续性、表名归属看板模块、摘要字段必填且不存在明文字段。

先运行：

```powershell
python -m pytest tests/modules/dashboard_management/test_external_api_credentials.py tests/modules/dashboard_management/test_manifest_and_migrations.py -q
```

### 3.2 增加模块表

表名固定为：

```text
dashboard_management_external_api_credentials
```

字段：

```sql
scope_key VARCHAR(128) PRIMARY KEY,
token_digest CHAR(64) NOT NULL,
token_fingerprint VARCHAR(16) NOT NULL,
created_by VARCHAR(128) NOT NULL,
created_at DATETIME(6) NOT NULL,
updated_by VARCHAR(128) NOT NULL,
updated_at DATETIME(6) NOT NULL
```

固定作用域值使用模块内常量，例如 `dashboard_management.board_preview`。禁止增加 `token`、`plaintext_token` 或可还原密文列。

### 3.3 实现仓储与领域服务

定义：

```python
@dataclass(frozen=True)
class ExternalApiCredentialStatus:
    configured: bool
    source: Literal["managed", "environment", "none"]


@dataclass(frozen=True)
class GeneratedExternalApiToken:
    token: str
    generated_at: datetime
    rotated: bool
```

仓储只暴露读取当前摘要和原子替换摘要的方法。服务提供：

```python
def status(self) -> ExternalApiCredentialStatus: ...
def authenticate(self, candidate: str) -> ExternalAuthDecision: ...
def generate(self, operator: str) -> GeneratedExternalApiToken: ...
```

生成算法：

1. 调用 `secrets.token_urlsafe(32)`。
2. 计算 `hashlib.sha256(token.encode("utf-8")).hexdigest()`。
3. 生成非敏感短指纹，仅供内部审计；前端状态接口不返回指纹。
4. 在单个事务内插入或替换固定作用域记录。
5. 提交成功后才构造并返回含明文的结果。

### 3.4 验证与检查点

运行 3.1 命令，并用搜索确认仓储、日志和监控模型不存在明文 Token 字段。

## 任务 4：将 Token 服务绑定到两个精确外部接口

**文件**

- 修改：`src/auto_check/modules/dashboard_management/api.py`
- 修改：`src/auto_check/modules/dashboard_management/module.py`
- 修改：`src/auto_check/modules/dashboard_management/external_api_monitoring.py`
- 修改：`src/auto_check/modules/dashboard_management/manifest.json`
- 修改：`src/auto_check/app/capabilities.py`
- 测试：`tests/modules/dashboard_management/test_api.py`
- 测试：`tests/modules/dashboard_management/test_module_integration.py`
- 测试：`tests/modules/dashboard_management/test_external_api_monitoring.py`
- 测试：`tests/test_capabilities.py`

### 4.1 先补失败测试

覆盖：

- 外部仅注册两个精确 GET 路由，不再把 `/boards/{board_code}/preview` 发布为 external。
- 两个路由都使用同一个模块专属认证器。
- 第三个看板和任意未知编码返回 404。
- 内部登录态 `/boards/{board_code}/preview` 保持原权限和行为。
- `POST /external-api/token/generate` 只接受 `{}`，拒绝含 `token` 或任意多余字段的请求。
- 无登录、无 CSRF、普通用户、只有监控权限的用户均无法生成。
- 有 `dashboard_management.external_api_token_manage` 的管理员可生成；响应只有 `token`、`generated_at`、`rotated` 和既有响应包络。
- 监控摘要增加 `token_source`，不增加任何敏感字段。
- 两个精确接口继续记录认证成功后的调用方 IP；认证失败不进入调用记录。
- 模块启动、停止、健康检查同时覆盖凭据服务可用性。
- 能力码默认矩阵中仅管理员默认拥有 Token 管理能力。

先运行：

```powershell
python -m pytest tests/modules/dashboard_management/test_api.py tests/modules/dashboard_management/test_module_integration.py tests/modules/dashboard_management/test_external_api_monitoring.py tests/test_capabilities.py -q
```

### 4.2 拆分内外部预览 handler

保留内部动态路由：

```text
GET /boards/{board_code}/preview
```

新增两个显式外部注册：

```text
GET /boards/report_submission/preview
GET /boards/reporting_process/preview
```

每个外部 handler 由注册闭包固定 `board_code`，不得从 URL 接受其他值。两条路由均登记 `credential_service.authenticate`，继续复用现有预览转换和调用监控逻辑。

### 4.3 增加管理接口和权限

在模块权限中新增：

```text
dashboard_management.external_api_token_manage
```

在平台能力树中对应：

```text
sys.dashboard_management.external_api_token_manage
```

默认管理员启用，普通用户和自定义角色默认关闭。新增 POST 路由使用新权限，限制很小的请求体，并校验 JSON 必须严格等于 `{}`。

模块启动时：

- 解析 `platform.external_api_status` 最低版本 2。
- 建立凭据仓储与服务。
- 将凭据服务 provider 同时传给 API 和监控服务。
- schema registry 注册新表。
- stop 时清除服务引用，health 同时检查主服务、监控服务和凭据服务。

### 4.4 更新清单

`manifest.json`：

- 模块版本：`1.2.28`。
- schema version：`4`。
- 新增 Token 管理 permission。
- `platform.external_api_status` minimum version：`2`。
- release note 新增一条“管理员可为两个固定监管看板接口生成和轮换专属 Token”；不新增重复的通用修复文案。

### 4.5 验证与检查点

运行 4.1 命令，额外审查搜索结果，确保模块外没有写入两个看板编码，且 Token 管理权限不由监控权限隐式继承。

## 任务 5：实现一次性展示的管理员页面

**文件**

- 修改：`src/auto_check/modules/dashboard_management/web/api.js`
- 修改：`src/auto_check/modules/dashboard_management/web/index.js`
- 修改：`src/auto_check/modules/dashboard_management/web/components/external_api_monitor.js`
- 新增：`src/auto_check/modules/dashboard_management/web/components/external_api_token_dialog.js`
- 修改：`src/auto_check/modules/dashboard_management/web/styles.css`
- 测试：`tests/modules/dashboard_management/test_frontend_static.py`
- 测试：`tests/modules/dashboard_management/test_frontend_behavior.py`

### 5.1 先补失败测试

覆盖：

- API 客户端以 POST `{}` 调用 `/external-api/token/generate`。
- 无新权限时不渲染生成/轮换按钮。
- `token_source=none|environment|managed` 分别显示安全状态，不显示值、摘要或指纹。
- 未配置时按钮为“生成 Token”；已配置时为“轮换 Token”。
- 轮换前出现“旧 Token 将立即失效”的确认。
- 成功后弹窗只显示本次响应 Token，并有复制和“我已保存”操作。
- 弹窗关闭、Escape、模块停用、页面切换后，DOM 和内存引用中的 Token 被清空。
- 不调用 `localStorage.setItem`、`sessionStorage.setItem`，不把 Token 加入 URL、筛选状态或监控调用记录。
- 页面继续符合现有接口监控布局和系统圆角、按钮、响应式规范。

先运行：

```powershell
python -m pytest tests/modules/dashboard_management/test_frontend_static.py tests/modules/dashboard_management/test_frontend_behavior.py -q
```

### 5.2 实现 API 与权限入口

在 `api.js` 增加：

```javascript
generateExternalApiToken: () => request(
  "/external-api/token/generate",
  body("POST", {}),
),
```

在 `index.js` 单独判断：

```javascript
const canManageExternalApiToken = hasPermission(
  user,
  "dashboard_management.external_api_token_manage",
);
```

不把该权限与 `canManage` 或 `canMonitor` 合并。生成成功后刷新非敏感摘要；明文只传给本次弹窗实例。

### 5.3 实现弹窗和清理

`external_api_token_dialog.js` 使用现有对话框结构、焦点陷阱和 Escape 处理。内部只保存一个局部字符串引用；关闭函数先清空输入/文本节点和局部引用，再移除 DOM。

固定提示：

- 该 Token 仅适用于“金融监管报表报送大屏”和“金融监管报送流程大屏”两个接口。
- 关闭后无法再次查看。
- 生产环境上线后必须重新生成生产 Token。

复制使用 `navigator.clipboard.writeText()`，只复制当前一次性 Token；复制失败给出普通错误提示，不把 Token 写入替代存储。

样式只使用模块作用域选择器和全局主题变量：`--ui-radius`、主题色、现有语义色；不新增全局按钮覆盖、不使用光晕。

### 5.4 验证与检查点

运行 5.1 命令；人工代码审查确认明文不进入 `state.js` 的持久状态，不出现在监控摘要、调用记录或筛选参数中。

## 任务 6：更新接口文档、模块说明和版本说明

**文件**

- 修改：`docs/dashboard-management-external-api.zh-CN.md`
- 修改：`src/auto_check/modules/dashboard_management/README.md`
- 修改：`README.md`
- 如当前接口对接文档仍在仓库中，修改其对应 Token 管理章节，但不得改变已确认的数据契约。

### 6.1 文档内容

明确：

- 管理员生成位置和所需权限。
- 仅两个精确 GET 接口可用。
- 首次生成/轮换、一次性展示和旧 Token 立即失效规则。
- 生产环境单独生成，不录入或复用开发 Token。
- 环境变量仅是数据库尚无凭据时的兼容回退。
- `token_source` 三个值的含义。
- 401、404、405、503 的边界。
- 不影响其他看板、内部页面和其他模块。

`README.md` 记录详细行为变化；应用内更新日志只通过模块 manifest 聚合，不为此修改全局 `src/auto_check/web/app.js`。

### 6.2 文档检查点

搜索所有文档，删除“全局 Token”“所有外部接口共用”等与新边界冲突的说法；不得在文档中写入本机开发 Token 明文。

## 任务 7：安全审查与全量回归

**执行方式**

按用户偏好，将测试和验证委派给原生 Codex 子代理；主会话负责检查输出和处理必要修正。

### 7.1 定向回归

```powershell
python -m pytest tests/module_system/test_routing.py tests/module_system/test_runtime.py tests/module_system/test_server_integration.py tests/test_platform_services.py tests/test_server.py tests/test_capabilities.py tests/modules/dashboard_management -q
```

### 7.2 全量回归

```powershell
python -m pytest -q
git diff --check
```

### 7.3 敏感信息与越权搜索

检查：

```powershell
rg -n "<never-place-real-token-here>" .
rg -n "localStorage|sessionStorage|token_digest|token_fingerprint|external_api_token" src/auto_check/modules/dashboard_management tests/modules/dashboard_management
rg -n "report_submission|reporting_process|dashboard_management" src/auto_check/app
```

验收标准：

- 本机已生成过的开发 Token 不出现在源码、测试、文档、日志或数据库迁移中。
- 平台层不存在两个看板编码和模块表名。
- 只有两个精确外部 GET 路由接受模块专属 Token。
- 轮换后旧 Token 失效，数据库写入失败时旧 Token 保持有效。
- 监控页能生成/轮换并一次性复制，关闭后不能再次读取。
- 其他看板、其他模块、内部接口和原有功能测试无回归。

### 7.4 最终交付边界

- 不运行 Windows 打包脚本，不刷新 `dist\auto-check.exe`。
- 不创建提交，不推送 GitHub/Gitee。
- 汇报具体改动、测试结果、仍需用户执行的生产步骤。
- 生产上线后的用户动作仅为：管理员登录生产 AutoCheck → 生成生产 Token → 一次性安全提供给 Kanban → Kanban 配置后仅验证两个接口。
