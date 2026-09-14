from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "src" / "auto_check" / "modules" / "dashboard_management" / "web"


def _read(relative: str) -> str:
    return (WEB / relative).read_text(encoding="utf-8")


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
    assert "dm-tab-preview-label" in tabs
    assert "dm-tab-preview-chevron" in tabs
    assert 'text: "⌄"' not in tabs
    assert '.querySelector?.(\'.dm-tab[aria-selected="true"]\')' in dialog
    assert ".dm-tabs {" in css and "min-height: 46px;" in css
    assert "padding: 0 18px 0 0;" in css
    assert ".dm-tab-switches {" in css
    assert ".dm-tab.is-active {" in css and "inset 0 -3px 0 var(--dm-brand)" in css
    assert ".dm-tab-preview-trigger {" in css and "align-items: center;" in css
    assert "border-right: 1px solid currentColor;" in css
    assert "translateY(-2px) rotate(45deg)" in css
    assert ".dm-tab-preview-menu {" in css and "top: 100%;" in css


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
