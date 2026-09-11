# Report Special Processing Semantic Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将报表特殊处理操作记录升级为基本信息与多处理表分层的语义化变更展示。

**Architecture:** 在模块内新增纯 Python 结构化 Diff 构建器，由服务保存审计时生成稳定、可计数的语义变化；结构化内容 JSON 保存表、条件和字段的内部稳定标识。前端新增纯渲染模型转换器并由记录抽屉渲染分组卡片，历史扁平审计保留原展示。

**Tech Stack:** Python 3.12、原生 JavaScript ES modules、pytest、Node.js DOM 测试脚本。

## Global Constraints

- 不改变修改内容区域已有的前后端必填校验。
- 不改变权限、状态流、附件审计和保存协议。
- 自动生成脚本是次级信息，不计入业务配置变更数。
- 历史审计记录必须继续可读。
- 只修改报表特殊处理模块、对应测试和文档，不打包、不提交、不推送。

---

### Task 1: 稳定条目标识

**Files:**
- Modify: `src/auto_check/modules/report_special_processing/structured_content.py`
- Modify: `src/auto_check/modules/report_special_processing/web/components/structured_content_editor.js`
- Test: `tests/modules/report_special_processing/test_structured_content.py`
- Test: `tests/modules/report_special_processing/test_frontend_static.py`

**Interfaces:**
- Produces: `item_id: str` on table, condition and field JSON objects.
- Consumes: Existing structured content without `item_id`, for which an empty identifier remains valid.

- [x] Write backend and frontend tests proving IDs survive parse, edit and serialization.
- [x] Run targeted tests and verify they fail because IDs are currently discarded.
- [x] Add optional validated IDs to dataclasses and generate IDs for new frontend rows.
- [x] Run targeted tests and verify they pass.

### Task 2: 结构化审计 Diff 构建器

**Files:**
- Create: `src/auto_check/modules/report_special_processing/audit_diff.py`
- Create: `tests/modules/report_special_processing/test_audit_diff.py`

**Interfaces:**
- Produces: `build_structured_audit_diff(old_content, new_content) -> dict[str, Any] | None`.
- Output contains `change_count`, table action counts, and isolated table entries with `table_info`, `scope_changes`, and `field_changes`.

- [x] Write failing tests for modified, added and removed tables; modified/added/removed conditions; modified/added/removed fields; no-op changes; and legacy fallback matching.
- [x] Run the new test file and verify failures are caused by the missing builder.
- [x] Implement normalized snapshots, stable-ID matching, conservative legacy matching and atomic change counting.
- [x] Run the new test file and verify it passes.

### Task 3: 服务审计接入

**Files:**
- Modify: `src/auto_check/modules/report_special_processing/service.py`
- Modify: `tests/modules/report_special_processing/test_service.py`

**Interfaces:**
- Consumes: `build_structured_audit_diff` and current/new structured content JSON.
- Produces: `changed_fields.structured_content` without duplicating derived `table_name`, `field_name`, `value_before`, or `value_after` rows in new structured audits.

- [x] Write a failing service test for a save containing basic information plus multi-table semantic changes.
- [x] Run the targeted test and verify the current flat audit fails the assertion.
- [x] Attach semantic Diff in `_changed_fields`, suppress duplicate compatibility strings, and include semantic counts in the action summary.
- [x] Run service tests and verify they pass.

### Task 4: 前端分层展示

**Files:**
- Create: `src/auto_check/modules/report_special_processing/web/components/audit_detail.js`
- Modify: `src/auto_check/modules/report_special_processing/web/components/record_drawer.js`
- Modify: `src/auto_check/modules/report_special_processing/web/styles.css`
- Test: `tests/modules/report_special_processing/test_record_attachments_frontend.py`
- Test: `tests/modules/report_special_processing/test_frontend_static.py`

**Interfaces:**
- Consumes: Existing audit item plus `changed_fields.structured_content`.
- Produces: summary counts, basic-information Diff, per-table cards, semantic add/remove rows, and collapsed script evidence.

- [x] Write failing DOM tests for the three approved examples and default expansion thresholds.
- [x] Run targeted frontend tests and verify the existing flat grid fails them.
- [x] Implement grouped rendering with legacy fallback and script secondary disclosure.
- [x] Add scoped styles using existing radius, theme and semantic colors.
- [x] Run targeted frontend tests and verify they pass.

### Task 5: Documentation and verification

**Files:**
- Modify: `docs/report-special-processing-module.zh-CN.md`
- Modify: `src/auto_check/modules/report_special_processing/README.md`
- Modify: `README.md`
- Modify: `src/auto_check/modules/report_special_processing/manifest.json`
- Modify: `tests/modules/report_special_processing/test_manifest_and_migrations.py`

**Interfaces:**
- Documents the new audit contract, compatibility behavior and counting rules.

- [x] Add a failing release-note expectation.
- [x] Update module and public documentation without changing the large version number.
- [x] Run module tests, then the full suite, then `git diff --check`.
- [x] Inspect the final diff and report changes without packaging, committing or pushing.
