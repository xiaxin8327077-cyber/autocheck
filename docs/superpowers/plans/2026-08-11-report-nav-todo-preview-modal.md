# 报送导航待办预览与全部弹窗 Implementation Plan

> **For agentic workers:** Implement task-by-task on `feature/auto-check` at `D:\xiaxin\auto_check`. Spec: `docs/superpowers/specs/2026-08-11-report-nav-todo-preview-modal-design.md`.

**Goal:** 我的待办卡片最多展示 5 条；「全部」打开全量弹窗；卡片与全部内「处理」直开确认弹窗，且从全部进入时不关全部。

**Architecture:** 前端 `slice(0,5)` 预览 + 系统模态框全量列表；RSP TodoAction 增加 `open=confirm`；`ModuleHost.openConfirmOverlay` 在报送导航原地打开确认浮层（不跳转录入页）；确认遮罩 z-index 高于全部弹窗。

**Tech Stack:** 现有静态前端 (`app.js`/`index.html`/`styles.css`) + RSP 模块 JS + pytest 静态/单元测试。

## Global Constraints

- 工作区：`D:\xiaxin\auto_check`，分支 `feature/auto-check`
- 预览上限：`5`
- 任意条数可点「全部」；从全部点处理不关全部
- 确认弹窗须盖在全部之上
- 应用内更新日志精简；README 写详细
- 改完跑 `python -m pytest -q`

---

### Task 1: RSP action `open=confirm` + 台账直开

**Files:**
- Modify: `src/auto_check/modules/report_special_processing/todos.py`
- Modify: `src/auto_check/modules/report_special_processing/web/pages/ledger.js`
- Modify: `tests/modules/report_special_processing/test_todos.py`（及必要前端静态断言）

- [ ] 测试：todo action query 含 `open=confirm`
- [ ] `todos.py` query 增加 `open=confirm`
- [ ] `ledger.js`：locate 时若 `open=confirm` 且找到记录则 `openRecord(record, null, "confirm")`
- [ ] 跑相关 pytest

### Task 2: 确认遮罩高于全部弹窗

**Files:**
- Modify: `src/auto_check/modules/report_special_processing/web/styles.css`
- Modify: `src/auto_check/web/styles.css`（全部弹窗 z-index 明确）

- [ ] 全部弹窗 z-index 取系统弹窗量级（如 3000）
- [ ] RSP `.rsp-record-modal-overlay` 提到更高（如 3200），保证叠在全部上
- [ ] 静态测试断言层级关系

### Task 3: 预览 5 条 + 全部弹窗 UI

**Files:**
- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/app.js`
- Modify: `src/auto_check/web/styles.css`
- Modify: `tests/test_web_static.py`

- [ ] 「全部」改为 button；新增 `reportNavTodoAllModal` markup
- [ ] `REPORT_NAV_TODO_PREVIEW_LIMIT = 5`；预览 slice；计数全量
- [ ] 打开/关闭全部；渲染全量；处理不关全部
- [ ] 处理走现有 `handleReportNavTodoAction`
- [ ] 静态测试覆盖

### Task 4: 文档与验证

**Files:**
- Modify: `README.md`
- Modify: `src/auto_check/web/app.js` 更新日志
- Modify: design spec 状态 → 已实施

- [ ] README 详细说明
- [ ] app.js 更新日志：功能点 + 必要时「系统优化及BUG修复」
- [ ] `python -m pytest -q`
- [ ] 不主动推送
