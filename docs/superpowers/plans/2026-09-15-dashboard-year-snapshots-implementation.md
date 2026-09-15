# 看板年度趋势快照 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 看板预览接口在查询四个内置趋势区域时保存并返回当年快照，并为 2026 年初始化已确认的历史基线。

**Architecture:** 模块迁移 `002` 只创建模块命名空间下的快照表；模块启动在内置区域存在后幂等写入 2026 历史基线。新增独立的周期规范化文件负责月份、季度和完成时间转换，仓储负责确定性 JSON 与事务写入，服务层在实时查询成功时更新快照、失败时回退当年快照；其他区域仍沿用实时结果。

**Tech Stack:** Python 3.12、SQLAlchemy Core、MySQL 模块迁移、pytest。

## Global Constraints

- 只修改 `src/auto_check/modules/dashboard_management/`、`tests/modules/dashboard_management/`、模块发布版本契约测试 `tests/module_system/test_packaging.py`、`README.md` 和本功能设计/计划文档。
- 不修改平台公共入口、模块宿主、其他业务模块或外部数据库。
- 仅四个内置区域启用快照；其他区域和用户新增区域继续实时返回。
- 2026 年“月度信托项目数量”和“报表对账完成时间”初始化 1—6 月，“报表校验问题处理”初始化 1—8 月，“季度报表特殊处理”初始化第一、第二季度；其他 7 月以后数据不得预置。
- 看板预览接口只返回当前自然年的快照；实时查询未返回的旧周期不得删除。
- 不新增后台定时任务；现有看板预览轮询触发刷新。
- 本次不打包、不提交、不推送。

---

### Task 1: 快照表、基线与仓储

**Files:**
- Create: `src/auto_check/modules/dashboard_management/migrations/002_year_snapshots.sql`
- Modify: `src/auto_check/modules/dashboard_management/storage.py`
- Modify: `src/auto_check/modules/dashboard_management/module.py`
- Modify: `src/auto_check/modules/dashboard_management/manifest.json`
- Test: `tests/modules/dashboard_management/test_manifest_and_migrations.py`
- Test: `tests/modules/dashboard_management/test_storage.py`
- Test: `tests/modules/dashboard_management/test_module_integration.py`

**Interfaces:**
- Produces: `DashboardManagementStorage.seed_initial_year_snapshots() -> None`。
- Produces: `DashboardManagementStorage.upsert_year_snapshots(region_id: int, rows: Sequence[SnapshotRow], refreshed_at: datetime) -> None`。
- Produces: `DashboardManagementStorage.refresh_year_snapshots(...) -> list[dict[str, Any]]`，在同一事务内按刷新时间保护写入并读取当年合并结果。
- Produces: `DashboardManagementStorage.list_year_snapshots(region_id: int, period_year: int) -> list[dict[str, Any]]`。
- Consumes: `SnapshotRow` from Task 2，字段为 `period_year`、`period_type`、`period_value`、`row`。

- [x] **Step 1: 写迁移、schema 和基线失败测试**

  断言 `schema_version == 2`、`002_year_snapshots.sql` 只创建 `dashboard_management_year_snapshots`、模块注册新表全部字段，并在 `seed_builtin_catalog()` 后得到 2026 年信托和对账完成时间 1—6 月、校验问题处理 1—8 月与前两季度数据，且其他区域没有 7 月或第三季度。

- [x] **Step 2: 运行最小测试并确认 RED**

  Run: `python -m pytest -q tests/modules/dashboard_management/test_manifest_and_migrations.py tests/modules/dashboard_management/test_storage.py -k "snapshot or manifest or schema"`

  Expected: FAIL，原因是 schema 版本仍为 1、迁移文件/快照表/仓储接口尚不存在。

- [x] **Step 3: 实现最小迁移和仓储**

  `002_year_snapshots.sql` 创建以下字段与约束：

  ```sql
  CREATE TABLE dashboard_management_year_snapshots (
      id BIGINT NOT NULL AUTO_INCREMENT,
      region_id BIGINT NOT NULL,
      period_year INT NOT NULL,
      period_type VARCHAR(16) NOT NULL,
      period_value INT NOT NULL,
      row_json LONGTEXT NOT NULL,
      source_refreshed_at DATETIME(6) NULL,
      created_at DATETIME(6) NOT NULL,
      updated_at DATETIME(6) NOT NULL,
      PRIMARY KEY (id),
      UNIQUE KEY uq_dashboard_management_year_snapshot_period
          (region_id, period_year, period_type, period_value),
      CONSTRAINT fk_dashboard_management_year_snapshots_region
          FOREIGN KEY (region_id) REFERENCES dashboard_management_regions (id)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
  ```

  仓储用 `json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",", ":"))` 写入；先更新，未命中再插入，整批使用模块数据库事务。启动基线只补缺失唯一键，不覆盖已有实时数据。

- [x] **Step 4: 运行测试并确认 GREEN**

  Run: `python -m pytest -q tests/modules/dashboard_management/test_manifest_and_migrations.py tests/modules/dashboard_management/test_storage.py tests/modules/dashboard_management/test_module_integration.py`

  Expected: PASS。

### Task 2: 周期与行数据规范化

**Files:**
- Create: `src/auto_check/modules/dashboard_management/year_snapshots.py`
- Create: `tests/modules/dashboard_management/test_year_snapshots.py`

**Interfaces:**
- Produces: `SNAPSHOT_REGION_CODES: frozenset[str]`。
- Produces: `SnapshotRow(period_year: int, period_type: str, period_value: int, row: Mapping[str, Any])`。
- Produces: `normalize_snapshot_rows(region_code: str, rows: Sequence[Mapping[str, Any]], now: datetime) -> tuple[SnapshotRow, ...]`。
- Produces: `snapshot_columns(fields: Sequence[Mapping[str, Any]]) -> tuple[str, ...]` 不改变现有字段顺序。

- [x] **Step 1: 写周期转换失败测试**

  覆盖：信托月份 `8月`/`08月`/`2026-08`，两个 `YYYY-MM` 区域，季度 `第3季度`/`2026年第3季度`，完成时间 ISO datetime 转 `HH:mm`，跨年与未来周期过滤、无效周期忽略、重复周期抛出 `ValidationError`。

- [x] **Step 2: 运行测试并确认 RED**

  Run: `python -m pytest -q tests/modules/dashboard_management/test_year_snapshots.py`

  Expected: FAIL，原因是 `year_snapshots` 模块尚不存在。

- [x] **Step 3: 实现最小规范化逻辑**

  使用严格正则解析周期；无年份格式使用 `now.year`；月度不接受晚于 `now.month` 的周期，季度不接受晚于当前季度的周期。规范化后分别输出 `M月`、`YYYY-MM`、`第N季度`，同一结果内重复唯一周期抛出 `ValidationError("快照区域返回了重复周期")`。

- [x] **Step 4: 运行测试并确认 GREEN**

  Run: `python -m pytest -q tests/modules/dashboard_management/test_year_snapshots.py`

  Expected: PASS。

### Task 3: 预览接口刷新与故障回退

**Files:**
- Modify: `src/auto_check/modules/dashboard_management/service.py`
- Modify: `src/auto_check/modules/dashboard_management/module.py`
- Test: `tests/modules/dashboard_management/test_service.py`
- Test: `tests/modules/dashboard_management/test_api.py`

**Interfaces:**
- `DashboardManagementService.__init__(..., now: Callable[[], datetime] | None = None)` 接收应用时间提供器。
- 快照区域成功响应新增 `snapshot_status: "fresh"` 和 `snapshot_refreshed_at`；实时失败且已有快照时新增 `snapshot_status: "stale"`，同时仍返回 `status: "success"`。
- 没有当年快照时沿用现有区域错误结构。

- [x] **Step 1: 写服务失败测试**

  覆盖实时结果写入后按周期升序返回、缺失周期保留、只返回当前年、查询失败回退旧快照、无快照仍报错、非快照区域不调用仓储快照接口。

- [x] **Step 2: 运行服务测试并确认 RED**

  Run: `python -m pytest -q tests/modules/dashboard_management/test_service.py -k snapshot`

  Expected: FAIL，原因是服务尚未接入规范化与快照仓储。

- [x] **Step 3: 实现刷新和回退**

  服务在 `_execute_saved_region` 成功后规范化并写入；随后从仓储读取 `now.year` 全量快照构造兼容的 `QueryPreview` 数据。异常路径仅对四个稳定内置 `region_code` 尝试回退，错误内容不回显 SQL、连接串或驱动信息。

- [x] **Step 4: 运行服务与 API 测试并确认 GREEN**

  Run: `python -m pytest -q tests/modules/dashboard_management/test_service.py tests/modules/dashboard_management/test_api.py`

  Expected: PASS。

### Task 4: 文档同步与完整验证

**Files:**
- Modify: `src/auto_check/modules/dashboard_management/README.md`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-09-15-dashboard-year-snapshots-design.md`
- Modify: `src/auto_check/modules/dashboard_management/manifest.json`

**Interfaces:**
- 文档明确四个快照区域、接口触发、当年返回、失败回退、2026 初始化边界和无后台任务。
- 模块发布说明新增一条快照能力，模块小版本递增，应用展示大版本不变。

- [x] **Step 1: 更新文档与发布说明**

  将设计中的“迁移初始化”落实为“`002` 建表，模块启动幂等初始化”，并补充 MySQL 回滚方式为保留表数据、回退代码后旧版本忽略新表。

- [x] **Step 2: 运行模块测试**

  Run: `python -m pytest -q tests/modules/dashboard_management`

  Expected: PASS。

- [x] **Step 3: 运行全量测试**

  Run: `python -m pytest -q`

  Expected: PASS。

- [x] **Step 4: 检查差异范围与空白错误**

  Run: `git diff --check`

  Expected: 无实际 whitespace error；改动范围只包含 Global Constraints 允许的文件。

## Self-Review

- Spec coverage：四个快照区域、实时成功覆盖、缺期保留、失败回退、当年过滤、2026 已确认基线（校验问题处理到 8 月，其余月度到 6 月、季度到 Q2）、无后台任务、回滚均有对应任务。
- Placeholder scan：计划中无 `TBD`、`TODO` 或未定义后续项。
- Type consistency：Task 1 仓储消费 Task 2 的 `SnapshotRow`；Task 3 使用同一规范化接口和仓储方法；响应元数据命名在设计与测试中统一。
