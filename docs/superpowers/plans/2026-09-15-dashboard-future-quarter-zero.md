# Dashboard Future Quarter Zero Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让季度报表特殊处理的对外看板预览接口为统计截止季度之后的缺失季度返回 0，包括季度首月尚无已完成月份数据的当前季度，但不写入年度快照。

**Architecture:** 在服务层将已持久化月度快照汇总并投影为接口行时，按请求业务时间的上月计算本年度统计截止季度，并仅为该季度之后缺失的季度构造临时行。1 月的本年度截止月份为 0；没有可用快照时由既有规则返回 `data_not_ready`。持久化存储、实时 SQL 归一化和快照覆盖规则保持不变。

**Tech Stack:** Python 3.12、SQLAlchemy、pytest

## Global Constraints

- 仅修改看板预览接口返回，不补写 `dashboard_management_year_snapshots`。
- 已有季度数据优先，未来季度只在缺失时补 0。
- 统计截止季度及之前的历史季度缺失时不补 0；本年度无快照时不伪造成功。

---

### Task 1: 季度接口投影补零

**Files:**
- Modify: `src/auto_check/modules/dashboard_management/service.py`
- Test: `tests/modules/dashboard_management/test_service.py`
- Modify: `src/auto_check/modules/dashboard_management/README.md`
- Modify: `README.md`
- Modify: `src/auto_check/modules/dashboard_management/manifest.json`

**Interfaces:**
- Consumes: `DashboardManagementService.preview_board_data()` 的统一请求时间和 `storage.list_year_snapshots()` 返回的快照列表。
- Produces: `_snapshot_preview(fields, snapshots, region_code, request_now) -> QueryPreview`，仅在 `quarterly_special_processing` 的统计截止季度之后缺失季度中生成临时 0 值行。

- [x] **Step 1: 写失败测试**

```python
def test_quarterly_snapshot_preview_returns_future_quarters_as_zero_without_persisting(storage):
    service = DashboardManagementService(storage, now=lambda: datetime(2026, 3, 15, 10, 0))
    payload = service.preview_board_data("report_submission", {"role": "admin"})
    quarterly = next(item for item in payload["regions"] if item["code"] == "quarterly_special_processing")
    assert quarterly["rows"] == [
        {"quarter": "第1季度", "special_processing_count": 31},
        {"quarter": "第2季度", "special_processing_count": 0},
        {"quarter": "第3季度", "special_processing_count": 0},
        {"quarter": "第4季度", "special_processing_count": 0},
    ]
    assert [row["period_value"] for row in storage.list_year_snapshots(quarterly_region_id, 2026)] == [1, 2]
```

- [x] **Step 2: 运行测试并确认因缺少未来季度投影而失败**

Run: `python -m pytest -q tests/modules/dashboard_management/test_service.py -k future_quarters`

Expected: FAIL，返回行中缺少尚未到达的季度。

- [x] **Step 3: 实现只读接口投影**

```python
def _snapshot_preview(fields, snapshots, *, region_code, request_now):
    projected = list(snapshots)
    if region_code == "quarterly_special_processing":
        reporting_month = request_now.month - 1
        reporting_quarter = (reporting_month - 1) // 3 + 1 if reporting_month else 0
        existing = {int(item["period_value"]) for item in projected}
        projected.extend(
            {
                "period_value": quarter,
                "row": {"quarter": f"第{quarter}季度", "special_processing_count": 0},
            }
            for quarter in range(reporting_quarter + 1, 5)
            if quarter not in existing
        )
        projected.sort(key=lambda item: int(item["period_value"]))
    # 使用 projected 生成 QueryPreview，不调用任何存储写入方法。
```

- [x] **Step 4: 运行模块测试与全量测试**

Run: `python -m pytest -q tests/modules/dashboard_management`

Expected: PASS。

Run: `python -m pytest -q`

Expected: PASS。

- [x] **Step 5: 更新说明并核对差异**

在模块说明、根 README 和模块发布说明中明确“未来季度补零仅为接口投影，不写快照”，然后运行 `git diff --check`，预期无实际空白错误。

### 2026-10-01 季度边界修正

现行实现内部保存月度快照，以上示意中的季度投影在月度汇总之后执行。补零边界改为截至上月的统计季度，SQL、固定历史基线、月度快照写入和跨年隔离保持原规则。

验收覆盖季度首月、北京时间跨季度、正常查询与旧快照回退、已有值及历史缺失、跨年无数据和占位行不持久化；先确认回归测试在旧逻辑下失败，再运行修复后的相关测试、模块测试和全量测试。
