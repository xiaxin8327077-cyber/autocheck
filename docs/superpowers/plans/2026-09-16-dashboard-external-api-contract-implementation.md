# AutoCheck 看板外部接口契约修正 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 AutoCheck 的两个固定看板接口、接口数据预览和看板页面预览共同使用一份完整、可跨年且包含日期的规范数据，并将 AutoCheck 预览固定为后续 Kanban 页面适配的内容与视觉基准。

**Architecture:** 在 `dashboard_management` 模块内建立唯一的固定看板结果投影：来源测试仍最多返回 10 行，完整看板读取使用无限行执行器；四个年度趋势区域在投影前写入/读取按业务期归属的年度快照；内部预览与外部接口复用同一个 service 结果，仅认证、监控和请求追踪不同。`report_reconciliation_completion_time` 以完整完成日期时间作为来源输入，AutoCheck 派生 `HH:mm` 展示字段，并对旧的仅时分历史快照做只读兼容。

**Tech Stack:** Python 3.12、SQLAlchemy、MySQL/PostgreSQL 只读查询、模块化 HTTP 路由、原生 HTML/JavaScript、pytest。

## Global Constraints

- 只允许影响 `report_submission` 与 `reporting_process` 两个固定看板；不得改变其他模块、其他定时任务、自动对数核心规则或接口监控行为。
- AutoCheck 是契约唯一定义方；Kanban 后续按本文产物兼容，不反向定义字段和业务语义。
- 历史数据以 AutoCheck 初始化年度快照为准；新数据以系统数据或“看板管理”中保存的 SQL 为准。
- `month` 必须是 `YYYY-MM`，且是年度归属和排序的唯一依据；不得使用完成日期重新归类业务月份。
- `reconciliation_completed_time` 必须是 `HH:mm`；`reconciliation_completed_at` 必须是 `YYYY-MM-DDTHH:mm:ss` 或 `null`。
- 2026 年 1—6 月初始化对账历史只保留既有时分，完整日期必须为 `null`；不得推算或伪造日期。
- 新数据必须提供完整 `reconciliation_completed_at`，AutoCheck 从中派生 `reconciliation_completed_time`；新数据只有 `HH:mm` 时必须校验失败。
- 外部 `v1` 不增加年度和分页参数；响应增加整数 `data.data_year`，且同一响应中的年度快照行不得混年。
- 每年 1 月允许“报表对账完成时间”来源返回上一年 12 月迟到记录；该记录写入上一年度快照，不进入本年度响应。
- 新年度没有可用年度趋势数据时返回区域错误 `data_not_ready` 与顶层 `partial`，不得用空列表或 `0` 伪装完整成功。
- 完整看板必须一次返回固定 7+3 区域的全部业务行；成功区域必须 `has_more=false` 且 `returned_count == len(rows)`。
- 任何被截断的来源结果返回区域错误 `truncated_result`；截断数据不得写入快照，也不得回退成成功区域。
- 数据来源编辑区的 SQL/系统数据测试继续最多显示 10 行；这个调试上限不得传播到接口数据预览、看板页面预览或外部接口。
- AutoCheck 的接口数据预览、看板页面预览和外部接口必须使用同一固定区域、字段、排序、年度快照及错误规则；自定义区域/字段只保留配置和来源测试能力，不进入完整看板预览。
- AutoCheck 两张内置预览页面是后续 Kanban 页面改造的视觉基准；当前阶段固定其区域、标题、指标、月份顺序、空值和时间展示，Kanban 阶段再执行同屏截图验收。
- 不新增数据库迁移：年度快照行保存在 JSON 中，新字段由现有目录播种自动补入，旧 JSON 在读取时兼容。
- 不新增能力码、菜单、后台任务或轮询；接口调用监控的写入、查询、IP、30 天留存和页面行为保持不变。
- 应用展示大版本继续为 `V1.2`；未经用户授权不得跨大版本。
- 工作区已有未提交改动，不得回退或覆盖。每次提交前只审查并暂存本任务对应的明确代码块。
- 未获得用户明确提交授权时，不执行下列提交命令；计划中的提交步骤仅作为获准后的原子提交边界。
- 本次不打包、不刷新 `dist/auto-check.exe`，除非用户另行明确要求。

---

## File Map

### 业务代码

- `src/auto_check/modules/dashboard_management/catalog.py`：固定输出字段契约；新增展示时分字段并保持完整日期时间字段。
- `src/auto_check/modules/dashboard_management/year_snapshots.py`：业务期校验、完整日期时间规范化、展示时分派生、历史仅时分兼容和初始化快照。
- `src/auto_check/modules/dashboard_management/sql_executor.py`：区分“最多 10 行的来源测试”和“不截断的完整看板读取”。
- `src/auto_check/modules/dashboard_management/system_data.py`：系统查询字段输入与跨年 12 月迟到数据查询；支持完整读取。
- `src/auto_check/modules/dashboard_management/service.py`：唯一固定看板结果投影、`data_year`、跨年写入、`data_not_ready`、`truncated_result`、内部/外部预览一致。
- `src/auto_check/modules/dashboard_management/api.py`：内部和外部预览使用相同响应业务包络，外部 `data` 增加 `data_year`；监控边界不变。
- `src/auto_check/modules/dashboard_management/web/screens/financial-report.html`：页面只使用 `reconciliation_completed_time` 展示时分。
- `src/auto_check/modules/dashboard_management/manifest.json`：在当前模块版本中合并契约与预览一致性说明，不增加重复更新项。

### 测试

- `tests/modules/dashboard_management/test_catalog.py`
- `tests/modules/dashboard_management/test_year_snapshots.py`
- `tests/modules/dashboard_management/test_storage.py`
- `tests/modules/dashboard_management/test_sql_executor.py`
- `tests/modules/dashboard_management/test_system_data.py`
- `tests/modules/dashboard_management/test_sql_preview_api.py`
- `tests/modules/dashboard_management/test_service.py`
- `tests/modules/dashboard_management/test_api.py`
- `tests/modules/dashboard_management/test_module_integration.py`
- `tests/modules/dashboard_management/test_frontend_static.py`
- `tests/modules/dashboard_management/test_manifest_and_migrations.py`

### 文档

- `docs/dashboard-management-external-api.zh-CN.md`：唯一正式对外契约、样例、完整性与消费规则。
- `src/auto_check/modules/dashboard_management/README.md`：模块内部来源、快照、预览和运维说明。
- `docs/superpowers/specs/2026-09-15-dashboard-year-snapshots-design.md`：修正旧的“完整日期裁剪为 HH:mm”描述。
- `docs/superpowers/specs/2026-09-16-dashboard-external-api-contract-design.md`：保持已批准设计与实现一致。
- `README.md`：详细记录 22 个固定字段、时间双字段、跨年和预览一致性。

---

### Task 1: 固定字段与年度快照日期契约

**Files:**
- Modify: `src/auto_check/modules/dashboard_management/catalog.py:62-64`
- Modify: `src/auto_check/modules/dashboard_management/year_snapshots.py:9-208`
- Test: `tests/modules/dashboard_management/test_catalog.py`
- Test: `tests/modules/dashboard_management/test_year_snapshots.py`
- Test: `tests/modules/dashboard_management/test_storage.py:35-105`

**Interfaces:**
- Produces: `normalize_reconciliation_completion_row(raw_row: Mapping[str, Any], *, allow_legacy_time: bool) -> dict[str, Any]`
- Produces: `normalize_snapshot_rows(region_code: str, rows: Sequence[Mapping[str, Any]], now: datetime) -> tuple[SnapshotRow, ...]`
- Produces: `RECONCILIATION_COMPLETED_TIME = "reconciliation_completed_time"`
- Consumes: 现有 `SnapshotRow`、`INITIAL_2026_SNAPSHOT_ROWS` 和字段播种逻辑。

- [ ] **Step 1: 先把字段数和双字段契约写成失败测试**

在 `tests/modules/dashboard_management/test_catalog.py` 将字段总数改为 22，并增加精确顺序断言：

```python
def test_reconciliation_completion_fields_separate_display_time_and_full_datetime() -> None:
    from auto_check.modules.dashboard_management.catalog import BUILTIN_FIELD_SEEDS

    fields = [
        item
        for item in BUILTIN_FIELD_SEEDS
        if item.region_code == "report_reconciliation_completion_time"
    ]

    assert [(item.alias, item.value_type, item.nullable, item.display_order) for item in fields] == [
        ("month", "string", False, 10),
        ("reconciliation_completed_time", "string", False, 20),
        ("reconciliation_completed_at", "datetime", True, 30),
    ]
```

将现有 `len(BUILTIN_FIELD_SEEDS) == 21` 改为 `22`。

- [ ] **Step 2: 写日期、跨月、跨年和旧快照兼容的失败测试**

在 `tests/modules/dashboard_management/test_year_snapshots.py` 用以下断言替换“完整日期被裁剪为时分”的旧断言，并补齐边界：

```python
def test_reconciliation_rows_keep_full_datetime_and_derive_display_time() -> None:
    from auto_check.modules.dashboard_management.year_snapshots import normalize_snapshot_rows

    rows = normalize_snapshot_rows(
        "report_reconciliation_completion_time",
        ({
            "month": "2026-08",
            "reconciliation_completed_at": "2026-09-15T09:30:47",
        },),
        datetime(2026, 9, 16, 10, 0),
    )

    assert rows[0].period_year == 2026
    assert rows[0].period_value == 8
    assert rows[0].row == {
        "month": "2026-08",
        "reconciliation_completed_time": "09:30",
        "reconciliation_completed_at": "2026-09-15T09:30:47",
    }


def test_january_accepts_previous_december_late_completion_without_mixing_year() -> None:
    from auto_check.modules.dashboard_management.year_snapshots import normalize_snapshot_rows

    rows = normalize_snapshot_rows(
        "report_reconciliation_completion_time",
        ({
            "month": "2026-12",
            "reconciliation_completed_at": "2027-01-03T01:15:00",
        },),
        datetime(2027, 1, 4, 9, 0),
    )

    assert rows[0].period_year == 2026
    assert rows[0].row["reconciliation_completed_time"] == "01:15"
    assert rows[0].row["reconciliation_completed_at"] == "2027-01-03T01:15:00"


@pytest.mark.parametrize("value", ["09:30", time(9, 30), None, "not-a-datetime"])
def test_new_reconciliation_rows_reject_missing_or_time_only_completion(value) -> None:
    from auto_check.modules.dashboard_management.year_snapshots import (
        SnapshotValidationError,
        normalize_snapshot_rows,
    )

    with pytest.raises(SnapshotValidationError, match="完整日期时间"):
        normalize_snapshot_rows(
            "report_reconciliation_completion_time",
            ({"month": "2026-08", "reconciliation_completed_at": value},),
            datetime(2026, 9, 16, 10, 0),
        )


def test_legacy_time_only_snapshot_is_exposed_without_fabricated_date() -> None:
    from auto_check.modules.dashboard_management.year_snapshots import (
        normalize_reconciliation_completion_row,
    )

    assert normalize_reconciliation_completion_row(
        {"month": "2026-01", "reconciliation_completed_at": "21:00"},
        allow_legacy_time=True,
    ) == {
        "month": "2026-01",
        "reconciliation_completed_time": "21:00",
        "reconciliation_completed_at": None,
    }
```

另加两个拒绝断言：2027 年 2 月请求不得再接收 2026-12；2027 年 1 月不得接收 2026-11。

- [ ] **Step 3: 运行最小测试并确认失败原因正确**

Run:

```powershell
python -m pytest -q tests/modules/dashboard_management/test_catalog.py tests/modules/dashboard_management/test_year_snapshots.py tests/modules/dashboard_management/test_storage.py::test_storage_seeds_catalog_source_configs_and_confirmed_2026_snapshots
```

Expected: FAIL；失败点应是字段仍为 21 个、缺少 `reconciliation_completed_time`、完整日期仍被裁剪、历史初始化仍把 `HH:mm` 放在 `reconciliation_completed_at`。

- [ ] **Step 4: 实现双字段和严格日期规范化**

在 `catalog.py` 使用以下固定字段：

```python
FieldSeed(
    "report_reconciliation_completion_time",
    "month",
    "月份",
    "string",
    False,
    10,
    "统计月份。格式：YYYY-MM，例如：2026-08。",
),
FieldSeed(
    "report_reconciliation_completion_time",
    "reconciliation_completed_time",
    "对账完成时间",
    "string",
    False,
    20,
    "页面展示时分。格式：HH:mm，例如：09:30。",
),
FieldSeed(
    "report_reconciliation_completion_time",
    "reconciliation_completed_at",
    "实际对账完成日期时间",
    "datetime",
    True,
    30,
    "实际完成日期时间。格式：YYYY-MM-DDTHH:mm:ss；历史未知日期时为 null。",
),
```

在 `year_snapshots.py` 增加业务时区和统一转换函数；完整实现保持以下签名和返回格式：

```python
from zoneinfo import ZoneInfo

BUSINESS_TIMEZONE = ZoneInfo("Asia/Shanghai")
RECONCILIATION_COMPLETED_TIME = "reconciliation_completed_time"


def _local_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, time) or value is None:
        raise ValueError("新数据必须提供完整日期时间")
    else:
        text = str(value).strip()
        if not text or ("T" not in text and " " not in text):
            raise ValueError("新数据必须提供完整日期时间")
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(BUSINESS_TIMEZONE).replace(tzinfo=None)
    return parsed.replace(microsecond=0)


def _display_time(value: Any) -> str:
    if isinstance(value, time):
        parsed = value
    else:
        parsed = time.fromisoformat(str(value).strip())
    return parsed.strftime("%H:%M")


def normalize_reconciliation_completion_row(
    raw_row: Mapping[str, Any], *, allow_legacy_time: bool
) -> dict[str, Any]:
    row = dict(raw_row)
    completed_at = row.get("reconciliation_completed_at")
    display_time = row.get(RECONCILIATION_COMPLETED_TIME)
    if allow_legacy_time and completed_at is not None:
        text = str(completed_at).strip()
        if "T" not in text and " " not in text:
            row[RECONCILIATION_COMPLETED_TIME] = _display_time(text)
            row["reconciliation_completed_at"] = None
            return row
    if completed_at is None:
        if not allow_legacy_time or display_time is None:
            raise ValueError("新数据必须提供完整日期时间")
        row[RECONCILIATION_COMPLETED_TIME] = _display_time(display_time)
        row["reconciliation_completed_at"] = None
        return row
    parsed = _local_datetime(completed_at)
    row[RECONCILIATION_COMPLETED_TIME] = parsed.strftime("%H:%M")
    row["reconciliation_completed_at"] = parsed.isoformat(timespec="seconds")
    return row
```

`normalize_snapshot_rows()` 继续忽略不属于响应年度的普通月/季度行，避免把来源中合法但不在本次投影范围内的周期混入响应；但“报表对账完成时间”命中合法业务月份后，若完整日期缺失、只有 `HH:mm` 或格式非法，必须抛出带稳定中文信息的 `SnapshotValidationError`，不得静默丢行或覆盖旧快照。`_month_period()` 增加 `allow_previous_december` 参数：仅对对账完成区域、仅在当前月份为 1 月、仅接收上一年 12 月。

初始化 2026 年 1—6 月数据改为：

```python
{
    "month": f"2026-{month:02d}",
    "reconciliation_completed_time": completed_time,
    "reconciliation_completed_at": None,
}
```

- [ ] **Step 5: 运行测试并确认新契约通过**

Run:

```powershell
python -m pytest -q tests/modules/dashboard_management/test_catalog.py tests/modules/dashboard_management/test_year_snapshots.py tests/modules/dashboard_management/test_storage.py::test_storage_seeds_catalog_source_configs_and_confirmed_2026_snapshots
```

Expected: PASS；初始化快照断言应同时验证 6 个 `reconciliation_completed_time` 值和 6 个 `reconciliation_completed_at is None`。

- [ ] **Step 6: 授权后按原子边界提交**

```powershell
git add -p src/auto_check/modules/dashboard_management/catalog.py src/auto_check/modules/dashboard_management/year_snapshots.py tests/modules/dashboard_management/test_catalog.py tests/modules/dashboard_management/test_year_snapshots.py tests/modules/dashboard_management/test_storage.py
git commit -m "修正看板对账完成日期字段契约"
```

Expected: 提交只包含字段目录、年度快照规范化及对应测试；若未获提交授权则跳过本步骤。

---

### Task 2: 来源输入字段与完整看板读取执行器

**Files:**
- Modify: `src/auto_check/modules/dashboard_management/sql_executor.py:98-206`
- Modify: `src/auto_check/modules/dashboard_management/system_data.py:96-116,206-270`
- Modify: `src/auto_check/modules/dashboard_management/service.py:42-65,388-535`
- Test: `tests/modules/dashboard_management/test_sql_executor.py`
- Test: `tests/modules/dashboard_management/test_system_data.py`
- Test: `tests/modules/dashboard_management/test_sql_preview_api.py`

**Interfaces:**
- Produces: `SqlPreviewExecutor(preview_limit: int | None = 10)`；`None` 表示读取全部行。
- Produces: `SystemDataPreviewExecutor(preview_limit: int | None = 10)`；`None` 表示读取全部行。
- Produces: `_source_fields(region_code: str, fields: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]`
- Produces: `_project_derived_preview(region_code: str, preview: QueryPreview, output_fields: Sequence[Mapping[str, Any]]) -> QueryPreview`
- Consumes: Task 1 的 `normalize_reconciliation_completion_row()`。

- [ ] **Step 1: 写“不截断完整读取”和“来源无需返回派生字段”的失败测试**

在 `tests/modules/dashboard_management/test_sql_executor.py` 增加：

```python
def test_unlimited_executor_fetches_all_rows_without_has_more(monkeypatch) -> None:
    from auto_check.modules.dashboard_management.sql_executor import SqlPreviewExecutor

    rows = [(index,) for index in range(25)]
    connection = _Connection(["value"], rows)
    _install_driver(monkeypatch, "postgresql", connection)

    preview = SqlPreviewExecutor(preview_limit=None).execute(
        _source(), "SELECT value", _fields(("value", "integer", False)), "list"
    )

    assert preview.returned_count == 25
    assert preview.has_more is False
    assert len(preview.rows) == 25
    assert connection.calls[-1] == ("fetchall", None)
```

测试游标增加：

```python
def fetchall(self):
    self.calls.append(("fetchall", None))
    return list(self.rows)
```

在 `tests/modules/dashboard_management/test_sql_preview_api.py` 增加以下完整 service 测试：

```python
def test_reconciliation_sql_test_requires_datetime_and_returns_derived_time():
    from auto_check.modules.dashboard_management.service import DashboardManagementService
    from auto_check.modules.dashboard_management.sql_executor import QueryPreview

    fields = [
        {"field_alias": "month", "value_type": "string", "nullable": False, "enabled": True},
        {"field_alias": "reconciliation_completed_time", "value_type": "string", "nullable": False, "enabled": True},
        {"field_alias": "reconciliation_completed_at", "value_type": "datetime", "nullable": True, "enabled": True},
    ]
    captured_aliases = []

    class Storage:
        def get_region(self, region_id):
            return {
                "id": region_id,
                "region_code": "report_reconciliation_completion_time",
                "shape": "list",
                "system_supported": True,
                "row_version": 1,
            }

        def list_fields(self, region_id, include_disabled=False):
            return fields

        def record_successful_sql_test(self, region_id, signature, username, schema_version):
            return {"row_version": 2, "tested_signature": signature}

    class Executor:
        def execute(self, source, sql, active_fields, shape):
            captured_aliases.extend(field["field_alias"] for field in active_fields)
            return QueryPreview(
                columns=("month", "reconciliation_completed_at"),
                rows=({
                    "month": "2026-08",
                    "reconciliation_completed_at": "2026-09-15T09:30:00",
                },),
                has_more=False,
                returned_count=1,
                tested_signature="a" * 64,
            )

    source = {"id": "safe", "config": object()}
    service = DashboardManagementService(
        Storage(), datasource_loader=lambda: [source], sql_executor=Executor()
    )
    response = service.test_sql(
        1,
        {"datasource_id": "safe", "sql_text": "SELECT month, completed_at"},
        {"username": "admin"},
    )

    assert captured_aliases == ["month", "reconciliation_completed_at"]
    assert response["columns"] == (
        "month", "reconciliation_completed_time", "reconciliation_completed_at",
    )
    assert response["rows"][0] == {
        "month": "2026-08",
        "reconciliation_completed_time": "09:30",
        "reconciliation_completed_at": "2026-09-15T09:30:00",
    }
```

- [ ] **Step 2: 写系统数据跨年查询和无限读取的失败测试**

在 `tests/modules/dashboard_management/test_system_data.py` 增加：

```python
def test_reconciliation_system_query_reads_previous_december_only_during_january() -> None:
    from auto_check.modules.dashboard_management.system_data import SYSTEM_QUERY_DEFINITIONS

    sql = SYSTEM_QUERY_DEFINITIONS["report_reconciliation_completion_time"].sql
    assert "MONTH(CURRENT_DATE) = 1" in sql
    assert "YEAR(header.run_date) = YEAR(CURRENT_DATE) - 1" in sql
    assert "MONTH(header.run_date) = 12" in sql


def test_unlimited_system_preview_fetches_all_rows() -> None:
    from auto_check.modules.dashboard_management.system_data import SystemDataPreviewExecutor

    class Result:
        def keys(self):
            return ("report_type", "reporting_date")

        def fetchall(self):
            return [
                ("1104", date(2026, 9, 20)),
                ("1105", date(2026, 9, 21)),
            ]

    class Connection(_Connection):
        def execute(self, statement):
            self.sql = str(statement)
            return Result()

    database = _Database()
    database.connection = Connection()
    fields = [
        {"field_alias": "report_type", "value_type": "string", "nullable": False, "enabled": True},
        {"field_alias": "reporting_date", "value_type": "date", "nullable": True, "enabled": True},
    ]

    result = SystemDataPreviewExecutor(preview_limit=None).execute(
        database, "monthly_regulatory_report_time", fields, "list",
    )

    assert result.preview.has_more is False
    assert result.preview.returned_count == 2
    assert result.preview.rows[-1]["report_type"] == "1105"
```

测试 `_Result` 同样实现 `fetchall()`；默认 `SystemDataPreviewExecutor()` 的旧测试继续断言 `fetchmany(11)`，以保证来源编辑区仍为 10 行。

- [ ] **Step 3: 运行最小测试并确认失败**

Run:

```powershell
python -m pytest -q tests/modules/dashboard_management/test_sql_executor.py tests/modules/dashboard_management/test_system_data.py tests/modules/dashboard_management/test_sql_preview_api.py
```

Expected: FAIL；失败点应为构造器不接受 `None`、游标仍调用 `fetchmany`、服务仍要求 SQL 返回派生时分字段或尚未补出该字段。

- [ ] **Step 4: 为两个执行器增加明确的无限读取模式**

`SqlPreviewExecutor` 使用以下分支，不改变默认 10 行行为：

```python
class SqlPreviewExecutor:
    def __init__(
        self,
        connect_timeout_seconds: int = 5,
        query_timeout_seconds: int = 10,
        preview_limit: int | None = 10,
    ) -> None:
        if preview_limit is not None and preview_limit < 1:
            raise ValueError("preview_limit 必须大于 0 或为 None")
        self.connect_timeout_seconds = connect_timeout_seconds
        self.query_timeout_seconds = query_timeout_seconds
        self.preview_limit = preview_limit

    def _visible_rows(self, rows: list[Sequence[Any]]) -> tuple[list[Sequence[Any]], bool]:
        if self.preview_limit is None:
            return rows, False
        return rows[: self.preview_limit], len(rows) > self.preview_limit
```

`_query()` 在 `preview_limit is None` 时调用 `cursor.fetchall()`；否则继续 `fetchmany(preview_limit + 1)`。`execute()` 只转换 `_visible_rows()` 返回的行，并用同一个布尔值设置 `has_more`。

`SystemDataPreviewExecutor` 使用同样的 `int | None` 校验、`fetchall/fetchmany` 分支和 `has_more` 规则。

- [ ] **Step 5: 将展示时分明确设为 AutoCheck 派生字段**

在 `service.py` 增加并在 `test_sql()`、`preview_system_data()`、`save_source_config()` 的签名计算及 `_execute_saved_region()` 中使用：

```python
from typing import Any, Callable, Mapping, Sequence


def _source_fields(
    region_code: str, fields: Sequence[Mapping[str, Any]]
) -> list[Mapping[str, Any]]:
    if region_code != "report_reconciliation_completion_time":
        return list(fields)
    return [
        field
        for field in fields
        if str(field["field_alias"]) != "reconciliation_completed_time"
    ]


def _project_derived_preview(
    region_code: str,
    preview: QueryPreview,
    output_fields: Sequence[Mapping[str, Any]],
) -> QueryPreview:
    if region_code != "report_reconciliation_completion_time":
        return preview
    columns = tuple(str(field["field_alias"]) for field in output_fields)
    rows = tuple(
        {
            alias: normalized.get(alias)
            for alias in columns
        }
        for row in preview.rows
        for normalized in (
            normalize_reconciliation_completion_row(row, allow_legacy_time=False),
        )
    )
    return QueryPreview(
        columns=columns,
        rows=rows,
        has_more=preview.has_more,
        returned_count=len(rows),
        tested_signature=preview.tested_signature,
    )
```

保存 SQL 时的 `expected_signature` 必须使用 `_source_fields()`，保证“测试成功”与随后保存使用同一输入字段集合。

- [ ] **Step 6: 调整系统查询但不让来源伪造展示字段**

`SYSTEM_QUERY_DEFINITIONS["report_reconciliation_completion_time"]` 的来源字段仍为 `month` 和 `reconciliation_completed_at`；SQL 只增加上一年 12 月的 1 月补采范围：

```sql
AND (
      YEAR(header.run_date) = YEAR(CURRENT_DATE)
      OR (
           MONTH(CURRENT_DATE) = 1
           AND YEAR(header.run_date) = YEAR(CURRENT_DATE) - 1
           AND MONTH(header.run_date) = 12
      )
    )
```

显示时分继续由 Task 1 的 Python 规范化函数派生，SQL 不重复计算。

- [ ] **Step 7: 运行三组测试并确认通过**

Run:

```powershell
python -m pytest -q tests/modules/dashboard_management/test_sql_executor.py tests/modules/dashboard_management/test_system_data.py tests/modules/dashboard_management/test_sql_preview_api.py
```

Expected: PASS；默认测试预览仍为 10 行，无限执行器完整返回，SQL 测试只要求完整日期时间并补出展示时分。

- [ ] **Step 8: 授权后按原子边界提交**

```powershell
git add -p src/auto_check/modules/dashboard_management/sql_executor.py src/auto_check/modules/dashboard_management/system_data.py src/auto_check/modules/dashboard_management/service.py tests/modules/dashboard_management/test_sql_executor.py tests/modules/dashboard_management/test_system_data.py tests/modules/dashboard_management/test_sql_preview_api.py
git commit -m "区分看板完整读取与来源测试预览"
```

Expected: 提交不包含快照结果投影和 API 包络改动；若未获提交授权则跳过本步骤。

---

### Task 3: 唯一固定看板投影、跨年与完整性错误

**Files:**
- Modify: `src/auto_check/modules/dashboard_management/service.py:42-295,590-675`
- Test: `tests/modules/dashboard_management/test_service.py:257-650`

**Interfaces:**
- Produces: `TruncatedResultError`，区域错误码固定为 `truncated_result`。
- Produces: `SnapshotDataNotReadyError`，区域错误码固定为 `data_not_ready`。
- Produces: `_preview_fixed_board_data(board_code: str) -> dict[str, Any]`，返回 `status/generated_at/data_year/board/regions`。
- Consumes: Task 1 的规范化函数和 Task 2 的完整读取执行器。

- [ ] **Step 1: 将内部/外部固定投影一致写成失败测试**

替换 `test_external_board_preview_uses_only_fixed_builtin_regions_and_fields` 中“内部预览会泄露自定义区域”的旧断言：

```python
internal_submission = service.preview_board_data("report_submission", admin)
external_submission = service.preview_external_board_data("report_submission")

assert internal_submission == external_submission
assert internal_submission["data_year"] == 2026
assert [item["code"] for item in internal_submission["regions"]] == [
    seed.code
    for seed in BUILTIN_REGION_SEEDS
    if seed.board_code == "report_submission"
]
assert custom_region["region_code"] not in str(internal_submission)
assert "must_not_leak" not in str(internal_submission)
```

同时保留目录接口断言，证明自定义区域和字段仍能配置、仍能做来源测试，只是不进入固定完整看板。

- [ ] **Step 2: 写跨年存储但不混年返回的失败测试**

在 `test_service.py` 增加：

```python
def test_january_writes_previous_december_but_returns_only_current_data_year(storage, admin):
    from auto_check.modules.dashboard_management.service import DashboardManagementService
    from auto_check.modules.dashboard_management.sql_executor import QueryPreview

    now = datetime(2027, 1, 4, 9, 0)
    completion_region = next(
        row for row in storage.list_regions("report_submission")
        if row["region_code"] == "report_reconciliation_completion_time"
    )

    class SystemExecutor:
        def execute(self, database, region_code, active_fields, shape):
            if region_code != "report_reconciliation_completion_time":
                raise RuntimeError("unrelated system region")
            preview = QueryPreview(
                columns=("month", "reconciliation_completed_at"),
                rows=(
                    {"month": "2026-12", "reconciliation_completed_at": "2027-01-03T01:15:00"},
                    {"month": "2027-01", "reconciliation_completed_at": "2027-01-04T08:30:00"},
                ),
                has_more=False,
                returned_count=2,
                tested_signature="",
            )
            return type("Result", (), {"preview": preview})()

    service = DashboardManagementService(
        storage, system_executor=SystemExecutor(), now=lambda: now
    )
    result = service.preview_external_board_data("report_submission")
    completion = next(
        item for item in result["regions"]
        if item["code"] == "report_reconciliation_completion_time"
    )

    assert result["data_year"] == 2027
    assert [row["month"] for row in completion["rows"]] == ["2027-01"]
    assert storage.list_year_snapshots(completion_region["id"], 2026)[-1]["row"]["month"] == "2026-12"
    assert storage.list_year_snapshots(completion_region["id"], 2027)[0]["row"]["month"] == "2027-01"
```

- [ ] **Step 3: 写新年度未准备和截断错误的失败测试**

将现有 `test_snapshot_preview_without_current_year_history_keeps_existing_error` 改为：

```python
assert item["status"] == "error"
assert item["error"] == {
    "code": "data_not_ready",
    "message": "当前年度数据尚未准备完成",
}
assert result["status"] == "partial"
assert result["data_year"] == 2027
```

将现有“截断后回退旧快照成功”测试改为：

```python
assert item["status"] == "error"
assert item["error"] == {
    "code": "truncated_result",
    "message": "数据来源未返回完整结果",
}
assert "rows" not in item
assert storage.list_year_snapshots(trust["id"], 2026)[5]["row"]["single_trust_count"] == 4
assert result["status"] == "partial"
```

- [ ] **Step 4: 写超过 10 行仍完整返回的失败测试**

选择 `reporting_process` 中的 `regulatory_report_count`，保存测试来源并让执行器替身返回 15 行：

```python
def test_fixed_board_returns_more_than_ten_rows_without_truncation(storage):
    from auto_check.modules.dashboard_management.service import DashboardManagementService
    from auto_check.modules.dashboard_management.sql_executor import QueryPreview

    region = next(
        row for row in storage.list_regions("reporting_process")
        if row["region_code"] == "regulatory_report_count"
    )
    source_config = storage.get_source_config(region["id"])
    storage.save_source_config(
        region["id"],
        {
            "source_mode": "sql",
            "datasource_id": "safe",
            "sql_text": "SELECT report_type, report_count",
            "tested_signature": "valid",
            "tested_at": datetime(2026, 9, 16, 8, 0),
            "tested_by": "admin",
        },
        source_config["row_version"],
        expected_region_version=region["row_version"],
    )
    rows = tuple(
        {"report_type": f"R{index:02d}", "report_count": index}
        for index in range(15)
    )

    class SqlExecutor:
        def signature_for(self, source, sql, active_fields, shape):
            return "valid"

        def execute(self, source, sql, active_fields, shape):
            return QueryPreview(
                columns=("report_type", "report_count"),
                rows=rows,
                has_more=False,
                returned_count=len(rows),
                tested_signature="valid",
            )

    service = DashboardManagementService(
        storage,
        datasource_loader=lambda: [{"id": "safe", "config": object()}],
        sql_executor=SqlExecutor(),
        now=lambda: datetime(2026, 9, 16, 9, 0),
    )
    result = service.preview_external_board_data("reporting_process")
    item = next(
        entry for entry in result["regions"]
        if entry["code"] == "regulatory_report_count"
    )

    assert item["status"] == "success"
    assert item["has_more"] is False
    assert item["returned_count"] == 15
    assert item["rows"] == rows
```

另加一致性断言：每个成功区域均满足 `returned_count == len(rows)` 且 `has_more is False`。

- [ ] **Step 5: 运行 service 测试并确认旧分支失败**

Run:

```powershell
python -m pytest -q tests/modules/dashboard_management/test_service.py
```

Expected: FAIL；内部结果仍含自定义区域、缺少 `data_year`、上一年 12 月被过滤、新年度错误仍为 `internal_error`、截断仍回退为成功。

- [ ] **Step 6: 合并为唯一固定看板结果投影**

把两个公开方法改成共用实现：

```python
def preview_board_data(
    self, board_code: str, current_user: Mapping[str, Any]
) -> dict[str, Any]:
    del current_user
    return self._preview_fixed_board_data(validate_board_code(board_code))


def preview_external_board_data(self, board_code: str) -> dict[str, Any]:
    try:
        selected = validate_board_code(board_code)
    except ValidationError as error:
        raise NotFoundError("外部看板接口不存在") from error
    return self._preview_fixed_board_data(selected)
```

`_preview_fixed_board_data()` 始终按 `BUILTIN_REGION_SEEDS` 与 `BUILTIN_FIELD_SEEDS` 生成 7+3 固定区域，不再根据调用方切换“内部自定义投影/外部固定投影”。返回值固定为：

```python
return {
    "status": "partial" if any(item.get("status") == "error" for item in regions) else "success",
    "generated_at": _datetime_text(request_now),
    "data_year": request_now.year,
    "board": {"code": board.code, "name": board.name},
    "regions": regions,
}
```

默认构造器保留 10 行编辑预览执行器，并增加完整看板执行器：

```python
self._sql_executor = sql_executor or SqlPreviewExecutor()
self._board_sql_executor = sql_executor or SqlPreviewExecutor(preview_limit=None)
self._system_executor = system_executor or SystemDataPreviewExecutor()
self._board_system_executor = system_executor or SystemDataPreviewExecutor(preview_limit=None)
```

`_execute_saved_region()` 的完整看板路径只使用 `_board_*_executor`。

- [ ] **Step 7: 实现精确错误分类和禁止截断回退**

在 `service.py` 增加：

```python
class TruncatedResultError(ValueError):
    pass


class SnapshotDataNotReadyError(ValueError):
    pass
```

任何完整看板 `preview.has_more` 立即抛 `TruncatedResultError`。异常处理顺序固定为：

```python
except TruncatedResultError as error:
    item.update(_preview_error(error))
except (SnapshotValidationError, SnapshotDataNotReadyError) as error:
    item.update(_preview_error(error))
except Exception as error:
    if not snapshot_enabled:
        item.update(_preview_error(error))
    else:
        fallback = self._snapshot_fallback(
            region,
            fields,
            period_year=request_now.year,
            request_now=request_now,
        )
        if fallback is None:
            item.update(_preview_error(SnapshotDataNotReadyError()))
        else:
            preview, refreshed_at = fallback
            item.update(_preview_item(preview))
            item.update({
                "snapshot_status": "stale",
                "snapshot_refreshed_at": refreshed_at,
            })
```

在进入上述运行故障回退前，`SnapshotValidationError`、`TruncatedResultError`，以及带字段明细的 `ValidationError` 必须先作为契约错误直接返回；只有连接、超时、表不可用等无法形成新结果的运行故障可以回退同年度完整快照。

`_preview_error()` 增加稳定映射：

```python
if isinstance(error, TruncatedResultError):
    return {
        "status": "error",
        "error": {"code": "truncated_result", "message": "数据来源未返回完整结果"},
    }
if isinstance(error, SnapshotDataNotReadyError):
    return {
        "status": "error",
        "error": {"code": "data_not_ready", "message": "当前年度数据尚未准备完成"},
    }
```

字段缺失、类型错误、非法周期和只有 `HH:mm` 的新数据继续映射 `invalid_request`，不允许用旧快照掩盖契约错误。

- [ ] **Step 8: 实现按业务期跨年写入与当前年投影**

`normalize_snapshot_rows()` 返回的多年度行全部交给现有 `storage.refresh_year_snapshots()`；该方法已按每行 `SnapshotRow.period_year` upsert，并按参数 `period_year` 读取当前响应年度。调用保持：

```python
normalized = normalize_snapshot_rows(region_code, preview.rows, request_now)
snapshots = self.storage.refresh_year_snapshots(
    int(region["id"]),
    normalized,
    period_year=request_now.year,
    refreshed_at=request_now,
)
if not snapshots:
    raise SnapshotDataNotReadyError()
```

`_snapshot_preview()` 在投影存量行前调用：

```python
row = (
    normalize_reconciliation_completion_row(
        snapshot["row"], allow_legacy_time=True
    )
    if region_code == "report_reconciliation_completion_time"
    else dict(snapshot["row"])
)
```

这样现有数据库中 `reconciliation_completed_at="21:00"` 的旧 JSON 会输出为 `time="21:00", at=null`，无需修改已发布迁移或批量写库。

季度未来补零仅在当前年度已有至少一条真实/历史快照后执行；空年度先触发 `data_not_ready`。

- [ ] **Step 9: 运行 service 测试并确认通过**

Run:

```powershell
python -m pytest -q tests/modules/dashboard_management/test_service.py
```

Expected: PASS；内部/外部 service 结果完全一致，当前响应不混年，截断与未准备错误码稳定，运行故障仍可使用同年度 stale 快照。

- [ ] **Step 10: 授权后按原子边界提交**

```powershell
git add -p src/auto_check/modules/dashboard_management/service.py tests/modules/dashboard_management/test_service.py
git commit -m "统一看板预览与外部接口数据投影"
```

Expected: 提交只包含固定看板 service 契约及测试；若未获提交授权则跳过本步骤。

---

### Task 4: 内外 API 包络一致与监控隔离

**Files:**
- Modify: `src/auto_check/modules/dashboard_management/api.py:36-46,117-151`
- Test: `tests/modules/dashboard_management/test_api.py:17-184,273-360`
- Test: `tests/modules/dashboard_management/test_module_integration.py:150-220`

**Interfaces:**
- Produces: `_board_success(data: Mapping[str, Any], request_id: str) -> ModuleHttpResponse`
- Consumes: Task 3 的 `status/generated_at/data_year/board/regions` 结果。

- [ ] **Step 1: 写内部与外部响应业务内容一致的失败测试**

更新 API 测试中的假 service，让 `preview_board_data()` 与 `preview_external_board_data()` 返回同一结构，并增加：

```python
def test_internal_and_external_board_preview_publish_the_same_business_payload():
    router = _router()
    internal = _dispatch(router, "GET", "/boards/report_submission/preview")
    external = _dispatch_external(router, "GET", "/boards/report_submission/preview")

    assert internal.status == external.status == 200
    assert internal.body["status"] == external.body["status"]
    assert internal.body["generated_at"] == external.body["generated_at"]
    assert internal.body["data"] == external.body["data"]
    assert internal.body["data"]["data_year"] == 2026
    assert internal.body["meta"]["request_id"].startswith("req-")
    assert external.body["meta"]["request_id"].startswith("req-")
```

删除旧的 `test_internal_board_preview_response_contract_is_unchanged`，因为用户已明确要求内部预览与真实看板一致。

- [ ] **Step 2: 加固“不记录内部预览”的现有测试**

保留并扩展：

```python
response = _dispatch(router, "GET", "/boards/report_submission/preview")
assert response.body["data"]["data_year"] == 2026
assert monitoring.calls == []
```

外部预览仍断言 `begin_call`/`finish_call` 各一次，并继续校验真实 `client_ip` 和 `request_id`。不得改动监控路由、留存或页面查询。

- [ ] **Step 3: 运行 API 与集成测试并确认失败**

Run:

```powershell
python -m pytest -q tests/modules/dashboard_management/test_api.py tests/modules/dashboard_management/test_module_integration.py
```

Expected: FAIL；内部仍使用 `{data, meta}` 通用包络且外部 `data` 缺少 `data_year`。

- [ ] **Step 4: 使用同一个看板响应转换函数**

将 `_external_success()` 收敛为内外共用的 `_board_success()`：

```python
def _board_success(data: Mapping[str, Any], request_id: str) -> ModuleHttpResponse:
    return ModuleHttpResponse.json(200, {
        "status": str(data["status"]),
        "generated_at": str(data["generated_at"]),
        "data": _public_value({
            "data_year": int(data["data_year"]),
            "board": data["board"],
            "regions": data["regions"],
        }),
        "meta": {"request_id": request_id},
    })
```

`board_preview()` 的内部路径改为：

```python
return _board_success(
    service_provider().preview_board_data(board_code, request.current_user),
    request_id,
)
```

外部路径调用相同 `_board_success()`，但现有 `monitor.begin_call()` 与 `monitor.finish_call()` 只包围外部路径。错误状态码、认证和未知看板 404 保持不变。

- [ ] **Step 5: 运行 API、集成和监控回归测试**

Run:

```powershell
python -m pytest -q tests/modules/dashboard_management/test_api.py tests/modules/dashboard_management/test_module_integration.py tests/modules/dashboard_management/test_external_api_monitoring.py
```

Expected: PASS；内外业务包络一致，内部预览不产生调用记录，外部调用记录仍按原规则写入。

- [ ] **Step 6: 授权后按原子边界提交**

```powershell
git add -p src/auto_check/modules/dashboard_management/api.py tests/modules/dashboard_management/test_api.py tests/modules/dashboard_management/test_module_integration.py
git commit -m "统一内外看板预览响应包络"
```

Expected: 不包含接口监控实现改动；若未获提交授权则跳过本步骤。

---

### Task 5: AutoCheck 页面预览内容基准

**Files:**
- Modify: `src/auto_check/modules/dashboard_management/web/screens/financial-report.html:1186-1227`
- Verify only: `src/auto_check/modules/dashboard_management/web/screens/financial-report-flow.html:670-750`
- Test: `tests/modules/dashboard_management/test_frontend_static.py:100-124`

**Interfaces:**
- Consumes: Task 4 的内部固定看板响应，路径仍为 `/api/modules/dashboard-management/boards/{board_code}/preview`。
- Produces: 页面展示只读取 `reconciliation_completed_time`；两张预览页均只读取共同固定看板业务负载。

- [ ] **Step 1: 写页面必须使用展示时分字段的失败测试**

在 `test_frontend_static.py` 的页面契约测试中增加：

```python
assert "value: row.reconciliation_completed_time" in report
assert "value: row.reconciliation_completed_at" not in report
assert "payload?.data?.data_year" in report
assert "/api/external/" not in report and "/api/external/" not in process
assert report.count("/api/modules/dashboard-management/boards/report_submission/preview") == 1
assert process.count("/api/modules/dashboard-management/boards/reporting_process/preview") == 1
```

`data_year` 只用于确认页面收到哪一业务年度，不得用 `reconciliation_completed_at` 推导横轴月份。

- [ ] **Step 2: 运行静态测试并确认字段断言失败**

Run:

```powershell
python -m pytest -q tests/modules/dashboard_management/test_frontend_static.py::test_copied_dashboard_pages_use_only_dashboard_management_preview_api
```

Expected: FAIL；报送大屏当前仍读取 `row.reconciliation_completed_at`，且尚未读取 `data_year`。

- [ ] **Step 3: 修改页面映射但不重新设计页面**

在 `financial-report.html` 中读取响应后保存当前业务年度，并切换时分字段：

```javascript
const dataYear = Number(payload?.data?.data_year);
if (!Number.isInteger(dataYear)) {
  throw new Error('接口缺少有效的数据年度');
}
document.documentElement.dataset.dataYear = String(dataYear);

renderReconciliation(
  regionRows(payload, 'report_reconciliation_completion_time').map((row) => ({
    month: row.month,
    value: row.reconciliation_completed_time,
  }))
);
```

`financial-report-flow.html` 只补同样的 `data_year` 有效性检查和 `data-data-year` 标记，不改变既有布局、配色、区域标题和指标映射。两张页面继续通过内部鉴权路由读取数据；由于 Task 4 已统一业务包络，其内容与 Kanban 调用外部接口得到的内容一致。

- [ ] **Step 4: 运行前端静态与行为测试**

Run:

```powershell
python -m pytest -q tests/modules/dashboard_management/test_frontend_static.py tests/modules/dashboard_management/test_frontend_behavior.py
```

Expected: PASS；页面仍可在现有近全屏弹窗中打开，不新增按钮、菜单或能力码。

- [ ] **Step 5: 记录当前阶段可验收与后续 Kanban 验收边界**

当前 AutoCheck 实施验收以下内容：

```text
1. 接口数据预览与外部接口的 data_year、board、regions 完全一致。
2. 页面预览只使用相同 regions 渲染，且对账完成时间只显示 HH:mm。
3. 两张预览页的区域、标题、指标、月份顺序、空值规则保持为 AutoCheck 基准。
```

Kanban 阶段验收以下内容，并且不反向修改本次契约：

```text
1. 同一份接口响应分别注入 AutoCheck 预览与 Kanban 页面。
2. 以相同浏览器尺寸截取两个页面。
3. 逐项核对区域、标题、指标、月份顺序、空值和时间文本。
4. 发现差异时修改 Kanban 适配，不在 Kanban 侧重定义 AutoCheck 字段语义。
```

- [ ] **Step 6: 授权后按原子边界提交**

```powershell
git add -p src/auto_check/modules/dashboard_management/web/screens/financial-report.html src/auto_check/modules/dashboard_management/web/screens/financial-report-flow.html tests/modules/dashboard_management/test_frontend_static.py
git commit -m "统一看板页面预览与接口展示字段"
```

Expected: 只改变数据映射和年度校验，不改变现有视觉设计；若未获提交授权则跳过本步骤。

---

### Task 6: 正式接口文档、模块说明与更新记录

**Files:**
- Modify: `docs/dashboard-management-external-api.zh-CN.md`
- Modify: `src/auto_check/modules/dashboard_management/README.md`
- Modify: `docs/superpowers/specs/2026-09-15-dashboard-year-snapshots-design.md`
- Modify: `docs/superpowers/specs/2026-09-16-dashboard-external-api-contract-design.md`
- Modify: `src/auto_check/modules/dashboard_management/manifest.json`
- Modify: `README.md`
- Test: `tests/modules/dashboard_management/test_manifest_and_migrations.py:13-65`

**Interfaces:**
- Consumes: Tasks 1—5 的最终字段名、错误码和响应样例。
- Produces: Kanban 后续只需遵循的一份正式 `v1` 文档。

- [ ] **Step 1: 先扩展文档契约测试**

在 `test_manifest_and_migrations.py` 的外部接口文档测试中增加以下精确片段：

```python
for fragment in [
    '"data_year": 2026',
    '"reconciliation_completed_time": "09:30"',
    '"reconciliation_completed_at": "2026-09-15T09:30:00"',
    '"reconciliation_completed_at": null',
    '"code": "data_not_ready"',
    '"code": "truncated_result"',
    'month=2026-12',
    '2027-01',
    'has_more=false',
    'returned_count',
    'AutoCheck 预览',
]:
    assert fragment in content
```

目录测试继续断言 release notes 不超过 20 条，并新增“完整日期时间”和“预览一致”的关键字断言。

- [ ] **Step 2: 运行文档测试并确认失败**

Run:

```powershell
python -m pytest -q tests/modules/dashboard_management/test_manifest_and_migrations.py
```

Expected: FAIL；正式文档尚缺双字段、`data_year`、两个新错误码和预览一致性说明。

- [ ] **Step 3: 重写正式接口文档的冲突条款和样例**

`docs/dashboard-management-external-api.zh-CN.md` 必须明确：

```text
- data.data_year 是当前自然年整数；v1 不接收 year 参数。
- report_reconciliation_completion_time 固定为 month、reconciliation_completed_time、reconciliation_completed_at 三列。
- month 是唯一业务归属；完成日期跨月、跨年不改变业务期。
- 初始化历史 at=null，新数据 at 必须是完整日期时间。
- 成功列表 has_more=false，returned_count 等于 rows 长度。
- data_not_ready 与 truncated_result 均为区域错误，并使顶层 status=partial。
- partial 不得覆盖 Kanban 最近一次完整 success；不得再按区域拼接出一份跨年度“成功”结果。
- AutoCheck 的接口数据预览和看板页面预览是同一业务结果的本地验收入口。
```

完整成功样例至少包含：

```json
{
  "status": "success",
  "generated_at": "2026-09-16T09:00:00",
  "data": {
    "data_year": 2026,
    "board": {"code": "report_submission", "name": "金融监管报表报送大屏"},
    "regions": [
      {
        "code": "report_reconciliation_completion_time",
        "status": "success",
        "columns": [
          "month",
          "reconciliation_completed_time",
          "reconciliation_completed_at"
        ],
        "rows": [
          {
            "month": "2026-01",
            "reconciliation_completed_time": "21:00",
            "reconciliation_completed_at": null
          },
          {
            "month": "2026-08",
            "reconciliation_completed_time": "09:30",
            "reconciliation_completed_at": "2026-09-15T09:30:00"
          }
        ],
        "has_more": false,
        "returned_count": 2
      }
    ]
  },
  "meta": {"request_id": "req-example"}
}
```

跨年示例必须写清：`month=2026-12`、`reconciliation_completed_at=2027-01-03T01:15:00` 仍写入 2026 快照；2027 响应不得混入该行。

- [ ] **Step 4: 同步模块、旧设计与根 README**

同步规则：

```text
1. 模块 README 将“21 个内置字段”改为“22 个内置字段”。
2. 把“接口数据预览读取全部启用区域”改为“读取固定 7+3 区域和固定字段”；自定义内容只在配置/测试中可见。
3. 把“年度快照只接收当前年”改为“响应只返回 data_year；1 月可补写上一年 12 月对账迟到记录”。
4. 明确来源测试 10 行、完整看板不限行。
5. 旧年度快照设计删除“reconciliation_completed_at 只保留 HH:mm”的描述，改为 time/at 双字段。
6. 根 README 详细记录日期、跨年、完整性和预览一致性，不改展示大版本 V1.2。
```

`manifest.json` 保持 `version`/`release_notes.version` 为当前系统小版本，不新增第 21 条；直接合并改写以下既有条目：

```json
"看板管理模块：报表对账完成时间按业务月份归属，接口同时返回 HH:mm 展示时分与完整完成日期时间，历史未知日期保持 null",
"看板管理模块：接口数据预览、看板页面预览和两个外部接口共用固定 7+3 区域的完整结果，AutoCheck 页面作为 Kanban 适配基准",
"看板管理模块：四个年度趋势区域按业务期维护快照，响应通过 data_year 隔离年度，并支持 1 月补写上一年 12 月迟到对账记录",
"看板管理模块：为两个固定监管看板提供 Bearer Token 认证、完整列表和明确 data_not_ready/truncated_result 语义的外部只读数据接口"
```

不直接修改全局 `src/auto_check/web/app.js`：应用已有模块 release notes 聚合逻辑，模块说明会自动并入最新系统版本；本次也不新增菜单或公共 UI。

- [ ] **Step 5: 运行文档和清单测试**

Run:

```powershell
python -m pytest -q tests/modules/dashboard_management/test_manifest_and_migrations.py tests/modules/dashboard_management/test_catalog.py
```

Expected: PASS；正式文档、字段目录和 release notes 用词一致，release notes 条目数不超过 20。

- [ ] **Step 6: 人工做一次契约一致性搜索**

Run:

```powershell
rg -n "reconciliation_completed_at.*HH:mm|21 个内置字段|按区域使用缓存|预览前 10 行.*外部|data_year|truncated_result|data_not_ready" README.md docs src/auto_check/modules/dashboard_management
```

Expected: 不再出现把 `reconciliation_completed_at` 定义为 `HH:mm`、把固定字段数写为 21、让 Kanban 用 `partial` 分区拼接覆盖完整缓存等冲突描述；`data_year` 和两个错误码只出现在本次相关模块与文档中。

- [ ] **Step 7: 授权后按原子边界提交**

```powershell
git add -p docs/dashboard-management-external-api.zh-CN.md src/auto_check/modules/dashboard_management/README.md docs/superpowers/specs/2026-09-15-dashboard-year-snapshots-design.md docs/superpowers/specs/2026-09-16-dashboard-external-api-contract-design.md src/auto_check/modules/dashboard_management/manifest.json README.md tests/modules/dashboard_management/test_manifest_and_migrations.py
git commit -m "文档：冻结看板外部接口与预览一致性规范"
```

Expected: 只包含本次契约和模块说明；若未获提交授权则跳过本步骤。

---

### Task 7: 模块回归、全量验证与交付检查

**Files:**
- Verify: `src/auto_check/modules/dashboard_management/**`
- Verify: `tests/modules/dashboard_management/**`
- Verify: `docs/dashboard-management-external-api.zh-CN.md`
- Verify: `README.md`

**Interfaces:**
- Consumes: Tasks 1—6 的全部实现。
- Produces: 可进入 Kanban 适配阶段的 AutoCheck 契约基线和可复核测试证据。

- [ ] **Step 1: 运行最小关键链路测试**

Run:

```powershell
python -m pytest -q tests/modules/dashboard_management/test_year_snapshots.py tests/modules/dashboard_management/test_service.py tests/modules/dashboard_management/test_api.py tests/modules/dashboard_management/test_frontend_static.py
```

Expected: PASS，且输出中无 skipped/xfail 掩盖本次新增用例。

- [ ] **Step 2: 运行整个看板管理模块测试**

Run:

```powershell
python -m pytest -q tests/modules/dashboard_management
```

Expected: PASS；尤其确认来源测试仍为 10 行、完整看板可超过 10 行、监控记录和 IP 行为未变。

- [ ] **Step 3: 运行全量测试**

Run:

```powershell
python -m pytest -q
```

Expected: PASS；其他看板、模块、定时任务、自动对数和权限测试无回归。

- [ ] **Step 4: 检查差异范围和空白错误**

Run:

```powershell
git diff --check
git status --short
git diff --name-only
```

Expected: `git diff --check` 无真实 whitespace error；本次新增改动只位于 File Map 中列出的 `dashboard_management` 模块、对应测试和文档。工作区原有无关改动必须保留且不得纳入本任务结论。

- [ ] **Step 5: 完成 AutoCheck 页面验收记录**

在已配置本地开发库的环境运行：

```powershell
python -m auto_check
```

打开“系统管理 → 看板管理 → 预览当前看板”，分别验证“接口数据”和“看板页面”：

```text
- 两种预览均为固定 7+3 区域，不出现自定义区域或额外字段。
- 接口数据含 data.data_year。
- 报表对账完成时间含 month/time/at 三字段。
- 页面只显示 HH:mm，不显示或截断完整日期。
- 超过 10 行的数据在接口数据和页面中完整出现。
- 两张预览页的区域、标题、指标、月份顺序、空值和时间文本记录为后续 Kanban 同屏对照基准。
```

Expected: 页面内容与接口业务负载一致；本步骤不调用外部接口，因此不新增接口监控记录。

- [ ] **Step 6: 输出交付摘要，不打包、不推送**

交付摘要必须列明：

```text
1. 代码：时间双字段、完整读取、固定投影、跨年和错误码。
2. 配置/存储：无新迁移；现有字段目录自动补字段，旧 JSON 只读兼容。
3. 页面：AutoCheck 预览与真实接口共用负载，只显示 HH:mm，并成为 Kanban 页面基准。
4. 文档：正式 v1 契约、README、模块说明和历史设计已同步。
5. 验证：关键测试、模块测试、全量测试、diff check 的实际结果。
6. 边界：接口监控、其他模块、其他看板和定时任务未改；未打包、未推送。
```

若某项验证失败，必须报告具体命令、失败测试和剩余影响，不得宣称完成。

- [ ] **Step 7: 获得用户明确提交授权后提交最终剩余修正**

```powershell
git diff --name-only
git add -p
git commit -m "完善看板接口契约回归验证"
```

Expected: 仅在前述原子提交后仍有本任务修正时创建；没有剩余修正或未获授权时不提交。

---

## Implementation Completion Gate

只有以下条件全部满足，AutoCheck 侧才可进入 Kanban 适配阶段：

- [ ] 两个内部预览与两个外部接口使用同一 service 投影。
- [ ] 外部响应存在 `data.data_year`，且年度快照行不混年。
- [ ] 对账完成区域固定返回 `month`、`reconciliation_completed_time`、`reconciliation_completed_at`。
- [ ] 初始化历史完整日期为 `null`；新数据只有时分时失败。
- [ ] 1 月上一年 12 月迟到对账数据只写入上一年度快照。
- [ ] 新年度未准备使用 `data_not_ready`；截断使用 `truncated_result`。
- [ ] 所有成功列表 `has_more=false` 且 `returned_count == len(rows)`。
- [ ] 来源编辑测试仍最多 10 行；完整看板没有 10 行截断。
- [ ] AutoCheck 页面只显示 `HH:mm`，接口保留完整日期。
- [ ] 自定义区域/字段仍可配置和测试，但不进入固定完整看板。
- [ ] 接口监控、其他模块、其他看板和定时任务回归不变。
- [ ] 正式接口文档、代码、样例、测试和 AutoCheck 预览一致。
- [ ] 关键、模块及全量测试通过，`git diff --check` 无真实错误。
- [ ] 未经明确要求没有打包、提交或推送。
