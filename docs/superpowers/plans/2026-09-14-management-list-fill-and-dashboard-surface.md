# Management List Fill and Dashboard Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让字典管理和定时任务管理列表默认撑满页面、分页固定在底部，并统一看板管理内容块的边框与背景色。

**Architecture:** 公共管理页只增加页面级 flex 高度约束；看板模块以单一外层卡片统一承载顶部切换栏和下方内容区，并在模块作用域内复用平台颜色与圆角变量。业务数据流与接口不变。

**Tech Stack:** CSS、pytest 静态前端契约测试。

## Global Constraints

- 不修改查询、分页、筛选、保存与预览逻辑。
- 公共页面样式必须使用页面 ID 限定作用域；看板样式必须保留模块根选择器。
- 不打包、不提交、不推送。

---

### Task 1: 管理列表默认撑满

**Files:**
- Modify: `tests/test_scheduled_tasks_frontend.py`
- Modify: `tests/test_dictionary_management_frontend.py`
- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/app.js`
- Modify: `src/auto_check/web/styles.css`

**Interfaces:**
- Consumes: `.page`、`.result-card`、`.table-wrap` 现有 flex 布局。
- Produces: 两个管理页面占满主内容区，且空数据或单页时分页栏仍固定在底部；字典列表按系统页容量分页。

- [x] **Step 1: 增加失败测试，断言两个页面共享 `height: 100%` 和 `min-height: 0`。**
- [x] **Step 2: 运行目标测试并确认缺少规则。**
- [x] **Step 3: 增加页面 ID 作用域的最小 CSS 规则。**
- [x] **Step 4: 运行字典和定时任务前端测试。**
- [x] **Step 5: 增加失败测试，覆盖字典分页 DOM、分页切片、筛选回到第一页和单页分页可见。**
- [x] **Step 6: 运行目标测试并确认字典缺少分页、定时任务单页隐藏分页。**
- [x] **Step 7: 为字典列表接入通用分页，并让管理分页栏始终显示。**
- [x] **Step 8: 运行字典和定时任务前端测试。**

### Task 2: 看板内容表面统一

**Files:**
- Modify: `tests/modules/dashboard_management/test_frontend_static.py`
- Modify: `src/auto_check/modules/dashboard_management/web/styles.css`
- Modify: `README.md`

**Interfaces:**
- Consumes: 平台 `--outline-variant`、`--surface-container-lowest` 变量。
- Produces: 与系统卡片一致的看板边框和内容背景。

- [x] **Step 1: 增加失败测试，禁止 `#d7dee9` 和 `#edf0f5` 硬编码覆盖。**
- [x] **Step 2: 运行目标测试并确认旧变量覆盖导致失败。**
- [x] **Step 3: 改用平台边框、背景和混合分隔线变量。**
- [x] **Step 4: 同步 README 详细变更说明。**
- [x] **Step 5: 运行相关测试与 `git diff --check`。**
- [x] **Step 6: 增加单一 `.dm-management-card` 外层，统一系统背景、四角裁切和 hover 描边。**
- [x] **Step 7: 顶部切换栏与内容布局移除各自外框，只保留内部系统分隔线。**

### Task 3: 三个管理页面分页样式统一

**Files:**
- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/app.js`
- Modify: `src/auto_check/web/styles.css`
- Modify: `tests/test_dictionary_management_frontend.py`
- Modify: `tests/test_scheduled_tasks_frontend.py`
- Modify: `tests/test_web_static.py`

**Interfaces:**
- Consumes: 角色权限页 `.pagination`、`.pagination-info`、`.pagination-controls`、`.page-btn`、`.page-current`、`.pagination-jump`。
- Produces: 字典、定时任务、用户管理一致的底部分页视觉和跳页交互。

- [x] **Step 1: 增加失败测试，锁定三页统一分页 DOM 和 CSS。**
- [x] **Step 2: 运行测试并确认三套旧分页结构触发失败。**
- [x] **Step 3: 替换三页分页 DOM，并为通用分页器补充跳页输入。**
- [x] **Step 4: 删除用户管理和通用管理列表的独立分页 CSS。**
- [x] **Step 5: 运行三页相关前端测试。**
