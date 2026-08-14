# 人行逐笔校验跨表映射 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将所有已实现的 ZG09、ZG10 逐笔字段与模板 `field_name` 对应关系持久化、可视化、可修改，并重排三类映射弹窗。

**Architecture:** 新建独立跨表映射模型与存储表；表映射继续负责物理表解析，跨表映射只负责逐笔字段到模板字段的一对一关系。规则执行时完全遍历当前有效跨表映射，不再在代码中生成 G/H 对应字段。三个设置按钮复用弹窗外壳但加载固定视图，自动值和人工值的差异由统一状态模型驱动。

**Tech Stack:** Python 3.11、SQLAlchemy、MySQL、原生 JavaScript/CSS、pytest。

## Global Constraints

- 设置区固定提供“查看表映射”“查看字段映射”“查看跨表映射”三个入口。
- 表映射列：表类型、逻辑表、物理表、修改，并包含模板表。
- 字段映射列：逻辑表、中文名、映射字段、修改。
- 跨表映射列：逐笔表、逐笔字段、模板表、模板字段、修改。
- 刷新自动值不得覆盖人工修改值；差异行必须高亮并可恢复自动值。
- 三类映射分别存在自动值与人工值差异时，对应入口按钮右上角显示橙色圆点；差异消失后自动隐藏。
- 表名和字段名保持单行省略，不出现横向滚动条。
- 弹窗提供不区分大小写的即时模糊筛选，并显示当前条数和总条数。
- 不修改默认元数据表 `xt_reg_table_baseinfo` 和 `xt_reg_table_field_info`。
- 不打包可执行文件。

---

### Task 1: 跨表映射模型、数据库结构与初始化

**Files:**
- Modify: `sql/app_storage/mysql/017_db_validation_mapping.sql`
- Modify: `src/auto_check/app/app_database.py`
- Modify: `src/auto_check/db_validation/mapping_models.py`
- Test: `tests/test_db_validation_indicator_mapping_schema.py`
- Test: `tests/test_app_database.py`

**Interfaces:**
- Produces: `CrossTableMapping`，包含逐笔逻辑表、自动/覆盖/当前逐笔字段、模板口径、自动/覆盖/当前模板表及模板字段、差异状态。

- [ ] **Step 1: 编写失败测试**

断言 SQL 存在 `db_validation_cross_table_mappings`，包含 `detail_field_name`、`template_table_name`、`template_field_name` 三组自动/覆盖/当前字段，并初始化 ZG09、ZG10 当前全部交叉关系；断言应用结构包含该表。

- [ ] **Step 2: 验证测试因结构缺失而失败**

Run: `python -m pytest tests/test_db_validation_indicator_mapping_schema.py tests/test_app_database.py -q`

- [ ] **Step 3: 实现最小结构和模型**

使用唯一键 `(logical_code, scope_code, automatic_detail_field_name, automatic_template_field_name)`；初始化 SQL 采用 `ON DUPLICATE KEY UPDATE`，更新自动值时以 `COALESCE(override_*, VALUES(automatic_*))` 保留人工值。

- [ ] **Step 4: 验证结构测试通过**

Run: `python -m pytest tests/test_db_validation_indicator_mapping_schema.py tests/test_app_database.py -q`

### Task 2: 存储、刷新差异、修改恢复与审计

**Files:**
- Modify: `src/auto_check/db_validation/mapping_storage.py`
- Modify: `src/auto_check/db_validation/mapping_service.py`
- Modify: `src/auto_check/db_validation/metadata.py`
- Modify: `src/auto_check/app/server.py`
- Test: `tests/test_db_validation_mapping_storage.py`
- Test: `tests/test_db_validation_mapping_service.py`

**Interfaces:**
- Produces: `TableFieldCatalog.cross_table_mappings_for(logical_code, scope_code)`。
- Produces: API payload `cross_tables`，每行含自动值、覆盖值、当前值、`difference_fields`、`difference_status`、`refreshed_at`。
- Produces: 映射摘要 `table_difference_count`、`field_difference_count`、`cross_table_difference_count`，供三个入口独立控制差异圆点。

- [ ] **Step 1: 编写失败测试**

覆盖读取全部关系、人工修改三个目标值、恢复、审计；模拟刷新自动值变化，断言人工值不变且 `difference_fields` 精确列出变化项；模拟自动值缺失，断言状态为 `automatic_missing`。

- [ ] **Step 2: 验证测试按预期失败**

Run: `python -m pytest tests/test_db_validation_mapping_storage.py tests/test_db_validation_mapping_service.py -q`

- [ ] **Step 3: 实现存储和接口**

扩展现有覆盖与审计机制，`mapping_kind="cross_table"`；覆盖值用 JSON 保存三个可修改目标，服务层解析并校验每个数据库标识符。刷新只写自动列，再重算当前列和差异状态。

- [ ] **Step 4: 验证存储测试通过**

Run: `python -m pytest tests/test_db_validation_mapping_storage.py tests/test_db_validation_mapping_service.py -q`

### Task 3: ZG09、ZG10 使用跨表映射执行校验

**Files:**
- Modify: `src/auto_check/db_validation/rules/basic.py`
- Modify: `src/auto_check/db_validation/engine.py`
- Modify: `tests/db_validation_rule_fixtures.py`
- Test: `tests/test_db_validation_rules.py`
- Test: `tests/test_db_validation_no_hardcoded_names.py`

**Interfaces:**
- Consumes: `TableFieldCatalog.cross_table_mappings_for(logical_code, scope_code)`。

- [ ] **Step 1: 编写失败规则测试**

构造自定义逐笔字段和模板字段映射，断言 ZG09/ZG10 无需遵循 G/H 命名规律即可命中；禁用一条关系后断言不执行；增加静态守卫，禁止规则源码出现初始化 SQL 中的具体跨表对应字段。

- [ ] **Step 2: 验证旧生成逻辑使测试失败**

Run: `python -m pytest tests/test_db_validation_rules.py tests/test_db_validation_no_hardcoded_names.py -q`

- [ ] **Step 3: 改为映射驱动**

删除 `_zg09_template_metrics`、`_zg10_metric_fields` 的对应关系生成职责；规则按映射逐行读取当前逐笔字段和模板字段。保留现有 `/10000` 单位换算、`0.01` 差异阈值和结果文案。

- [ ] **Step 4: 验证规则测试通过**

Run: `python -m pytest tests/test_db_validation_rules.py tests/test_db_validation_no_hardcoded_names.py -q`

### Task 4: 三个独立入口和固定表格视图

**Files:**
- Modify: `src/auto_check/web/index.html`
- Modify: `src/auto_check/web/app.js`
- Modify: `tests/test_web_static.py`

**Interfaces:**
- Consumes: `tables`、`fields`、`cross_tables` API 数组。
- Produces: `openDbValidationMappingView("table" | "field" | "cross_table")`。

- [ ] **Step 1: 编写失败静态测试**

断言三个按钮和固定打开函数存在，旧循环切换函数不存在；分别断言三组固定列名、跨表修改请求 `mapping_kind="cross_table"`、统一筛选框和条数统计，以及三个按钮根据各自差异计数独立切换橙色圆点和可访问说明。

- [ ] **Step 2: 验证旧单入口界面使测试失败**

Run: `python -m pytest tests/test_web_static.py -q`

- [ ] **Step 3: 实现三个入口和渲染器**

三个按钮通过 `data-mapping-view` 打开同一弹窗；渲染器按视图生成固定表头。每行只显示当前生效值；存在覆盖时显示“恢复自动”。跨表修改对话框依次编辑逐笔字段、模板表、模板字段并提交一个原子请求。加载、刷新、修改或恢复映射后，使用三类差异计数更新对应按钮的 `mapping-has-difference` 类和 `aria-label`。

- [ ] **Step 4: 验证前端静态测试和语法**

Run: `node --check src/auto_check/web/app.js`

Run: `python -m pytest tests/test_web_static.py -q`

### Task 5: 弹窗排版和自动/人工差异视觉状态

**Files:**
- Modify: `src/auto_check/web/app.js`
- Modify: `src/auto_check/web/styles.css`
- Test: `tests/test_web_static.py`

**Interfaces:**
- Consumes: `difference_fields`、`difference_status`、自动值、当前值、`refreshed_at`。

- [ ] **Step 1: 编写失败样式测试**

断言映射弹窗使用响应式宽度、表格 `table-layout: fixed`、容器 `overflow-x: hidden`、数据单元格 `white-space: nowrap; overflow: hidden; text-overflow: ellipsis`；断言按钮右上角橙色圆点、差异行、橙色徽标、红色缺失徽标和带完整比较信息的 `title`。

- [ ] **Step 2: 验证现有样式不满足测试**

Run: `python -m pytest tests/test_web_static.py -q`

- [ ] **Step 3: 实现紧凑响应式布局**

弹窗宽度使用 `min(1180px, calc(100vw - 32px))`；各视图通过类名设置列宽，操作列固定，长值单行省略。入口按钮设为相对定位，`mapping-has-difference::after` 在右上角绘制橙色圆点。差异行淡黄、缺失行淡红；徽标 `title` 包含逐项自动值、当前值和刷新时间。

- [ ] **Step 4: 验证前端测试通过**

Run: `node --check src/auto_check/web/app.js`

Run: `python -m pytest tests/test_web_static.py -q`

### Task 6: 全量验证与开发库迁移说明

**Files:**
- Modify: `docs/superpowers/specs/2026-08-13-db-validation-cross-table-mapping-design.md`（仅在实现与设计产生必要偏差时）

- [ ] **Step 1: 执行重点回归**

Run: `python -m pytest tests/test_db_validation_mapping_storage.py tests/test_db_validation_mapping_service.py tests/test_db_validation_rules.py tests/test_db_validation_engine.py tests/test_web_static.py tests/test_app_database.py -q`

- [ ] **Step 2: 执行静态检查**

Run: `node --check src/auto_check/web/app.js`

Run: `python -m compileall -q src/auto_check`

Run: `git diff --check`

- [ ] **Step 3: 执行完整测试**

Run: `python -m pytest -q --disable-warnings --maxfail=1`

- [ ] **Step 4: 交付说明**

报告修改范围、测试结果，并明确开发应用库需执行更新后的 `sql/app_storage/mysql/017_db_validation_mapping.sql` 后，使用 `python -m auto_check --port 9999 --no-browser` 启动；不生成安装包或可执行文件。
