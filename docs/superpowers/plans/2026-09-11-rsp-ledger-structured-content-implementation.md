# Report Special Processing Ledger Structured Content Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在台账中新增所属业务系统列，并以独立的“修改字段 / 修改内容”双列展示新旧两类记录。

**Architecture:** 在 `record_table.js` 内构建纯展示模型，结构化记录按完整值对跨表分组、组内按物理英文表名合并字段、中文名优先显示且英文名保留在悬停提示，旧记录使用保守兼容解析；前两列的记录内容跨列纵向排列，组内 Grid 保证表名与字段对齐。现有列表接口已返回结构化内容和业务系统名称快照，无需后端或迁移改动。

**Tech Stack:** 原生 JavaScript ES modules、模块作用域 CSS、pytest、Node.js DOM 测试脚本。

## Global Constraints

- 列结构固定为“修改字段、修改内容、所属业务系统、关联报送、状态、处理人、处理时间、操作”。
- 列表不展示处理摘要。
- 新数据按相同值对跨处理表合并；旧数据无法可靠对应时原样保留。
- 不改变保存校验、权限、状态流、导出和操作记录。
- 不打包、不提交、不推送。

---

### Task 1: 列表展示模型与旧数据兼容

**Files:**
- Modify: `src/auto_check/modules/report_special_processing/web/components/record_table.js`
- Test: `tests/modules/report_special_processing/test_record_table_frontend.py`

**Interfaces:**
- Consumes: 列表记录中的 `structured_content`、`field_name`、`value_before`、`value_after` 和 `business_system_name_snapshot`。
- Produces: 按完整值对聚合的 `{before, after, tables}` 展示组，以及旧记录的保守展示组。

- [x] 编写结构化双表、同表同值对归组、跨表归组的失败测试。
- [x] 编写旧手工单值共享、逐行配对和不可靠对应原样保留的失败测试。
- [x] 运行新测试，确认因旧列表仍使用三列扁平渲染而失败。
- [x] 实现展示模型、纵向分组和“所属业务系统”名称快照单元格。
- [x] 运行新测试并确认通过。

### Task 2: 列宽、视觉层级与兼容测试

**Files:**
- Modify: `src/auto_check/modules/report_special_processing/web/styles.css`
- Modify: `tests/modules/report_special_processing/test_frontend_static.py`
- Modify: `src/auto_check/modules/report_special_processing/README.md`
- Modify: `docs/report-special-processing-module.zh-CN.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 1 输出的模块作用域类名。
- Produces: 纵向变更摘要、组内表名/字段对齐、业务系统列和长内容完整换行样式。

- [x] 更新静态测试，要求新 8 列、跨列纵向分组、模块作用域样式和旧数据分支。
- [x] 运行静态测试，确认旧表头和旧列宽断言失败。
- [x] 添加模块作用域样式并更新说明文档，不改变大版本号。
- [x] 运行直接相关测试、模块测试、全量测试和 `git diff --check`。
- [x] 检查最终差异，确认本次任务未新增平台入口、数据库迁移或其他模块改动。
