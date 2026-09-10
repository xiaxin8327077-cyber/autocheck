# 报送管理模块基础、映射与报表生成实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立可加载的报送管理独立模块，实现七类报送的长期数据配置、原子映射快照、KJB/KTR/Spider 混合流程编排和独立报表生成记录。

**Architecture:** 模块通过四个版本化服务读取报送导航、数据源、Spider 流程并保存永久文件。模块数据库保存配置和不可变执行快照；Kettle 与 Spider 分别由适配器实现统一步骤协议，后台协调器按全局/报送维度信号量控制并发。

**Tech Stack:** Python 3.12、现有模块运行时与迁移器、PostgreSQL/MySQL、原生 JavaScript/CSS、pytest。

## Global Constraints

- 必须先完成并验收 `2026-09-08-regulatory-reporting-platform-services.md`。
- 模块根目录固定为 `src/auto_check/modules/regulatory_reporting/`，不把业务实现放入公共入口。
- 报送名单只来自 `platform.report_navigation` v1，不写第二份七项常量。
- 配置不跟报送期走；映射只服务报文生成，不参与 SQL 校验。
- KJB/KTR 文件只保存生产服务器上的远端标识，不提供上传、在线编辑或执行任意脚本。
- 生成成功可选择创建独立校验任务；模块基础层只发布回调/命令接口，不把两类记录合并。
- 默认并发：同一报送一个生成任务、Kettle 全局 2 步、Spider 全局 1 步。
- 取消不得重复提交或强杀已提交的 Spider `sp_task`。
- 不自动打包、不提交、不推送。

---

## 文件结构

### 模块骨架

- `src/auto_check/modules/regulatory_reporting/__init__.py`
- `src/auto_check/modules/regulatory_reporting/manifest.json`
- `src/auto_check/modules/regulatory_reporting/module.py`
- `src/auto_check/modules/regulatory_reporting/api.py`
- `src/auto_check/modules/regulatory_reporting/contracts.py`
- `src/auto_check/modules/regulatory_reporting/permissions.py`
- `src/auto_check/modules/regulatory_reporting/storage.py`
- `src/auto_check/modules/regulatory_reporting/service.py`
- `src/auto_check/modules/regulatory_reporting/migrations/001_foundation.sql`
- `src/auto_check/modules/regulatory_reporting/migrations/002_mapping.sql`
- `src/auto_check/modules/regulatory_reporting/migrations/003_generation.sql`

### 映射

- `src/auto_check/modules/regulatory_reporting/mapping/contracts.py`
- `src/auto_check/modules/regulatory_reporting/mapping/metadata_loader.py`
- `src/auto_check/modules/regulatory_reporting/mapping/matcher.py`
- `src/auto_check/modules/regulatory_reporting/mapping/service.py`
- `src/auto_check/modules/regulatory_reporting/mapping/storage.py`

### 混合流程

- `src/auto_check/modules/regulatory_reporting/workflow/contracts.py`
- `src/auto_check/modules/regulatory_reporting/workflow/kettle_adapter.py`
- `src/auto_check/modules/regulatory_reporting/workflow/spider_gateway.py`
- `src/auto_check/modules/regulatory_reporting/workflow/coordinator.py`
- `src/auto_check/modules/regulatory_reporting/workflow/recovery.py`
- `src/auto_check/modules/regulatory_reporting/workflow/storage.py`

### 测试

- `tests/modules/regulatory_reporting/test_manifest_and_migrations.py`
- `tests/modules/regulatory_reporting/test_permissions.py`
- `tests/modules/regulatory_reporting/test_profiles.py`
- `tests/modules/regulatory_reporting/test_mapping.py`
- `tests/modules/regulatory_reporting/test_workflow_configuration.py`
- `tests/modules/regulatory_reporting/test_kettle_adapter.py`
- `tests/modules/regulatory_reporting/test_workflow_execution.py`
- `tests/modules/regulatory_reporting/test_generation_api.py`

## 模块内部接口冻结

```python
# contracts.py
ReportFrequency = Literal["monthly", "quarterly", "semiannual", "annual", "custom"]

@dataclass(frozen=True)
class ReportProfile:
    report_code: str
    report_name: str
    data_source_id: str
    classification_id: str
    frequency: ReportFrequency
    custom_frequency: str
    config_version: int

@dataclass(frozen=True)
class GenerationRequest:
    report_code: str
    report_period: str
    auto_validate: bool
    actor_id: str
    actor_name: str

@dataclass(frozen=True)
class GenerationReference:
    run_id: str
```

```python
# workflow/contracts.py
StepKind = Literal["kjb", "ktr", "spider"]
FailurePolicy = Literal["stop", "continue"]
RunState = Literal["queued", "running", "succeeded", "failed", "cancelled", "interrupted", "unknown"]

@dataclass(frozen=True)
class WorkflowStepSnapshot:
    id: str
    name: str
    kind: StepKind
    remote_reference: str
    order: int
    enabled: bool
    parameter_mapping: dict[str, str]
    timeout_seconds: int
    failure_policy: FailurePolicy

@dataclass(frozen=True)
class StepStartContext:
    generation_run_id: str
    report_code: str
    report_period: str
    actor_name: str
    parameters: dict[str, str]

@dataclass(frozen=True)
class ExternalStepReference:
    provider: StepKind
    external_id: str

class StepAdapter(Protocol):
    def start(self, step: WorkflowStepSnapshot, context: StepStartContext) -> ExternalStepReference: ...
    def poll(self, reference: ExternalStepReference, after_log_cursor: int) -> tuple[RunState, int, tuple[dict[str, object], ...], int]: ...
    def cancel(self, reference: ExternalStepReference) -> RunState: ...
```

```python
# workflow/kettle_adapter.py
class KettleStepAdapter(StepAdapter):
    def __init__(self, facade: KettleExecutionFacade) -> None: ...
```

模块不构造 Authorization，不读取 Kettle 用户名、密码、base URL 或 HTTP 响应内部结构，只通过 `platform.kettle_execution` v1 调用。KJB/KTR 分别由平台使用 `executeJob/executeTrans` 启动、`jobStatus/transStatus` 读取状态和增量日志、`stopJob/stopTrans` 请求停止；模块只处理统一状态和日志游标。

## Task 1：模块骨架、能力码和基础迁移

**Files:**
- Create: 模块骨架文件及 `001_foundation.sql`
- Modify: `src/auto_check/app/capabilities.py`
- Test: `tests/modules/regulatory_reporting/test_manifest_and_migrations.py`
- Test: `tests/modules/regulatory_reporting/test_permissions.py`
- Modify Test: `tests/test_capabilities.py`
- Modify Test: `tests/test_role_capabilities_storage.py`

**Interfaces:**
- Consumes: `platform.report_navigation` v1、`platform.data_sources` v1、`platform.kettle_execution` v1、`platform.flow_execution` v1、`platform.artifact_storage` v1。
- Produces: 可加载模块、相对路由注册和十个能力码。

- [ ] **Step 1: 写 manifest 失败测试**

```python
def test_manifest_contract(manifest):
    assert manifest.id == "regulatory_reporting"
    assert manifest.required is False
    assert manifest.api_prefix == "/api/modules/regulatory-reporting"
    assert {item.name for item in manifest.service_dependencies} == {
        "platform.report_navigation", "platform.data_sources",
        "platform.kettle_execution", "platform.flow_execution", "platform.artifact_storage",
    }
```

同时断言导航只有一个“报送管理”入口，permission 为 `regulatory_reporting.view`。

- [ ] **Step 2: 写能力矩阵失败测试**

能力码固定为：

```python
REGULATORY_REPORTING_CAPABILITIES = (
    "regulatory_reporting.view",
    "regulatory_reporting.generate_report",
    "regulatory_reporting.stop_generation",
    "regulatory_reporting.run_validation",
    "regulatory_reporting.view_validation_details",
    "regulatory_reporting.generate_message",
    "regulatory_reporting.download_message",
    "regulatory_reporting.manage_report_config",
    "regulatory_reporting.manage_flow_config",
    "regulatory_reporting.manage_validation_config",
)
```

普通用户前五项为 true、后五项为 false；管理员全部为 true。自定义角色沿用默认用户矩阵，不得获得管理员默认配置权限。

- [ ] **Step 3: 运行失败测试**

Run: `python -m pytest tests/modules/regulatory_reporting/test_manifest_and_migrations.py tests/modules/regulatory_reporting/test_permissions.py tests/test_capabilities.py tests/test_role_capabilities_storage.py -q`

Expected: FAIL，模块和能力码尚不存在。

- [ ] **Step 4: 创建 manifest 与生命周期**

manifest 的 `schema_version` 先设为 3，`table_prefix` 为 `regulatory_reporting_`。`module.start()` 依次解析四个 facade，构造 storage/service/coordinator，注册相对 API；`module.stop()` 先拒绝新任务，再关闭协调器和 service facade。

- [ ] **Step 5: 创建基础表**

`001_foundation.sql` 创建：

- `regulatory_reporting_profiles`
- `regulatory_reporting_flow_definitions`
- `regulatory_reporting_flow_steps`

所有主键使用字符串 UUID；所有可变配置包含 `row_version`、`created_at/by`、`updated_at/by`。profile 以 `report_code` 唯一；flow step 以 `(flow_definition_id, order_no)` 唯一。

- [ ] **Step 6: 实现权限帮助函数**

```python
def require_permission(user: Mapping[str, object], capability: str) -> None:
    if capability not in tuple(user.get("capabilities") or ()):
        raise PermissionError("无权执行该操作")
```

每个 API handler 内再次调用，不只依赖前端显隐。

- [ ] **Step 7: 运行专项测试**

Run: `python -m pytest tests/modules/regulatory_reporting/test_manifest_and_migrations.py tests/modules/regulatory_reporting/test_permissions.py tests/test_capabilities.py tests/test_role_capabilities_storage.py -q`

Expected: PASS。

- [ ] **Step 8: 用户授权后提交检查点**

```powershell
git add src/auto_check/modules/regulatory_reporting src/auto_check/app/capabilities.py tests/modules/regulatory_reporting tests/test_capabilities.py tests/test_role_capabilities_storage.py
git commit -m "建立报送管理独立模块骨架"
```

## Task 2：七类报送资料与长期配置

**Files:**
- Create: `src/auto_check/modules/regulatory_reporting/contracts.py`
- Create: `src/auto_check/modules/regulatory_reporting/storage.py`
- Create: `src/auto_check/modules/regulatory_reporting/service.py`
- Modify: `src/auto_check/modules/regulatory_reporting/api.py`
- Test: `tests/modules/regulatory_reporting/test_profiles.py`
- Test: `tests/modules/regulatory_reporting/test_generation_api.py`

**Interfaces:**
- Consumes: `ReportNavigationFacade.list_report_processes()`、`DataSourcesFacade.list_sources()`。
- Produces: `ReportingService.catalog()`、`get_profile(report_code)`、`save_profile(command, actor)`。

- [ ] **Step 1: 写目录与保存失败测试**

断言 catalog 中报送列表与平台返回顺序和编码完全一致；不存在平台编码的保存请求返回 400；不存在数据源 ID 返回 400；`classification_id` 不能为空；custom 频率必须给出受控表达式，其他频率必须清空 custom_frequency。

- [ ] **Step 2: 运行失败测试**

Run: `python -m pytest tests/modules/regulatory_reporting/test_profiles.py tests/modules/regulatory_reporting/test_generation_api.py -q`

Expected: FAIL，profile service 尚不存在。

- [ ] **Step 3: 实现配置存储和乐观锁**

```python
@dataclass(frozen=True)
class SaveProfileCommand:
    report_code: str
    data_source_id: str
    classification_id: str
    frequency: ReportFrequency
    custom_frequency: str
    row_version: int | None
```

新建时 `row_version=1`；修改时 SQL 使用 `WHERE report_code=? AND row_version=?`，受影响行数为 0 返回 409。保存成功增加配置版本，但不自动删除旧映射。

- [ ] **Step 4: 实现 API**

固定路由：

- `GET /catalog`
- `GET /profiles/{report_code}`
- `PUT /profiles/{report_code}`

GET 需要 view，PUT 需要 manage_report_config；响应只返回数据源 ID/name/type，不返回连接信息。

- [ ] **Step 5: 运行专项测试**

Run: `python -m pytest tests/modules/regulatory_reporting/test_profiles.py tests/modules/regulatory_reporting/test_generation_api.py -q`

Expected: PASS。

## Task 3：分类编号驱动的原子映射快照

**Files:**
- Create: `src/auto_check/modules/regulatory_reporting/mapping/*.py`
- Create: `src/auto_check/modules/regulatory_reporting/migrations/002_mapping.sql`
- Modify: `src/auto_check/modules/regulatory_reporting/service.py`
- Modify: `src/auto_check/modules/regulatory_reporting/api.py`
- Test: `tests/modules/regulatory_reporting/test_mapping.py`

**Interfaces:**
- Consumes: `DataSourcesFacade.fetch/inspect/quote_identifier`；参考 `FieldMetadataLoader` 的 baseinfo→field_info 顺序。
- Produces: `MappingService.refresh(report_code, actor) -> MappingSnapshotSummary`、`current_snapshot(report_code)`、`list_tables(snapshot_id)`、`list_fields(snapshot_id, table_id)`。

- [ ] **Step 1: 写分类查询和失败回滚测试**

```python
def test_refresh_uses_classification_and_keeps_previous_snapshot_on_failure(service):
    first = service.refresh("pbc_detail", actor)
    gateway.fail_on_field_info = True
    with pytest.raises(RuntimeError):
        service.refresh("pbc_detail", actor)
    assert service.current_snapshot("pbc_detail").id == first.id
```

再断言请求只提供 classification ID，不接受用户传 table IDs。

- [ ] **Step 2: 运行失败测试**

Run: `python -m pytest tests/modules/regulatory_reporting/test_mapping.py -q`

Expected: FAIL，映射服务尚不存在。

- [ ] **Step 3: 创建映射表**

`002_mapping.sql` 创建 snapshots、mapping_tables、mapping_fields、mapping_overrides。snapshot 头保存 report_code、data_source_id、classification_id、profile_config_version、state、created_at/by；只有 `state='active'` 的一个快照通过事务切换为当前。

- [ ] **Step 4: 实现元数据加载**

查询顺序固定为：分类编号查询 `xt_reg_table_baseinfo` 得全部表 ID，再按表 ID 查询 `xt_reg_table_field_info` 得字段中英文名和顺序，最后用 information_schema 验证物理表/字段。表名配置沿用现有人行逐笔校验引擎的配置方式，不把 SQL 写死在页面。

- [ ] **Step 5: 实现自动匹配和人工覆盖**

自动匹配算法从 `src/auto_check/db_validation/metadata.py` 提取等价纯函数到模块自己的 matcher，不直接导入另一个业务模块。最终值优先级为 manual override > unique automatic match；冲突和缺失都保存明确状态，不能按列位置猜。

- [ ] **Step 6: 实现原子发布**

先在事务外收集和验证候选数据，再在一个应用数据库事务中写完整 snapshot/tables/fields，确认行数和唯一约束后切换 current；任何异常回滚整个候选快照。

- [ ] **Step 7: 实现 API 并测试**

固定路由：

- `POST /profiles/{report_code}/mapping/refresh`
- `GET /profiles/{report_code}/mapping/status`
- `GET /mapping/{snapshot_id}/tables`
- `GET /mapping/{snapshot_id}/tables/{table_id}/fields`
- `PUT /mapping/overrides/{override_id}`
- `DELETE /mapping/overrides/{override_id}`（含义为恢复自动值，不删除历史快照）

所有写操作需要 manage_report_config。

Run: `python -m pytest tests/modules/regulatory_reporting/test_mapping.py -q`

Expected: PASS。

## Task 4：流程定义和 Kettle/Spider 适配器

**Files:**
- Create: `src/auto_check/modules/regulatory_reporting/workflow/contracts.py`
- Create: `src/auto_check/modules/regulatory_reporting/workflow/kettle_adapter.py`
- Create: `src/auto_check/modules/regulatory_reporting/workflow/spider_gateway.py`
- Create: `src/auto_check/modules/regulatory_reporting/workflow/storage.py`
- Modify: `src/auto_check/modules/regulatory_reporting/service.py`
- Modify: `src/auto_check/modules/regulatory_reporting/api.py`
- Test: `tests/modules/regulatory_reporting/test_workflow_configuration.py`
- Test: `tests/modules/regulatory_reporting/test_kettle_adapter.py`

**Interfaces:**
- Consumes: `KettleExecutionFacade`、`FlowExecutionFacade`。
- Produces: `WorkflowRepository.get_active_snapshot(report_code)`、KJB/KTR/Spider 三个 `StepAdapter`。

- [ ] **Step 1: 写流程配置验证失败测试**

断言 kind 只允许 kjb/ktr/spider；order 连续且唯一；timeout 为 1..86400 秒；failure_policy 只允许 stop/continue；KJB/KTR 必须有 remote_reference，Spider reference 必须存在于平台流程目录。

- [ ] **Step 2: 写适配器契约失败测试**

Fake Kettle facade 返回 start/status/log/cancel 四种状态，断言统一映射为 `ExternalStepReference` 和 `RunState`；日志游标只能递增；模块请求不包含 base URL、Authorization 或凭据字段。

- [ ] **Step 3: 运行失败测试**

Run: `python -m pytest tests/modules/regulatory_reporting/test_workflow_configuration.py tests/modules/regulatory_reporting/test_kettle_adapter.py -q`

Expected: FAIL。

- [ ] **Step 4: 实现流程配置快照**

每次保存创建新的 definition version，并把步骤复制成不可变版本；运行只读取一个版本。API 固定为：

- `GET /profiles/{report_code}/workflow`
- `PUT /profiles/{report_code}/workflow`
- `GET /spider-flows?keyword=...`

读需要 view，写需要 manage_flow_config。

- [ ] **Step 5: 实现 Spider 适配器**

直接调用 `platform.flow_execution`，不复制 `DatabaseFlowGateway` 或 `run_flow_chain()`。取消语义原样传递并显示“只停止本地等待及后续提交”。

- [ ] **Step 6: 实现 Kettle 适配器**

KJB/KTR 分别把 remote_reference 和参数映射传给 `KettleStartRequest`，kind 固定为 kjb/ktr。实际 URL、Basic Auth、状态和日志解析全部由平台 facade 负责；模块只保存平台返回的 run_id。

- [ ] **Step 7: 运行专项测试**

Run: `python -m pytest tests/modules/regulatory_reporting/test_workflow_configuration.py tests/modules/regulatory_reporting/test_kettle_adapter.py -q`

Expected: PASS；没有 Pentaho 11 实测样例时报告“适配器契约完成，生产联调未完成”。

## Task 5：生成任务、恢复、日志和自动校验挂钩

**Files:**
- Create: `src/auto_check/modules/regulatory_reporting/migrations/003_generation.sql`
- Create: `src/auto_check/modules/regulatory_reporting/workflow/coordinator.py`
- Create: `src/auto_check/modules/regulatory_reporting/workflow/recovery.py`
- Modify: `src/auto_check/modules/regulatory_reporting/workflow/storage.py`
- Modify: `src/auto_check/modules/regulatory_reporting/service.py`
- Modify: `src/auto_check/modules/regulatory_reporting/api.py`
- Test: `tests/modules/regulatory_reporting/test_workflow_execution.py`
- Test: `tests/modules/regulatory_reporting/test_generation_api.py`

**Interfaces:**
- Consumes: 三个 `StepAdapter`、活动 workflow snapshot、模块 `background_executor`。
- Produces: `GenerationCoordinator.start(request) -> GenerationReference`、`status(run_id, after_log_id)`、`cancel(run_id)`、`recover_interrupted()`、`set_auto_validation_callback(callable)`。

- [ ] **Step 1: 写并发、策略和恢复失败测试**

覆盖同报送互斥、不同报送并行、Kettle 2/Spider 1 信号量、失败停止产生 skipped、失败继续执行下一步、取消、重启查询已提交 external_id 且不重复 start。

- [ ] **Step 2: 运行失败测试**

Run: `python -m pytest tests/modules/regulatory_reporting/test_workflow_execution.py tests/modules/regulatory_reporting/test_generation_api.py -q`

Expected: FAIL。

- [ ] **Step 3: 创建运行表**

`003_generation.sql` 创建 generation_runs、generation_steps、generation_logs。run 保存报送名称快照、报送期、profile/workflow 版本、参数快照、actor、auto_validate；step 保存适配器类型、配置快照、external_id、状态、进度和错误；log 使用自增 ID 支持增量读取。

- [ ] **Step 4: 实现协调器**

状态转换只允许 queued→running→terminal；每个步骤先持久化“准备提交”，调用 adapter.start 后立即保存 external_id，再进入 poll。外部状态不确定时标记 unknown，不重复提交。

- [ ] **Step 5: 实现自动校验挂钩**

生成成功且 `auto_validate=true` 时只调用：

```python
auto_validation_callback(
    report_code=run.report_code,
    report_period=run.report_period,
    source_generation_run_id=run.id,
    actor_id=run.actor_id,
    actor_name=run.actor_name,
)
```

回调创建独立 validation run。校验启动失败只追加生成日志“自动校验创建失败”，不得把已成功的生成任务改为失败。

- [ ] **Step 6: 实现生成 API**

固定路由：

- `POST /generation-runs`
- `GET /generation-runs?report_code=&report_period=&page=&page_size=`
- `GET /generation-runs/{run_id}?after_log_id=`
- `POST /generation-runs/{run_id}/cancel`

启动需要 generate_report，取消需要 stop_generation，读取需要 view；page_size 固定限制 1..100。

- [ ] **Step 7: 运行专项与模块回归**

Run: `python -m pytest tests/modules/regulatory_reporting/test_workflow_execution.py tests/modules/regulatory_reporting/test_generation_api.py tests/modules/regulatory_reporting/test_mapping.py -q`

Expected: PASS。

- [ ] **Step 8: 运行全套验证**

Run: `python -m pytest -q`

Expected: PASS。

Run: `git diff --check`

Expected: 无实际 whitespace error。

- [ ] **Step 9: 用户授权后提交检查点**

```powershell
git add src/auto_check/modules/regulatory_reporting tests/modules/regulatory_reporting
git commit -m "实现报送配置映射和混合流程生成"
```
