from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "src" / "auto_check" / "modules" / "report_special_processing" / "web"


def read(name: str) -> str:
    return (WEB / name).read_text(encoding="utf-8")


def test_module_structural_surfaces_follow_the_platform_surface_hierarchy():
    css = read("styles.css")
    root = css.split(
        '.auto-check-module[data-module="report_special_processing"] {', 1
    )[1].split("}", 1)[0]

    for declaration in (
        "--rsp-brand: var(--theme-accent, #3466d9);",
        "--rsp-text: var(--on-surface, #17233c);",
        "--rsp-muted: var(--on-surface-variant, #66738a);",
        "--rsp-line: var(--ui-content-border, var(--outline-variant, #d8e1ee));",
        "--rsp-panel: var(--ui-panel-surface, var(--surface-container-lowest, #ffffff));",
        "--rsp-subsection: var(--ui-subsection-surface, var(--surface-container-low, #f1f4f6));",
        "--rsp-disabled: var(--ui-disabled-surface, var(--surface-container, #ebeef0));",
    ):
        assert declaration in root

    neutral_hardcoded_backgrounds = {
        "#fff",
        "#ffffff",
        "#fbfdff",
        "#fbfcff",
        "#fbfcfe",
        "#fafbfc",
        "#f8fafc",
        "#f8f9fd",
        "#f7f9fc",
        "#f6f8fb",
        "#f5f8fc",
        "#f3f5f8",
        "#f2f6fb",
        "#f0f2f5",
        "#e8eef6",
    }
    backgrounds = {
        value.lower()
        for value in re.findall(
            r"background(?:-color)?\s*:\s*(#[0-9a-fA-F]{3,8})\b", css
        )
    }
    assert backgrounds.isdisjoint(neutral_hardcoded_backgrounds)


def test_default_period_uses_previous_month_end():
    source = read("state.js")

    assert "export function defaultPeriod" in source
    assert "Date.UTC(year, month, 0)" in source
    assert "toISOString().slice(0, 10)" in source


def test_frontend_uses_native_module_lifecycle_and_host_context_only():
    source = read("index.js")

    for lifecycle in ("mount", "activate", "deactivate", "unmount"):
        assert f"export function {lifecycle}" in source
    for capability in ("context.root", "context.api", "context.user", "context.notify", "context.confirm", "context.prompt", "context.navigate"):
        assert capability in source
    assert "window." not in "\n".join(read(path) for path in ("index.js", "api.js", "state.js"))
    assert "AbortController" in read("api.js")
    assert "cancelAll" in read("api.js")


def test_api_contract_covers_catalog_ledger_actions_conflicts_and_audit():
    source = read("api.js")

    for endpoint in (
        '"/catalog"',
        '"/records"',
        '"/records/export"',
        '"/summary"',
        '"/status"',
        '"/void"',
        '"/reopen"',
        '"/audit"',
        '"/confirm-attachments"',
        '"/datasources"',
        "/datasources/${encodeURIComponent(datasourceId)}/tables",
        "/columns",
    ):
        assert endpoint in source
    assert "listDatasources" in source
    assert "listTables" in source
    assert "listColumns" in source
    assert "exportRecords" in source
    assert "Content-Disposition" in source
    assert "record_version_conflict" in source
    assert "记录已被其他人更新，请刷新后重试" in source
    assert "isVersionConflict" in source
    assert "status === 409 || code === \"record_version_conflict\"" not in source
    assert "internal_error" in source
    assert "withLatestVersion" in read("pages/ledger.js")


def test_candidate_a_is_dynamic_full_width_and_accessible():
    source = "\n".join(
        read(path)
        for path in (
            "pages/ledger.js",
            "components/filters.js",
            "components/record_table.js",
            "components/record_drawer.js",
        )
    )

    assert "report_processes.map" in source or "tabItems" in source
    assert 'name: "全部"' in source or 'text: "全部"' in source or '"全部"' in source
    assert "ALL_PROCESS" in source
    assert "record_total" in read("pages/ledger.js")
    assert "counts.values()].reduce" not in read("pages/ledger.js")
    assert "state.summary.record_total == null" in read("pages/ledger.js")
    assert "users.map" in source
    assert 'role: "tablist"' in source
    assert 'role: "tab"' in source
    assert "aria-selected" in source
    assert 'tabIndex: "0"' in source or 'tabIndex: active ? "0"' in source
    assert 'event.key === "Enter"' in source or "ArrowLeft" in source
    assert "关联报送" in source
    assert "所属维度" in source
    assert "数据治理负责人" in source
    assert "处理摘要" in source
    assert "处理表名" in source
    assert "处理字段名" in source
    assert "修改前" in source
    assert "修改后" in source
    assert "处理时间" in source
    assert "createProcessMultiSelect" in read("components/record_drawer.js")
    assert "report_process_codes" in read("components/record_drawer.js")
    assert "rsp-multi-select" in read("styles.css")
    assert 'type: "checkbox"' not in read("components/process_multi_select.js")
    assert "is-selected" in read("components/process_multi_select.js")
    assert "rsp-process-field" in read("components/record_drawer.js")
    assert 'labeledField(documentRef, "关联报送"' in read("components/record_drawer.js")
    assert "rsp-span-two rsp-process-field" not in read("components/record_drawer.js")
    drawer = read("components/record_drawer.js")
    assert "涉及报表" not in drawer
    assert "处理说明" not in drawer
    assert 'labeledField(documentRef, "特殊处理时间"' not in drawer
    assert "nowHandlingAt" in drawer
    assert 'labeledField(documentRef, "所处报送期", fields.period)' in drawer
    assert 'labeledField(documentRef, "处理人", fields.handler)' in drawer
    assert 'labeledField(documentRef, "所属维度"' in drawer
    assert 'labeledField(documentRef, "数据治理负责人"' in drawer
    assert 'createTableFieldGroups(documentRef' in drawer
    assert 'tableName: groupControl("table")' in drawer
    assert 'fieldName: groupControl("field")' in drawer
    assert 'labeledField(documentRef, "修改前"' in drawer
    assert 'labeledField(documentRef, "修改后"' in drawer
    assert "rsp-form-grid-basic" in drawer
    assert "defaultHandlerId" in drawer
    assert "governance_owner_candidates_by_dimension" in drawer
    assert "fillSelect(governanceOwner, users," in drawer
    assert "fillSelect(governanceOwner, candidates" not in drawer
    assert "previous && candidates.some" not in drawer
    assert "syncGovernanceOwnerOptions({ preferExisting: false, autoPick: true })" in drawer
    assert "Math.floor(Math.random()" in drawer
    assert 'labeledField(documentRef, "操作原因"' not in drawer
    assert "rsp-workflow-state" not in drawer
    assert "流程状态" not in drawer
    assert "handleRowAction" in read("pages/ledger.js")
    assert "askReason" in read("pages/ledger.js")
    assert 'await prompt("作废原因"' in read("pages/ledger.js")
    assert "maxlength: maxLength" in read("pages/ledger.js")
    assert "const maxLength = 20" in read("pages/ledger.js")
    assert "required: true" in read("pages/ledger.js")
    assert 'requiredMessage: "请输入作废原因"' in read("pages/ledger.js")
    assert "onInvalid:" not in read("pages/ledger.js")
    assert "defaultView?.prompt" not in read("pages/ledger.js")
    assert "prompt: context.prompt" in read("index.js")
    assert 'typeof context.prompt !== "function"' in read("index.js")
    assert "处理人" in source
    assert "状态" in source
    assert "操作" in source
    assert 'type: "datetime-local"' not in source
    assert 'type: "date"' in source
    assert 'type: "time"' not in source
    assert "rsp-datetime-pair" not in source
    assert "composeHandlingAt" not in source
    assert "special_handling_from" not in source
    assert "special_handling_to" not in source
    assert "脚本仅保存留痕，不在系统内执行。" in source
    assert "复制脚本" in source
    assert "执行脚本" not in source
    assert "提交审批" not in source
    assert "find((item) => item.active !== false)?.code" not in source
    assert 'text: "导出"' in read("components/filters.js")
    assert "onExport" in read("components/filters.js")
    assert "exportLedger" in read("pages/ledger.js")
    assert "rsp-btn-icon" in read("components/filters.js")
    assert "data-export-label" in read("components/filters.js")
    filters = read("components/filters.js")
    assert "涉及报表" not in filters
    assert 'labeledField(documentRef, "处理状态"' in filters
    assert 'labeledField(documentRef, "处理人"' in filters
    assert 'labeledField(documentRef, "关键词"' in filters


def test_dimension_governance_drawer_list_and_confirm_modal():
    drawer = read("components/record_drawer.js")
    table = read("components/record_table.js")
    ledger = read("pages/ledger.js")

    assert "SUMMARY_MAX_LENGTH = 128" in drawer
    assert "FIELD_TEXT_MAX_LENGTH = 128" in drawer
    assert 'maxlength: String(SUMMARY_MAX_LENGTH)' in drawer
    assert 'maxlength: String(FIELD_TEXT_MAX_LENGTH)' in drawer
    assert "涉及报表" not in drawer
    assert "处理说明" not in drawer
    assert "所属维度" in drawer
    assert "数据治理负责人" in drawer
    assert "处理编号" in drawer
    # 处理编号不再占用表单行，改为标题行右侧只读元信息，无编号时不渲染
    assert 'aria-label": "处理编号"' not in drawer
    assert "rsp-readonly-input" not in drawer
    assert "保存后自动生成" not in drawer
    assert "rsp-record-no-meta" in drawer
    assert "recordNoText" in drawer
    assert "复制处理编号" in drawer
    assert 'labeledField(documentRef, "处理编号"' not in drawer
    assert "处理表名" in drawer
    assert "处理字段名" in drawer
    assert "修改前" in drawer
    assert "修改后" in drawer
    assert 'summary: element(documentRef, "textarea"' in drawer
    assert 'className: "rsp-summary"' in drawer
    assert 'labeledField(documentRef, "修改前", fields.valueBefore)' in drawer
    assert 'labeledField(documentRef, "修改后", fields.valueAfter)' in drawer
    # 修改前/修改后左右并排对比
    assert 'className: "rsp-span-two rsp-value-pair"' in drawer
    assert 'labeledField(documentRef, "处理摘要", fields.summary, "rsp-span-all rsp-summary-field")' in drawer
    assert "源系统已确认" in drawer
    assert 'mode === "confirm"' in drawer or 'mode === "confirm"' in ledger

    assert 'pending: "待确认"' in table
    assert '"修改字段", "修改前", "修改后", "所属业务系统", "关联报送", "状态", "处理人", "处理时间", "操作"' in table
    assert "变更摘要" not in table
    assert 'colspan: "9"' in table
    assert "clampedTextCell" in table
    assert "rsp-cell-clamp" in table
    assert "rsp-cell-tip" in table
    assert "showCellTip" in table
    assert "-webkit-line-clamp: 3" in read("styles.css")
    assert "涉及报表" not in table
    assert 'text: "完成"' not in table
    assert 'text: "确认"' in table or '确认"' in table
    assert "record.can_confirm" in table

    assert "record_id" in ledger
    assert "highlight" in ledger
    assert "openConfirm" in ledger
    assert 'openRecord(record, null, "confirm")' in ledger
    assert "async function openConfirmOverlay(recordId)" in ledger
    assert "async function openDetailOverlay(recordId)" in ledger
    assert "async function openRecordOverlay(recordId, mode" in ledger
    assert 'openRecordOverlay(recordId, "confirm")' in ledger
    assert 'openRecordOverlay(recordId, "detail")' in ledger
    assert "todoConfirmHost" in ledger
    assert "rsp-todo-confirm-host" in ledger
    assert "rsp-todo-confirm-host" in read("styles.css")
    assert "export function openConfirmOverlay(recordId)" in read("index.js")
    assert "export function openDetailOverlay(recordId)" in read("index.js")
    assert "auto-check:report-navigation-refresh" in ledger
    assert "locateOpenConfirm" in ledger
    assert "applyLocateContext" in ledger
    assert "api.getRecord(recordId)" in ledger or "api.getRecord(recordId)" in ledger
    assert 'keyword: String(record.record_no' in ledger
    assert 'action === "confirm"' in ledger
    assert 'target_status: "completed"' in drawer
    assert 'reason: "源系统已确认"' not in drawer
    assert "confirm_images" in drawer
    assert "MAX_CONFIRM_IMAGES = 3" in drawer
    assert "确认说明（选填）" in drawer
    assert "onPaste: handleConfirmPaste" in drawer
    assert "最多粘贴 3 张图片" in drawer
    assert "rsp-image-lightbox" in drawer
    assert "openImageLightbox" in drawer
    assert "if (event.target === lightboxNode) closeImageLightbox();" not in drawer
    assert "上传" not in drawer
    assert "type: \"file\"" not in drawer
    assert 'await confirm("确认完成"' not in ledger
    assert 'confirm("确认将该记录标记为已完成吗？")' not in ledger
    assert "源系统已确认" in drawer


def test_ledger_pagination_matches_system_arrow_jump_style():
    source = read("pages/ledger.js")
    css = read("styles.css")

    assert "rsp-page-btn" in source
    assert "rsp-pagination-jump" in source
    assert "跳至" in source
    assert "暂无数据" in source
    assert "20条/页" not in source
    assert 'text: "上一页"' not in source
    assert 'text: "下一页"' not in source
    assert "rsp-page-current" in css
    assert "width: 30px" in css
    assert "height: 30px" in css


def test_ledger_does_not_pass_null_availability_into_replace_children():
    source = read("pages/ledger.js")
    css = read("styles.css")

    # 顶部已对齐系统轻标题：删除独立 rsp-page-intro，标题+报送期+新建按钮并入 Tab 白卡头部。
    assert 'className: "rsp-page-intro"' not in source
    assert "数据录入 / 报表特殊处理录入" not in source
    assert "按报送流程维护特殊处理记录" not in source
    assert 'className: "rsp-tabs-card"' in source
    assert 'className: "rsp-tabs-header"' in source
    assert 'className: "rsp-tabs-title"' in source
    assert 'className: "rsp-tabs-actions"' in source
    assert ".rsp-tabs-card" in css
    assert ".rsp-tabs-header" in css
    assert ".rsp-tabs-title" in css
    assert ".rsp-tabs-actions" in css
    assert 'input[type="date"]' in css
    assert ".rsp-tabs-header .rsp-button" in css
    assert "height: 32px" in css
    assert "width: 118px" in css
    assert ".rsp-form-grid-basic > label:not(.rsp-span-two) .custom-select-shell" in css
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in css
    assert ".rsp-span-cols-2" in css
    assert "grid-column: span 2" in css
    assert "background: var(--rsp-disabled) !important" in css
    assert ".rsp-record-modal input:disabled" in css
    assert ".custom-select-disabled .custom-select-trigger" in css
    assert ".rsp-multi-select-trigger:disabled" in css
    assert "--select-height: 32px !important" in css
    assert '请填写处理表名' in read("components/record_drawer.js")
    assert '请填写处理字段名' in read("components/record_drawer.js")
    assert "rsp-compact-select" in read("components/record_drawer.js")
    assert ".rsp-compact-select-dropdown .custom-select-option" in css
    assert "font-size: 12px" in css
    assert "root.replaceChildren(...[availability, layout, modal].filter(Boolean))" in source
    assert 'createTabs({ title: "报表特殊处理", actions: tabsActions })' in source
    assert "root.replaceChildren(...[availability, createTabs(" not in source
    assert "root.replaceChildren(...[intro, availability, createTabs(), layout, modal].filter(Boolean))" not in source
    assert "grid-template-rows: auto auto minmax(0, 1fr) auto" in css
    assert "rsp-catalog-warning" in source
    assert "rsp-record-modal" in source


def test_editor_supports_draft_record_and_audit_pagination():
    source = read("components/record_drawer.js")

    assert 'canEdit ? "编辑" : "查看"' in source
    assert "rsp-eyebrow" not in source
    for label in ("保存草稿", "保存记录", "保存修改", "操作记录"):
        assert label in source
    assert "操作留痕" not in source
    assert "rsp-audit-summary" in source
    assert "rsp-audit-summary-line" in source
    for action in ("saveDraft", "saveRecord", "loadAudit"):
        assert action in source
    assert "syncAuditPager" in source
    assert "auditTotalPages" in source
    assert "暂无操作记录" in source
    assert 'creating || current.status === "draft"' in source
    assert 'footerButtons.push(actionButton(documentRef, "保存草稿"' in source
    assert "SUMMARY_MAX_LENGTH = 128" in source
    assert "FIELD_TEXT_MAX_LENGTH = 128" in source
    assert "validateForm" in source
    assert "showFormHint" in source
    assert "formatFieldMessage" in source
    assert "rsp-field-hint" in source
    assert "rsp-modal-actions-right" in source
    assert "处理摘要最多支持" in source
    assert "关联报送" in source
    assert "errorBox" not in source
    assert "rsp-form-error" not in source
    assert "showSummaryHint" not in source
    assert 'maxlength: String(SUMMARY_MAX_LENGTH)' in source
    assert 'aria-label": "处理摘要"' in source
    assert "rsp-field-hint" in read("styles.css")
    assert "rsp-modal-actions-right" in read("styles.css")
    assert "rsp-audit-summary" in read("styles.css")
    css = read("styles.css")
    assert ".rsp-audit th," in css
    assert "text-align: left;" in css
    assert ".rsp-audit-table-wrap" in css
    audit_wrap = css.split(".rsp-audit-table-wrap", 1)[1].split(".rsp-audit table", 1)[0]
    assert "overflow-x: auto" not in audit_wrap
    for moved in ("开始处理", "转为待处理", "操作原因", "completeRecord", "voidRecord", "reopenRecord"):
        assert moved not in source
    assert "row_version" in source
    assert "catalogAvailable" in source
    assert "disabled" in source
    assert 'aria-modal": "true"' in source
    assert "rsp-record-modal-overlay" in source
    assert "Escape" in source
    assert "if (event.target === overlay) onClose()" not in source


def test_audit_diff_panel_preserves_long_values_and_operation_semantics():
    drawer = read("components/record_drawer.js")
    css = read("styles.css")

    for token in (
        "AUDIT_ACTION_META", "AUDIT_FIELD_LABELS", "describeAuditEntry",
        "renderAuditDetail", "查看变更详情", "收起详情", "aria-expanded",
        "changed_fields", "重开原因", "作废理由", "确认说明", "rsp-audit-detail-scroll",
        "hasStructuredAuditData", "formatScriptAuditPair", "rsp-audit-script-copy",
        "copyAuditScript", "copyTextToClipboard", "execCommand", "copyIsPreview",
        "SCRIPT_AUDIT_PREVIEW_CHARS = 400", "SCRIPT_AUDIT_PREVIEW_LINES = 8",
        "已复制脚本开头预览；系统不会执行该脚本",
        "脚本已复制；系统不会执行该脚本",
        "复制${label}脚本",
        "confirm_attachments", "rsp-confirm-thumbs", "rsp-image-lightbox",
        "确认图片",
    ):
        assert token in drawer
    assert "rsp-audit-value--script" in css
    assert "-webkit-line-clamp: 8" in css
    assert ".rsp-audit-script-copy" in css
    assert ".rsp-audit-script-text" in css
    for tone in ("update", "reopen", "void", "completed", "neutral"):
        assert f"rsp-audit-action-{tone}" in drawer
    for label in ("创建", "修改", "重开", "作废", "完成"):
        assert f'label: "{label}"' in drawer
    for old_label in ("创建记录", "修改记录", "重开记录", "作废记录", "完成记录"):
        assert old_label not in drawer
    for selector in (
        ".rsp-audit-detail-row", ".rsp-audit-diff-grid",
        ".rsp-audit-detail-scroll",
        ".rsp-audit-value-before", ".rsp-audit-value-after",
        ".rsp-audit-action-void", ".rsp-audit-action-reopen",
    ):
        assert selector in css
    assert "white-space: pre-wrap" in css
    assert "overflow-wrap: anywhere" in css
    audit_table_css = css.rsplit(".rsp-audit table {", 1)[1].split("}", 1)[0]
    assert "min-width: 0" in audit_table_css
    audit_detail_css = css.split(".rsp-audit-detail-row", 1)[1].split(".rsp-audit-pagination", 1)[0]
    assert "max-height:" not in audit_detail_css
    audit_detail_cell_css = css.split(".rsp-audit-detail-row > td {", 1)[1].split("}", 1)[0]
    assert "max-width: 0" in audit_detail_cell_css
    assert "overflow: hidden" in audit_detail_cell_css
    audit_detail_box_css = css.split(".rsp-audit-detail {", 1)[1].split("}", 1)[0]
    assert "width: 100%" in audit_detail_box_css
    assert "min-width: 0" in audit_detail_box_css
    audit_scroll_css = css.split(".rsp-audit-detail-scroll {", 1)[1].split("}", 1)[0]
    assert "overflow: hidden" in audit_scroll_css
    assert "border: 1px solid #dfe7f2" in audit_scroll_css
    assert "width: 100%" in audit_scroll_css
    assert "max-width: 100%" in audit_scroll_css
    grid_css = css.split(".rsp-audit-diff-grid {", 1)[1].split("}", 1)[0]
    assert "width: 100%" in grid_css
    assert "min-width: 0" in grid_css
    assert "grid-template-columns: 120px minmax(0, 1fr) minmax(0, 1fr)" in grid_css
    assert "isCompact" not in drawer
    assert "is-scrollable" not in drawer
    assert "可横向滚动查看" not in drawer
    assert ".rsp-audit-detail-scroll.is-scrollable" not in css
    assert ".rsp-audit-detail-scroll::-webkit-scrollbar" not in css
    assert "if (!hasDetails && !entry.hasStructuredAuditData)" in drawer


def test_audit_detail_uses_semantic_basic_and_per_table_groups():
    drawer = read("components/record_drawer.js")
    detail = read("components/audit_detail.js")
    css = read("styles.css")

    assert 'import { buildSemanticAuditViewModel, renderSemanticAuditDetail } from "./audit_detail.js"' in drawer
    assert 'key === "structured_content"' in drawer
    assert "renderSemanticAuditDetail" in drawer
    for text in ("基本信息", "特殊处理内容", "表信息变更", "处理范围变更", "修改字段变更", "查看删除前配置", "脚本变更"):
        assert text in detail
    for selector in (".rsp-audit-semantic", ".rsp-audit-table-card", ".rsp-audit-event-added", ".rsp-audit-event-removed"):
        assert selector in css


def test_ledger_row_actions_include_status_operations():
    table_source = read("components/record_table.js")
    ledger_source = read("pages/ledger.js")
    css = read("styles.css")

    for label in ("编辑", "查看", "确认", "作废", "删除", "重开"):
        assert label in table_source
    for removed in ("开始处理", "转为待处理"):
        assert removed not in table_source
        assert removed not in ledger_source
    assert "record.can_reopen" in table_source
    assert 'action === "reopen"' in ledger_source
    assert "reopenRecord" in read("api.js")
    assert "buildRowActions" in table_source
    assert "onAction" in table_source
    assert 'onClick: () => onOpen(record, row)' not in table_source
    assert 'if (event.key === "Enter") onOpen(record, row)' not in table_source
    assert "handleRowAction" in ledger_source
    assert 'await confirm("确认完成"' not in ledger_source
    assert 'confirm("确认完成"' not in ledger_source
    assert 'action === "confirm"' in ledger_source
    assert "源系统已确认" in read("components/record_drawer.js")
    assert 'confirm("确认作废"' in ledger_source
    assert 'confirm("确认删除"' in ledger_source
    assert "删除后不可恢复" in ledger_source
    assert "deleteRecord" in read("api.js")
    assert 'action === "delete"' in ledger_source
    assert 'confirm("确认将该记录标记为已完成吗？")' not in ledger_source
    assert 'confirm("确认作废该记录吗？作废后仍保留完整留痕。")' not in ledger_source
    assert 'action === "complete"' not in ledger_source
    assert 'action === "start"' not in ledger_source
    assert 'action === "pend"' not in ledger_source
    assert 'action === "reopen"' in ledger_source
    assert "rsp-row-actions" in table_source
    assert "rsp-row-actions-inner" in table_source
    assert ".rsp-row-actions-inner" in css
    assert "rsp-text-action-danger" in css
    assert "rsp-text-action-success" in css
    assert 'width: 26%' in css
    assert "grid-template-columns: minmax(0, 5fr) minmax(0, 3fr)" not in css
    assert "padding-left: 40px" in css
    assert "padding-left: 22px" in css
    assert "padding-left: 8px" in css
    assert "padding-right: 22px" in css
    assert "padding-right: 8px" in css


def test_ledger_table_empty_state_and_list_layout_align_with_system_lists():
    table_source = read("components/record_table.js")
    ledger_source = read("pages/ledger.js")
    css = read("styles.css")
    scope = '.auto-check-module[data-module="report_special_processing"]'

    assert 'className: "rsp-empty-row"' in table_source
    assert 'colspan: "9"' in table_source
    assert "没有符合条件的特殊处理记录" in table_source
    assert "wrap.append(element(documentRef, \"div\", { className: \"rsp-empty\"" not in table_source
    assert "formatDisplayDateTime" in table_source
    assert "formatDisplayDateTime(record.special_handling_at)" in table_source
    assert 'replace("T", " ")' in table_source
    assert "processNameList" in table_source
    assert "displayWidth" in table_source
    assert "compareByDisplayWidth" in table_source
    assert "code <= 0x00ff" in table_source
    assert ".sort(compareByDisplayWidth)" in table_source
    assert "left.code === focus" not in table_source
    assert "createRecordTable(documentRef, state.records, {\n        selectedId: state.drawer?.record?.id,\n        activeProcessCode:" not in ledger_source
    assert "rsp-process-name-line" in table_source
    assert "normalizeProcessNames" not in table_source
    assert 'replace(/\\//g, "、")' not in table_source
    assert 'names.join("；")' in read("components/process_multi_select.js")
    assert "rsp-process-names-block" in table_source
    assert "is-compact" in table_source
    assert "names.length > 3" in table_source
    assert "fitProcessNameNodes" not in table_source
    assert "is-compact" in css
    assert "font-size: 12px" in css
    assert "scheduleProcessNameFit" not in table_source
    assert "rsp-cell-fit" not in table_source
    assert '(record.reports || []).join("、")' not in table_source
    assert '"修改字段", "修改前", "修改后", "所属业务系统", "关联报送", "状态", "处理人", "处理时间", "操作"' in table_source
    assert "th:nth-child(1)" in css
    assert "th:nth-child(9)" in css
    assert "td.rsp-process-names" in css
    assert "rsp-process-name-line" in css
    assert "text-align: center" in css
    assert f"{scope} .rsp-ledger-table th" in css

    assert f"{scope} .rsp-filters" in css
    assert "display: flex" in css
    assert f"{scope} .rsp-ledger-table th" in css
    assert "text-align: center" in css
    assert "min-height: 280px" not in css
    assert "min-height: max(520px, calc(100vh - 270px))" not in css
    assert "calc(100vh - 270px)" not in css
    assert "flex: 1 1 auto" in css
    assert "grid-template-rows: minmax(0, 1fr)" in css
    assert "grid-template-rows: auto auto minmax(0, 1fr) auto" in css
    assert "rsp-name-line" not in css
    assert "rsp-name-more" not in css
    assert "rsp-cell-clamp" in css
    assert "-webkit-line-clamp: 3" in css
    assert "rsp-cell-tip" in css
    assert "scrollbar-width: thin" in css
    assert "processCatalog:" not in read("pages/ledger.js")
    assert "td.rsp-process-names" in css
    assert 'cellNode.style.textAlign = "left"' not in table_source
    assert "text-align: left !important" not in css
    assert "pageSize: 10" in read("state.js")
    assert f"{scope} .rsp-empty-row td" in css
    assert "margin: 0 20px 12px" not in css
    assert "margin: 0 20px 24px" not in css
    assert "margin: 0 20px 10px" not in css
    assert "background: transparent" in css
    assert "padding: 4px 0 12px" in css
    assert "padding: 12px 20px" in css
    assert "padding: 8px 20px" in css
    assert "padding-left: 40px" in css
    assert "padding-right: 20px" in css
    assert "\nbutton {" not in css
    assert "\ntable {" not in css
    assert "\ninput {" not in css
    assert "is-highlighted" in css or "rsp-row-highlight" in css


def test_module_css_is_scoped_light_only_and_keeps_centered_modal():
    css = read("styles.css")
    scope = '.auto-check-module[data-module="report_special_processing"]'

    assert scope in css
    for forbidden in ("\nbutton {", "\ninput {", "\ntable {", "prefers-color-scheme", "dark-mode", "text-shadow"):
        assert forbidden not in css
    assert "position: fixed" in css
    assert "rsp-record-modal-overlay" in css
    assert "z-index: 3200" in css
    assert "z-index: 100;" not in css.split("rsp-record-modal-overlay", 1)[-1].split("}", 1)[0]
    assert "rsp-record-modal" in css
    assert "width: min(900px, calc(100vw - 72px))" in css
    assert "inset: 0" in css
    assert "rsp-record-drawer" not in css
    assert "grid-template-columns: minmax(0, 1fr)" in css
    assert "linear-gradient(135deg, #3466d9, #6aa4ff)" in css.lower()
    assert "var(--ui-radius)" in css
    assert "@media (max-width: 1366px)" in css
    assert "flex-wrap: wrap" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "height: 58px" in css
    assert "rsp-eyebrow" not in css


def test_no_business_catalog_is_hardcoded_in_module_frontend():
    source = "\n".join(path.read_text(encoding="utf-8") for path in WEB.rglob("*.js"))

    for old_catalog_value in (
        "人行大集中报送",
        "资管产品模板、逐笔报送",
        "1104报送",
        "全要素报送",
        "中信登定期报送",
        "EAST5.0报送",
        "五篇大文章报送",
    ):
        assert old_catalog_value not in source


def test_record_drawer_integrates_attachment_section_and_save_flow():
    source = read("components/record_drawer.js")

    assert (
        'import { createRecordAttachmentSection, renderRecordAttachmentSnapshot } from "./record_attachments.js";'
        in source
    )
    # 保存前等待附件构建，并把非 null 结果写入 payload。
    assert "async function buildSavePayload(saveMode)" in source
    assert "await attachmentSection.buildChangePayload()" in source
    assert "payload.record_attachments = attachmentChange" in source
    # 粘贴监听挂在抽屉层，且由组件决定是否拦截。
    assert 'overlay.addEventListener("paste"' in source
    assert "attachmentSection.handlePaste(event)" in source
    # 关闭与保存成功后销毁附件组件，失败保留。
    assert "attachmentSection?.destroy()" in source
    # authPreflight 声明只出现在 api.js，不在抽屉里。
    assert "authPreflight" not in source
    # 抽屉不请求认证端点、不显示登录 UI。
    assert "/api/auth/" not in source
    # 附件预览 Blob URL 关闭时释放。
    assert "revokeObjectURL" in source


def test_record_drawer_audit_renders_attachment_dual_columns():
    source = read("components/record_drawer.js")

    assert 'if (key === "record_attachments")' in source
    assert "attachmentDiff = {" in source
    assert "Array.isArray(meta.old) ? meta.old : []" in source
    assert "rsp-audit-record-attachments-columns" in source
    assert '"修改前"' in source
    assert '"修改后"' in source
    assert "Boolean(entry.attachmentDiff)" in source
    # 附件对象不得 JSON.stringify 进普通单元格。
    assert "JSON.stringify(meta)" not in source


def test_attachment_styles_are_scoped_and_follow_theme_rules():
    css = read("styles.css")

    assert ".rsp-attachment-section" in css
    assert ".rsp-attachment-card" in css
    assert ".rsp-attachment-change-added" in css
    assert ".rsp-attachment-change-removed" in css
    assert ".rsp-attachment-change-retained" in css
    assert ".rsp-audit-record-attachments-columns" in css
    # 所有附件相关规则必须限定在模块作用域内。
    for line in css.splitlines():
        if "rsp-attachment" in line and "{" in line:
            assert line.strip().startswith('.auto-check-module[data-module="report_special_processing"]'), line
    # 圆角复用全局变量；卡片悬浮无主题光晕。
    attachment_css = css[css.index(".rsp-attachment-section"):]
    assert "var(--ui-radius)" in attachment_css
    assert "box-shadow: 0 0 0" not in attachment_css.split(".rsp-audit-record-attachments")[0]
    # 上传按钮为次要样式（不使用渐变），删除按钮使用危险红色。
    assert "rsp-button-secondary rsp-attachment-upload" in read("components/record_attachments.js")
    assert "#cf3d3d" in attachment_css


def test_module_download_uses_platform_raw_api_without_private_login_handling():
    source = read("api.js")

    # 下载统一走平台 API 的 raw 响应模式，由平台负责认证恢复。
    assert 'responseType: "raw"' in source
    assert "context.api(" in source
    assert "fetchRecordAttachment" in source
    # 模块不再通过 window.location 跳登录页，也不自判 401 做私有登录恢复。
    assert "window.location" not in source
    assert "/login.html" not in source
    assert "response.status === 401" not in source
    assert "login required" not in source
    # 保留 AbortController、Content-Disposition、空 Blob 与错误归一化行为。
    assert "AbortController" in source
    assert "Content-Disposition" in source
    assert "normalizeError" in source
    assert "生成的导出文件为空" in source


def test_record_drawer_guards_duplicate_submissions():
    source = read("components/record_drawer.js")

    # 提交互斥锁：在途保存/确认期间忽略重复点击并禁用底部操作按钮。
    assert "let submitting = false;" in source
    assert "if (submitting) return;" in source
    assert "setFooterActionsDisabled(true)" in source
    # 失败后解锁允许重试；成功路径保持锁定直到抽屉关闭。
    run_source = source[source.index("async function run("):]
    run_source = run_source[: run_source.index("function validateForm(")]
    assert "submitting = false;" in run_source
    assert "setFooterActionsDisabled(false)" in run_source
    assert run_source.index("submitting = true;") < run_source.index("submitting = false;")
    assert "footerActionButtons.push(...footerButtons)" in source


def test_business_system_dropdown_in_basic_section_after_dimension():
    drawer = read("components/record_drawer.js")
    assert "catalog?.business_systems" in drawer
    assert 'aria-label": "所属业务系统"' in drawer
    assert 'labeledField(documentRef, "所属维度", fields.dimension)' in drawer
    # 顺序：所属维度之后紧跟所属业务系统
    assert drawer.index('labeledField(documentRef, "所属维度", fields.dimension)') < drawer.index(
        'labeledField(documentRef, "所属业务系统", fields.businessSystem)'
    ) < drawer.index('labeledField(documentRef, "数据治理负责人", fields.governanceOwner)')
    assert "business_system_code: fields.businessSystem?.value || null" in drawer
    assert "请先在系统管理—字典管理中维护业务系统" in drawer
    # 停用历史项仍可选择并保留快照
    assert "（已停用）" in drawer
    assert "business_system_name_snapshot" in drawer


def test_bilingual_name_list_component_contract():
    source = read("components/bilingual_name_list.js")
    assert 'export const BILINGUAL_PART_SEPARATOR = "｜"' in source
    assert 'export const BILINGUAL_ITEM_SEPARATOR = "；"' in source
    assert "export function parseBilingualItems" in source
    assert "export function serializeBilingualItems" in source
    assert "export function createBilingualNameList" in source
    # 最多 5 项、单名 100 字符
    assert "BILINGUAL_MAX_ITEMS = 5" in source
    assert 'maxlength: "100"' in source
    # 历史值以普通输入行展示，未编辑时保持原序列化值。
    assert "legacyDirty" in source
    assert "请补充英文名称后保存" in source
    assert "历史格式" not in source
    assert "改为中英文录入" not in source
    # 添加操作位于末行删除操作之后；仅一行时不得删除。
    assert "function updateRowActions" in source
    assert "row.removeButton.hidden = rows.length <= 1" in source
    assert "lastRow.actions.append(addButton)" in source


def test_table_field_groups_component_contract():
    source = read("components/table_field_groups.js")
    # 分组序列化复用双语规范串工具，组间分隔符为双全角分号
    assert "parseBilingualGroups" in source
    assert "serializeBilingualGroups" in source
    assert "serializeBilingualItems" in source
    # 上限：最多 5 张表、每表最多 5 个字段
    assert "MAX_TABLE_GROUPS = BILINGUAL_MAX_ITEMS" in source
    assert "MAX_FIELDS_PER_TABLE = BILINGUAL_MAX_ITEMS" in source
    # 顶部添加表；分组内部添加字段；表/字段均可单独删除
    assert "+ 添加表" in source
    assert "+ 添加字段" in source
    assert "删除表" in source
    # 删表二次确认提示关联字段一并删除
    assert "确认删除表" in source
    assert "删除该表将同时删除其下" in source
    assert "个关联字段，确认删除吗？" in source
    # 折叠/展开与字段计数标题
    assert "COLLAPSE_FIELD_THRESHOLD" in source
    assert "aria-expanded" in source
    assert "个字段）" in source
    # 历史值未修改时原样提交，编辑后升级
    assert "dirty" in source
    assert "未修改时将保留原有历史值" in source
    # 中英文列使用固定列标题，不只依赖 placeholder
    assert "rsp-tf-cols-head" in source
    assert "中文表名" in source
    assert "英文表名" in source
    assert "中文字段名" in source
    assert "英文字段名" in source
    # 对抽屉暴露与旧接口兼容的 tableValue / fieldValue
    assert '"tableValue"' in source
    assert '"fieldValue"' in source


def test_drawer_and_table_use_grouped_table_field_component():
    drawer = read("components/record_drawer.js")
    table = read("components/record_table.js")
    assert 'import { createTableFieldGroups } from "./table_field_groups.js"' in drawer
    assert "createTableFieldGroups(documentRef" in drawer
    assert 'confirm: options.confirm' in drawer
    assert 'className: "rsp-span-two rsp-tf-field" }, [tableFieldGroups]' in drawer
    # 处理摘要保留在基本信息区并使用默认 56px 多行高度
    assert 'className: "rsp-summary",\n      rows: "3",' in drawer
    assert 'labeledField(documentRef, "处理摘要", fields.summary, "rsp-span-all rsp-summary-field")' in drawer
    # 台账使用修改字段/修改前/修改后三列；新旧记录都按完整值对分组。
    assert 'import { parseBilingualItems, parseBilingualGroups, BILINGUAL_PART_SEPARATOR } from "./bilingual_name_list.js"' in table
    assert "function structuredChangeGroups(record)" in table
    assert "function legacyChangeGroups(record)" in table
    assert "function recordChangeGroups(record)" in table
    assert "function changeGridCell(documentRef, groups)" in table
    assert "groupByValuePair" in table
    assert 'cell(documentRef, record.business_system_name_snapshot, "rsp-business-system")' in table
    assert 'tableFieldCell' not in table
    assert 'record.table_name' not in table


def test_bilingual_styles_are_scoped():
    css = read("styles.css")
    assert ".auto-check-module[data-module=\"report_special_processing\"] .rsp-bilingual-list" in css
    assert ".auto-check-module[data-module=\"report_special_processing\"] .rsp-bilingual-row" in css
    assert ".auto-check-module[data-module=\"report_special_processing\"] .rsp-bilingual-field" in css
    assert ".auto-check-module[data-module=\"report_special_processing\"] .rsp-cell-clamp-multiline" in css
    # 表-字段分组卡片、固定列标题、处理编号元信息与修改前/后并排样式同样限定在模块作用域内
    for selector in (".rsp-tf-groups", ".rsp-tf-card", ".rsp-tf-card-head", ".rsp-tf-card-body", ".rsp-tf-field-row", ".rsp-tf-cols-head", ".rsp-record-no-meta", ".rsp-value-pair"):
        assert f".auto-check-module[data-module=\"report_special_processing\"] {selector}" in css
    # 列宽固定：表行与字段行共用同一栅格模板，删除列固定宽不漂移
    assert css.count("grid-template-columns: 24px 112px minmax(0, 1fr) 16px minmax(0, 1fr) 56px") >= 3
    # 处理摘要使用默认多行高度
    assert "min-height: 56px" in css


def test_structured_content_editor_contract():
    source = read("components/structured_content_editor.js")
    drawer = read("components/record_drawer.js")
    # 数据源/表/字段均来自元数据接口；行内表单式交互，不再使用二级选择弹窗
    assert "createStructuredContentEditor" in source
    assert "listDatasources" in source
    assert "listTables" in source
    assert "listColumns" in source
    assert "openMetadataPicker" not in source
    # 数据源归属每张表；英文表名为可搜索输入 + 候选面板（中英文模糊搜索）
    assert "rsp-sc-ds-select" in source
    assert "rsp-sc-combo-input" in source
    assert "请选择表（支持中文/英文模糊搜索）" in source
    # 中文名称：选择英文名后自动带出 comment，始终允许修改，只保存业务记录
    assert "请输入中文表名" in source
    assert "请输入中文字段名" in source
    # 添加表/添加字段直接新增行，不弹窗；字段区永不渲染空态占位
    assert "rsp-sc-tbl-head" in source
    assert "rsp-sc-field-head" in source
    assert "暂无关联字段" not in source
    # 修改前/后为字段级输入；新字段默认留空，不继承上一个字段
    assert "rsp-sc-value-input" in source
    assert "table.fields.push(emptyField())" in source
    # 保存校验逐条定位
    for message in ("请选择数据源", "请选择处理表", "请输入中文表名", "请至少为", "请输入中文字段名", "请输入修改前内容", "请输入修改后内容"):
        assert message in source
    # 结构化 payload 与兼容派生串
    assert "getStructured" in source
    assert "getStrings" in source
    # 每张表最多 5 字段、最多 5 张表
    assert "MAX_SC_TABLES" in source
    assert "MAX_SC_FIELDS" in source
    # 报送期字段匹配规则来自系统字典目录，不在前端写死。
    assert "reportPeriodFieldMatchers = []" in source
    assert "reportPeriodFieldMatchers: catalog?.report_period_fields || []" in drawer
    assert "const matcherCodes = reportPeriodFieldMatchers" in source
    assert "REPORT_PERIOD_PATTERNS" not in source
    assert "cldate" not in source.lower()
    assert "caldate" not in source.lower()


def test_disabled_structured_editor_keeps_each_tables_saved_datasource_visible():
    source = read("components/structured_content_editor.js")

    assert 'table.datasourceName = String(rawTable?.datasource_name || datasourceNameSnapshot || "");' in source
    assert "function fillDatasourceSelect(select, selectedId, selectedName" in source
    assert "name: selectedName || selectedId" in source
    assert "fillDatasourceSelect(" in source
    assert "table.datasourceName," in source


def test_readonly_drawer_uses_preview_content_instead_of_disabled_form_controls():
    drawer = read("components/record_drawer.js")
    css = read("styles.css")

    assert 'import { createLegacyContentPreview, createStructuredContentPreview, readonlyField, readonlyTextBlock } from "./record_preview.js"' in drawer
    assert "const readOnly = !canEdit;" in drawer
    assert "createStructuredContentPreview(documentRef" in drawer
    assert "createLegacyContentPreview(documentRef" in drawer
    assert 'className: "rsp-readonly-basic-preview"' in drawer
    assert 'className: "rsp-readonly-basic-grid"' in drawer
    assert '"rsp-readonly-related-reports"' in drawer
    assert drawer.index('className: "rsp-readonly-basic-grid"') < drawer.index('readonlyField(documentRef, "关联报送"')
    assert '"rsp-readonly-script"' in drawer
    for selector in (
        ".rsp-readonly-info-item",
        ".rsp-readonly-info-label",
        ".rsp-readonly-info-value",
        ".rsp-readonly-basic-preview",
        ".rsp-readonly-related-reports",
        ".rsp-readonly-summary",
        ".rsp-config-preview-card",
        ".rsp-preview-table",
    ):
        assert selector in css
    preview_wrap = css.split(
        '.auto-check-module[data-module="report_special_processing"] .rsp-preview-table-wrap {', 1
    )[1].split("}", 1)[0]
    assert "overflow: hidden;" in preview_wrap
    assert "overflow-x: auto" not in preview_wrap
    preview_table = css.split(
        '.auto-check-module[data-module="report_special_processing"] .rsp-preview-table {', 1
    )[1].split("}", 1)[0]
    assert "min-width: 0;" in preview_table
    assert "max-width: 100%;" in preview_table



def test_condition_field_selection_displays_chinese_and_english_names():
    source = read("components/structured_content_editor.js")
    condition_source = source[source.index("function renderConditionRow(table, condition, isLast) {"):source.index("function renderFields(table) {")]
    assert "combo.input.value = columnDisplayLabel(item);" in condition_source
    assert "condition.chinese = String(item.column_comment || item.secondary || \"\");" in condition_source
    assert "combo.input.value = tableColumnDisplayLabel(table, condition.column, condition.chinese);" in condition_source


def test_structured_combobox_focus_search_and_selection_contract():
    source = read("components/structured_content_editor.js")

    # 数据源下拉仅展示数据源原名称，不拼接数据库类型。
    assert 'text: item.name,' in source
    assert 'text: `${item.name}（${DB_TYPE_LABELS' not in source

    # 表、条件字段、修改字段、数据日期字段统一在聚焦时加载前 10 条；
    # 输入为空也保留默认候选，输入关键词后继续走中英文模糊查询。
    assert source.count("pageSize: 10,") >= 4
    open_source = source[source.index("function open() {"):source.index("function scheduleSearch() {")]
    assert "load(1);" in open_source
    assert "if (!String(input.value || \"\").trim()) return;" not in open_source
    search_source = source[source.index("function scheduleSearch() {"):source.index("function attachScrollClose() {")]
    assert "load(1);" in search_source
    assert "panel.hidden = true;" not in search_source

    # 点击候选项时由通用组件先回填物理名，再触发各业务选择回调。
    option_source = source[source.index("items.forEach((item) => {"):source.index("if (page < totalPages) {")]
    assert "input.value = primaryText;" in option_source
    assert option_source.index("input.value = primaryText;") < option_source.index("onPick(item);")

    # 候选列表自身滚动不得触发外层滚动关闭逻辑。
    assert "function closeOnHostScroll(event)" in source
    assert "shell.contains(event.target)" in source
    assert 'addEventListener?.("scroll", closeOnHostScroll, true)' in source

    # “加载更多”追加下一页候选，不覆盖已经显示的表/字段，并保留滚动位置。
    load_source = source[source.index("async function load(requestedPage = 1) {"):source.index("function renderItems() {")]
    assert "const nextItems = Array.isArray(payload.items) ? payload.items : [];" in load_source
    assert "items = requestedPage === 1 ? nextItems : items.concat(nextItems);" in load_source
    assert "const previousScrollTop = listBox.scrollTop;" in load_source
    assert "listBox.scrollTop = previousScrollTop;" in load_source


def test_structured_table_delete_keeps_one_table_and_stacks_confirmation():
    source = read("components/structured_content_editor.js")
    css = read("styles.css")

    # 特殊处理内容至少保留一张表；单表时隐藏表级删除按钮，增删后统一刷新。
    assert "if (state.tables.length <= 1)" in source
    assert "function updateTableRemoveButtons()" in source
    assert "table.removeButton = removeButton;" in source
    assert "const visible = !disabled && state.tables.length > 1;" in source
    assert "table.removeButton.hidden = !visible;" in source

    # 模块内删除确认临时提升到编辑弹窗（3200）之上，结束后清理层级类。
    assert 'confirmModal?.classList.add("rsp-confirm-above-record")' in source
    assert 'confirmModal?.classList.remove("rsp-confirm-above-record")' in source
    assert "#confirmModal.rsp-confirm-above-record" in css
    confirm_rule = css.split("#confirmModal.rsp-confirm-above-record {", 1)[1].split("}", 1)[0]
    assert "z-index: 3300;" in confirm_rule


def test_structured_editor_persists_stable_item_ids_for_audit_matching():
    source = read("components/structured_content_editor.js")

    assert "createItemId" in source
    assert "item_id: table.itemId" in source
    assert "item_id: condition.itemId" in source
    assert "item_id: field.itemId" in source


def test_metadata_picker_contract():
    source = read("components/metadata_picker.js")
    assert "openMetadataPicker" in source
    assert "fetchPage" in source
    # 后端搜索 + 后端分页，不整库加载
    assert "上一页" in source and "下一页" in source
    assert "加载中…" in source
    assert "已添加" in source
    assert "selectMode" in source
    assert "if (event.target === shell)" not in source


def test_drawer_switches_between_structured_and_legacy_modes():
    drawer = read("components/record_drawer.js")
    assert 'import { createStructuredContentEditor } from "./structured_content_editor.js"' in drawer
    assert "const useStructured = creating || Boolean(recordStructured)" in drawer
    assert "createStructuredContentEditor(documentRef" in drawer
    # 历史手工记录保留分组录入路径（方案 A 兼容）
    assert "createTableFieldGroups(documentRef" in drawer
    assert "structuredEditor ? structuredEditor.getStructured() : null," in drawer
    assert "structured_content" in drawer
    # 正式保存才要求字段级修改前/后；草稿可空
    assert "validateForm({ formal: true })" in drawer
    assert "validateForm({ formal: false })" in drawer
    # 脚本预览由前端纯函数渐进生成，不复用或放宽正式保存校验。
    assert 'import { buildScriptPreview } from "./script_preview.js"' in drawer
    assert "buildScriptPreview(" in drawer
    assert "actions.generateScript(" not in drawer
    assert "validateForm({ formal: true, focus: false })" not in drawer
    assert 'fields.period.addEventListener("change", scheduleAutoGenerate);' in drawer
    assert "function validateForm({ formal = false, focus = true } = {})" in drawer
    assert "function showFormHint(message, focusControl = null, { focus = true } = {})" in drawer
    assert "if (focus) focusControl?.focus?.();" in drawer
    assert 'documentRef, "手动编辑", "rsp-button-secondary", null,' in drawer
    assert drawer.count('manualEditButton.addEventListener("click"') == 1
    # 结构化模式不再渲染全局修改前/后
    assert "rsp-sc-field" in drawer
    # 审计标签补充数据源
    assert 'datasource_name_snapshot: "数据源"' in drawer


def test_ledger_change_columns_align_and_group_exact_value_pairs():
    table = read("components/record_table.js")
    css = read("styles.css")
    assert 'className: "rsp-change-grid-cell"' in table
    assert 'className: "rsp-change-grid-row"' in table
    assert 'className: "rsp-change-grid-item rsp-change-grid-field"' in table
    assert 'className: "rsp-change-grid-item rsp-change-grid-value"' in table
    assert '"修改字段", "修改前", "修改后"' in table
    assert "变更摘要" not in table
    assert "rsp-change-index" not in table
    assert 'role: "row"' not in table
    assert 'const key = JSON.stringify([before, after]);' in table
    assert "deduplicateFieldParts" in table
    assert "groups.length === 1" in table
    assert "is-stacked" in table
    assert "rsp-record-row" in table
    assert "rowspan" not in table
    assert 'colspan: "3"' in table
    assert "rsp-change-field-list" in table
    assert "structuredFieldParts" in table
    assert "fieldLabelTextNode" in table
    assert "rsp-change-field-name" in table
    assert "title: parts.english" not in table
    assert "rsp-change-field-english" not in table
    assert "rsp-change-field-english" not in css
    assert ".rsp-change-paired-grid" not in css
    assert ".rsp-change-table-name" not in css
    assert ".rsp-change-field-list" in css
    assert ".rsp-business-system" in css


def test_structured_and_picker_styles_are_scoped():
    css = read("styles.css")
    for selector in (
        ".rsp-sc-editor", ".rsp-sc-tbl-head", ".rsp-sc-tbl-row", ".rsp-sc-field-head",
        ".rsp-sc-field-row", ".rsp-sc-fields-area", ".rsp-sc-combo", ".rsp-sc-combo-panel",
        ".rsp-sc-combo-option", ".rsp-sc-ds-select",
        ".rsp-picker-overlay", ".rsp-picker", ".rsp-picker-row", ".rsp-picker-check",
    ):
        assert f".auto-check-module[data-module=\"report_special_processing\"] {selector}" in css


def test_new_record_drawer_matches_compact_reason_and_structured_content_layout():
    drawer = read("components/record_drawer.js")
    editor = read("components/structured_content_editor.js")
    css = read("styles.css")

    # 处理摘要使用默认 56px 多行控件。
    assert 'className: "rsp-summary",\n      rows: "3",' in drawer
    assert '"aria-label": "处理摘要"' in drawer
    summary_rule = css.split(
        '.auto-check-module[data-module="report_special_processing"] .rsp-summary {', 1
    )[1].split("}", 1)[0]
    assert "height: 56px;" in summary_rule
    assert "min-height: 56px;" in summary_rule

    # 特殊处理内容采用截图中的宽弹窗、标题行添加处理表、分层处理范围和修改字段区。
    modal_rule = css.split(
        '.auto-check-module[data-module="report_special_processing"] .rsp-record-modal {', 1
    )[1].split("}", 1)[0]
    assert "calc(100vw - 72px)" in modal_rule
    assert "900px" in modal_rule
    assert 'className: "rsp-modal-section rsp-special-content-section"' in drawer
    # 添加操作已移至行尾图标按钮，标题栏不再有添加按钮
    assert editor.count("rsp-sc-add-action") == 1  # 仅表级添加保留
    assert editor.count("rsp-sc-header-action") == 1  # 仅表级操作区保留
    assert editor.count('className: "rsp-sc-section-head ') == 2
    assert 'text: "＋ 添加处理表"' in editor
    assert 'text: "指定数据日期"' in editor
    assert 'text: "修改字段"' in editor
    for selector in (".rsp-special-content-section", ".rsp-sc-scope", ".rsp-sc-fields-area"):
        assert f'.auto-check-module[data-module="report_special_processing"] {selector}' in css

    # 行级操作：左对齐 [-] / [-][+]，使用 Minus/Plus 图标，无假占位
    assert "rsp-sc-row-actions" in editor
    assert "rsp-sc-icon-btn" in editor
    assert "rsp-sc-icon-add" in editor
    assert "rsp-sc-icon-minus" in editor
    assert "rsp-sc-action-slot" not in editor
    assert "ICON_MINUS" in editor
    assert "ICON_PLUS" in editor
    # 删除“操作”表头文字
    assert 'text: "操作"' not in editor
    # 表级删除按钮位于标题前，单表隐藏
    title_bar = editor.split('className: "rsp-sc-card-title" }', 1)[1].split("]);", 1)[0]
    assert title_bar.index("removeButton") < title_bar.index("titleIndex")
    assert "table.removeButton.hidden = !visible;" in editor

    # 一个处理表只保留一个外层卡片，内部区块以浅分割线和留白建立层级。
    for selector in (".rsp-sc-scope", ".rsp-sc-fields-area"):
        rule = css.split(
            f'.auto-check-module[data-module="report_special_processing"] {selector} {{', 1
        )[1].split("}", 1)[0]
        assert "border: 0;" in rule
        assert "border-top: 1px solid" in rule
        assert "border-radius: 0;" in rule
    date_rule = css.split(
        '.auto-check-module[data-module="report_special_processing"] .rsp-sc-date-label {', 1
    )[1].split("}", 1)[0]
    assert "font-size: 12px;" in date_rule
    assert "font-weight: 400;" in date_rule

    # 三组内容使用明确 Grid，并共享固定 52px 紧凑操作列及 12px 列间距。
    assert "--action-width: 52px;" in css
    assert "minmax(180px, 0.9fr) minmax(260px, 1.3fr) minmax(240px, 1.15fr) var(--action-width)" in css
    assert "minmax(170px, 1.05fr) minmax(170px, 1.05fr) minmax(140px, 0.85fr) minmax(140px, 0.85fr) var(--action-width)" in css
    assert "column-gap: 12px;" in css
    action_rule = css.split(
        '.auto-check-module[data-module="report_special_processing"] .rsp-sc-header-action {', 1
    )[1].split("}", 1)[0]
    assert "width: var(--action-width);" in action_rule
    assert "flex: 0 0 var(--action-width);" in action_rule
    assert "justify-content: flex-end;" in action_rule

    # 单张处理表内边距统一为 16px，内部仅保留指定浅分割线。
    card_rule = css.split(
        '.auto-check-module[data-module="report_special_processing"] .rsp-sc-card {', 1
    )[1].split("}", 1)[0]
    assert "padding: 16px;" in card_rule
    assert css.count("border-top: 1px solid #eef1f5;") >= 2

    # 自动识别失败或不唯一时，日期字段使用当前表真实字段的行内可搜索选择器。
    assert "const periodFieldCombo = makeCombo({" in editor
    assert 'placeholder: "请选择数据日期字段"' in editor
    assert 'periodFieldCombo.shell.classList.add("rsp-sc-date-field-picker")' in editor
    assert "periodFieldCombo.shell.hidden = !show" in editor
    assert 'table.reportPeriodFieldSource !== "AUTO"' in editor
    assert "&& !table.reportPeriodField" not in editor
    assert 'table.reportPeriodFieldSource = "MANUAL"' in editor
    assert 'className: "rsp-sc-scope-controls"' in editor
    assert "function columnDisplayLabel(item)" in editor
    assert 'periodFieldCombo.input.value = columnDisplayLabel(item);' in editor
    assert "return tableColumnDisplayLabel(table, table.reportPeriodField);" in editor
    assert "rsp-sc-rp-field-row" not in editor
    assert 'text: "报送期字段"' not in editor
    assert "未能自动匹配到报送期字段，请输入" not in editor

    # 日期字段选择器与条件值列严格同列：标题行复用条件行完全相同的四列 Grid，
    # 除以栅格外不得使用 margin/transform/absolute 手工偏移。
    scope_main_rule = css.split(
        '.auto-check-module[data-module="report_special_processing"] .rsp-sc-scope-title-row .rsp-sc-section-head-main {', 1
    )[1].split("}", 1)[0]
    assert "display: grid;" in scope_main_rule
    assert (
        "grid-template-columns: minmax(180px, 0.9fr) minmax(260px, 1.3fr) "
        "minmax(240px, 1.15fr) var(--action-width);" in scope_main_rule
    )
    # 与条件行单行模板完全一致（含固定操作列），并铺满卡片宽度。
    cond_template = (
        "minmax(180px, 0.9fr) minmax(260px, 1.3fr) minmax(240px, 1.15fr) var(--action-width)"
    )
    cond_rule = css.split(
        '.auto-check-module[data-module="report_special_processing"] .rsp-sc-cond-head,\n'
        '.auto-check-module[data-module="report_special_processing"] .rsp-sc-cond-row {', 1
    )[1].split("}", 1)[0]
    assert cond_template in cond_rule
    assert cond_template in scope_main_rule
    assert "column-gap: 12px;" in scope_main_rule
    assert "width: 100%;" in scope_main_rule
    controls_rule = css.split(
        '.auto-check-module[data-module="report_special_processing"] .rsp-sc-scope-controls {', 1
    )[1].split("}", 1)[0]
    assert "grid-column: 1 / 3;" in controls_rule
    # 控件行与 32px 表单等高：选择器显示/隐藏都不改变标题行高度与位置。
    assert "min-height: 32px;" in controls_rule
    picker_rule = css.split(
        '.auto-check-module[data-module="report_special_processing"] .rsp-sc-date-field-picker {', 1
    )[1].split("}", 1)[0]
    assert "grid-column: 3;" in picker_rule
    assert "width: 100%;" in picker_rule
    assert "min-width: 0;" in picker_rule
    # 禁止用固定宽度或手工偏移凑位置。
    assert "margin-left" not in picker_rule
    assert "transform" not in picker_rule
    assert "position: absolute" not in picker_rule


def test_row_action_icons_follow_semantic_colors():
    css = read("styles.css")
    scope = '.auto-check-module[data-module="report_special_processing"]'

    # 添加（＋）默认主题蓝、hover 浅蓝底；删除（－）默认 danger 红、hover 加深并配极浅红底。
    add_rule = css.split(f"{scope} .rsp-sc-icon-add {{", 1)[1].split("}", 1)[0]
    assert "var(--rsp-brand)" in add_rule
    add_hover = css.split(f"{scope} .rsp-sc-icon-add:hover:not(:disabled) {{", 1)[1].split("}", 1)[0]
    assert "background:" in add_hover

    minus_rule = css.split(f"{scope} .rsp-sc-icon-minus {{", 1)[1].split("}", 1)[0]
    assert "var(--action-danger" in minus_rule
    assert "#9ca3af" not in minus_rule
    minus_hover = css.split(f"{scope} .rsp-sc-icon-minus:hover:not(:disabled) {{", 1)[1].split("}", 1)[0]
    assert "var(--action-danger" in minus_hover
    assert "background:" in minus_hover

    # 仅剩一条条件/字段时减号是禁用态，不能被通用灰色禁用样式盖掉；
    # 仍使用危险色并降透明度表达不可用。
    disabled_generic = css.index(f"{scope} .rsp-sc-icon-btn:disabled {{")
    disabled_minus = css.index(f"{scope} .rsp-sc-icon-minus:disabled {{")
    assert disabled_minus > disabled_generic, "减号禁用规则必须在通用禁用规则之后才能生效"
    disabled_rule = css.split(f"{scope} .rsp-sc-icon-minus:disabled {{", 1)[1].split("}", 1)[0]
    assert "var(--action-danger" in disabled_rule
    assert "opacity: 0.6;" in disabled_rule

    # 行级操作区：左对齐紧凑操作组（减号为固定锚点、加号仅最后一行追加），无假占位。
    actions_rule = css.split(f"{scope} .rsp-sc-row-actions {{", 1)[1].split("}", 1)[0]
    assert "display: flex;" in actions_rule
    assert "justify-content: flex-start;" in actions_rule
    assert "gap: 4px;" in actions_rule
    assert "width: 52px;" in actions_rule
    assert "grid-template-columns" not in actions_rule
    assert "rsp-sc-action-slot" not in css, "不得保留空占位元素"
    icon_rule = css.split(f"{scope} .rsp-sc-icon-btn {{", 1)[1].split("}", 1)[0]
    assert "border: 0;" in icon_rule
    assert "border-radius: 4px;" in icon_rule
    assert "width: 28px;" in icon_rule
    assert "height: 28px;" in icon_rule
    editor = read("components/structured_content_editor.js")
    assert "ICON_MINUS" in editor
    assert "ICON_TRASH" in editor
    assert "removeBtn.innerHTML = ICON_MINUS;" in editor


def test_record_metadata_backend_surface():
    from pathlib import Path

    package = Path(__file__).resolve().parents[3] / "src/auto_check/modules/report_special_processing"
    storage = (package / "storage.py").read_text(encoding="utf-8")
    assert 'Column("datasource_id", String(64))' in storage
    assert 'Column("structured_content_json", Text)' in storage
    assert 'result["structured_content"] = structured' in storage
    service = (package / "service.py").read_text(encoding="utf-8")
    assert "metadata_service" in service
    assert "_pin_datasource" in service
    assert "list_datasource_tables" in service
    api = (package / "api.py").read_text(encoding="utf-8")
    assert '"/datasources/{datasource_id}/tables"' in api
    assert '"/datasources/{datasource_id}/tables/{table_name}/columns"' in api
    metadata = (package / "metadata.py").read_text(encoding="utf-8")
    assert "information_schema" in metadata
    assert "pg_description" in metadata
    assert "load_data_sources" in metadata
    assert "数据源连接失败，请检查数据源配置" in metadata or "DataSourceConnectionError" in metadata


def test_plain_change_columns_have_no_inner_grid_or_decorative_summary_styles():
    css = read("styles.css")
    scope = '.auto-check-module[data-module="report_special_processing"] '
    assert ".rsp-change-table-head" not in css
    assert ".rsp-change-index" not in css
    assert ".rsp-change-table-name" not in css
    assert scope + ".rsp-ledger-table th:not(:last-child)" not in css
    assert scope + ".rsp-ledger-table td:not(:last-child)" not in css
    assert "border-right: 1px solid #e4eaf2;" not in css
    grid = css.split(scope + ".rsp-change-grid {", 1)[1].split("}", 1)[0]
    assert "grid-template-columns: 26fr 11fr 11fr;" in grid
    assert "row-gap: 10px;" in grid
    fields = css.split(scope + ".rsp-change-grid-item {", 1)[1].split("}", 1)[0]
    assert "text-align: center;" in fields
    assert "align-items: center;" in fields
    assert "justify-content: center;" in fields
    assert "white-space: pre-wrap;" in fields
