# 报送管理 SQL 校验与永久明细实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为七类报送交付可在线维护、试运行和正式执行的 SQL 校验引擎，并永久保存每条规则的错误数量、动态列和完整错误明细。

**Architecture:** 规则配置保存在模块数据库并以不可变 revision 和 audit diff 留痕。SQL 静态分析负责安全初筛、参数位置和涉及源表；所选数据源的零行包装查询负责权威展示列识别；正式执行将动态行流式编码成 gzip JSONL 分块并交给 `platform.artifact_storage`。

**Tech Stack:** Python 3.12、sqlglot、PostgreSQL/MySQL、gzip/JSONL、现有模块运行时、pytest。

## Global Constraints

- 必须先完成基础、映射与生成计划；本计划不读取或依赖报文映射快照。
- 每条规则选择自己的数据源；更换连接只修改 `data_source_id`，不改写 SQL 内 schema/table。
- 规则保存后永久有效，除非用户主动禁用；不建有效期、权重、自定义 SQL 开关或定位字段。
- SQL 必须是单条只读 `SELECT` 或 `WITH ... SELECT`；数据库只读会话是最终安全边界。
- SQL 查询返回 0 行即通过，返回行即错误明细，完整行数即错误条数；异常单独统计且不停止其他规则。
- 展示字段来自零行元数据查询，用户只能调整显示/隐藏；保存明细仍包含查询返回的全部列。
- 试运行最多 5 行、10 秒、不计总数、不写历史、不持久化明细。
- 正式执行单规则 120 秒；同报送一个任务，全局任务 2、单数据源 SQL 4、全局 SQL 16。
- 正式记录和明细第一阶段永久保留，不提供删除 API 或清理任务。
- 生产页面不提供批量导入；用户给出的初始化文件只在开发阶段转为版本化种子。
- 不自动打包、不提交、不推送。

---

## 文件结构

### 新增

- `src/auto_check/modules/regulatory_reporting/validation/contracts.py`
- `src/auto_check/modules/regulatory_reporting/validation/sql_policy.py`
- `src/auto_check/modules/regulatory_reporting/validation/parameters.py`
- `src/auto_check/modules/regulatory_reporting/validation/field_detection.py`
- `src/auto_check/modules/regulatory_reporting/validation/rule_service.py`
- `src/auto_check/modules/regulatory_reporting/validation/rule_storage.py`
- `src/auto_check/modules/regulatory_reporting/validation/detail_chunks.py`
- `src/auto_check/modules/regulatory_reporting/validation/executor.py`
- `src/auto_check/modules/regulatory_reporting/validation/coordinator.py`
- `src/auto_check/modules/regulatory_reporting/migrations/004_validation_configuration.sql`
- `src/auto_check/modules/regulatory_reporting/migrations/005_validation_history.sql`
- `src/auto_check/modules/regulatory_reporting/migrations/006_validation_seed.sql`（取得用户初始化文件后生成）
- `scripts/convert_regulatory_validation_seed.py`
- `tests/modules/regulatory_reporting/test_sql_policy.py`
- `tests/modules/regulatory_reporting/test_validation_parameters.py`
- `tests/modules/regulatory_reporting/test_field_detection.py`
- `tests/modules/regulatory_reporting/test_rule_service.py`
- `tests/modules/regulatory_reporting/test_validation_executor.py`
- `tests/modules/regulatory_reporting/test_validation_details.py`
- `tests/modules/regulatory_reporting/test_validation_api.py`
- `tests/modules/regulatory_reporting/test_validation_seed_converter.py`

### 修改

- `pyproject.toml`：加入 `sqlglot>=26.0.0`，只用于解析，不用于改写生产 SQL。
- `src/auto_check/modules/regulatory_reporting/manifest.json`：`schema_version` 更新为 6。
- `src/auto_check/modules/regulatory_reporting/module.py`：构造校验服务，并把自动校验 callback 注入生成协调器。
- `src/auto_check/modules/regulatory_reporting/api.py`：注册规则、试运行、执行、历史和明细接口。

## 校验接口冻结

```python
# validation/contracts.py
Severity = Literal["error", "warning", "info"]
RuleState = Literal["enabled", "disabled"]
RuleResultState = Literal["passed", "failed", "error", "cancelled"]

@dataclass(frozen=True)
class DisplayField:
    name: str
    database_type: str
    visible: bool
    order: int

@dataclass(frozen=True)
class RuleDraft:
    report_code: str
    code: str
    name: str
    major_category_id: str
    minor_category_id: str
    severity: Severity
    group_id: str
    data_source_id: str
    enabled: bool
    description: str
    sql: str
    display_fields: tuple[DisplayField, ...]
    row_version: int | None

@dataclass(frozen=True)
class ValidationStartRequest:
    report_code: str
    report_period: str
    group_ids: tuple[str, ...]
    trigger_type: Literal["manual", "after_generation"]
    source_generation_run_id: str | None
    actor_id: str
    actor_name: str
```

```python
# validation/parameters.py
@dataclass(frozen=True)
class ResolvedSql:
    sql: str
    bound_values: tuple[object, ...]
    preview_values: dict[str, str]

def resolve_sql(
    sql: str,
    *,
    report_period: str,
    frequency: str,
    custom_parameters: Mapping[str, object],
    dialect: Literal["postgresql", "mysql"],
    mode: Literal["metadata", "trial", "full"],
) -> ResolvedSql: ...
```

```python
# validation/detail_chunks.py
@dataclass(frozen=True)
class DetailChunkIndex:
    artifact_id: str
    first_row: int
    last_row: int
    row_count: int
    byte_count: int
    sha256: str

class DetailChunkWriter:
    def append(self, row: Mapping[str, object]) -> None: ...
    def finish(self) -> tuple[DetailChunkIndex, ...]: ...
    def abort(self) -> None: ...
```

每块固定最多 5,000 行或 16 MiB 未压缩 JSON，以先达到者切块；每行编码为 UTF-8 JSONL，日期、Decimal 和 bytes 使用显式类型标签，读取时无损还原为前端可序列化值。

## Task 1：SQL 策略、参数和日期推导

**Files:**
- Create: `validation/sql_policy.py`
- Create: `validation/parameters.py`
- Modify: `pyproject.toml`
- Test: `test_sql_policy.py`
- Test: `test_validation_parameters.py`

**Interfaces:**
- Consumes: report profile frequency、`sqlglot` AST。
- Produces: `analyze_sql(sql, dialect) -> SqlAnalysis`、`resolve_sql()`。

- [ ] **Step 1: 写危险 SQL 和复杂只读 SQL 失败测试**

```python
@pytest.mark.parametrize("sql", [
    "delete from a", "update a set x=1", "select 1; select 2",
    "with x as (delete from a returning *) select * from x",
    "copy a to '/tmp/a'", "set role admin",
])
def test_rejects_non_read_only(sql):
    with pytest.raises(SqlPolicyError):
        analyze_sql(sql, "postgresql")

def test_accepts_ctes_and_collects_real_source_tables():
    result = analyze_sql("with x as (select * from s.a) select * from x join s.b on 1=1", "postgresql")
    assert result.source_tables == (("s", "a"), ("s", "b"))
```

- [ ] **Step 2: 写内置参数边界测试**

覆盖月报、季报、半年报、年报和自定义频率下 `${report_period}`、`${report_period_yyyymmdd}`、`${report_period_yyyymm}`、`${previous_period}`、`${previous_period_yyyymmdd}`、`${year_begin}`、`${previous_year_end}`。覆盖闰年、跨年、季度末和未定义占位符。

- [ ] **Step 3: 运行失败测试**

Run: `python -m pytest tests/modules/regulatory_reporting/test_sql_policy.py tests/modules/regulatory_reporting/test_validation_parameters.py -q`

Expected: FAIL。

- [ ] **Step 4: 实现 AST 安全策略**

只允许一个根表达式，根节点必须为 Select/Union 或只包含只读 CTE 的 Select；遍历 AST 拒绝 Insert、Update、Delete、Merge、Create、Alter、Drop、Truncate、Command、Transaction、Copy 和多语句。返回源表时排除 CTE 名。

- [ ] **Step 5: 实现参数编译**

值位置转换为驱动 `%s` 占位符并追加 bound_values；标识符位置仅接受参数定义中 `kind='identifier'` 且 `source in {'derived','enum'}` 的值，经 `^[A-Za-z_][A-Za-z0-9_$]*$` 校验后按方言引用。任意用户输入不得进入标识符参数。

- [ ] **Step 6: 实现外层包装**

```python
def wrap_for_metadata(sql: str) -> str:
    return f"SELECT * FROM ({sql}) ac_meta WHERE 1 = 0"

def wrap_for_trial(sql: str) -> str:
    return f"SELECT * FROM ({sql}) ac_trial LIMIT 5"
```

先移除末尾单个分号，不改写内部排序、CTE 或表达式。

- [ ] **Step 7: 运行专项测试**

Run: `python -m pytest tests/modules/regulatory_reporting/test_sql_policy.py tests/modules/regulatory_reporting/test_validation_parameters.py -q`

Expected: PASS。

## Task 2：规则配置、零行字段识别和修订审计

**Files:**
- Create: `migrations/004_validation_configuration.sql`
- Create: `validation/field_detection.py`
- Create: `validation/rule_storage.py`
- Create: `validation/rule_service.py`
- Modify: `manifest.json`
- Modify: `api.py`
- Test: `test_field_detection.py`
- Test: `test_rule_service.py`
- Test: `test_validation_api.py`

**Interfaces:**
- Consumes: `DataSourcesFacade.inspect()`、Task 1 的 `analyze_sql/resolve_sql`。
- Produces: categories/groups/parameters/rules CRUD、`RuleService.trial()` 前的可执行规则快照。

- [ ] **Step 1: 写字段识别缓存与可见性继承失败测试**

```python
def test_detection_uses_zero_row_metadata_and_preserves_visibility(service):
    first = service.detect_fields(draft(sql="select a,b,c from t"), period="2026-08-31")
    saved = service.save(draft(display_fields=hide(first, "c")), actor)
    second = service.detect_fields(draft(sql="select a,b,d from t"), period="2026-08-31")
    assert [(f.name, f.visible) for f in second] == [("a", True), ("b", True), ("d", True)]
```

再断言相同 `(source_id, sql_sha256, parameter_definition_sha256)` 不重复 inspect；重名/空列名拒绝保存。

- [ ] **Step 2: 写审计差异失败测试**

创建、SQL 修改、数据源修改、展示字段隐藏、启停均生成 revision 与 audit；audit 字段必须保存 field、before、after，展示方式可直接供前端仿照“报表特殊处理”的操作记录。

- [ ] **Step 3: 运行失败测试**

Run: `python -m pytest tests/modules/regulatory_reporting/test_field_detection.py tests/modules/regulatory_reporting/test_rule_service.py tests/modules/regulatory_reporting/test_validation_api.py -q`

Expected: FAIL。

- [ ] **Step 4: 创建配置表**

`004_validation_configuration.sql` 创建 categories、groups、parameters、rules、rule_display_fields、rule_revisions、rule_audit_logs 和 field_detection_cache。rule code 在 report_code 内唯一；minor category 必须属于 major；所有关联表有 report_code 防串报送检查。

- [ ] **Step 5: 实现字段识别**

用测试报送期解析参数，调用 `inspect(ReadOnlyQuery(..., timeout_seconds=5, maximum_rows=1))`。数据库返回列名/别名是权威值；静态分析的 source_tables 仅用于展示。缓存仅保存列结构和源表，不保存查询数据。

- [ ] **Step 6: 实现保存事务**

一个事务中：乐观锁当前 rule、写 current fields、创建完整 revision、计算逐字段 diff、写 audit、递增 row_version。数据源或 SQL 变化必须重新识别；只切换 visible 不重新查数据库。

- [ ] **Step 7: 实现配置 API**

固定路由：

- `GET/POST /validation/categories`
- `PUT /validation/categories/{id}`
- `GET/POST /validation/groups`
- `PUT /validation/groups/{id}`
- `GET/POST /validation/parameters`
- `PUT /validation/parameters/{id}`
- `GET/POST /validation/rules`
- `GET/PUT /validation/rules/{id}`
- `POST /validation/rules/{id}/enable`
- `POST /validation/rules/{id}/disable`
- `POST /validation/rules/detect-fields`
- `GET /validation/rules/{id}/revisions`
- `GET /validation/rules/{id}/audit`

所有配置写操作需要 manage_validation_config；读取规则需要 view。

- [ ] **Step 8: 运行专项测试**

Run: `python -m pytest tests/modules/regulatory_reporting/test_field_detection.py tests/modules/regulatory_reporting/test_rule_service.py tests/modules/regulatory_reporting/test_validation_api.py -q`

Expected: PASS。

## Task 3：5 行试运行

**Files:**
- Modify: `validation/rule_service.py`
- Modify: `api.py`
- Test: `test_validation_executor.py`
- Test: `test_validation_api.py`

**Interfaces:**
- Consumes: 已保存规则或未保存 draft、Task 1 参数解析、`DataSourcesFacade.fetch()`。
- Produces: `trial_rule(rule_or_draft, report_period) -> TrialResult`。

- [ ] **Step 1: 写 5 行与无历史失败测试**

断言请求 SQL 外层含 `LIMIT 5`、timeout=10、maximum_rows=5；返回最多 5 行；不执行 count；运行前后 validation_runs 数不变。

- [ ] **Step 2: 运行失败测试**

Run: `python -m pytest tests/modules/regulatory_reporting/test_validation_executor.py tests/modules/regulatory_reporting/test_validation_api.py -q`

Expected: FAIL。

- [ ] **Step 3: 实现试运行**

返回 `columns`、`rows`、`duration_ms`、`source_tables` 和参数预览，不返回完整 SQL、连接信息或驱动堆栈。未解析参数、SQL 策略错误、超时和数据库错误都转为脱敏 400/422 响应。

- [ ] **Step 4: 注册接口并验证**

`POST /validation/rules/trial` 需要 manage_validation_config；请求包含 report_code、report_period 和 rule_id 或完整 draft 二选一。

Run: `python -m pytest tests/modules/regulatory_reporting/test_validation_executor.py tests/modules/regulatory_reporting/test_validation_api.py -q`

Expected: PASS。

## Task 4：正式执行、错误计数和永久分块

**Files:**
- Create: `migrations/005_validation_history.sql`
- Create: `validation/detail_chunks.py`
- Create: `validation/executor.py`
- Create: `validation/coordinator.py`
- Modify: `validation/rule_storage.py`
- Modify: `module.py`
- Modify: `api.py`
- Test: `test_validation_executor.py`
- Test: `test_validation_details.py`
- Test: `test_validation_api.py`

**Interfaces:**
- Consumes: `DataSourcesFacade.stream()`、`ArtifactStorageFacade`、规则 revision snapshot。
- Produces: `ValidationCoordinator.start()`、`status()`、`cancel()`、分页 detail、完整 detail 下载流。

- [ ] **Step 1: 写结果语义失败测试**

覆盖 0 行→passed、N 行→failed/error_count=N、SQL 抛错→error 且其他规则继续、取消→未启动规则 cancelled；汇总分别统计 completed/passed/failed/error/error_rows。

- [ ] **Step 2: 写分块原子性和分页失败测试**

写入 12,001 行应产生至少 3 块；请求 page=2/page_size=100 只打开覆盖第 101..200 行的块；中途异常 abort 所有未发布 writer，rule result 状态为 error 且没有可下载的残缺明细。

- [ ] **Step 3: 运行失败测试**

Run: `python -m pytest tests/modules/regulatory_reporting/test_validation_executor.py tests/modules/regulatory_reporting/test_validation_details.py tests/modules/regulatory_reporting/test_validation_api.py -q`

Expected: FAIL。

- [ ] **Step 4: 创建历史表**

`005_validation_history.sql` 创建 validation_runs、validation_rule_results、validation_detail_chunks。run 保存规则 ID/revision/SQL hash/参数/分组快照，不能只在读取时连接当前规则；rule result 保存列定义、错误总数、耗时和脱敏异常；chunk 保存 artifact_id、首末行、行数、字节和 sha256。

- [ ] **Step 5: 实现分块 writer**

每条规则使用独立 business key `validation/<report_code>/<report_period>/<run_id>/<rule_result_id>`。所有块成功提交后才在应用数据库事务中登记索引；任一块失败，调用 abort 并把该规则标为 error。

- [ ] **Step 6: 实现协调器与并发**

使用一个全局 16 许可、每数据源 4 许可、全局 run 2 许可、每 report_code 1 许可的信号量集合。获取顺序固定为 report→run→global SQL→source SQL，释放逆序，避免死锁。自动校验忽略 groups 并选择全部启用规则；手工校验空 groups 也表示全部启用规则。

- [ ] **Step 7: 接入生成后的自动校验**

`module.start()` 把 `ValidationCoordinator.start_after_generation` 注入生成协调器。自动记录 trigger_type=`after_generation` 且保存 source_generation_run_id；它与生成 run 使用不同 ID、表和状态。

- [ ] **Step 8: 实现执行和明细 API**

固定路由：

- `POST /validation-runs`
- `GET /validation-runs?report_code=&report_period=&page=&page_size=`
- `GET /validation-runs/{run_id}`
- `POST /validation-runs/{run_id}/cancel`
- `GET /validation-runs/{run_id}/rules`
- `GET /validation-rule-results/{result_id}/details?page=&page_size=`
- `GET /validation-rule-results/{result_id}/download`

启动需要 run_validation；查看明细/下载需要 view_validation_details；page_size 限制 1..200。下载按块流式合并为 UTF-8 BOM CSV，列顺序使用保存的完整 columns，不受 UI visible 过滤影响。

- [ ] **Step 9: 运行专项测试**

Run: `python -m pytest tests/modules/regulatory_reporting/test_validation_executor.py tests/modules/regulatory_reporting/test_validation_details.py tests/modules/regulatory_reporting/test_validation_api.py -q`

Expected: PASS。

## Task 5：一次性初始规则转换器

**Files:**
- Create: `scripts/convert_regulatory_validation_seed.py`
- Create: `migrations/006_validation_seed.sql`
- Test: `test_validation_seed_converter.py`

**Interfaces:**
- Consumes: 用户最终提供的 Excel 或 SQL 文件、明确的数据源映射。
- Produces: 可重复执行且幂等的版本化种子迁移，不产生生产上传入口。

- [ ] **Step 1: 写转换器夹具失败测试**

夹具覆盖重复 rule code、未知数据源、危险 SQL、未定义参数、空名称、合法复杂 SQL；非法输入必须给出行号和原因且不生成部分迁移。

- [ ] **Step 2: 运行失败测试**

Run: `python -m pytest tests/modules/regulatory_reporting/test_validation_seed_converter.py -q`

Expected: FAIL。

- [ ] **Step 3: 实现只离线运行的转换器**

命令固定为：

```powershell
$seedInput = (Resolve-Path $env:REGULATORY_RULE_SEED).Path
$sourceMap = (Resolve-Path $env:REGULATORY_RULE_SOURCE_MAP).Path
python scripts/convert_regulatory_validation_seed.py --input $seedInput --source-map $sourceMap --output src/auto_check/modules/regulatory_reporting/migrations/006_validation_seed.sql
```

脚本只接受本地开发参数，不被服务器或前端导入。输出按 report_code/rule_code 排序，SQL 字符串安全转义，插入前用唯一键 `NOT EXISTS` 保证幂等。

- [ ] **Step 4: 收到用户文件后生成并复核迁移**

先以 `--check-only` 输出总数、分报送数量、分数据源数量、重复项和错误项；全部为 0 错误后再生成迁移。实际总数必须与用户提供文件的有效规则数一致，不以“约 2000”代替精确核对。

- [ ] **Step 5: 运行转换与迁移测试**

Run: `python -m pytest tests/modules/regulatory_reporting/test_validation_seed_converter.py tests/modules/regulatory_reporting/test_manifest_and_migrations.py -q`

Expected: PASS；迁移执行两次后规则总数不增加。

## Task 6：校验全量回归与文档检查点

**Files:**
- Modify: `src/auto_check/modules/regulatory_reporting/README.md`
- Modify: `docs/superpowers/specs/2026-09-08-regulatory-reporting-module-design.md`（仅当实现与已确认契约存在经用户批准的差异）

- [ ] **Step 1: 运行模块校验测试**

Run: `python -m pytest tests/modules/regulatory_reporting -q`

Expected: PASS。

- [ ] **Step 2: 运行全套测试**

Run: `python -m pytest -q`

Expected: PASS。

- [ ] **Step 3: 检查迁移和差异**

Run: `git diff --check`

Expected: 无实际 whitespace error。

Run: `git status --short`

Expected: 只包含本需求文件和用户已有未跟踪设计/原型，不覆盖无关改动。

- [ ] **Step 4: 用户授权后提交检查点**

```powershell
git add pyproject.toml src/auto_check/modules/regulatory_reporting scripts/convert_regulatory_validation_seed.py tests/modules/regulatory_reporting
git commit -m "实现报送SQL校验和永久错误明细"
```
