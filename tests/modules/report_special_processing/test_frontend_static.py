from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "src" / "auto_check" / "modules" / "report_special_processing" / "web"


def read(name: str) -> str:
    return (WEB / name).read_text(encoding="utf-8")


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
    ):
        assert endpoint in source
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
    assert "涉及报表" in source
    assert "处理摘要" in source
    assert "特殊处理时间" in source
    assert "createProcessMultiSelect" in read("components/record_drawer.js")
    assert "report_process_codes" in read("components/record_drawer.js")
    assert "rsp-multi-select" in read("styles.css")
    assert 'type: "checkbox"' not in read("components/process_multi_select.js")
    assert "is-selected" in read("components/process_multi_select.js")
    assert "rsp-process-field" in read("components/record_drawer.js")
    assert 'labeledField(documentRef, "关联报送"' in read("components/record_drawer.js")
    assert "rsp-span-two rsp-process-field" not in read("components/record_drawer.js")
    drawer = read("components/record_drawer.js")
    assert 'labeledField(documentRef, "特殊处理时间"' not in drawer
    assert "nowHandlingAt" in drawer
    assert 'labeledField(documentRef, "所处报送期", fields.period)' in drawer
    assert 'labeledField(documentRef, "处理人", fields.handler)' in drawer
    assert "rsp-form-grid-basic" in drawer
    assert "defaultHandlerId" in drawer
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
    assert "--select-height: 32px !important" in css
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
    assert "SUMMARY_MAX_LENGTH = 25" in source
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
    assert "overflow-x: auto" in css.split(".rsp-audit-table-wrap", 1)[1].split(".rsp-audit table", 1)[0]
    assert "scrollbar-width: thin" in css.split(".rsp-audit-table-wrap", 1)[1].split(".rsp-audit table", 1)[0]
    assert "height: 6px" in css.split(".rsp-audit-table-wrap", 1)[1].split(".rsp-audit table", 1)[0]
    for moved in ("开始处理", "转为待处理", "完成", "作废", "重开", "操作原因", "completeRecord", "voidRecord", "reopenRecord"):
        assert moved not in source
    assert "row_version" in source
    assert "catalogAvailable" in source
    assert "disabled" in source
    assert 'aria-modal": "true"' in source
    assert "rsp-record-modal-overlay" in source
    assert "收起详情" not in source
    assert "Escape" in source
    assert "if (event.target === overlay) onClose()" not in source


def test_ledger_row_actions_include_status_operations():
    table_source = read("components/record_table.js")
    ledger_source = read("pages/ledger.js")
    css = read("styles.css")

    for label in ("编辑", "查看", "完成", "作废", "删除"):
        assert label in table_source
    for removed in ("开始处理", "转为待处理", "重开"):
        assert removed not in table_source
        assert removed not in ledger_source
    assert "buildRowActions" in table_source
    assert "onAction" in table_source
    assert 'onClick: () => onOpen(record, row)' not in table_source
    assert 'if (event.key === "Enter") onOpen(record, row)' not in table_source
    assert "handleRowAction" in ledger_source
    assert 'await confirm("确认完成"' in ledger_source or 'confirm("确认完成"' in ledger_source
    assert 'confirm("确认作废"' in ledger_source
    assert 'confirm("确认删除"' in ledger_source
    assert "删除后不可恢复" in ledger_source
    assert "deleteRecord" in read("api.js")
    assert 'action === "delete"' in ledger_source
    assert 'confirm("确认将该记录标记为已完成吗？")' not in ledger_source
    assert 'confirm("确认作废该记录吗？作废后仍保留完整留痕。")' not in ledger_source
    assert 'action === "complete"' in ledger_source
    assert 'action === "start"' not in ledger_source
    assert 'action === "pend"' not in ledger_source
    assert 'action === "reopen"' not in ledger_source
    assert "rsp-row-actions" in table_source
    assert "rsp-row-actions-inner" in table_source
    assert ".rsp-row-actions-inner" in css
    assert "rsp-text-action-danger" in css
    assert "rsp-text-action-success" in css
    assert 'width: 14%' in css
    assert "padding-left: 28px" in css


def test_ledger_table_empty_state_and_list_layout_align_with_system_lists():
    table_source = read("components/record_table.js")
    ledger_source = read("pages/ledger.js")
    css = read("styles.css")
    scope = '.auto-check-module[data-module="report_special_processing"]'

    assert 'className: "rsp-empty-row"' in table_source
    assert 'colspan: "7"' in table_source
    assert "没有符合条件的特殊处理记录" in table_source
    assert "wrap.append(element(documentRef, \"div\", { className: \"rsp-empty\"" not in table_source
    assert "formatDisplayDateTime" in table_source
    assert "formatDisplayDateTime(record.special_handling_at)" in table_source
    assert 'replace("T", " ")' in table_source
    assert "reportNamesCell" in table_source
    assert "rsp-report-name-line" in table_source
    assert "rsp-report-names-block" in table_source
    assert "summaryCell" in table_source
    assert "rsp-summary-text" in table_source
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
    assert "max-height: calc(13px * 1.55 * 3)" in css
    assert "const maxLines = 7" in table_source
    assert "names.length > 3" in table_source
    assert "rsp-report-names-block" in table_source
    assert ".rsp-report-names-block.is-compact" in css
    assert "${name}等" in table_source
    assert "names.slice(0, 3)" not in table_source.split("function processNamesCell")[1].split("function summaryCell")[0]
    assert "${name}等" not in table_source.split("function processNamesCell")[1].split("function summaryCell")[0]
    assert "rsp-process-names-block" in table_source
    assert "is-compact" in table_source
    assert "names.length > 3" in table_source
    assert "fitProcessNameNodes" not in table_source
    assert "is-compact" in css
    assert "font-size: 12px" in css
    assert "scheduleProcessNameFit" not in table_source
    assert "rsp-cell-fit" not in table_source
    assert '(record.reports || []).join("、")' not in table_source
    assert '["处理摘要", "关联报送", "涉及报表", "特殊处理时间", "处理人", "状态", "操作"]' in table_source
    assert "th:nth-child(1) { width: 22%; }" in css
    assert "th:nth-child(2) { width: 13%; }" in css
    assert "td.rsp-process-names" in css
    assert "td.rsp-report-names" in css
    assert "td.rsp-summary" in css
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
    assert "rsp-cell-clamp" not in css
    assert "-webkit-line-clamp" not in css
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
    assert "padding-left: 28px" in css
    assert "padding-right: 20px" in css
    assert "\nbutton {" not in css
    assert "\ntable {" not in css
    assert "\ninput {" not in css


def test_module_css_is_scoped_light_only_and_keeps_centered_modal():
    css = read("styles.css")
    scope = '.auto-check-module[data-module="report_special_processing"]'

    assert scope in css
    for forbidden in ("\nbutton {", "\ninput {", "\ntable {", "prefers-color-scheme", "dark-mode", "text-shadow"):
        assert forbidden not in css
    assert "position: fixed" in css
    assert "rsp-record-modal-overlay" in css
    assert "rsp-record-modal" in css
    assert "width: clamp(720px, 70vw, 860px)" in css
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
