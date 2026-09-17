from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "src" / "auto_check" / "modules" / "dashboard_management" / "web"


def _read(relative: str) -> str:
    return (WEB / relative).read_text(encoding="utf-8")


def test_module_structural_surfaces_follow_the_platform_surface_hierarchy() -> None:
    css = _read("styles.css")
    root = css.split(
        '.auto-check-module[data-module="dashboard_management"] {', 1
    )[1].split("}", 1)[0]

    for declaration in (
        "--dm-border: var(--ui-content-border, var(--outline-variant, #dfe6f1));",
        "--dm-surface: var(--ui-panel-surface, var(--surface-container-lowest, #ffffff));",
        "--dm-subtle: var(--ui-subsection-surface, var(--surface-container-low, #f1f4f6));",
        "--dm-disabled: var(--ui-disabled-surface, var(--surface-container, #ebeef0));",
        "background: transparent;",
    ):
        assert declaration in root

    neutral_hardcoded_backgrounds = {
        "#fff",
        "#ffffff",
        "#fafbfd",
        "#fbfcfe",
        "#f6f8fb",
        "#f4f7fb",
        "#f2f5f9",
        "#f2f4f7",
        "#f1f5fa",
        "#f0f4fa",
        "#f0f2f5",
    }
    backgrounds = {
        value.lower()
        for value in re.findall(
            r"background(?:-color)?\s*:\s*(#[0-9a-fA-F]{3,8})\b", css
        )
    }
    assert backgrounds.isdisjoint(neutral_hardcoded_backgrounds)


def test_dashboard_management_frontend_has_required_contract_and_copy() -> None:
    index = _read("index.js")
    tabs = _read("components/dashboard_tabs.js")
    source_editor = _read("components/source_editor.js")
    preview = _read("components/preview_table.js")

    for name in ("mount", "activate", "deactivate", "unmount"):
        assert f"export function {name}" in index
    assert "金融监管报表报送大屏" in tabs
    assert "金融监管报送流程大屏" in tabs
    assert "个数据区域" not in tabs
    assert "接口数据" in tabs
    assert "看板页面" in tabs
    assert 'button("看板页面", "dm-tab-preview-item"' in tabs
    assert 'button("看板页面", "dm-tab-preview-item", () => {}, { disabled: true })' not in tabs
    assert "previewBoard" in _read("api.js")
    assert "openBoardPreviewDialog" in index
    assert "正在读取接口数据" in _read("components/board_preview_dialog.js")
    assert "openBoardScreenPreviewDialog" in _read("components/board_preview_dialog.js")
    assert "dm-board-screen-frame" in _read("components/board_preview_dialog.js")
    assert "deleteRegion" in _read("api.js")
    assert "删除区域" in _read("components/catalog_dialog.js")
    assert "context.confirm" in index
    assert "force: true" in index and "openManageRegionDialog" in index
    assert "新增数据区域" in _read("components/region_list.js")
    assert "新增字段" in _read("components/catalog_dialog.js")
    assert "测试执行" in source_editor
    assert "预览系统数据" in source_editor
    assert "系统生成 SQL" in source_editor
    assert "来源功能" in source_editor
    assert "数据表" not in source_editor
    assert "table_details" not in source_editor
    assert "fieldLabels" in preview
    assert "field.name" in preview
    assert "renderPreviewTable(draft.preview, draft.source_mode, region.fields || [])" in index
    assert "保存配置" in index
    assert "基本信息" not in index
    assert "dm-region-context" in index
    assert "该 SQL 由系统按当前指标自动生成" not in source_editor
    assert "结果预览（前 10 行）" in preview
    assert "context.api" in _read("api.js")
    assert "previewSystem" in _read("api.js")
    assert "编辑" in _read("components/region_list.js")
    assert "已停用" in _read("components/catalog_dialog.js")
    assert "aria-labelledby" in _read("components/catalog_dialog.js")
    assert "addEventListener(\"keydown\"" in _read("components/catalog_dialog.js")
    assert "updateRegion" in _read("api.js")
    assert "dm-region-enabled-switch" in index
    assert 'enabledSwitch.setAttribute("role", "switch")' in index
    assert 'enabledSwitch.setAttribute("aria-checked", region.enabled === false ? "false" : "true")' in index
    manage_dialog = _read("components/catalog_dialog.js").split("export function openManageRegionDialog", 1)[1].split("export function openFieldDialog", 1)[0]
    assert 'labeledControl("启用区域"' not in manage_dialog
    assert "enabled: enabled.checked" not in manage_dialog
    assert 'form.append(nameControl, labeledControl(builtIn ? "数据形态（系统固定）" : "数据形态", shape), descriptionControl)' in manage_dialog
    assert "revision" in _read("state.js")
    assert "wasSystem" in index
    assert "已切换为自定义 SQL，需由一条 SQL 返回全部启用字段" in index
    assert "aria-controls" in tabs
    assert 'role: "tabpanel"' in index
    assert "api.createField(created.id" not in index
    assert "首批字段别名不能重复" in _read("components/catalog_dialog.js")
    assert "dm-panel-${board.code}" in tabs
    assert "hidden" in index and 'role: "tabpanel"' in index
    assert "if (recordPreview(state, token, preview))" in index
    assert "if (markSaved(state, token, saved))" in index
    assert 'draft.source_mode === "sql" && draft.testStatus !== "passed"' not in index
    assert 'nextDraft?.source_mode === "sql" && nextDraft?.testStatus !== "passed"' not in index
    assert "查询 SQL 可直接保存，测试仅用于预览和校验结果" in index


def test_external_api_token_dialog_is_single_use_scoped_and_cleared_on_exit() -> None:
    index = _read("index.js")
    state = _read("state.js")
    dialog = _read("components/external_api_token_dialog.js")

    assert "pendingToken" not in state
    assert "pendingToken" not in index
    assert "activeTokenDialog?.close()" in index
    assert "host.appendChild(overlay)" in dialog
    assert "document.body.appendChild(overlay)" not in dialog
    assert 'class: `${CLASS_ROOT}__title`' in dialog
    assert 'tokenInput.value = ""' in dialog
    assert "secret = \"\"" in dialog
    assert 'if (event.target === overlay) close();' not in dialog


def test_region_dialog_save_targets_the_dialog_region_instead_of_the_selected_region() -> None:
    index = _read("index.js")

    save_region = re.search(
        r"const saveRegion = async \(targetRegion, boardCode, generation, payload, successText = \"区域配置已保存\"\) => \{(?P<body>.*?)\n  \};",
        index,
        re.DOTALL,
    )

    assert save_region is not None
    assert "await api.updateRegion(targetRegion.id, payload)" in save_region.group("body")
    assert "captureRequest(state)" not in save_region.group("body")
    assert "onSave: (payload) => saveRegion(region, boardCode, generation, payload)" in index


def test_copied_dashboard_pages_use_only_dashboard_management_preview_api() -> None:
    report = _read("screens/financial-report.html")
    process = _read("screens/financial-report-flow.html")

    assert "金融监管报表报送大屏" in report
    assert "金融监管报表报送流程大屏" in process
    assert "/jsxt/" not in report and "/jsxt/" not in process
    assert "/api/modules/dashboard-management/boards/report_submission/preview" in report
    assert "/api/modules/dashboard-management/boards/reporting_process/preview" in process
    for region_code in (
        "annual_supplement_completed", "monthly_report_validation_remaining", "monthly_trust_projects",
        "report_reconciliation_completion_time", "report_validation_issue_handling", "quarterly_special_processing",
        "monthly_report_submission_time_comparison",
    ):
        assert region_code in report
    for region_code in (
        "regulatory_report_count", "monthly_regulatory_report_time", "report_validation_statistics",
    ):
        assert region_code in process
    assert "value: row.reconciliation_completed_time" in report
    assert "value: row.reconciliation_completed_at" not in report
    assert "payload?.data?.data_year" in report
    assert "/api/external/" not in report and "/api/external/" not in process
    assert report.count("/api/modules/dashboard-management/boards/report_submission/preview") == 1
    assert process.count("/api/modules/dashboard-management/boards/reporting_process/preview") == 1


def test_copied_dashboard_pages_match_kanban_dynamic_chart_and_date_display() -> None:
    report = _read("screens/financial-report.html")
    process = _read("screens/financial-report-flow.html")

    assert "function submissionGroupX(index, count)" in report
    assert "const x = submissionGroupX(index, data.length);" in report
    assert "const x = submissionGroupX(index, data.length) + 22;" in report
    assert "const xPositions = [96, 238, 380, 522, 664, 806];" not in report

    assert "function reportCountBarX(index, count)" in process
    assert "const x = reportCountBarX(index, data.length);" in process
    assert "const x = 25 + index * 50;" not in process
    assert "function reportTypeLines(value)" in process
    assert "function appendReportTypeLabel(group, value, x)" in process
    assert "appendReportTypeLabel(group, row.report_type, x + 8);" in process
    assert "y: Math.max(4, 149 - height)" in process
    assert "y: Math.max(10, 149 - height)" not in process
    assert "function formatReportingDate(value)" in process
    assert "formatReportingDate(row[valueAlias])" in process


def test_dashboard_tabs_are_compact_and_preview_only_the_active_board() -> None:
    tabs = _read("components/dashboard_tabs.js")
    dialog = _read("components/board_preview_dialog.js")
    css = _read("styles.css")

    assert "dm-tab-switches" in tabs
    assert "预览当前看板" in tabs
    assert "const activeBoard = boards.find" in tabs
    assert 'onPreview(activeBoard, "data", trigger)' in tabs
    assert 'onPreview(activeBoard, "screen", trigger)' in tabs
    assert tabs.count("dm-tab-preview-trigger") == 1
    assert 'button("", "dm-tab-action-button dm-tab-preview-trigger"' in tabs
    assert 'button("接口监控", "dm-tab-action-button dm-tab-monitor"' in tabs
    assert '"dm-button dm-button-secondary dm-tab-monitor"' not in tabs
    assert "dm-tab-preview-label" in tabs
    assert "dm-tab-preview-chevron" in tabs
    assert 'text: "⌄"' not in tabs
    assert 'const actions = node("div", { className: "dm-tab-actions" });' in tabs
    assert "actions.append(preview)" in tabs
    assert "actions.append(monitorBtn)" in tabs
    assert "toolbar.append(actions)" in tabs
    assert "toolbar.append(preview)" not in tabs
    assert "toolbar.append(monitorBtn)" not in tabs
    assert '.querySelector?.(\'.dm-tab[aria-selected="true"]\')' in dialog
    assert ".dm-tabs {" in css and "min-height: 46px;" in css
    assert "padding: 0 18px 0 0;" in css
    assert ".dm-tab-switches {" in css
    assert ".dm-tab.is-active {" in css and "inset 0 -3px 0 var(--dm-brand)" in css
    assert ".dm-tab-action-button {" in css and "align-items: center;" in css
    assert "min-height: 32px;" in css and "font-size: 12px;" in css and "font-weight: 400;" in css
    assert "border-right: 1px solid currentColor;" in css
    assert "translateY(-2px) rotate(45deg)" in css
    assert ".dm-tab-preview-menu {" in css and "top: 100%;" in css
    assert ".dm-tab-actions {" in css and "margin-left: auto;" in css


def test_dashboard_management_styles_are_fully_scoped_and_use_light_theme_tokens() -> None:
    css = _read("styles.css")
    scope = '.auto-check-module[data-module="dashboard_management"]'

    assert css.lstrip().startswith(scope)
    assert "--ui-radius" in css
    assert "#3466D9" in css and "#6AA4FF" in css
    assert "--dm-border: #d7dee9" not in css
    assert "--dm-divider: #edf0f5" not in css
    assert "--dm-divider: color-mix(in srgb, var(--outline-variant" in css
    assert "[data-theme" not in css
    for forbidden in ("\nbutton {", "\ninput {", "\ntable {", "\n.card {"):
        assert forbidden not in css
    for line in css.splitlines():
        stripped = line.strip()
        if stripped and "{" in stripped and not stripped.startswith(("@", "/*", "--")):
            selector = stripped.split("{", 1)[0].strip()
            assert scope in selector, f"unscoped selector: {selector}"
    assert ".dm-preview-table th" in css and "text-align: center;" in css
    assert ".dm-preview-table td" in css and "vertical-align: middle;" in css


def test_dashboard_content_is_one_system_card_with_clipped_radius_and_hover_outline() -> None:
    index = _read("index.js")
    css = _read("styles.css")

    assert 'className: "dm-management-card"' in index
    assert "shell.append(" in index
    assert "context.root.append(shell);" in index
    assert ".dm-management-card {" in css
    assert "border: 1px solid var(--outline-variant" in css
    assert "border-radius: var(--ui-radius);" in css
    assert "background: var(--surface-container-lowest" in css
    assert "overflow: hidden;" in css
    assert ".dm-management-card:hover {" in css
    assert "border-color: color-mix(in srgb, var(--theme-accent) 36%, var(--outline-variant))" in css
    hover_rule = css.split(".dm-management-card:hover {", 1)[1].split("}", 1)[0]
    assert "box-shadow" not in hover_rule
    assert "transform" not in hover_rule
    assert ".dm-tabs { width: 100%;" in css and "border: 0;" in css
    assert ".dm-layout { flex: 1 1 auto;" in css and "border: 0;" in css


def test_sql_input_updates_draft_without_re_rendering_the_page() -> None:
    index = _read("index.js")
    source_editor = _read("components/source_editor.js")

    assert "onSql: (value) => invalidateDraftView(markSqlChanged(state, value))" in index
    assert "onSql: (value) => { markSqlChanged(state, value); render(); }" not in index
    assert "const nextDraft = onSql(sqlText.value)" in source_editor
    assert "syncTestState(nextDraft || draft)" in source_editor


def test_system_source_layout_avoids_nested_vertical_scrollbar() -> None:
    source_editor = _read("components/source_editor.js")
    css = _read("styles.css")

    assert ".dm-detail { height: auto; min-height: 0; overflow-x: hidden; overflow-y: visible;" in css
    assert ".dm-region-panel { min-height: 0; overflow-y: visible;" in css
    assert ".dm-system-sql { height: 104px; min-height: 104px !important;" in css
    assert 'generatedSqlControl.classList.add("dm-sql-control")' in source_editor
    assert ".dm-sql-text {" in css and "resize: none !important;" in css


def test_custom_sql_controls_align_and_fill_desktop_height() -> None:
    source_editor = _read("components/source_editor.js")
    css = _read("styles.css")

    assert 'datasourceControl.classList.add("dm-datasource-control")' in source_editor
    assert 'sqlControl.classList.add("dm-sql-control")' in source_editor
    assert ".dm-source-choices {" in css and "width: 220px;" in css
    assert ".dm-datasource-control { width: 220px;" in css
    assert ".dm-detail-content { display: flex; flex-direction: column; height: 100%;" in css
    assert ".dm-source-preview-grid { flex: 1 1 auto;" in css
    assert ".dm-sql-control { display: flex; flex: 1 1 auto;" in css


def test_dashboard_management_monitor_page_structure():
    component = _read("components/external_api_monitor.js")
    css = _read("styles.css")
    for class_name in [
        "dm-monitor-page", "dm-monitor-header", "dm-monitor-status-section",
        "dm-monitor-metrics", "dm-management-card", "dm-monitor-filters",
        "dm-monitor-table-wrap", "pagination", "pagination-info",
        "pagination-controls", "page-btn", "page-current", "pagination-jump",
    ]:
        assert class_name in component or class_name in css
    for text in [
        "返回看板管理", "调用方 IP", "近 24 小时调用", "部分成功",
        "平均耗时", "记录保留", "暂无数据", "跳至", "正在加载接口监控",
        "重新加载",
    ]:
        assert text in component
    assert "state.monitorLoading" in component
    assert "state.monitorError" in component
    assert component.count('type: "date"') == 2
    assert 'type: "datetime-local"' not in component
    assert 'className: "pagination-jump"' in component
    assert 'text: "页"' in component
    assert 'attrs: { value: "report_submission" }' in component
    assert 'attrs: { value: "reporting_process" }' in component
    assert 'attrs: { value: "success" }' in component
    assert 'attrs: { value: "partial" }' in component
    assert 'attrs: { value: "error" }' in component
    assert "height: 100%" in css
    assert "min-height: 0" in css
    assert "flex: 1" in css
    assert "var(--ui-radius)" in css
    assert "box-shadow: 0 0" not in css
    assert ".dm-monitor-table-wrap { flex: 1 1 auto; min-width: 0; min-height: 0;" in css
    assert ".dm-monitor-table-wrap { scrollbar-width: thin; scrollbar-color: var(--ui-thin-scrollbar-thumb, #c5d0e0) transparent; }" in css
    assert ".dm-monitor-table-wrap::-webkit-scrollbar { width: var(--ui-thin-scrollbar-size, 6px); height: var(--ui-thin-scrollbar-size, 6px); }" in css
    assert ".dm-monitor-table-wrap::-webkit-scrollbar-thumb { border-radius: 999px; background: var(--ui-thin-scrollbar-thumb, #c5d0e0); }" in css
    assert ".dm-monitor-table-wrap::-webkit-scrollbar-track { background: transparent; }" in css
    assert ".dm-monitor-page { display: flex; width: 100%; min-width: 0;" in css
    assert ".dm-monitor-card { display: flex; width: 100%; min-width: 0;" in css
    assert ".dm-filter-select { width: 190px; flex: none;" in css
    assert ".dm-filter-input { width: 180px; flex: none;" in css
    assert 'managed: "系统生成"' in component
    assert component.index("dm-monitor-ip-whitelist-badge") < component.index("`\u6765\u6e90：${tokenSourceText(summary.token_source)}`")
    assert ".dm-monitor-status-badge { display: inline-flex; align-items: center; height: 24px;" in css
    assert "box-sizing: border-box" in css
    assert 'text: `生成时间：${formatMonitorDateTime(summary.token_generated_at)}`' in component
    assert 'configured ? "更新 Token" : "生成 Token"' in component
    assert '"Token 已配置"' not in component
    assert '"Token 未配置"' not in component
    assert '"轮换 Token"' not in component
    assert "最近调用：" not in component
    assert "最近成功：" not in component
    assert "dm-monitor-status-meta" not in component
    assert 'rotated ? "Token 已更新" : "Token 已生成"' in _read("components/external_api_token_dialog.js")
    assert "生产环境上线后必须重新生成生产 Token" not in _read("components/external_api_token_dialog.js")


def test_external_api_monitor_uses_management_list_layout() -> None:
    component = _read("components/external_api_monitor.js")
    css = _read("styles.css")

    for class_name in [
        "dm-monitor-status-overview",
        "dm-monitor-status-badges",
        "dm-monitor-status-badge",
        "dm-monitor-endpoint-list",
        "dm-monitor-endpoint-row",
        "dm-monitor-filter-field",
        "dm-monitor-filter-actions",
        "management-list-status",
    ]:
        assert class_name in component
    for label in ["看板", "业务状态", "调用方 IP", "开始日期", "结束日期"]:
        assert f'monitorFilterField("{label}"' in component
    assert 'button("重置", "dm-button dm-button-secondary dm-monitor-reset"' in component
    assert 'button("清除"' not in component
    assert 'className: "dm-monitor-endpoint-path"' in component
    assert ".dm-monitor-table th { position: sticky;" in css
    assert ".dm-monitor-status-badge.is-enabled" in css
    assert ".dm-monitor-filter-field {" in css
    assert ".dm-monitor-endpoint-path {" in css
    assert ".dm-monitor-endpoint-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));" in css
    assert ".dm-monitor-table th, .auto-check-module[data-module=\"dashboard_management\"] .dm-monitor-table td { height: 46px; padding: 8px 12px; border-bottom: 1px solid var(--outline-variant); text-align: center;" in css
    assert 'button("◀", "page-btn"' in component
    assert 'button("▶", "page-btn"' in component
    assert 'button("上一页", "page-btn"' not in component
    assert 'button("下一页", "page-btn"' not in component


def test_external_api_ip_whitelist_dialog_contract_and_scope():
    index = _read("index.js")
    api = _read("api.js")
    dialog = _read("components/external_api_ip_whitelist_dialog.js")
    component = _read("components/external_api_monitor.js")
    css = _read("styles.css")
    scope = '.auto-check-module[data-module="dashboard_management"]'

    # 前端 API
    assert "externalApiIpWhitelist: () =>" in api
    assert 'request("/external-api/ip-whitelist")' in api
    assert "updateExternalApiIpWhitelist: (payload) =>" in api
    assert 'body("PUT", payload)' in api

    # 弹窗契约
    assert "export function openIpWhitelistDialog({ host, policy, onSave, onClose })" in dialog
    assert "return { element: overlay, close }" in dialog
    assert 'text: "IP 白名单配置"' in dialog
    assert 'text: "启用 IP 白名单"' in dialog
    assert "IP 地址（每行一个）" in dialog
    assert "未启用时不限制来源 IP。启用后，仅白名单中的 IP 和运行 AutoCheck 的本机可以访问两个外部接口；未填写 IP 时仅允许本机访问。" in dialog
    assert 'closeButton("取消"' in dialog
    assert 'closeButton("保存"' in dialog
    assert 'dm-button dm-button-plain ${CLASS_ROOT}__close' in dialog
    assert "const MAX_ALLOWED_IPS = 100;" in dialog
    assert ".slice(0, MAX_ALLOWED_IPS)" not in dialog
    assert ".filter((line) => line.length > 0)" in dialog
    assert "最多只能配置 100 个 IP 地址，请删除多余地址后再保存。" in dialog
    # 关闭路径绝不触发保存，点击遮罩也不关闭
    assert 'if (event.target === overlay) close();' not in dialog
    assert 'if (event.key === "Escape")' in dialog
    assert "host.appendChild(overlay)" in dialog
    assert "document.body.appendChild(overlay)" not in dialog
    assert "if (saving || closed) return;" in dialog
    assert "await onSave(payload)" in dialog

    # 监控页
    assert "monitorIpWhitelistText" in component
    assert 'return enabled ? `IP 白名单：已启用（${count} 个）` : "IP 白名单：未启用";' in component
    assert '"配置 IP 白名单"' in component
    assert '"dm-button dm-button-secondary dm-monitor-ip-whitelist-action"' in component
    assert "canManageIpWhitelist" in component
    assert "summary.ip_whitelist_enabled" in component

    # 页面装配
    assert 'import { openIpWhitelistDialog } from "./components/external_api_ip_whitelist_dialog.js";' in index
    assert "const canManageIpWhitelist = hasPermission(" in index
    assert '"dashboard_management.external_api_ip_whitelist_manage",' in index
    assert "let activeIpWhitelistDialog = null;" in index
    assert "let ipWhitelistSaveInProgress = false;" in index
    assert "const onConfigureIpWhitelist = async () =>" in index
    assert "await api.externalApiIpWhitelist()" in index
    assert "await api.updateExternalApiIpWhitelist(payload)" in index
    assert 'notify("IP 白名单配置已保存", "success")' in index
    assert 'notify(message(error, "保存 IP 白名单失败"), "error")' in index
    assert "state.monitorSummary = null;" in index
    assert "if (!state.active) return;\n      state.monitorSummary = null;\n      loadMonitorData(captureRequest(state));" in index
    assert "onClose: () => {\n          activeIpWhitelistDialog = null;\n          ipWhitelistSaveInProgress = false;\n        }," in index
    assert "onConfigureIpWhitelist, canManageIpWhitelist" in index
    assert index.count("activeIpWhitelistDialog?.close(); activeIpWhitelistDialog = null; ipWhitelistSaveInProgress = false;") == 2

    # 全局状态不长期保存完整 IP 列表
    state = _read("state.js")
    assert "allowed_ips" not in state
    assert "ipWhitelist" not in state

    # 样式作用域与主题变量
    for class_name in [
        "dm-ip-whitelist-dialog__overlay",
        "dm-ip-whitelist-dialog__dialog",
        "dm-ip-whitelist-dialog__switch",
        "dm-ip-whitelist-dialog__switch-input",
        "dm-ip-whitelist-dialog__hint",
        "dm-ip-whitelist-dialog__textarea",
        "dm-ip-whitelist-dialog__actions",
        "dm-monitor-ip-whitelist-action",
        "dm-monitor-ip-whitelist-badge",
    ]:
        assert f"{scope} .{class_name}" in css
    assert ".dm-ip-whitelist-dialog__textarea { width: 100%;" in css
    assert ".dm-ip-whitelist-dialog__close:hover" in css
    assert "background: var(--surface-container-low);" in css
    assert "var(--ui-radius)" in css
    assert "[data-theme" not in css


def test_dashboard_management_monitor_interactions_expose_loading_without_copy_controls():
    index = _read("index.js")
    component = _read("components/external_api_monitor.js")

    assert "state.monitorLoading = true" in index
    assert "state.monitorError = \"\"" in index
    assert "state.monitorPage = calls.page" in index
    assert "navigator.clipboard" not in index
    assert "onCopy" not in index
    assert "onCopy" not in component
    assert 'button("复制"' not in component
