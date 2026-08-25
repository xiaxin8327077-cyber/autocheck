# 报表特殊处理操作记录差异展示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让报表特殊处理操作记录以可展开的完整改前/改后对照展示长内容，并明确区分修改、重开、作废、完成与创建操作。

**Architecture:** 审计 API 已返回 `action_code`、`action_summary` 和未截断的 `changed_fields`；前端在记录抽屉内将其转换为操作语义、成对差异和未编号补充说明。摘要行保持紧凑，详情作为跨三列的后续表格行按需展开；服务端写入、数据库结构和接口形状保持不变。

**Tech Stack:** 原生 ES Modules、模块 scoped CSS、Python pytest 静态结构测试、Node.js 语法检查。

## Global Constraints

- 仅修改 `src/auto_check/modules/report_special_processing/`、`tests/modules/report_special_processing/`、模块相关文档和根 `README.md`。
- 禁止修改公共 `server.py`、`app.js`、`index.html`、全局 `styles.css`、数据库迁移、权限或审计写入逻辑。
- 使用现有亮色主题、`--ui-radius` 和语义色：修改为主题蓝、重开为警告色、作废为危险红、完成为成功绿、创建/草稿为中性；语义不可只靠颜色表达。
- 长文本必须 `pre-wrap` 与强制断词；不得省略、固定高度裁剪或使用主题光晕。字段列固定为较窄宽度，修改前、修改后始终均分剩余空间，不提供横向滚动。
- 重开原因、作废理由、确认说明为紧随操作状态的未编号补充说明，不计入“共 N 项变更”，不得显示为“2.”。
- 测试与验证交由子代理或后台线程优先执行；不打包、不提交、不推送。

---

## File Structure

| Path | Responsibility |
| --- | --- |
| `src/auto_check/modules/report_special_processing/web/components/record_drawer.js` | 将审计结构化数据转换为摘要、差异详情和未编号说明，并维护每页展开状态。 |
| `src/auto_check/modules/report_special_processing/web/styles.css` | 操作语义、对照详情、长文本折行和可访问焦点样式。 |
| `tests/modules/report_special_processing/test_frontend_static.py` | 锁定前端结构、语义、展开状态和长文本 CSS 约束。 |
| `src/auto_check/modules/report_special_processing/manifest.json` | 递增模块补丁版本与模块发布说明。 |
| `src/auto_check/modules/report_special_processing/README.md` | 模块用户/运维边界中的审计展示说明。 |
| `docs/report-special-processing-module.zh-CN.md` | 模块设计说明中的审计呈现与兼容性说明。 |
| `README.md` | 对外功能说明中的完整审计差异展示行为。 |

## Task 1: 锁定审计详情交互与视觉契约

**Files:**
- Modify: `tests/modules/report_special_processing/test_frontend_static.py:280-326`

**Interfaces:**
- Consumes: `record_drawer.js` 的审计项字段 `action_code`、`changed_fields`、`action_summary`。
- Produces: 对前端转换函数、展开按钮、对照表和语义 CSS 的回归契约。

- [ ] **Step 1: 写入失败的前端结构测试。**

  在 `test_editor_supports_draft_record_and_audit_pagination` 后新增以下测试，明确要求结构化审计呈现而不是继续从 `action_summary` 拼出旧值和新值：

  ```python
  def test_audit_diff_panel_preserves_long_values_and_operation_semantics():
      drawer = read("components/record_drawer.js")
      css = read("styles.css")

      for token in (
          "AUDIT_ACTION_META", "AUDIT_FIELD_LABELS", "describeAuditEntry",
          "renderAuditDetail", "查看变更详情", "收起详情", "aria-expanded",
          "changed_fields", "重开原因", "作废理由", "确认说明",
      ):
          assert token in drawer
      for tone in ("update", "reopen", "void", "completed", "neutral"):
          assert f"rsp-audit-action-{tone}" in drawer
      for selector in (
          ".rsp-audit-detail-row", ".rsp-audit-diff-grid",
          ".rsp-audit-value-before", ".rsp-audit-value-after",
          ".rsp-audit-action-void", ".rsp-audit-action-reopen",
      ):
          assert selector in css
      assert "white-space: pre-wrap" in css
      assert "overflow-wrap: anywhere" in css
      assert "max-height:" not in css.split(".rsp-audit-detail-row", 1)[1].split(".rsp-audit-pagination", 1)[0]
  ```

- [ ] **Step 2: 运行测试并确认失败。**

  Run:

  ```powershell
  & 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/modules/report_special_processing/test_frontend_static.py::test_audit_diff_panel_preserves_long_values_and_operation_semantics -q
  ```

  Expected: FAIL，缺少 `AUDIT_ACTION_META`、详情展开结构和对应 CSS。

- [ ] **Step 3: 保留既有分页/空态断言。**

  确认原 `test_editor_supports_draft_record_and_audit_pagination` 保留 `syncAuditPager`、`auditTotalPages`、`暂无操作记录`、`Escape` 等断言；删除其对“收起详情”不存在的旧断言，避免与新设计冲突。

## Task 2: 实现可展开的结构化审计对照

**Files:**
- Modify: `src/auto_check/modules/report_special_processing/web/components/record_drawer.js:1-7, 350-398`
- Modify: `src/auto_check/modules/report_special_processing/web/styles.css:1297-1370`
- Test: `tests/modules/report_special_processing/test_frontend_static.py:280-350`

**Interfaces:**
- Consumes: `actions.audit(id, { page, page_size })` 返回的 `items[]`；每一项含 `id`、`action_code`、`action_summary`、`changed_fields`、`from_status`、`to_status`。
- Produces: `describeAuditEntry(item)` 返回 `{ label, tone, paired, notes, summary }`，`renderAuditDetail(entry)` 返回跨三列详情行；`loadAudit()` 继续维护同一页码、总页数和空态。

- [ ] **Step 1: 在抽屉组件顶部定义操作与字段展示元数据。**

  紧随现有长度常量定义下列元数据；标签与服务端 `_AUDIT_FIELD_LABELS` 保持一致，操作元数据同时提供文字和色调类：

  ```js
  const AUDIT_ACTION_META = {
  create: { label: "创建记录", tone: "neutral" },
  update: { label: "修改记录", tone: "update" },
  status_change: { label: "状态变更", tone: "update" },
    reopen: { label: "重开记录", tone: "reopen" },
    void: { label: "作废记录", tone: "void" },
  };
  const AUDIT_FIELD_LABELS = {
    report_process_name_snapshot: "关联报送", report_period: "所处报送期",
    dimension: "所属维度", summary: "处理摘要", table_name: "处理表名",
    field_name: "处理字段名", value_before: "修改前", value_after: "修改后",
    processing_script: "处理脚本", special_handling_at: "特殊处理时间",
    handler_display_name_snapshot: "处理人",
    governance_owner_display_name_snapshot: "数据治理负责人", status: "状态",
  };
  ```

- [ ] **Step 2: 实现审计项转换，不解析截断后的 `action_summary`。**

  在 `createRecordDrawer` 外新增 `describeAuditEntry(item)`。它遍历 `item.changed_fields || {}`：含自身 `old` 与 `new` 属性的字段放入 `paired`；`processing_script` 用 `old_chars` 与 `new_chars` 形成“X 字”成对值；`reason` 形成 `notes`，其标签按 `item.action_code` 选取“重开原因”“作废理由”“确认说明”或“操作说明”。`reason` 不进入 `paired`，不参与数量。没有结构化项时，把完整 `action_summary` 切为 `summary` 行并保留换行。

  ```js
  function describeAuditEntry(item) {
    const action = AUDIT_ACTION_META[item.action_code] || { label: "操作记录", tone: "neutral" };
    const paired = [];
    const notes = [];
    Object.entries(item.changed_fields || {}).forEach(([key, meta]) => {
      if (!meta || typeof meta !== "object") return;
      if (key === "reason" && meta.new != null) {
        const labels = { reopen: "重开原因", void: "作废理由", status_change: "确认说明" };
        notes.push({ label: labels[item.action_code] || "操作说明", value: String(meta.new) });
      } else if (key === "processing_script" && ("old_chars" in meta || "new_chars" in meta)) {
        paired.push({ label: "处理脚本", old: `${Number(meta.old_chars || 0)} 字`, new: `${Number(meta.new_chars || 0)} 字` });
      } else if (AUDIT_FIELD_LABELS[key] && Object.hasOwn(meta, "old") && Object.hasOwn(meta, "new")) {
        paired.push({ label: AUDIT_FIELD_LABELS[key], old: formatAuditValue(meta.old), new: formatAuditValue(meta.new) });
      }
    });
    return { ...action, paired, notes, summary: String(item.action_summary || item.action_code || "—") };
  }
  ```

  `Object.hasOwn` 使用 `Object.prototype.hasOwnProperty.call(meta, "old")` 与对应的 `new` 调用，兼容现有运行时。`formatAuditValue` 必须将 `null`、空字符串转换为“（空）”，其余值转为字符串；不得截断。若 `item.action_code === "status_change" && item.to_status === "completed"`，在返回前覆盖为 `{ label: "完成记录", tone: "completed" }`；其他状态变化保留主题蓝的“状态变更”。

- [ ] **Step 3: 将 `loadAudit()` 的逐项直出逻辑替换为摘要行＋详情行。**

  在当前分页闭包中增加 `const expandedAuditIds = new Set();`。每页加载成功后清空该集合；`loadAudit()` 将 `items.forEach` 改为调用 `renderAuditRows(item)`。摘要行的操作内容包含操作类型文本、可用时的“状态：旧值 → 新值”、`共 N 项变更` 和原生按钮“查看变更详情”；按钮携带 `aria-expanded`，点击只切换集合并调用当前页的表体重绘函数。

  ```js
  const detailToggle = element(documentRef, "button", {
    type: "button",
    className: "rsp-audit-detail-toggle",
    text: expanded ? "收起详情" : "查看变更详情",
    "aria-expanded": expanded ? "true" : "false",
    onClick: () => { expanded ? expandedAuditIds.delete(item.id) : expandedAuditIds.add(item.id); renderAuditBody(items); },
  });
  ```

  展开后追加一个 `tr.rsp-audit-detail-row`，其中的 `td` 使用 `colspan: "3"`。详情内用“字段 / 修改前 / 修改后”三列表头，逐项渲染 `paired`；`notes` 在表尾以“标签：完整内容”渲染，不加数字前缀。无 `paired` 和 `notes` 的旧记录只使用可换行的 `summary`，不显示展开按钮。

- [ ] **Step 4: 添加模块 scoped CSS。**

  将旧 `.rsp-audit-summary` 的 `white-space: nowrap` 改为能显示完整历史摘要的 `white-space: pre-wrap`，并添加以下关键样式。所有选择器以前缀 `.auto-check-module[data-module="report_special_processing"]` 开始：

  ```css
  .rsp-audit-detail-row > td { padding: 0; background: #fbfcff; }
  .rsp-audit-diff-grid { display: grid; grid-template-columns: minmax(110px, .6fr) minmax(0, 1.7fr) minmax(0, 1.7fr); }
  .rsp-audit-value { min-width: 0; padding: 10px 12px; white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; line-height: 1.55; }
  .rsp-audit-value-before { background: #f6f8fb; }
  .rsp-audit-value-after { background: #f2f7ff; color: var(--rsp-brand); }
  .rsp-audit-action-update { color: var(--rsp-brand); }
  .rsp-audit-action-reopen { color: #a86611; }
  .rsp-audit-action-void { color: #b63a3a; }
  .rsp-audit-action-completed { color: #1e8d5f; }
  ```

  操作类型以文本标签呈现，详情切换按钮为纯主题色文字；不设置 `max-height`、`overflow-x` 或截断规则。窄于 900px 时把详情网格改为单列堆叠，并在每个值前保留“修改前／修改后”文本标签。

- [ ] **Step 5: 运行聚焦测试与 JavaScript 语法检查。**

  Run:

  ```powershell
  & 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/modules/report_special_processing/test_frontend_static.py -q
  node --check src/auto_check/modules/report_special_processing/web/components/record_drawer.js
  ```

  Expected: 模块前端静态测试全绿，Node 语法检查无输出且退出码为 0。

## Task 3: 同步模块版本、说明和全量验证

**Files:**
- Modify: `src/auto_check/modules/report_special_processing/manifest.json:3,35-38`
- Modify: `tests/modules/report_special_processing/test_manifest_and_migrations.py:36-37`
- Modify: `src/auto_check/modules/report_special_processing/README.md:13-15`
- Modify: `docs/report-special-processing-module.zh-CN.md:9-11`
- Modify: `README.md:18`
- Test: `tests/modules/report_special_processing/test_manifest_and_migrations.py`

**Interfaces:**
- Consumes: 模块清单版本与 `release_notes` 聚合协议。
- Produces: 版本 `1.2.2` 和“操作记录优化改前改后差异展示”模块发布说明。

- [ ] **Step 1: 写入失败的清单断言。**

  将 `test_manifest_and_migrations.py` 中的期望替换为：

  ```python
  assert manifest.version == "1.2.2"
  assert manifest.release_notes.version == "1.2.2"
  assert "操作记录优化改前改后差异展示" in manifest.release_notes.items
  ```

  Run:

  ```powershell
  & 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/modules/report_special_processing/test_manifest_and_migrations.py -q
  ```

  Expected: FAIL，当前清单仍为 `1.2.1`。

- [ ] **Step 2: 更新清单与中文说明。**

  将 `manifest.json` 的顶层 `version` 和 `release_notes.version` 改为 `1.2.2`，`release_notes.items` 只保留本版本的条目 `操作记录优化改前改后差异展示`。在三个说明位置补充同一行为：操作记录按操作类型显示语义，支持摘要行展开完整改前/改后对照；长值换行保留；重开/作废原因是未编号说明。根 README 的“报表特殊处理录入”功能条目补充该行为，不调整应用大版本或直接编辑全局更新日志。

- [ ] **Step 3: 运行相关验证。**

  Run:

  ```powershell
  & 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/modules/report_special_processing -q
  & 'C:\Users\jsitc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q
  git diff --check
  ```

  Expected: 两组 pytest 均通过；`git diff --check` 仅允许 CRLF/LF 提示，不得出现 whitespace error。

- [ ] **Step 4: 检查交付范围。**

  Run:

  ```powershell
  git diff --name-only
  git status --short
  ```

  Expected: 本次文件仅包含模块前端、模块测试、模块/根说明和本设计/计划文件；保留已有公共文件未提交改动，且不执行打包、提交或推送。
