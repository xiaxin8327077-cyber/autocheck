# 报表特殊处理前端渐进式脚本预览实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 处理表、修改字段或条件字段一经选择便在前端实时形成对应 `UPDATE`、`SET`、`WHERE` 片段，并修复处理脚本手动编辑模式。

**Architecture:** 新增模块内纯前端 `script_preview.js`，只消费结构化编辑器当前状态并生成预览文本；不调用或放宽后端脚本生成与保存解析，不修改正式保存校验。`record_drawer.js` 只负责防抖、自动/手动模式和文本框状态。

**Tech Stack:** 原生 ES Modules、Python pytest、Node.js 场景测试。

## Global Constraints

- 表选择后立即生成 `UPDATE <table>`。
- 修改字段选择后立即生成 `SET <field> = ''`；修改后内容变化时替换字面量。
- 条件字段选择后立即生成 `WHERE <field> <operator> ''`；条件值变化时替换字面量。
- 报送期条件始终使用 `YYYY-MM-DD`，字符字段也不得转换为 `YYYYMMDD`。
- 没有条件字段时不生成 `WHERE`，允许预览无 WHERE 的全表更新语句。
- 多表独立生成，任一表未完成不得阻塞其他表。
- 不修改 `structured_content.py`、`validator.py`、记录 create/update 服务及其必填校验。
- 手动模式保留现有脚本、允许输入、暂停配置联动；恢复自动生成后按最新配置覆盖。
- 不打包、不提交、不推送。

---

### Task 1: 前端渐进式脚本预览纯函数

**Files:**
- Create: `src/auto_check/modules/report_special_processing/web/components/script_preview.js`
- Test: `tests/modules/report_special_processing/test_script_preview_frontend.py`

**Interfaces:**
- Consumes: `buildScriptPreview(structuredContent, fieldTypes, reportPeriod)` 的普通对象参数。
- Produces: 每表分段的 SQL 预览字符串；空表列表返回空字符串。

- [ ] **Step 1: 写失败测试**

覆盖表名立即生成、空修改值生成 `''`、空条件值生成 `''`、无条件不输出 WHERE、多表互不阻塞、引号转义、IN/LIKE/NULL，以及字符/日期字段均使用 `YYYY-MM-DD` 的报送期条件。

- [ ] **Step 2: 确认测试按预期失败**

Run: `python -m pytest -q tests/modules/report_special_processing/test_script_preview_frontend.py`

Expected: FAIL，原因是 `script_preview.js` 尚不存在。

- [ ] **Step 3: 实现最小纯函数**

导出：

```javascript
export function buildScriptPreview(structuredContent, fieldTypes = {}, reportPeriod = "") {
  // 过滤未选表；逐表拼接注释、UPDATE、已选字段的 SET、已选条件字段的 WHERE。
}
```

修改字段已选择但修改后为空时使用空字符串字面量；条件字段已选择但值为空时，除 `IS NULL`/`IS NOT NULL` 外同样使用空字符串字面量。字符串单引号按 SQL 规则转义。

- [ ] **Step 4: 确认纯函数测试通过**

Run: `python -m pytest -q tests/modules/report_special_processing/test_script_preview_frontend.py`

Expected: PASS。

### Task 2: 抽屉接入与手动编辑回归修复

**Files:**
- Modify: `src/auto_check/modules/report_special_processing/web/components/record_drawer.js`
- Modify: `tests/modules/report_special_processing/test_record_attachments_frontend.py`
- Modify: `tests/modules/report_special_processing/test_frontend_static.py`

**Interfaces:**
- Consumes: Task 1 的 `buildScriptPreview(...)`。
- Produces: 400ms 真防抖的本地自动预览，以及可恢复的 MANUAL 模式。

- [ ] **Step 1: 写失败场景测试**

扩展现有抽屉 Node 场景，断言不调用 `actions.generateScript`；点击一次“手动编辑”后按钮变为“恢复自动生成”、提示可见、textarea `readOnly === false`，输入内容不会被编辑器变化覆盖；恢复后重新生成。

- [ ] **Step 2: 确认场景测试按预期失败**

Run: `python -m pytest -q tests/modules/report_special_processing/test_record_attachments_frontend.py -k "script or manual"`

Expected: FAIL，当前双重 click 监听会立即恢复 AUTO，且仍调用后端生成接口。

- [ ] **Step 3: 实现抽屉状态机**

移除按钮创建时的重复 `onClick`，只保留一个异步 click 监听；AUTO 模式通过 `buildScriptPreview` 更新脚本，MANUAL 模式清除定时器并忽略配置变化。提示文案固定为“手动编辑模式，自动生成已暂停”，置于 textarea 上方。

- [ ] **Step 4: 确认抽屉与静态测试通过**

Run: `python -m pytest -q tests/modules/report_special_processing/test_record_attachments_frontend.py tests/modules/report_special_processing/test_frontend_static.py -k "script or manual or drawer"`

Expected: PASS。

### Task 3: 文档同步与回归验证

**Files:**
- Modify: `docs/report-special-processing-module.zh-CN.md`
- Modify: `src/auto_check/modules/report_special_processing/README.md`
- Modify: `README.md`
- Modify: `src/auto_check/modules/report_special_processing/manifest.json`
- Modify: `src/auto_check/modules/report_special_processing/sql_builder.py`
- Modify: `tests/modules/report_special_processing/test_sql_builder.py`

**Interfaces:**
- Consumes: Task 1、2 的最终行为。
- Produces: 与实际行为一致的当前版本说明，不修改大版本号或 schema_version。

- [ ] **Step 1: 更新说明**

将“后端完整校验后生成”改为“前端渐进式预览”；明确表/字段选择即形成片段、无条件时不生成 WHERE、报送期统一 `YYYY-MM-DD`、正式保存校验不变、手动模式暂停联动。保留的后端生成接口只同步报送期格式，不放宽其校验。

- [ ] **Step 2: 运行模块测试**

Run: `python -m pytest -q tests/modules/report_special_processing/`

Expected: PASS。

- [ ] **Step 3: 运行全量测试与差异检查**

Run: `python -m pytest -q`

Expected: PASS。

Run: `git diff --check`

Expected: 无真实 whitespace error；仅 CRLF/LF 转换提示可接受。
