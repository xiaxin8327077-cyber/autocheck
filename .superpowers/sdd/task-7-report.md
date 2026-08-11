# Task 7 Report: RSP TodoProvider + 我的待办前端

## Status

**DONE**

## Commit

- `46b59bd` — `feat: wire RSP pending confirms into report navigation todos`

## Files Changed

- Create: `src/auto_check/modules/report_special_processing/todos.py`
- Modify: `src/auto_check/modules/report_special_processing/module.py`
- Modify: `src/auto_check/modules/report_special_processing/storage.py`
- Modify: `src/auto_check/modules/report_special_processing/web/pages/ledger.js`
- Modify: `src/auto_check/modules/report_special_processing/web/state.js`
- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/app.js`
- Modify: `src/auto_check/web/styles.css`
- Modify: `src/auto_check/web/module_host.js`
- Create: `tests/modules/report_special_processing/test_todos.py`
- Modify: `tests/modules/report_special_processing/test_statistics_and_module.py`
- Modify: `tests/modules/report_special_processing/test_frontend_static.py`
- Modify: `tests/module_system/test_frontend_host.py`
- Modify: `tests/test_web_static.py`

## What Was Implemented

### RSP TodoProvider
- `PendingConfirmTodoProvider` lists `status=pending` records where `governance_owner_user_id` matches current user
- Todo title=`报表特殊处理待确认`；summary=`{维度标签} · {field_name}`
- Action navigates to `report-special-processing` with `record_id` + `highlight=1`（不直接打开确认弹窗）
- Module `start` registers `rsp_pending_confirm`；`stop` closes card + todo handles

### 我的待办前端
- 去掉静态 3 条 mock；`reportNavTodoList` 空容器 + `reportNavTodoCount`
- `renderReportNavTodos(payload.todos || [])`；空态「暂无待办」
- 「处理」经 ModuleHost `activate(route?query)` / hash 跳转

### Deep-link 定位增强
- `module_host.js` 解析 hash query，按基路由匹配模块，并把 `{name,query}` 传给 `activate`
- 同模块不同 query 会重新 activate，保留 query 在 hash
- Ledger `applyLocateContext`：`GET` 记录后对齐报送期/清空流程筛选，并用 `record_no` 关键词定位，避免不在当前页时找不到行

## Tests

```text
pytest tests/modules/report_special_processing/test_todos.py \
  tests/test_report_navigation_todos.py \
  tests/modules/report_special_processing/test_statistics_and_module.py \
  tests/modules/report_special_processing/test_frontend_static.py \
  tests/module_system/test_frontend_host.py \
  tests/test_web_static.py::test_report_navigation_page_uses_readonly_panorama_details_and_compact_todo_rows \
  tests/test_web_static.py::test_report_navigation_frontend_preserves_snapshot_period_refresh_and_card_maintenance_logic -q
# 44 passed

pytest tests/modules/report_special_processing/ -q
# 75 passed
```

TDD：先写 `test_todos.py`（ImportError RED）与静态空容器断言，再实现 provider / 前端。

## Self-Review

| Check | Result |
|-------|--------|
| Provider 仅当前治理负责人 pending | OK |
| 确认后不再出现 | OK（status 非 pending） |
| 「处理」跳转列表+定位，不直接弹窗 | OK |
| 静态 mock 移除 + 动态渲染/空态 | OK |
| record 不在当前页可定位 | OK（getRecord + 筛选调整） |
| 未 bump README/版本 | OK（Task 8） |
| 仅提交本任务文件 | OK |

## Concerns

1. 定位依赖 `record_no` 关键词筛选；用户从待办进入后列表可能暂时只显示该条，直到手动清筛选。
2. Dashboard todos 仍依赖模块已 `start` 并注册 provider；模块未加载时待办为空属预期。

## Follow-ups

- Task 8：README / 版本号 / 更新日志 / 总验收
