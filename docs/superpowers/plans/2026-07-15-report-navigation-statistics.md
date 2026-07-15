# Report Navigation Statistics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将报送导航从静态示例改为由新增关系表、严格串行定时采集和应用库快照驱动的动态页面，并支持管理员人工完成步骤和双击维护报送日期。

**Architecture:** 在现有 MySQL 应用库旁新增 14 张报送导航专用表，不修改现有表和 `app_schema_version`。`report_navigation.py` 负责固定判断器与串行采集，`storage_report_navigation.py` 负责配置、快照、人工覆盖和日期持久化；页面只调用快照 API，不直接访问业务数据源。

**Tech Stack:** Python 3.12、SQLAlchemy Core、MySQL/PyMySQL、PostgreSQL/Psycopg、原生 HTML/CSS/JavaScript、pytest、openpyxl、PyInstaller。

---

## 文件结构

- Create `sql/app_storage/mysql/002_report_navigation.sql`：14 张新增关系表的幂等 DDL，只含 `CREATE TABLE IF NOT EXISTS`。
- Create `sql/app_storage/mysql/003_report_navigation_seed.sql`：节点、步骤、依赖、数据源/表/字段/固定值和 2026 月度日期初始化数据。
- Create `scripts/build_report_navigation_seed.py`：读取工作日 Excel，校验标签并生成日期初始化 SQL；1104 同月取最大日期。
- Create `src/auto_check/app/storage_report_navigation.py`：SQLAlchemy Core 表定义和配置、快照、人工覆盖、日期、任务锁仓储。
- Create `src/auto_check/app/report_navigation.py`：固定判断器、报告期格式化、周期边界、串行统计服务和后台调度器。
- Modify `src/auto_check/app/app_database.py`：将 14 张新表加入应用预期结构，保持结构版本为 1。
- Modify `src/auto_check/app/db.py`：公开安全标识符引用函数，供固定判断器生成只读 SQL。
- Modify `src/auto_check/app/server.py`：注入报送导航服务，增加 4 个 API 路由并管理调度器生命周期。
- Modify `src/auto_check/web/index.html`：将静态统计值、日期和鱼骨节点改为可渲染容器，移除静态注意事项示例。
- Modify `src/auto_check/web/app.js`：加载快照、切换周期、渲染鱼骨、人工完成/取消、日期编辑及错误提示。
- Modify `src/auto_check/web/styles.css`：动态状态、人工标识、错误/过期提示、日期编辑和 6/7 节点布局，兼容活力/沉稳/暗色。
- Modify `README.md`：记录动态统计、建表顺序、定时口径和管理员操作。
- Create `tests/test_report_navigation_schema.py`：DDL、预期表结构和 seed 非 JSON/非 ALTER 验证。
- Create `tests/test_report_navigation_seed.py`：Excel 日期解析、季度节点过滤和 1104 最大日期验证。
- Create `tests/test_report_navigation.py`：判断器、依赖、人工覆盖、完成时间、周期统计、锁和严格串行验证。
- Create `tests/test_report_navigation_api.py`：只读 API、管理员权限、参数校验和调度生命周期验证。
- Modify `tests/mysql_config_test_support.py`：内存 MySQL 契约库加入 14 张新表及复合键筛选支持。
- Modify `tests/test_app_database.py`、`tests/test_sqlite_to_mysql_export.py`：应用预期表数量和导出边界更新。
- Modify `tests/test_web_static.py`：动态 DOM 钩子、无百分比角标、主题和交互静态约束。

### Task 1: 新增报送导航关系表并接入应用结构校验

**Files:**
- Create: `sql/app_storage/mysql/002_report_navigation.sql`
- Modify: `src/auto_check/app/app_database.py`
- Test: `tests/test_report_navigation_schema.py`
- Test: `tests/test_app_database.py`

- [ ] **Step 1: 写预期失败的 DDL 与应用结构测试**

```python
def test_report_navigation_schema_only_creates_new_relational_tables():
    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    assert "ALTER TABLE" not in sql.upper()
    assert "DROP TABLE" not in sql.upper()
    assert " JSON" not in sql.upper()
    for name in REPORT_NAV_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS `{name}`" in sql


def test_application_schema_keeps_version_one_and_adds_report_navigation_tables():
    assert CURRENT_APP_SCHEMA_VERSION == 1
    assert len(EXPECTED_APP_SCHEMA) == 34
    assert EXPECTED_APP_SCHEMA["report_nav_steps"] >= {
        "step_code", "process_code", "evaluator_key", "default_completed"
    }
```

- [ ] **Step 2: 运行测试并确认因 DDL 和表定义缺失失败**

Run: `python -m pytest tests/test_report_navigation_schema.py tests/test_app_database.py -q`

Expected: FAIL，提示 `002_report_navigation.sql` 不存在或 `report_nav_steps` 不在 `EXPECTED_APP_SCHEMA`。

- [ ] **Step 3: 创建 14 张只新增关系表的 DDL**

DDL 必须创建下列精确表列和主键；时间列统一使用 `DATETIME(6)`，布尔列使用 `TINYINT(1)`，代码列使用 `VARCHAR(64)`：

```python
TABLE_COLUMNS_AND_KEYS = {
    "report_nav_processes": (("process_code", "process_name", "display_order", "enabled", "allow_manual_step_completion"), ("process_code",)),
    "report_nav_process_months": (("process_code", "month_no"), ("process_code", "month_no")),
    "report_nav_steps": (("step_code", "process_code", "step_name", "display_order", "evaluator_key", "enabled", "default_completed", "manual_completion_allowed"), ("step_code",)),
    "report_nav_step_dependencies": (("step_code", "depends_on_step_code"), ("step_code", "depends_on_step_code")),
    "report_nav_step_sources": (("id", "step_code", "source_role", "data_source_name", "table_name", "display_order", "enabled"), ("id",)),
    "report_nav_step_fields": (("id", "step_source_id", "field_role", "column_name"), ("id",)),
    "report_nav_step_values": (("id", "step_code", "value_role", "value_text", "value_type", "display_order"), ("id",)),
    "report_nav_step_overrides": (("report_month", "step_code", "completed", "operator_id", "operator_username", "operator_name", "created_at", "updated_at"), ("report_month", "step_code")),
    "report_nav_step_snapshots": (("report_month", "step_code", "auto_status", "effective_status", "completion_source", "status_message", "error_message", "auto_completed_at", "evaluated_at", "run_id"), ("report_month", "step_code")),
    "report_nav_process_snapshots": (("report_month", "process_code", "total_steps", "completed_steps", "status", "completed_at", "evaluated_at", "run_id"), ("report_month", "process_code")),
    "report_nav_card_snapshots": (("stat_period", "card_code", "total_count", "completed_count", "incomplete_count", "completion_rate", "evaluated_at", "run_id"), ("stat_period", "card_code")),
    "report_nav_monthly_schedules": (("report_month", "process_code", "report_date", "source_type", "source_year", "updated_by", "updated_at"), ("report_month", "process_code")),
    "report_nav_stat_runs": (("id", "trigger_type", "report_month", "business_report_date", "started_at", "finished_at", "status", "completed_processes", "failed_steps", "error_message"), ("id",)),
    "report_nav_scheduler_state": (("id", "enabled", "interval_minutes", "next_run_at", "lock_owner", "lock_until", "last_started_at", "last_finished_at", "last_status", "last_error", "updated_at"), ("id",)),
}
```

所有状态、值和错误信息使用 `VARCHAR`/`TEXT`，不使用 JSON。外键只指向本次新增表，避免改变现有表。

- [ ] **Step 4: 将 14 张表及全部列加入 `EXPECTED_APP_SCHEMA`**

```python
"report_nav_card_snapshots": _columns(
    "stat_period", "card_code", "total_count", "completed_count",
    "incomplete_count", "completion_rate", "evaluated_at", "run_id",
),
```

保持 `CURRENT_APP_SCHEMA_VERSION = 1`，并把原测试中的预期表数从 20 调整为 34。

- [ ] **Step 5: 运行结构测试**

Run: `python -m pytest tests/test_report_navigation_schema.py tests/test_app_database.py -q`

Expected: PASS。

- [ ] **Step 6: 提交本任务**

```powershell
git add sql/app_storage/mysql/002_report_navigation.sql src/auto_check/app/app_database.py tests/test_report_navigation_schema.py tests/test_app_database.py
git commit -m "feat: add report navigation schema"
```

### Task 2: 生成节点配置和月度报送日期初始化数据

**Files:**
- Create: `scripts/build_report_navigation_seed.py`
- Create: `sql/app_storage/mysql/003_report_navigation_seed.sql`
- Test: `tests/test_report_navigation_seed.py`

- [ ] **Step 1: 写 Excel 解析与 seed 约束的失败测试**

```python
def test_schedule_rows_use_monthly_max_for_1104(tmp_path):
    source = _workbook(tmp_path, [("1104", "2026-07-06"), ("1104", "2026-07-10")])
    rows = load_schedule_rows(source)
    assert [(r.process_code, r.report_date.isoformat()) for r in rows] == [
        ("jr_1104", "2026-07-10")
    ]


def test_five_articles_only_has_quarterly_months(tmp_path):
    rows = load_schedule_rows(_full_workbook(tmp_path))
    assert {r.report_date.month for r in rows if r.process_code == "five_articles"} == {1, 4, 7, 10}


def test_seed_uses_only_new_tables_and_contains_no_json_columns():
    sql = SEED_SQL.read_text(encoding="utf-8")
    assert "app_schema_version" not in sql
    assert "INSERT INTO `report_nav_processes`" in sql
    assert "INSERT INTO `report_nav_scheduler_state`" in sql
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest tests/test_report_navigation_seed.py -q`

Expected: FAIL，提示 `load_schedule_rows` 或 seed 文件不存在。

- [ ] **Step 3: 实现工作日 Excel 解析器**

```python
LABEL_TO_PROCESS = {
    "人行模板\\逐笔": "pbc_template",
    "1104": "jr_1104",
    "全要素": "full_elements",
    "中信登定期": "citic_registration",
    "EAST5.0": "east5",
    "五篇大文章": "five_articles",
}


def load_schedule_rows(path: Path) -> list[ScheduleRow]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook["工作日数据"]
    grouped: dict[tuple[str, int, int], date] = {}
    for label, value, *_ in sheet.iter_rows(min_row=2, values_only=True):
        process_code = LABEL_TO_PROCESS.get(str(label or "").strip())
        report_date = _coerce_date(value)
        if not process_code or report_date is None:
            continue
        key = (process_code, report_date.year, report_date.month)
        grouped[key] = max(grouped.get(key, report_date), report_date)
    return _with_monthly_pbc_central_defaults(grouped)
```

`_with_monthly_pbc_central_defaults` 为每个已出现年份的 12 个月增加 `pbc_central` 每月 1 日；五篇大文章过滤非 1、4、7、10 月。

- [ ] **Step 4: 生成完整 seed SQL**

seed 必须包含 7 个节点、其适用月份、全部展示步骤、依赖关系、用户文档中的数据源/表/字段/固定值、调度器默认行以及 2026 日期。使用带 `ON DUPLICATE KEY UPDATE` 的幂等 MySQL upsert；不得写现有表。

Run: `python scripts/build_report_navigation_seed.py "D:\xiaxin\wx\xwechat_files\ccqlove_5f6d\msg\file\2026-07\工作日数据(1).xlsx" --output sql/app_storage/mysql/003_report_navigation_seed.sql`

Expected: 输出 `wrote sql/app_storage/mysql/003_report_navigation_seed.sql`，其中人行大集中 12 条、1104 每月最多 1 条、五篇大文章 4 条。

- [ ] **Step 5: 运行 seed 测试**

Run: `python -m pytest tests/test_report_navigation_seed.py -q`

Expected: PASS。

- [ ] **Step 6: 提交本任务**

```powershell
git add scripts/build_report_navigation_seed.py sql/app_storage/mysql/003_report_navigation_seed.sql tests/test_report_navigation_seed.py
git commit -m "feat: seed report navigation configuration"
```

### Task 3: 新增报送导航应用库仓储

**Files:**
- Create: `src/auto_check/app/storage_report_navigation.py`
- Modify: `tests/mysql_config_test_support.py`
- Test: `tests/test_report_navigation.py`

- [ ] **Step 1: 写配置加载、人工覆盖、日期和快照仓储的失败测试**

```python
def test_store_replaces_month_snapshot_and_preserves_first_completion_time(database):
    store = ReportNavigationStore(database)
    store.save_process_snapshot(_process_snapshot(status="completed", completed_at=NOW))
    store.save_process_snapshot(_process_snapshot(status="completed", completed_at=LATER))
    assert store.load_dashboard("2026-07")["processes"][0]["completed_at"] == NOW


def test_cancel_manual_completion_deletes_only_current_month_override(database):
    store = ReportNavigationStore(database)
    store.set_manual_complete("2026-07", "pbc_template_7", _admin())
    store.cancel_manual_complete("2026-07", "pbc_template_7")
    assert store.load_overrides("2026-07") == {}


def test_schedule_inherits_previous_year_and_clamps_leap_day(database):
    store = ReportNavigationStore(database)
    store.upsert_schedule("2024-02", "east5", date(2024, 2, 29), source_type="imported")
    assert store.ensure_schedule("2025-02", "east5").report_date == date(2025, 2, 28)
```

- [ ] **Step 2: 运行测试并确认仓储缺失失败**

Run: `python -m pytest tests/test_report_navigation.py -k "store or schedule or manual" -q`

Expected: FAIL，提示 `ReportNavigationStore` 不存在。

- [ ] **Step 3: 定义 SQLAlchemy Core 新表和仓储数据类**

```python
@dataclass(frozen=True)
class StepSnapshot:
    report_month: str
    step_code: str
    auto_status: str
    effective_status: str
    completion_source: str
    status_message: str
    error_message: str
    auto_completed_at: datetime | None
    evaluated_at: datetime
    run_id: int


class ReportNavigationStore:
    def __init__(self, database: ApplicationDatabase):
        self.database = database
```

仓储必须提供 `load_configuration(report_month)`、`load_overrides(report_month)`、`save_run_result(result)`、`load_dashboard(report_month, period)`、`set_manual_complete(report_month, step_code, user)`、`cancel_manual_complete(report_month, step_code)`、`upsert_schedule(report_month, process_code, report_date, source_type, updated_by)`。实现中使用带 `ON DUPLICATE KEY UPDATE` 的 SQLAlchemy MySQL upsert；节点从完成转未完成时清空 `completed_at`，持续完成时沿用原时间。

人工完成写入或取消后，使用现有步骤自动快照和人工覆盖在同一事务内重算该步骤 `effective_status`、所属节点完成数和节点完成时间，不发起业务数据源查询。人工操作补齐最后一步时以操作时间写入节点 `completed_at`；取消后若节点不再全部完成则立即清空。

- [ ] **Step 4: 实现数据库互斥锁与任务摘要方法**

```python
def try_acquire_scheduler_lock(self, owner: str, now: datetime, lease: timedelta) -> bool:
    statement = text("""
        UPDATE report_nav_scheduler_state
        SET lock_owner=:owner, lock_until=:lock_until, last_started_at=:now
        WHERE id=1 AND enabled=1 AND (lock_until IS NULL OR lock_until < :now)
    """)
    with self.database.transaction() as connection:
        return connection.execute(statement, values).rowcount == 1
```

同时实现 `start_run`、`finish_run`、`release_scheduler_lock` 和 `load_latest_run`。

- [ ] **Step 5: 扩展内存 MySQL 契约测试库**

在 `MySqlContractConnection.tables` 增加 14 张新表；复合主键表按 `(report_month, step_code)`、`(stat_period, card_code)` 等键更新，筛选器支持 `report_month`、`step_code`、`process_code`、`stat_period`、`card_code`。

- [ ] **Step 6: 运行仓储测试**

Run: `python -m pytest tests/test_report_navigation.py -k "store or schedule or manual or lock" -q`

Expected: PASS。

- [ ] **Step 7: 提交本任务**

```powershell
git add src/auto_check/app/storage_report_navigation.py tests/mysql_config_test_support.py tests/test_report_navigation.py
git commit -m "feat: add report navigation storage"
```

### Task 4: 实现安全查询构建和固定步骤判断器

**Files:**
- Modify: `src/auto_check/app/db.py`
- Create: `src/auto_check/app/report_navigation.py`
- Test: `tests/test_report_navigation.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: 写报告期格式、标识符校验、空数据和规则判断的失败测试**

```python
@pytest.mark.parametrize(
    ("style", "expected"),
    [("date", "2026-06-30"), ("underscore", "2026_06_30"), ("version", "V.20260630")],
)
def test_format_business_report_date(style, expected):
    assert format_business_report_date(date(2026, 6, 30), style) == expected


def test_negative_rule_requires_scope_rows_before_accepting_no_exceptions():
    executor = RecordingExecutor([{"scope_count": 0, "exception_count": 0}])
    result = evaluate_no_exceptions(_context(executor), _step("pbc_central_3_ck"))
    assert result.status == "incomplete"
    assert result.message == "当前报告期无数据"


def test_configured_identifier_rejects_sql_fragment():
    with pytest.raises(ValueError, match="非法标识符"):
        validate_identifier("ck_result; DROP TABLE users")
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest tests/test_report_navigation.py tests/test_db.py -k "format_business or negative_rule or identifier" -q`

Expected: FAIL。

- [ ] **Step 3: 公开安全标识符引用并定义判断结果模型**

```python
def quote_identifier(db_type: str, identifier: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", identifier):
        raise ValueError(f"非法标识符：{identifier}")
    return _quote_identifier(db_type, identifier)


@dataclass(frozen=True)
class EvaluationResult:
    status: Literal["completed", "incomplete", "waiting_report_period", "error"]
    message: str
    error: str = ""
```

- [ ] **Step 4: 实现固定判断器注册表**

```python
EVALUATORS: dict[str, Evaluator] = {
    "all_rows_match_report_date": evaluate_all_rows_match_report_date,
    "amounts_equal": evaluate_amounts_equal,
    "no_blank_fields": evaluate_no_blank_fields,
    "no_ck_result": evaluate_no_ck_result,
    "minimum_time_in_current_month": evaluate_minimum_time_in_current_month,
    "no_pending_status": evaluate_no_pending_status,
    "month_rows_or_dependency": evaluate_month_rows_or_dependency,
    "default_completed": evaluate_default_completed,
    "dependency_completed": evaluate_dependency_completed,
    "all_versions_present": evaluate_all_versions_present,
    "date_reached": evaluate_date_reached,
    "quarterly_rows_exist": evaluate_quarterly_rows_exist,
    "current_month_rows_in_all_sources": evaluate_current_month_rows_in_all_sources,
    "version_present": evaluate_version_present,
}
```

每个查询先统计作用域数据量，再统计异常或匹配数据量。配置只提供数据源、表、字段和固定值，判断分支不从数据库动态执行 SQL。

- [ ] **Step 5: 写完整规则矩阵测试**

对设计文档中每个判断器至少覆盖 completed、incomplete、empty 和 error；对依赖判断覆盖步骤 2/5/6 关系；对 `date_reached` 覆盖日期前、当天、日期后。

```python
@pytest.mark.parametrize("manage_codes", [("20002", "zbbs24"), ("system1104",), ("qysnew",), ("zxdreport",), ("east5",), ("dwz5",)])
def test_version_evaluators_require_every_configured_manage_code(manage_codes):
    matching = RecordingExecutor([{"matched_count": len(manage_codes)}])
    complete = evaluate_all_versions_present(_version_context(matching, manage_codes))
    assert complete.status == "completed"

    missing = RecordingExecutor([{"matched_count": len(manage_codes) - 1}])
    incomplete = evaluate_all_versions_present(_version_context(missing, manage_codes))
    assert incomplete.status == "incomplete"
```

- [ ] **Step 6: 运行判断器测试**

Run: `python -m pytest tests/test_report_navigation.py tests/test_db.py -k "evaluate or evaluator or report_date or identifier" -q`

Expected: PASS。

- [ ] **Step 7: 提交本任务**

```powershell
git add src/auto_check/app/db.py src/auto_check/app/report_navigation.py tests/test_report_navigation.py tests/test_db.py
git commit -m "feat: evaluate report navigation steps"
```

### Task 5: 实现严格串行采集、卡片快照和调度器

**Files:**
- Modify: `src/auto_check/app/report_navigation.py`
- Modify: `src/auto_check/app/storage_report_navigation.py`
- Test: `tests/test_report_navigation.py`

- [ ] **Step 1: 写串行次序、完成时间、补录周期和锁的失败测试**

```python
def test_collection_runs_processes_and_steps_strictly_in_display_order():
    calls = []
    service = _service(executor=lambda step: calls.append(step.step_code) or completed())
    service.collect_once(now=NOW)
    assert calls == EXPECTED_ENABLED_STEP_ORDER


def test_supplement_task_snapshots_cover_four_periods_without_parallel_queries():
    executor = NonConcurrentExecutor()
    _service(executor=executor).collect_once(now=NOW)
    assert executor.max_active == 1
    assert executor.periods == ["week", "month", "quarter", "year"]


def test_process_completion_time_clears_and_is_recreated():
    service = _service_with_statuses(["completed", "incomplete", "completed"])
    assert service.collect_once(now=T1).processes[0].completed_at == T1
    assert service.collect_once(now=T2).processes[0].completed_at is None
    assert service.collect_once(now=T3).processes[0].completed_at == T3
```

- [ ] **Step 2: 运行测试并确认编排尚未实现**

Run: `python -m pytest tests/test_report_navigation.py -k "collection or supplement or completion_time or scheduler" -q`

Expected: FAIL。

- [ ] **Step 3: 实现业务报告期与周期边界解析**

```python
def latest_business_report_date(database: ApplicationDatabase) -> date | None:
    with database.connect() as connection:
        value = connection.execute(text("SELECT MAX(run_date) FROM run_headers WHERE kind='reconcile'")).scalar_one_or_none()
    return coerce_date(value)


def period_bounds(period: str, today: date) -> tuple[datetime, datetime]:
    if period == "week":
        start_day = today - timedelta(days=today.weekday())
        end_day = start_day + timedelta(days=7)
    elif period == "month":
        start_day = today.replace(day=1)
        end_day = (start_day.replace(day=28) + timedelta(days=4)).replace(day=1)
    elif period == "quarter":
        start_month = ((today.month - 1) // 3) * 3 + 1
        start_day = today.replace(month=start_month, day=1)
        end_day = date(today.year + (start_month == 10), 1 if start_month == 10 else start_month + 3, 1)
    elif period == "year":
        start_day = date(today.year, 1, 1)
        end_day = date(today.year + 1, 1, 1)
    else:
        raise ValueError("period must be week, month, quarter or year")
    return datetime.combine(start_day, time.min), datetime.combine(end_day, time.min)
```

- [ ] **Step 4: 实现一次完整串行采集**

```python
class ReportNavigationService:
    def collect_once(self, *, trigger_type: str = "scheduled", now: datetime | None = None) -> CollectionResult:
        current = now or beijing_now()
        report_month = current.strftime("%Y-%m")
        owner = uuid.uuid4().hex
        if not self.store.try_acquire_scheduler_lock(owner, current, timedelta(minutes=30)):
            return CollectionResult.skipped(report_month)
        try:
            run_id = self.store.start_run(trigger_type, report_month, latest_business_report_date(self.database), current)
            result = self._evaluate_strictly_serial(report_month, run_id, current)
            self.store.save_run_result(result)
            return result
        finally:
            self.store.release_scheduler_lock(owner, beijing_now())
```

`_evaluate_strictly_serial` 必须使用普通 `for process in configurations`/`for step in process.steps`，不得使用线程池、`asyncio.gather` 或 `Promise.all`；单步骤异常转为 error 快照后继续下一步骤。

- [ ] **Step 5: 实现补录任务四周期卡片快照**

```sql
SELECT COUNT(*) AS total_count,
       SUM(CASE WHEN status = %s THEN 1 ELSE 0 END) AS completed_count,
       SUM(CASE WHEN status IS NULL OR status <> %s THEN 1 ELSE 0 END) AS incomplete_count
FROM `jsxt_console`.`rep_data_task_detail`
WHERE del_flag = %s AND create_date >= %s AND create_date < %s
```

依次执行 week、month、quarter、year；数据治理和特殊治理固定写 0；报送报表按当前月可见节点快照统计。

- [ ] **Step 6: 实现调度器启动、停止和不可重入行为**

```python
class ReportNavigationScheduler:
    def start(self) -> None:
        self._thread = threading.Thread(target=self._run_loop, name="report-navigation-scheduler", daemon=True)
        self._thread.start()

    def _run_loop(self) -> None:
        if self._stop.wait(30):
            return
        while not self._stop.is_set():
            self.service.collect_once()
            if self._stop.wait(self.service.interval_minutes * 60):
                return

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
```

- [ ] **Step 7: 运行采集与调度测试**

Run: `python -m pytest tests/test_report_navigation.py -q`

Expected: PASS。

- [ ] **Step 8: 提交本任务**

```powershell
git add src/auto_check/app/report_navigation.py src/auto_check/app/storage_report_navigation.py tests/test_report_navigation.py
git commit -m "feat: schedule report navigation snapshots"
```

### Task 6: 增加快照、人工完成和日期 API

**Files:**
- Modify: `src/auto_check/app/server.py`
- Create: `tests/test_report_navigation_api.py`
- Modify: `tests/test_server.py`

- [ ] **Step 1: 写 API 失败测试**

```python
def test_dashboard_period_only_changes_supplement_card(router):
    status, payload = router.handle("GET", "/api/report-navigation/dashboard", None, current_user=_user())
    assert status == 200
    assert payload["period"] == "month"


def test_manual_complete_requires_admin(router):
    status, payload = router.handle("POST", "/api/report-navigation/steps/pbc_template_7/manual-complete", {"report_month": "2026-07"}, current_user=_user())
    assert (status, payload["error"]) == (403, "admin role required")


def test_schedule_rejects_date_outside_report_month(router):
    status, payload = router.handle("POST", "/api/report-navigation/schedules/east5", {"report_month": "2026-07", "report_date": "2026-08-01"}, current_user=_admin())
    assert status == 400
```

- [ ] **Step 2: 运行 API 测试并确认 404/缺方法失败**

Run: `python -m pytest tests/test_report_navigation_api.py -q`

Expected: FAIL。

- [ ] **Step 3: 向 `ApiRouter` 注入服务并增加路由**

```python
if method == "GET" and path == "/api/report-navigation/dashboard":
    period = dict(parse_qsl(self._query_string)).get("period", "month")
    return 200, self.report_navigation.dashboard(period=period, current_user=current_user)

manual_match = re.fullmatch(r"/api/report-navigation/steps/([^/]+)/(manual-complete|manual-cancel)", path)
if method == "POST" and manual_match:
    _require_admin(current_user)
    step_code, action = manual_match.groups()
    report_month = str((body or {}).get("report_month", "")).strip()
    return 200, self.report_navigation.set_manual_state(step_code, action, report_month, current_user)

schedule_match = re.fullmatch(r"/api/report-navigation/schedules/([^/]+)", path)
if method == "POST" and schedule_match:
    _require_admin(current_user)
    process_code = schedule_match.group(1)
    report_month = str((body or {}).get("report_month", "")).strip()
    report_date = str((body or {}).get("report_date", "")).strip()
    return 200, self.report_navigation.update_schedule(process_code, report_month, report_date, current_user)
```

路由参数只允许已配置 `step_code`/`process_code`。人工完成的 `report_month` 必须等于当前月；日期维护允许当前月和未来月，拒绝历史月，且 `report_date` 必须处于 `report_month`。日期 API 无二次确认；人工完成和取消确认由前端完成。

- [ ] **Step 4: 在服务启动与关闭时管理调度器**

`run_server` 完成数据库结构校验后创建服务和调度器，HTTP 服务开始前 `scheduler.start()`；`finally` 中先 `scheduler.stop()` 再 `application_database.close()`。测试构造 `ApiRouter` 默认不自动启动后台线程。

- [ ] **Step 5: 运行 API 和既有服务测试**

Run: `python -m pytest tests/test_report_navigation_api.py tests/test_server.py -q`

Expected: PASS，且既有路由不受影响。

- [ ] **Step 6: 提交本任务**

```powershell
git add src/auto_check/app/server.py tests/test_report_navigation_api.py tests/test_server.py
git commit -m "feat: expose report navigation APIs"
```

### Task 7: 将报送导航改为动态快照渲染

**Files:**
- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/app.js`
- Modify: `tests/test_web_static.py`

- [ ] **Step 1: 写动态 DOM 与交互钩子的失败静态测试**

```python
def test_report_navigation_uses_snapshot_render_targets_without_static_examples():
    page = _report_navigation_body()
    assert 'id="reportNavStats"' in page
    assert 'id="reportNavSchedules"' in page
    assert 'id="reportNavBranches"' in page
    assert 'id="reportNavStatus"' in page
    assert "▲ 8%" not in page
    assert "注意事项" not in page


def test_report_navigation_javascript_loads_snapshots_and_supports_admin_actions():
    js = _read(APP_JS)
    for token in ["loadReportNavigation", "renderReportNavigation", "manual-complete", "manual-cancel", "updateReportNavigationSchedule"]:
        assert token in js
```

- [ ] **Step 2: 运行测试并确认静态示例仍存在而失败**

Run: `python -m pytest tests/test_web_static.py -k report_navigation -q`

Expected: FAIL。

- [ ] **Step 3: 改造 HTML 为最小动态容器**

保留设计稿布局类名，但卡片值、日期和分支由 JavaScript 生成：

```html
<div class="report-nav-status" id="reportNavStatus" role="status" hidden></div>
<div class="report-nav-stats-grid" id="reportNavStats" aria-live="polite"></div>
<div class="report-nav-batches" id="reportNavSchedules"></div>
<div class="report-nav-branches" id="reportNavBranches"></div>
<p class="report-nav-last-run" id="reportNavLastRun"></p>
```

删除静态趋势百分比、静态完成示例和注意事项卡。

- [ ] **Step 4: 页面进入时加载快照并切换周期**

```javascript
async function loadReportNavigation() {
  const period = reportNavPeriodSelect?.value || "month";
  reportNavStatus.hidden = true;
  try {
    reportNavigationState = await api(`/api/report-navigation/dashboard?period=${encodeURIComponent(period)}`);
    renderReportNavigation(reportNavigationState);
  } catch (error) {
    renderReportNavigationError(error.message);
  }
}
```

在 `switchPage("report-navigation")` 时调用；周期 change 只重载快照，不触发业务库查询。

- [ ] **Step 5: 渲染四卡、日期和 6/7 节点鱼骨图**

```javascript
function renderReportNavigation(payload) {
  reportNavStats.innerHTML = payload.cards.map(renderReportNavCard).join("");
  reportNavSchedules.innerHTML = payload.processes.map(renderReportNavSchedule).join("");
  reportNavBranches.innerHTML = payload.processes.map((process, index) => renderReportNavBranch(process, index)).join("");
  reportNavBranches.dataset.count = String(payload.processes.length);
  reportNavLastRun.textContent = payload.last_run?.finished_at ? `统计于 ${payload.last_run.finished_at}` : "等待首次统计";
}
```

卡片底部统一“已完成 X”“未完成 X”；右上角趋势百分比不渲染。仅 1、4、7、10 月 API 返回五篇大文章，因此当前 DOM 自动为 6 或 7 个节点。

- [ ] **Step 6: 实现人工完成/取消和双击日期编辑**

管理员点击步骤状态图标时调用现有 `showConfirm`，确认后 POST 对应接口并重新读取快照；普通用户图标不可操作。管理员双击当前月日期弹出原生 `input[type=date]` 编辑层，保存前校验年月，成功后刷新。

```javascript
const action = step.completion_source === "manual" ? "manual-cancel" : "manual-complete";
const confirmed = await showConfirm(title, message);
if (confirmed) await api(`/api/report-navigation/steps/${encodeURIComponent(step.step_code)}/${action}`, {
  method: "POST", body: JSON.stringify({ report_month: state.report_month })
});
```

- [ ] **Step 7: 运行报送导航前端静态测试**

Run: `python -m pytest tests/test_web_static.py -k report_navigation -q`

Expected: PASS。

- [ ] **Step 8: 提交本任务**

```powershell
git add src/auto_check/web/index.html src/auto_check/web/app.js tests/test_web_static.py
git commit -m "feat: render report navigation snapshots"
```

### Task 8: 完善动态状态和主题样式

**Files:**
- Modify: `src/auto_check/web/styles.css`
- Modify: `tests/test_web_static.py`

- [ ] **Step 1: 写主题、日期颜色和动态布局失败测试**

```python
def test_report_navigation_dynamic_states_are_theme_compatible():
    css = _read(STYLES_CSS)
    for selector in [
        '.report-nav-step[data-status="completed"]',
        '.report-nav-step[data-status="error"]',
        '.report-nav-manual-badge',
        '.report-nav-branches[data-count="6"]',
        '.report-nav-schedule-editor',
        '[data-color-mode="dark"] #page-report-navigation .report-nav-batch time',
    ]:
        assert selector in css
```

- [ ] **Step 2: 运行样式测试并确认失败**

Run: `python -m pytest tests/test_web_static.py -k "report_navigation and (theme or dynamic or date)" -q`

Expected: FAIL。

- [ ] **Step 3: 添加动态状态、6 节点重排和日期编辑样式**

```css
#page-report-navigation .report-nav-batch time { color: #111827; }
[data-color-mode="dark"] #page-report-navigation .report-nav-batch time { color: #f8fafc; }
#page-report-navigation .report-nav-step[data-status="error"] { color: #dc2626; }
#page-report-navigation .report-nav-manual-badge { /* 主题化小标签 */ }
#page-report-navigation .report-nav-branches[data-count="6"] .report-nav-branch { /* 六节点均匀位置 */ }
#page-report-navigation .report-nav-schedule-editor { /* 日期输入、保存、取消 */ }
```

沿用已有鱼骨几何和活力/沉稳色彩变量，不改变顶部导航行为。

- [ ] **Step 4: 运行全部前端静态测试**

Run: `python -m pytest tests/test_web_static.py -q`

Expected: PASS。

- [ ] **Step 5: 提交本任务**

```powershell
git add src/auto_check/web/styles.css tests/test_web_static.py
git commit -m "style: polish report navigation states"
```

### Task 9: 更新导出边界、README 和应用内更新日志

**Files:**
- Modify: `tests/test_sqlite_to_mysql_export.py`
- Modify: `scripts/export_sqlite_to_mysql.py`
- Modify: `README.md`
- Modify: `src/auto_check/web/app.js`
- Modify: `tests/test_web_static.py`

- [ ] **Step 1: 写文档和迁移边界失败测试**

```python
def test_readme_documents_report_navigation_schema_and_scheduler():
    readme = _read(README_MD)
    assert "002_report_navigation.sql" in readme
    assert "003_report_navigation_seed.sql" in readme
    assert "每 10 分钟" in readme
    assert "页面只读取快照" in readme
```

SQLite 历史导出仍只处理原 20 张可迁移表；测试明确报送导航新表由 DDL/seed 初始化，不从旧 SQLite 导出。

- [ ] **Step 2: 运行文档和导出测试并确认失败**

Run: `python -m pytest tests/test_sqlite_to_mysql_export.py tests/test_web_static.py -k "readme or changelog or sqlite" -q`

Expected: FAIL。

- [ ] **Step 3: 更新 README 详细说明**

README 说明上线顺序为 `001` → `002` → `003`，应用预期表共 34 张；说明定时任务 30 秒后首跑、默认每 10 分钟、严格串行、页面只读快照、管理员人工完成和日期双击编辑。

- [ ] **Step 4: 精简应用内 v2.1 更新日志**

在当前版本新增一项“新增报送导航动态状态统计、报送日期维护及管理员人工完成能力。”；布局、样式和错误处理只保留统一条目“系统优化及BUG修复。”。

- [ ] **Step 5: 明确旧 SQLite 导出不包含新表**

`scripts/export_sqlite_to_mysql.py` 继续以 `001_init_schema.sql` 为旧数据迁移目标；在输出报告和测试中明确新表需执行 `002`/`003`，避免错误尝试从旧 SQLite 导出不存在的数据。

- [ ] **Step 6: 运行文档和迁移测试**

Run: `python -m pytest tests/test_sqlite_to_mysql_export.py tests/test_web_static.py -q`

Expected: PASS。

- [ ] **Step 7: 提交本任务**

```powershell
git add README.md src/auto_check/web/app.js scripts/export_sqlite_to_mysql.py tests/test_sqlite_to_mysql_export.py tests/test_web_static.py
git commit -m "docs: document report navigation statistics"
```

### Task 10: 全量回归、视觉核验和 Windows 打包

**Files:**
- Verify: all changed files
- Package: `dist/auto-check.exe`

- [ ] **Step 1: 运行报送导航专项测试**

Run: `python -m pytest tests/test_report_navigation_schema.py tests/test_report_navigation_seed.py tests/test_report_navigation.py tests/test_report_navigation_api.py -q`

Expected: PASS。

- [ ] **Step 2: 运行全量测试**

Run: `python -m pytest -q`

Expected: 全部 PASS，无 warning 导致失败。

- [ ] **Step 3: 启动本地页面做可见行为核验**

验证活力、沉稳、暗色三种状态：四卡无右上角百分比；底部为已完成/未完成；报送日期浅色为黑字；鱼骨 6/7 节点排列正确；管理员人工完成确认和日期编辑可用；普通用户只读；无快照与过期快照提示清楚。

- [ ] **Step 4: 检查差异和空白错误**

Run: `git diff --check`

Expected: 无实际 whitespace error；CRLF/LF 提示可记录但不视为失败。

- [ ] **Step 5: 结束占用 EXE 的进程**

```powershell
$target = (Resolve-Path 'dist\auto-check.exe' -ErrorAction SilentlyContinue)
if ($target) {
  Get-CimInstance Win32_Process -Filter "Name='auto-check.exe'" |
    Where-Object { $_.ExecutablePath -eq $target.Path } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
}
```

Expected: 只结束当前工作树 `dist\auto-check.exe` 对应进程。

- [ ] **Step 6: 重新打包 Windows EXE**

Run: `powershell -ExecutionPolicy Bypass -File scripts\package-windows.ps1`

Expected: 测试通过，生成 `dist\auto-check.exe`。

- [ ] **Step 7: 核验产物**

```powershell
Get-Item dist\auto-check.exe | Select-Object FullName,Length,LastWriteTime
Get-FileHash dist\auto-check.exe -Algorithm SHA256
```

Expected: 时间为本次构建时间、文件非空并输出 SHA256。

- [ ] **Step 8: 提交最终交付变更**

只暂存本功能相关文件和 `dist/auto-check.exe`，不得带入工作区其他未关联改动。

```powershell
git status --short
git add dist/auto-check.exe
git commit -m "build: package report navigation statistics"
```
