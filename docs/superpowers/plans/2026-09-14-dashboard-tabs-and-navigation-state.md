# Dashboard Tabs and Navigation State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复系统管理刷新展开和预览关闭后下拉未收回问题，并按参考图重做看板切换栏。

**Architecture:** 模块宿主将分组高亮与展开状态解耦；看板模块把每个页签内的预览入口合并为右侧当前看板预览入口，并在弹窗关闭时把焦点返回当前看板按钮。图标由模块内部创建 SVG，不依赖平台私有前端函数。

**Tech Stack:** 原生 JavaScript、模块作用域 CSS、pytest 驱动的 Node 前端行为测试与静态契约测试。

## Global Constraints

- 平台宿主改动仅调整合并分组的激活状态，不改变点击、悬浮和键盘展开协议。
- 看板模块不读取平台私有函数，不改变预览数据和业务逻辑。
- 使用现有主题色和圆角变量。
- 不打包、不提交、不推送。

---

### Task 1: 平台分组刷新状态

**Files:**
- Modify: `tests/module_system/test_frontend_host.py`
- Modify: `src/auto_check/web/module_host.js`

**Interfaces:**
- Consumes: `setLegacyGroupNavigationActive(groupId, active)`
- Produces: 活跃分组高亮但保持收起的导航状态。

- [x] **Step 1: 修改现有行为测试，断言激活模块路由时分组不含 `open` 且 `aria-expanded=false`。**
- [x] **Step 2: 运行目标测试并确认旧行为导致失败。**
- [x] **Step 3: 解耦 active 与 open，只同步高亮并强制清理程序化展开状态。**
- [x] **Step 4: 运行目标测试并确认通过。**

### Task 2: 看板切换栏和预览菜单

**Files:**
- Modify: `tests/modules/dashboard_management/test_frontend_static.py`
- Modify: `src/auto_check/modules/dashboard_management/web/components/dashboard_tabs.js`
- Modify: `src/auto_check/modules/dashboard_management/web/components/board_preview_dialog.js`
- Modify: `src/auto_check/modules/dashboard_management/web/styles.css`
- Modify: `src/auto_check/modules/dashboard_management/README.md`
- Modify: `src/auto_check/modules/dashboard_management/manifest.json`
- Modify: `README.md`

**Interfaces:**
- Consumes: `renderDashboardTabs({ boards, activeBoardCode, onSelect, onPreview })`
- Produces: 左侧切换按钮组、右侧当前看板预览菜单和关闭后的焦点回退。

- [x] **Step 1: 增加失败的静态测试，覆盖单一预览按钮、当前按钮焦点回退和 flex 对齐。**
- [x] **Step 2: 运行目标测试并确认因新结构尚不存在而失败。**
- [x] **Step 3: 重排页签 DOM 并调整样式。**
- [x] **Step 4: 修改预览弹窗关闭焦点目标，使下拉菜单收回。**
- [x] **Step 5: 同步模块说明、发布说明和 README。**
- [x] **Step 6: 运行模块测试、相关平台测试和 `git diff --check`。**

### Task 3: 当月报表报送时间对比排除人行大集中

**Files:**
- Modify: `tests/modules/dashboard_management/test_system_data.py`
- Modify: `src/auto_check/modules/dashboard_management/system_data.py`
- Modify: `src/auto_check/modules/dashboard_management/README.md`
- Modify: `src/auto_check/modules/dashboard_management/manifest.json`
- Modify: `README.md`

**Interfaces:**
- Consumes: `SYSTEM_QUERY_DEFINITIONS["monthly_report_submission_time_comparison"]`
- Produces: 排除 `process.process_name = '人行大集中'` 的系统生成 SQL。

- [x] **Step 1: 增加失败测试，断言 SQL 包含 `process.process_name <> '人行大集中'`。**
- [x] **Step 2: 运行目标测试并确认旧 SQL 缺少排除条件。**
- [x] **Step 3: 在现有 `WHERE process.enabled = 1` 后增加流程名称排除条件。**
- [x] **Step 4: 运行目标测试并同步说明。**
