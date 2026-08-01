# 自定义报表模块实施计划

> **For Codex:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task by task. 每个任务先写失败测试，再实现最小功能；完成一个里程碑后暂停评审，不跨里程碑提前开发。

**Goal:** 在标准模块宿主上交付可独立开发、加载、迁移、测试和停用的自定义报表模块，实现同一数据源内单表/多表字段拼接、预览、模板保存、查看和 CSV/XLSX 导出。

**Architecture:** 模块 ID 为 `custom_reports`，全部业务代码位于 `src/auto_check/modules/custom_reports/`，API 前缀为 `/api/modules/custom-reports`。前端只由模块清单加载，模块表只由模块迁移维护；不修改 `server.py`、`index.html`、`app.js`、`styles.css` 和现有业务模块。前端提交结构化定义，后端按元数据白名单验证并分别编译 PostgreSQL/MySQL 参数化 SQL，查询和导出使用模块自有的受限连接适配器。

**Tech Stack:** Python 3.12、现有模块宿主协议、SQLAlchemy Core、psycopg、PyMySQL、openpyxl、原生 ES Module、HTML/CSS、pytest。

---

## 0. 实施前置和固定边界

开始 Task 1 前必须确认：

- `docs/superpowers/plans/2026-07-31-modular-extension-host-implementation.md` 已完整实施并验收。
- 空白示例模块可以自动发现、执行独立迁移、注册 `/api/modules/*` 路由、加载模块前端资源并参与打包。
- 至少准备一个 PostgreSQL 和一个 MySQL 只读测试数据源。
- 准备 3～5 个真实报表示例及预期字段、关联和结果数量。

固定容量常量：

```python
MAX_TABLES = 5
MAX_COLUMNS = 50
MAX_JOIN_CONDITIONS = 5
PREVIEW_LIMIT = 100
DEFAULT_PAGE_SIZE = 50
QUERY_TIMEOUT_SECONDS = 30
METADATA_CACHE_SECONDS = 300
SYNC_EXPORT_ROWS = 20_000
MAX_EXPORT_ROWS = 500_000
EXPORT_CONCURRENCY = 2
EXPORT_TIMEOUT_SECONDS = 600
EXPORT_RETENTION_DAYS = 7
```

首期约束：

- 只支持同一数据源内明细报表。
- 只支持原始字段，不支持计算字段、聚合、分组、自由 SQL 和数据库函数。
- 只支持 `LEFT JOIN`、`INNER JOIN` 和等值关联，单条关联内条件以 `AND` 组合。
- 普通模式采用线性关联配置，关系图仅为高级模式。
- 模板可见范围只支持 `private` 和 `all`。
- PostgreSQL/MySQL 数据源账户必须只读；服务端仍需实施 SQL 白名单、超时、行数和并发限制。
- 模块不得调用 `DatabaseClient._connect` 等私有方法；连接、流式读取和取消适配保留在模块内。

## 1. 目标目录

```text
src/auto_check/modules/custom_reports/
├── __init__.py
├── manifest.json
├── module.py
├── constants.py
├── contracts.py
├── permissions.py
├── metadata.py
├── validator.py
├── sql_compiler.py
├── executor.py
├── diagnostics.py
├── storage.py
├── service.py
├── export_jobs.py
├── api.py
├── migrations/
│   └── 001_initial.sql
└── web/
    ├── index.js
    ├── api.js
    ├── store.js
    ├── styles.css
    ├── pages/
    │   ├── templates.js
    │   ├── designer.js
    │   ├── viewer.js
    │   └── history.js
    └── components/
        ├── data_source_picker.js
        ├── join_editor.js
        ├── field_picker.js
        ├── filter_editor.js
        ├── result_table.js
        └── export_panel.js

tests/modules/custom_reports/
├── conftest.py
├── test_module.py
├── test_contracts.py
├── test_storage.py
├── test_permissions.py
├── test_metadata.py
├── test_validator.py
├── test_sql_compiler.py
├── test_executor.py
├── test_diagnostics.py
├── test_service.py
├── test_api.py
├── test_export_jobs.py
├── test_frontend_static.py
└── test_acceptance.py
```

## Task 1：建立标准模块骨架和空页面

**Files:**

- Create: `src/auto_check/modules/custom_reports/__init__.py`
- Create: `src/auto_check/modules/custom_reports/manifest.json`
- Create: `src/auto_check/modules/custom_reports/module.py`
- Create: `src/auto_check/modules/custom_reports/web/index.js`
- Create: `src/auto_check/modules/custom_reports/web/styles.css`
- Create: `tests/modules/custom_reports/test_module.py`
- Create: `tests/modules/custom_reports/test_frontend_static.py`

- [ ] **Step 1: 写失败测试**

测试模块可被宿主发现，清单满足：`id=custom_reports`、`platform_api=1`、`api_prefix=/api/modules/custom-reports`、资源位于 `/module-assets/custom_reports/`、权限至少包含 `custom_reports.view`。验证 `register_routes()`、`register_schema()`、`start()`、`stop()`、`health()` 均符合宿主协议。

- [ ] **Step 2: 运行失败测试**

```powershell
python -m pytest tests/modules/custom_reports/test_module.py tests/modules/custom_reports/test_frontend_static.py -q
```

Expected: FAIL，模块文件尚不存在。

- [ ] **Step 3: 实现最小模块**

模块先只注册 `GET /health` 和空白导航页。前端 `mount(context)` 只在宿主分配的根节点内渲染，`unmount()` 清理事件和 DOM；CSS 顶层选择器固定为 `.custom-report-module`，不得出现无作用域的 `button`、`table`、`input` 等选择器。

- [ ] **Step 4: 验证**

```powershell
python -m pytest tests/modules/custom_reports/test_module.py tests/modules/custom_reports/test_frontend_static.py -q
```

Expected: PASS。

## Task 2：定义报表协议、枚举和容量限制

**Files:**

- Create: `src/auto_check/modules/custom_reports/constants.py`
- Create: `src/auto_check/modules/custom_reports/contracts.py`
- Create: `tests/modules/custom_reports/test_contracts.py`

- [ ] **Step 1: 写失败测试**

覆盖 `ReportDefinitionV1` 的解析、序列化和拒绝逻辑。定义至少包含：

- `schema_version=1`
- `data_source_id`
- `base_table`
- `tables[]`：稳定节点 ID、schema、table、alias
- `joins[]`：left node、right node、join type、conditions
- `columns[]`：node ID、column、label、format、visible、exportable
- `filters[]`：fixed/default/runtime、operator、typed value
- `sorts[]`
- `display`
- `export`

必须拒绝未知 schema 版本、重复节点/别名、超过容量、空列、原始 SQL、计算表达式和任意函数。

- [ ] **Step 2: 运行失败测试**

```powershell
python -m pytest tests/modules/custom_reports/test_contracts.py -q
```

Expected: FAIL。

- [ ] **Step 3: 实现不可变协议对象**

使用冻结 dataclass/枚举，所有外部 JSON 经显式解析；不把原始字典直接传入 SQL 层。保存时输出稳定字段顺序并计算 definition fingerprint。

- [ ] **Step 4: 验证**

```powershell
python -m pytest tests/modules/custom_reports/test_contracts.py -q
```

Expected: PASS。

## Task 3：建立模块迁移、仓储和细粒度权限

**Files:**

- Create: `src/auto_check/modules/custom_reports/migrations/001_initial.sql`
- Create: `src/auto_check/modules/custom_reports/storage.py`
- Create: `src/auto_check/modules/custom_reports/permissions.py`
- Create: `tests/modules/custom_reports/test_storage.py`
- Create: `tests/modules/custom_reports/test_permissions.py`
- Modify: `src/auto_check/modules/custom_reports/module.py`

- [ ] **Step 1: 写迁移和仓储失败测试**

验证迁移创建：

- `custom_report_templates`
- `custom_report_template_versions`
- `custom_report_runs`
- `custom_report_export_jobs`
- `custom_report_user_permissions`

验证模板编码唯一、同模板版本唯一、发布版本归属正确、审计记录不级联删除。权限表包含 `can_design`、`can_publish`、`can_export`、`can_admin`、`allowed_data_source_ids_json`。

- [ ] **Step 2: 写权限失败测试**

规则固定为：系统管理员拥有全部能力；普通用户默认仅可读取对其公开且数据源在白名单内的已发布模板；设计、发布、导出和报表管理均需模块权限表明确授权。所有业务路由可以使用宿主的 `custom_reports.view` 粗粒度鉴权，但服务方法必须再次执行模块细粒度校验。

- [ ] **Step 3: 运行失败测试**

```powershell
python -m pytest tests/modules/custom_reports/test_storage.py tests/modules/custom_reports/test_permissions.py -q
```

Expected: FAIL。

- [ ] **Step 4: 实现迁移和仓储**

使用 SQLAlchemy Core 和现有 `ApplicationDatabase` 事务入口。模块表迁移只操作 `custom_report_*` 表，迁移版本为 1；不得修改全局 `EXPECTED_APP_SCHEMA` 或 `CURRENT_APP_SCHEMA_VERSION`。

- [ ] **Step 5: 验证**

```powershell
python -m pytest tests/modules/custom_reports/test_storage.py tests/modules/custom_reports/test_permissions.py -q
```

Expected: PASS。

## Task 4：实现 PostgreSQL/MySQL 元数据服务

**Files:**

- Create: `src/auto_check/modules/custom_reports/metadata.py`
- Create: `tests/modules/custom_reports/test_metadata.py`

- [ ] **Step 1: 写失败测试**

覆盖数据源列表、schema、表/视图、字段、注释、数据库类型、可空、主键、唯一索引和外键。验证密码不会进入返回值、日志和缓存键，禁用或未授权数据源返回权限错误。验证 300 秒缓存、手动刷新及数据源配置变化后失效。

- [ ] **Step 2: 运行失败测试**

```powershell
python -m pytest tests/modules/custom_reports/test_metadata.py -q
```

Expected: FAIL。

- [ ] **Step 3: 实现两种方言适配器**

PostgreSQL 查询 `information_schema` 和 `pg_catalog`；MySQL 查询 `information_schema`。所有标识符先保留为结构化值，元数据阶段不生成 SQL 片段。连接只在调用范围内存在，使用现有配置解密能力但不复制明文凭据。

- [ ] **Step 4: 验证**

```powershell
python -m pytest tests/modules/custom_reports/test_metadata.py -q
```

Expected: PASS。

## Task 5：实现单表定义和权限校验器

**Files:**

- Create: `src/auto_check/modules/custom_reports/validator.py`
- Create: `tests/modules/custom_reports/test_validator.py`

- [ ] **Step 1: 写失败测试**

覆盖：数据源权限、表/字段白名单、字段类型与操作符、运行参数类型、排序字段、展示/导出字段、容量限制。单表阶段遇到任何 join 均返回“当前阶段未开放多表”，遇到不存在/改名/类型变化的字段返回可定位错误，不生成 SQL。

- [ ] **Step 2: 运行失败测试**

```powershell
python -m pytest tests/modules/custom_reports/test_validator.py -q
```

Expected: FAIL。

- [ ] **Step 3: 实现校验器**

校验结果包含结构化 `errors[]`、`warnings[]` 和标准化定义；错误项含 `code`、`path`、`message`，前端不得解析数据库异常文本。

- [ ] **Step 4: 验证**

```powershell
python -m pytest tests/modules/custom_reports/test_validator.py -q
```

Expected: PASS。

## Task 6：实现单表安全 SQL 编译器

**Files:**

- Create: `src/auto_check/modules/custom_reports/sql_compiler.py`
- Create: `tests/modules/custom_reports/test_sql_compiler.py`

- [ ] **Step 1: 写失败测试**

分别断言 PostgreSQL/MySQL 的标识符引用、参数占位、空值、IN、BETWEEN、LIKE、日期、布尔、排序、LIMIT/OFFSET。输入包含引号、注释符、分号或 SQL 关键字时只能作为参数值，不能改变 SQL 结构。

- [ ] **Step 2: 运行失败测试**

```powershell
python -m pytest tests/modules/custom_reports/test_sql_compiler.py -q
```

Expected: FAIL。

- [ ] **Step 3: 实现编译器**

编译器只接收 Task 5 的标准化定义和元数据快照，输出 `CompiledQuery(sql, parameters, selected_columns, fingerprint)`。表、字段和排序方向必须来自枚举/白名单；值全部参数化，不接受调用方传入 SQL 片段。

- [ ] **Step 4: 验证**

```powershell
python -m pytest tests/modules/custom_reports/test_sql_compiler.py -q
```

Expected: PASS。

## Task 7：实现有界查询执行、超时和取消

**Files:**

- Create: `src/auto_check/modules/custom_reports/executor.py`
- Create: `tests/modules/custom_reports/test_executor.py`

- [ ] **Step 1: 写失败测试**

覆盖 `fetch_page()`、`iter_rows()`、连接关闭、30 秒超时、最大行数、取消、异常脱敏和并发查询句柄清理。验证预览永远不超过 100 行，流式迭代不调用 `fetchall()`。

- [ ] **Step 2: 运行失败测试**

```powershell
python -m pytest tests/modules/custom_reports/test_executor.py -q
```

Expected: FAIL。

- [ ] **Step 3: 实现专用连接适配器**

PostgreSQL 使用 psycopg 游标、事务只读和 `connection.cancel()`；MySQL 使用 PyMySQL 流式游标及独立连接关闭/`KILL QUERY` 能力。查询句柄以不可猜测 ID 注册，取消前校验操作者或管理员权限。禁止复用查询连接执行应用数据库写入。

- [ ] **Step 4: 验证**

```powershell
python -m pytest tests/modules/custom_reports/test_executor.py -q
```

Expected: PASS。

## Task 8：完成单表后端闭环和 API

**Files:**

- Create: `src/auto_check/modules/custom_reports/service.py`
- Create: `src/auto_check/modules/custom_reports/api.py`
- Create: `tests/modules/custom_reports/test_service.py`
- Create: `tests/modules/custom_reports/test_api.py`
- Modify: `src/auto_check/modules/custom_reports/module.py`

- [ ] **Step 1: 写失败测试**

覆盖元数据、未保存定义校验/预览、创建模板、保存草稿、模板列表/详情、运行已发布模板、分页、取消。验证未发布模板不能被非所有者运行，越权统一返回 403，非法定义返回 400，不存在返回 404，数据库内部错误不泄露。

- [ ] **Step 2: 运行失败测试**

```powershell
python -m pytest tests/modules/custom_reports/test_service.py tests/modules/custom_reports/test_api.py -q
```

Expected: FAIL。

- [ ] **Step 3: 实现服务和相对路由**

注册 `/metadata/*`、`/query/validate`、`/query/preview`、`/templates/*`、`/runs/*`。修改类请求继续使用宿主会话和 CSRF 防护。API 层只做 JSON 转换，业务状态、权限和事务归 service/storage。

- [ ] **Step 4: 里程碑 M1 后端验证**

```powershell
python -m pytest tests/modules/custom_reports/test_contracts.py tests/modules/custom_reports/test_storage.py tests/modules/custom_reports/test_permissions.py tests/modules/custom_reports/test_metadata.py tests/modules/custom_reports/test_validator.py tests/modules/custom_reports/test_sql_compiler.py tests/modules/custom_reports/test_executor.py tests/modules/custom_reports/test_service.py tests/modules/custom_reports/test_api.py -q
```

Expected: PASS。

## Task 9：完成单表设计器前端

**Files:**

- Create: `src/auto_check/modules/custom_reports/web/api.js`
- Create: `src/auto_check/modules/custom_reports/web/store.js`
- Create: `src/auto_check/modules/custom_reports/web/pages/templates.js`
- Create: `src/auto_check/modules/custom_reports/web/pages/designer.js`
- Create: `src/auto_check/modules/custom_reports/web/components/data_source_picker.js`
- Create: `src/auto_check/modules/custom_reports/web/components/field_picker.js`
- Create: `src/auto_check/modules/custom_reports/web/components/filter_editor.js`
- Modify: `src/auto_check/modules/custom_reports/web/index.js`
- Modify: `src/auto_check/modules/custom_reports/web/styles.css`
- Modify: `tests/modules/custom_reports/test_frontend_static.py`

- [ ] **Step 1: 写失败静态/Node 测试**

验证模块只使用宿主上下文和自身根节点，API 均以 `/api/modules/custom-reports` 开头，卸载时清理监听器。六步流程为：基本信息、数据源与主表、关联表、展示字段、筛选排序、预览保存；单表阶段第 3 步显示“暂不添加关联表”。

- [ ] **Step 2: 实现模板列表和设计器**

遵循现有亮色活力主题、`--ui-radius` 及主题变量；只有实心主操作按钮使用 `#3466D9` 到 `#6AA4FF` 渐变，危险操作使用红色，警告同时含图标和文字，悬浮不使用光晕。

- [ ] **Step 3: 验证**

```powershell
python -m pytest tests/modules/custom_reports/test_frontend_static.py -q
```

Expected: PASS。

手工验收：新建单表模板、选字段、加参数、预览 100 行、保存草稿，刷新后可继续编辑。

## Task 10：完成已发布模板查看和分页

**Files:**

- Create: `src/auto_check/modules/custom_reports/web/pages/viewer.js`
- Create: `src/auto_check/modules/custom_reports/web/components/result_table.js`
- Modify: `src/auto_check/modules/custom_reports/web/index.js`
- Modify: `tests/modules/custom_reports/test_frontend_static.py`
- Modify: `tests/modules/custom_reports/test_acceptance.py`

- [ ] **Step 1: 写失败测试**

覆盖运行参数校验、分页、排序、空结果、超时、取消、模板失效和字段变化提示。页面不得加载全部结果后再前端分页。

- [ ] **Step 2: 实现查看页**

查看页显示模板版本、参数区、条件摘要、结果表、总耗时和当前页；服务端无法低成本计算总数时不强制执行全量 count，仅显示“已加载行数/是否有下一页”。

- [ ] **Step 3: M1 验收**

```powershell
python -m pytest tests/modules/custom_reports -q
```

Expected: PASS。完成产品评审后再进入多表关联。

## Task 11：实现多表关联校验和 SQL 编译

**Files:**

- Modify: `src/auto_check/modules/custom_reports/validator.py`
- Modify: `src/auto_check/modules/custom_reports/sql_compiler.py`
- Modify: `tests/modules/custom_reports/test_validator.py`
- Modify: `tests/modules/custom_reports/test_sql_compiler.py`

- [ ] **Step 1: 写失败测试**

覆盖 2～5 表、`LEFT JOIN`/`INNER JOIN`、每条 1～5 个等值条件、稳定别名、同名字段、复合键。拒绝跨数据源、孤立节点、重复边、自连接未使用不同节点 ID、类型族不兼容、无条件 JOIN、RIGHT/FULL/CROSS JOIN。

- [ ] **Step 2: 实现关联图校验**

所有节点必须从主表可达。普通线性模式新增表必须连接到已存在节点；高级关系图可编辑任意合法边，但保存前执行同一服务端验证。

- [ ] **Step 3: 实现方言 JOIN 编译**

字段引用始终使用节点别名，多个条件以 `AND` 组合；列别名由服务端生成唯一稳定值，前端标签不参与 SQL 标识符。

- [ ] **Step 4: 验证**

```powershell
python -m pytest tests/modules/custom_reports/test_validator.py tests/modules/custom_reports/test_sql_compiler.py -q
```

Expected: PASS。

## Task 12：实现关联诊断和风险门槛

**Files:**

- Create: `src/auto_check/modules/custom_reports/diagnostics.py`
- Create: `tests/modules/custom_reports/test_diagnostics.py`
- Modify: `src/auto_check/modules/custom_reports/service.py`
- Modify: `src/auto_check/modules/custom_reports/api.py`

- [ ] **Step 1: 写失败测试**

基于受限样本统计主表样本数、关联后样本数、匹配率、未匹配率和膨胀倍数。缺少唯一约束或样本显示多对多时产生警告；超过配置阈值时普通设计人员不能发布，报表管理员确认后才可覆盖。

- [ ] **Step 2: 实现有界诊断**

诊断 SQL 也必须来自结构化编译器，受同样的超时、取消和参数化限制。诊断失败不应返回原始数据库错误，但必须阻止未经确认的高风险发布。

- [ ] **Step 3: 验证**

```powershell
python -m pytest tests/modules/custom_reports/test_diagnostics.py tests/modules/custom_reports/test_service.py tests/modules/custom_reports/test_api.py -q
```

Expected: PASS。

## Task 13：实现模板发布、版本、回退和权限治理

**Files:**

- Modify: `src/auto_check/modules/custom_reports/storage.py`
- Modify: `src/auto_check/modules/custom_reports/permissions.py`
- Modify: `src/auto_check/modules/custom_reports/service.py`
- Modify: `src/auto_check/modules/custom_reports/api.py`
- Modify: `tests/modules/custom_reports/test_storage.py`
- Modify: `tests/modules/custom_reports/test_permissions.py`
- Modify: `tests/modules/custom_reports/test_service.py`
- Modify: `tests/modules/custom_reports/test_api.py`

- [ ] **Step 1: 写失败测试**

覆盖复制、发布、停用、恢复、回退、不可变历史版本、私有/公开可见范围、所有者、数据源白名单、管理员配置报表权限。发布时保存 definition/metadata fingerprint；表或字段变化后运行返回“模板配置已失效”，不自动替换字段。

- [ ] **Step 2: 实现状态机**

允许状态：`draft -> published -> disabled`；编辑已发布模板创建新草稿版本，回退产生新的发布版本而不是修改旧记录。模板编码创建后不可变。

- [ ] **Step 3: 验证**

```powershell
python -m pytest tests/modules/custom_reports/test_storage.py tests/modules/custom_reports/test_permissions.py tests/modules/custom_reports/test_service.py tests/modules/custom_reports/test_api.py -q
```

Expected: PASS。

## Task 14：实现 CSV/XLSX 导出任务

**Files:**

- Create: `src/auto_check/modules/custom_reports/export_jobs.py`
- Create: `tests/modules/custom_reports/test_export_jobs.py`
- Modify: `src/auto_check/modules/custom_reports/service.py`
- Modify: `src/auto_check/modules/custom_reports/api.py`
- Modify: `src/auto_check/modules/custom_reports/module.py`

- [ ] **Step 1: 写失败测试**

覆盖小于等于 20,000 行同步导出、超过阈值后台导出、500,000 行上限、2 个并发、10 分钟超时、取消、7 天过期清理、文件名净化、下载权限、失败重试边界。验证 CSV 逐批写入，XLSX 使用 `write_only=True`，不调用 `list(iterator)` 或 `fetchall()`。

- [ ] **Step 2: 运行失败测试**

```powershell
python -m pytest tests/modules/custom_reports/test_export_jobs.py -q
```

Expected: FAIL。

- [ ] **Step 3: 实现导出服务**

导出只包含 `exportable=true` 字段。CSV 使用 UTF-8 BOM；XLSX 单工作表超过 Excel 行上限前按工作表拆分，仍受 500,000 行业务上限。文件路径必须位于模块专用临时目录，下载前重新校验任务所有者或管理员权限。

- [ ] **Step 4: 实现任务恢复和清理**

模块启动时把进程中断遗留的 `running` 任务标记为失败或可重试；定期清理过期文件和记录。模块停止时取消待执行任务并关闭查询连接。

- [ ] **Step 5: 验证**

```powershell
python -m pytest tests/modules/custom_reports/test_export_jobs.py tests/modules/custom_reports/test_executor.py tests/modules/custom_reports/test_api.py -q
```

Expected: PASS。

## Task 15：完成多表设计、发布、导出和历史前端

**Files:**

- Create: `src/auto_check/modules/custom_reports/web/components/join_editor.js`
- Create: `src/auto_check/modules/custom_reports/web/components/export_panel.js`
- Create: `src/auto_check/modules/custom_reports/web/pages/history.js`
- Modify: `src/auto_check/modules/custom_reports/web/pages/designer.js`
- Modify: `src/auto_check/modules/custom_reports/web/pages/viewer.js`
- Modify: `src/auto_check/modules/custom_reports/web/index.js`
- Modify: `src/auto_check/modules/custom_reports/web/styles.css`
- Modify: `tests/modules/custom_reports/test_frontend_static.py`
- Modify: `tests/modules/custom_reports/test_acceptance.py`

- [ ] **Step 1: 写失败测试**

验证线性新增关联表是默认入口；高级关系图可切换但不是强制。关联诊断必须显示匹配率、未匹配率、膨胀倍数和文字警告。验证发布确认、导出格式、进度、取消、失败、下载和历史记录。

- [ ] **Step 2: 实现交互**

前端只保存结构化定义。任何后端校验错误均定位到六步设计器的具体步骤和字段；不得把 SQL、数据库账号或内部异常显示给用户。

- [ ] **Step 3: M2/M3 前端验收**

```powershell
python -m pytest tests/modules/custom_reports/test_frontend_static.py tests/modules/custom_reports/test_acceptance.py -q
```

Expected: PASS。

手工验收：完成两表、三表、五表报表各一份；验证 LEFT/INNER 结果、风险警告、发布、普通用户查看和 CSV/XLSX 导出。

## Task 16：安全、性能和跨数据库集成验收

**Files:**

- Modify: `tests/modules/custom_reports/test_acceptance.py`
- Create: `tests/modules/custom_reports/test_integration_postgresql.py`
- Create: `tests/modules/custom_reports/test_integration_mysql.py`
- Create: `docs/custom-report-performance-verification.zh-CN.md`

- [ ] **Step 1: 建立验收数据集**

两种数据库使用等价结构，覆盖复合主键、唯一索引、外键、无外键、中文列名、保留字列名、NULL、日期/时间、decimal、大文本和 10 万行数据。

- [ ] **Step 2: 执行安全测试**

覆盖 SQL 注入、越权模板 ID、越权导出 ID、路径穿越、CSRF、日志脱敏、错误脱敏、恶意文件名、并发耗尽和取消后连接释放。

- [ ] **Step 3: 执行性能测试**

记录单表和 2/3/5 表预览耗时、内存峰值、10 万行 CSV/XLSX 导出耗时和内存、取消生效时间。任何超出固定边界的结果必须先形成风险说明和调整方案，不能静默放宽限制。

- [ ] **Step 4: 运行模块和全量测试**

```powershell
python -m pytest tests/modules/custom_reports -q
python -m pytest -q
git diff --check
```

Expected: 全部 PASS，`git diff --check` 无实际 whitespace error。

测试和验证按项目约定优先交由后台子任务执行，主会话负责审阅结果和补充检查。除非用户明确要求交付可执行程序，本计划不运行 Windows 打包，也不刷新 `dist/auto-check.exe`。

## Task 17：文档、试运行和正式交付

**Files:**

- Create: `docs/custom-report-user-guide.zh-CN.md`
- Create: `docs/custom-report-operations.zh-CN.md`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-07-31-custom-report-designer-design.md`
- Modify: `docs/superpowers/plans/2026-07-31-custom-report-designer-project-plan.md`
- Modify: `docs/superpowers/plans/2026-07-31-custom-report-module-implementation.md`

- [ ] **Step 1: 完成用户和运维文档**

用户文档覆盖设计、关联、诊断、发布、查看和导出。运维文档覆盖模块启停、迁移、权限、容量参数、任务恢复、文件清理、数据源只读账号、故障诊断和回滚。

- [ ] **Step 2: 同步版本说明**

README 记录详细功能、限制和行为变化。由于本项目明确采用“新增模块不修改现有模块代码”，不修改 `src/auto_check/web/app.js` 的全局更新日志；模块内帮助页和模块文档承担本模块版本说明。若产品负责人要求全局更新日志展示，应作为独立平台变更评审，不混入报表业务提交。

- [ ] **Step 3: 试运行**

选取 3～5 个真实报表，至少包含单表、两表和三表；连续试运行不少于 5 个工作日，记录正确性、性能、权限、导出和模板变更问题。高风险问题清零后进入正式验收。

- [ ] **Step 4: 最终验收**

```powershell
python -m pytest tests/modules/custom_reports -q
python -m pytest -q
git diff --check
```

验收标准：

- 单表和 2～5 表明细报表结果与基准 SQL 一致。
- PostgreSQL/MySQL 均通过元数据、预览、分页、取消和导出验证。
- 模板草稿、发布、复制、停用、回退和历史审计完整。
- 普通用户无法越权设计、发布、查看或下载。
- 大数据导出内存有界、可取消、可清理。
- 删除整个 `src/auto_check/modules/custom_reports/` 后，现有模块业务代码无需修复；重新放回后可由宿主自动发现。
- 报表模块实现期间没有修改 `server.py`、`index.html`、`app.js`、`styles.css` 和其他业务模块。

## 里程碑映射

| 里程碑 | 包含任务 | 出口 |
|---|---|---|
| 前置门 | 模块宿主独立计划 | 零改动示例模块通过发现、迁移、加载、鉴权、任务和打包验收 |
| M0 技术验证 | Task 1～7 的技术样例 | 两种数据库元数据、参数化 SQL、流式读取、超时和取消成立 |
| M1 单表闭环 | Task 8～10 | 单表设计、预览、保存、发布、查看和分页可验收 |
| M2 多表关联 | Task 11～12 | 2～5 表关联、诊断和风险门槛可验收 |
| M3 生产化 | Task 13～15 | 权限、版本、回退、后台导出和历史可验收 |
| M4 上线 | Task 16～17 | 全量测试、试运行、文档和最终验收通过 |

## 实施协作建议

- 后端 A：Task 2、4～8、11～12。
- 后端 B/平台集成人员：Task 3、13～14，并审查迁移、权限和后台任务。
- 前端：Task 1 的前端部分、Task 9～10、15。
- 测试：从 Task 1 同步维护验收用例，主导 Task 16。
- 产品/业务：每个里程碑提供真实报表并签署出口标准。

多人并行时仅在任务文件集不重叠时并行。`contracts.py`、`service.py`、`api.py`、`module.py` 属于阶段共享文件，应由当前里程碑的一名负责人合并；公共宿主文件不属于任何报表开发人员的修改范围。

## 暂缓项

以下能力不插入首期：跨数据源 JOIN、计算字段、聚合和分组、图表/仪表盘、自由 SQL、定时报表、订阅推送、快照、组织/用户组授权、逐模板用户授权、数据血缘和查询成本优化器。新增其中任何一项，都需要单独范围变更、数据模型和安全评审。
