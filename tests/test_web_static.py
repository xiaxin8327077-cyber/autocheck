from __future__ import annotations

import re
import subprocess
import textwrap
from pathlib import Path
from zipfile import ZipFile

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "src" / "auto_check" / "web" / "index.html"
APP_JS = ROOT / "src" / "auto_check" / "web" / "app.js"
EXPORT_DETAIL_JS = ROOT / "src" / "auto_check" / "web" / "export_detail.js"
SERVER_PY = ROOT / "src" / "auto_check" / "app" / "server.py"
STYLES_CSS = ROOT / "src" / "auto_check" / "web" / "styles.css"
README_MD = ROOT / "README.md"
PYINSTALLER_SPEC = ROOT / "auto-check.spec"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_reason_filter_contains_all_current_reasons():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)

    assert '<option value="">全部差异类型</option>' in html
    assert "全部预估差异原因" not in html

    for reason in [
        "资产缺失",
        "资产重复",
        "资产差异",
        "负债及权益科目差异",
        "负债及权益科目缺失",
        "负债及权益科目重复",
        "实收本金差异",
        "实收本金缺失",
        "实收本金重复",
        "暂无法确定",
    ]:
        assert f'<option value="{reason}">{reason}</option>' in html

    for detail_reason in [
        "AM标的缺失",
        "FA与AM标的不一致",
        "合同投融资余额为0但FA科目余额不为0",
        "实收信托有误",
    ]:
        assert f'<option value="{detail_reason}">{detail_reason}</option>' not in html

    assert "function differenceReasonMatchesFilter(differenceReason, selectedReason)" in app_js
    assert ".split(/\\s*\\+\\s*/)" in app_js
    assert "function resultMatchesReasonFilter(item, selectedReason)" in app_js
    assert "differenceReasonMatchesFilter(item.difference_reason, selectedReason)" in app_js
    assert "resultMatchesReasonFilter(item, reason)" in app_js
    assert "item.difference_reason === reason" not in app_js


def test_result_list_and_export_do_not_show_difference_direction():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)

    result_table = re.search(r'<table class="result-table">(?P<table>.*?)</table>', html, re.S)
    assert result_table is not None
    assert "差异类型" in result_table.group("table")
    assert "预估差异原因" not in result_table.group("table")
    assert "差异方向" not in result_table.group("table")
    assert "col-direction" not in result_table.group("table")

    render_results = re.search(r"function renderResults\(\) \{(?P<body>.*?)function renderDetails", app_js, re.S)
    assert render_results is not None
    assert "item.direction" not in render_results.group("body")

    export_to_excel = re.search(r"function exportToExcel\(\) \{(?P<body>.*?)exportBtn.addEventListener", app_js, re.S)
    assert export_to_excel is not None
    assert "差异方向" not in export_to_excel.group("body")
    assert "item.direction" not in export_to_excel.group("body")


def test_result_list_and_export_show_valuation_asset_total_before_asset_total():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)

    result_table = re.search(r'<table class="result-table">(?P<table>.*?)</table>', html, re.S)
    assert result_table is not None
    table = result_table.group("table")
    assert table.index("资产合计（估值表）") < table.index("资产合计 (元)")
    assert '<tr><td colspan="9" class="empty">暂无结果</td></tr>' in table

    render_results = re.search(r"function renderResults\(\) \{(?P<body>.*?)function renderDetails", app_js, re.S)
    assert render_results is not None
    render_body = render_results.group("body")
    assert "item.valuation_asset_total" in render_body
    assert render_body.index("item.valuation_asset_total") < render_body.index("item.asset_total")
    assert 'colspan="9"' in render_body

    export_to_excel = re.search(r"function exportToExcel\(\) \{(?P<body>.*?)exportBtn.addEventListener", app_js, re.S)
    assert export_to_excel is not None
    export_body = export_to_excel.group("body")
    assert app_js.index('header: "资产合计（估值表）"') < app_js.index('header: "资产合计"')
    assert "item.valuation_asset_total" in export_body
    assert export_body.index("item.valuation_asset_total") < export_body.index("item.asset_total")


def test_auto_check_no_source_data_empty_state_and_date_box_layout():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert "run-bar-icon" not in html
    assert ".run-bar-icon" not in css
    assert "RESULT_EMPTY_SOURCE" in app_js
    assert "resultEmptyState = noSourceData ? RESULT_EMPTY_SOURCE : \"\";" in app_js
    assert "Boolean(h.no_source_data)" in app_js
    assert "let hideLastRunTimeForNoSourceData = false;" in app_js
    assert "hideLastRunTimeForNoSourceData = true;" in app_js
    assert "if (lastRunTime) lastRunTime.hidden = true;" in app_js
    assert "hideLastRunTimeForNoSourceData = false;" in app_js
    assert "lastRunTime.hidden = Boolean(resultRestoreHistoryMeta) || hideLastRunTimeForNoSourceData;" in app_js
    assert "lastRunTime.textContent && !resultRestoreHistoryMeta && !hideLastRunTimeForNoSourceData" in app_js
    assert "renderSourceNoDataRow" in app_js
    assert "报表对应日期无数据" in app_js
    assert "appendRunLog(noDataMessage)" not in app_js
    assert ".no-source-panel" in css
    assert "@keyframes noSourceScan" in css


def test_cards_hover_glow_tracks_theme_palette_instead_of_dark_shadow():
    css = _read(STYLES_CSS)
    readme = _read(README_MD)

    root_rule = re.search(r"(?m)^:root\s*\{(?P<body>.*?)\}", css, re.S)
    space_theme_rule = re.search(r'(?m)^\[data-theme="space-tech"\]\s*\{(?P<body>.*?)\}', css, re.S)
    assert root_rule is not None
    assert space_theme_rule is not None
    assert "--card-hover-glow: #166534;" in root_rule.group("body")
    assert "--card-hover-shadow: rgba(22, 101, 52" in root_rule.group("body")
    assert "--card-hover-glow: #38bdf8;" in space_theme_rule.group("body")
    assert "--card-hover-shadow: rgba(14, 116, 144" in space_theme_rule.group("body")

    card_hover = re.search(r"(?m)^\.card:hover\s*\{(?P<body>.*?)\}", css, re.S)
    assert card_hover is not None
    card_hover_body = card_hover.group("body")
    assert "border-color: color-mix(in srgb, var(--card-hover-glow)" in card_hover_body
    assert "0 0 0 1px color-mix(in srgb, var(--card-hover-glow)" in card_hover_body
    assert "0 0 24px color-mix(in srgb, var(--card-hover-glow)" in card_hover_body
    assert "var(--card-hover-shadow" in card_hover_body
    assert "#38bdf8" not in card_hover_body
    assert "rgba(0, 0, 0" not in card_hover_body

    settings_card_hover = re.search(r"(?m)^#page-settings \.card:hover\s*\{(?P<body>.*?)\}", css, re.S)
    assert settings_card_hover is not None
    settings_hover_body = settings_card_hover.group("body")
    assert "border-color: color-mix(in srgb, var(--card-hover-glow)" in settings_hover_body
    assert "0 0 24px color-mix(in srgb, var(--card-hover-glow)" in settings_hover_body
    assert "var(--card-hover-shadow-soft)" in settings_hover_body
    assert "transform: none;" in settings_hover_body
    assert "#38bdf8" not in settings_hover_body
    assert "rgba(0, 0, 0" not in settings_hover_body

    for selector in [
        r'\[data-theme="space-tech"\] \.home-stat-card:hover',
        r'\[data-theme="space-tech"\]\[data-color-mode="dark"\] \.home-stat-card:hover',
        r"\.glass-card:hover",
        r'\[data-color-mode="dark"\] \.glass-card:hover',
        r"\.home-stat-card:hover",
        r"\.home-analysis-card:hover",
        r"\.glass-stat-card:hover",
        r"\.tool-card:hover",
        r"\.data-manage-item:hover",
        r"#page-settings \.settings-dashboard-card:hover",
        r'\[data-theme="space-tech"\] #page-settings \.settings-dashboard-card:hover',
        r'\[data-theme="space-tech"\]\[data-color-mode="dark"\] #page-settings \.settings-dashboard-card:hover',
    ]:
        rule = re.search(rf"(?m)^{selector}\s*\{{(?P<body>.*?)\}}", css, re.S)
        assert rule is not None
        rule_body = rule.group("body")
        assert "var(--card-hover-glow)" in rule_body
        assert "#38bdf8" not in rule_body
        assert "rgba(0, 0, 0" not in rule_body
    assert "卡片悬停在活力主题使用淡蓝光晕、沉稳主题使用深绿色柔和光晕" in readme


def test_export_to_excel_includes_processing_script_column_after_detail():
    app_js = _read(APP_JS)

    export_to_excel = re.search(r"function exportToExcel\(\) \{(?P<body>.*?)exportBtn.addEventListener", app_js, re.S)
    assert export_to_excel is not None
    export_body = export_to_excel.group("body")
    assert 'header: "处理脚本"' in app_js
    assert app_js.index('header: "差异原因详情"') < app_js.index('header: "处理脚本"')
    assert "buildProcessingScriptText(item)" in export_body
    assert "function buildProcessingScriptText(item)" in app_js
    assert "window.buildProcessingScript(item)" in app_js
    assert "escapeExcelSingleLineText(buildProcessingScriptText(item))" in export_body


def test_export_to_excel_includes_remark_for_combined_difference_reason():
    app_js = _read(APP_JS)

    export_to_excel = re.search(r"function exportToExcel\(\) \{(?P<body>.*?)exportBtn.addEventListener", app_js, re.S)
    assert export_to_excel is not None
    export_body = export_to_excel.group("body")
    assert '{ header: "备注", width: 220, style: "SpecificReason", type: "string" }' in app_js
    assert "function remarkText(item)" in app_js
    assert "资产端存在多组候选资产均可解释差额" in app_js
    assert "负债及权益端存在多组候选科目均可解释差额" in app_js
    assert "资产端差额已由" in app_js
    assert "资产端差额可归入" in app_js
    assert "解释实收本金部分，剩余部分由" in app_js
    assert 'remarkText(item) || "无"' in export_body
    assert app_js.index('header: "差异类型"') < app_js.index('header: "具体原因"')
    assert app_js.index('header: "处理脚本"') < app_js.index('header: "备注"')


def test_export_button_shows_progress_and_failure_feedback():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert 'data-export-label>导出</span>' in html
    assert 'class="export-progress" id="exportProgress" hidden' in html
    assert 'id="exportProgressText">准备导出...' in html
    assert "const exportBtnLabel = exportBtn?.querySelector(\"[data-export-label]\");" in app_js
    assert "function setExportState(exporting, message = \"\")" in app_js
    assert "function updateExportProgress(message)" in app_js
    assert "async function exportToExcel()" in app_js
    assert "await waitForExportUiFrame();" in app_js
    assert "showToast(`已导出 ${data.length} 条结果`, \"success\");" in app_js
    assert "showToast(`导出失败：${message}`, \"error\");" in app_js
    assert 'showToast("无数据可导出", "warning");' in app_js
    assert ".export-progress" in css
    assert ".export-progress-spinner" in css


def test_export_to_excel_groups_rows_by_difference_reason_stably():
    app_js = _read(APP_JS)

    assert "function exportRowsForExcel(data)" in app_js
    export_rows = re.search(r"function exportRowsForExcel\(data\) \{(?P<body>.*?)\n\}", app_js, re.S)
    assert export_rows is not None
    export_body = export_rows.group("body")
    assert "reasonOrder" in export_body
    assert "difference_reason" in export_body
    assert "originalIndex" in export_body
    assert "reasonDelta || left.originalIndex - right.originalIndex" in export_body

    export_to_excel = re.search(r"function exportToExcel\(\) \{(?P<body>.*?)exportBtn.addEventListener", app_js, re.S)
    assert export_to_excel is not None
    assert "const data = exportRowsForExcel(filteredResults());" in export_to_excel.group("body")


def test_export_to_excel_only_wraps_project_name_and_blocks_overflow():
    app_js = _read(APP_JS)

    assert "const EXPORT_COLUMNS" in app_js
    assert '{ header: "项目名称", width: 180, style: "ProjectName", type: "string" }' in app_js
    assert '{ header: "差异金额", width: 110, style: "Money", type: "number" }' in app_js
    assert '{ header: "差异类型", width: 180, style: "Text", type: "string" }' in app_js
    assert '{ header: "具体原因", width: 180, style: "SpecificReason", type: "string" }' in app_js
    assert '{ header: "差异原因详情", width: 360, style: "Detail", type: "string" }' in app_js
    assert '{ header: "处理脚本", width: 360, style: "Script", type: "string" }' in app_js
    assert '{ header: "备注", width: 220, style: "SpecificReason", type: "string" }' in app_js
    assert "预估差异原因" not in app_js
    assert app_js.index('header: "差异类型"') < app_js.index('header: "具体原因"')
    assert app_js.index('header: "具体原因"') < app_js.index('header: "匹配状态"')
    assert app_js.index('header: "处理脚本"') < app_js.index('header: "备注"')
    assert 'wrapText="1"' in app_js
    assert app_js.count('wrapText="1"') == 1
    assert 'shrinkToFit="1"' not in app_js
    assert 'ht="20" customHeight="1"' not in app_js
    assert "white-space:pre" not in app_js
    assert "function wrapExcelDetailLine(value)" not in app_js
    assert "EXPORT_OVERFLOW_GUARD_CELL" not in app_js

    export_to_excel = re.search(r"function exportToExcel\(\) \{(?P<body>.*?)exportBtn.addEventListener", app_js, re.S)
    assert export_to_excel is not None
    export_body = export_to_excel.group("body")
    assert "buildExcelWorkbookBlob(rows" in export_body
    assert 'type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"' in app_js
    assert "a.download = `自动对数_${ds}_${ts}.xlsx`;" in export_body


def test_export_to_excel_keeps_detail_cells_single_line():
    app_js = _read(APP_JS)

    export_to_excel = re.search(r"function exportToExcel\(\) \{(?P<body>.*?)exportBtn.addEventListener", app_js, re.S)
    assert export_to_excel is not None
    export_body = export_to_excel.group("body")
    assert "buildDetailText(item)" in export_body
    assert "escapeExcelSingleLineText(buildDetailText(item))" not in export_body
    assert "function escapeExcelDetailText(value)" not in app_js
    assert "const detail = escapeExcelSingleLineText(buildDetailText(item));" not in export_body
    assert "escapeExcelText(buildDetailText(item))" not in export_body


def test_export_to_xlsx_preserves_numeric_and_detail_formatting(tmp_path):
    app_js = _read(APP_JS)
    export_section = app_js[app_js.index("const EXPORT_COLUMNS"):app_js.index("function exportRowsForExcel")]
    output_path = tmp_path / "result.xlsx"
    script_path = tmp_path / "build_export_xlsx.js"
    script_path.write_text(
        export_section
        + textwrap.dedent(
            f"""
            const fs = require("fs");
            globalThis.Blob = require("buffer").Blob;
            (async () => {{
              const rows = [[
                "P001",
                "项目一",
                "1000",
                900,
                "800.5",
                -100,
                "资产缺失 + 负债及权益科目差异",
                "FA与AM标的不一致",
                "已解释",
                "第一行\\n第二行\\n第三行",
                "select 1; update t set a = 1;",
                "资产端差额已由“资产缺失”解释，修正资产端后仍存在剩余差额，剩余部分由“负债及权益科目差异”解释，因此展示为组合差异类型。"
              ]];
              const blob = buildExcelWorkbookBlob(rows, "自动对数结果 — 2026-05-31");
              const buffer = Buffer.from(await blob.arrayBuffer());
              fs.writeFileSync({str(output_path)!r}, buffer);
            }})();
            """
        ),
        encoding="utf-8",
    )

    subprocess.run(["node", str(script_path)], check=True, cwd=ROOT)

    with ZipFile(output_path) as archive:
        assert "xl/worksheets/sheet1.xml" in archive.namelist()
        worksheet_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        assert '<row r="2" ht="30" customHeight="1">' in worksheet_xml
        assert '<row r="3"' in worksheet_xml
        assert '<c r="C3" s="5"><v>1000</v></c>' in worksheet_xml

        assert '<c r="F3" s="5"><v>-100</v></c>' in worksheet_xml
        assert "第一行\n第二行\n第三行" in worksheet_xml

    workbook = load_workbook(output_path)
    sheet = workbook.active
    assert sheet.row_dimensions[2].height == 30
    assert sheet["C3"].value == 1000
    assert sheet["C3"].data_type == "n"
    assert sheet["F3"].value == -100
    assert sheet["F3"].data_type == "n"
    assert sheet["G2"].value == "差异类型"
    assert sheet["H2"].value == "具体原因"
    assert sheet["I2"].value == "匹配状态"
    assert sheet["J2"].value == "差异原因详情"
    assert sheet["K2"].value == "处理脚本"
    assert sheet["L2"].value == "备注"
    assert sheet["G3"].value == "资产缺失 + 负债及权益科目差异"
    assert sheet["H3"].value == "FA与AM标的不一致"
    assert sheet["H3"].alignment.horizontal == "left"
    assert sheet["J3"].value == "第一行\n第二行\n第三行"
    assert sheet["J3"].alignment.wrap_text is None
    assert sheet["J3"].alignment.shrink_to_fit is None
    assert sheet["J3"].font.sz == 11
    assert sheet["K3"].value == "select 1; update t set a = 1;"
    assert sheet["K3"].alignment.wrap_text is None
    assert sheet["K3"].alignment.shrink_to_fit is None
    assert sheet["K3"].font.sz == 11
    assert sheet["L3"].value == "资产端差额已由“资产缺失”解释，修正资产端后仍存在剩余差额，剩余部分由“负债及权益科目差异”解释，因此展示为组合差异类型。"
    assert sheet["L3"].alignment.wrap_text is None
    assert sheet["L3"].alignment.shrink_to_fit is None
    assert sheet["L3"].font.sz == 11


def test_home_target_code_mismatch_count_prefers_refinement_rows_without_double_counting(tmp_path):
    app_js = _read(APP_JS)
    normalize_fn = app_js[
        app_js.index("function normalizeHomeReasonText"):
        app_js.index("function homeSpecificReasonMatchesPaidIn")
    ]
    text_match_fn = app_js[
        app_js.index("function homeTargetCodeMismatchTextMatches"):
        app_js.index("function homeTargetCodeMismatchCount")
    ]
    count_fn = app_js[
        app_js.index("function homeTargetCodeMismatchCount"):
        app_js.index("function homeReasonCategoryFromItem")
    ]
    script_path = tmp_path / "home_target_code_count.js"
    script_path.write_text(
        normalize_fn
        + text_match_fn
        + count_fn
        + textwrap.dedent(
            """
            const mixedDetails = {
              details: [
                {
                  kind: "fa_am",
                  data: { specific_reason: "FA与AM标的不一致" },
                },
                {
                  kind: "asset_missing_refinement",
                  data: {
                    rows: [
                      { check_result: "FA和AM标的不一致", pact_id: "PACT_A" },
                      { check_result: "FA和AM标的不一致", pact_id: "PACT_B" },
                    ],
                  },
                },
              ],
            };
            const legacyFaAmOnly = {
              details: [
                {
                  kind: "fa_am",
                  data: { specific_reason: "FA与AM标的不一致" },
                },
              ],
            };
            const counts = [
              homeTargetCodeMismatchCount(mixedDetails),
              homeTargetCodeMismatchCount(legacyFaAmOnly),
            ];
            if (counts[0] !== 2 || counts[1] !== 1) {
              throw new Error(`unexpected counts: ${counts.join(",")}`);
            }
            """
        ),
        encoding="utf-8",
    )

    subprocess.run(["node", str(script_path)], check=True, cwd=ROOT)


def test_candidate_ambiguous_status_is_available_in_result_filters_and_badge():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)

    assert '<option value="候选不唯一">候选不唯一</option>' in html
    assert 'if (s === "候选不唯一") return `<span class="status-badge status-badge--warn">候选不唯一</span>`;' in app_js


def test_export_to_excel_keeps_processing_script_single_line():
    app_js = _read(APP_JS)

    export_to_excel = re.search(r"function exportToExcel\(\) \{(?P<body>.*?)exportBtn.addEventListener", app_js, re.S)
    assert export_to_excel is not None
    export_body = export_to_excel.group("body")
    assert "EXPORT_SCRIPT_MAX_CHARS" not in app_js
    assert "escapeExcelTruncatedSingleLineText" not in app_js
    assert "replace(/\\s*(?:\\r\\n?|\\n)\\s*/g, \" \")" in app_js
    assert ".slice(0, maxLength)" not in app_js
    assert "escapeExcelSingleLineText(buildProcessingScriptText(item))" in export_body
    assert "escapeExcelDetailText(buildProcessingScriptText(item))" not in export_body
    assert "escapeExcelText(buildProcessingScriptText(item))" not in export_body


def test_result_list_shows_loading_animation_when_returning_to_auto_check_page():
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert "let resultListLoadingTimer" in app_js
    assert "function renderResultListLoading()" in app_js
    assert "function showResultListReturnLoading()" in app_js
    loading_fn = re.search(r"function renderResultListLoading\(\) \{(?P<body>.*?)\n\}", app_js, re.S)
    assert loading_fn is not None
    assert "success-panel" not in loading_fn.group("body")
    assert "launchConfetti" not in loading_fn.group("body")
    assert "if (!resultBody || !results.length) return;" in app_js
    assert "renderResultListLoading();" in app_js
    assert "resultListLoadingTimer = setTimeout(() => {" in app_js
    assert "renderResults();" in app_js

    switch_page = re.search(r"function switchPage\(name, options = \{\}\) \{(?P<body>.*?)\n\}", app_js, re.S)
    assert switch_page is not None
    assert 'const previousPage = document.documentElement.getAttribute("data-page") || "";' in switch_page.group("body")
    assert 'if (name === "auto-check" && previousPage !== "auto-check") showResultListReturnLoading();' in switch_page.group("body")

    run_handler = re.search(r"runBtn.addEventListener\(\"click\", async \(\) => \{(?P<body>.*?)\n\}\);", app_js, re.S)
    assert run_handler is not None
    assert "renderResultListLoading();" not in run_handler.group("body")

    assert "openResultDetailRow" not in app_js
    assert "result-detail-loading" not in app_js
    assert 'class="result-loading-row"' in app_js
    assert 'class="loading-spinner result-loading-spinner"' in app_js
    assert "正在加载执行结果列表..." in app_js

    assert ".result-loading-row td" in css
    assert ".result-loading-spinner" in css
    assert "@keyframes resultListLoadingSweep" in css
    assert ".result-detail-loading" not in css
    assert ".detail-row.is-loading" not in css


def test_result_detail_expansion_is_single_open():
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    handler = re.search(r"resultBody\.addEventListener\(\"click\", \(e\) => \{(?P<body>.*?)\n\}\);", app_js, re.S)
    assert handler is not None
    body = handler.group("body")
    assert 'class="result-main-row" data-result-index="${gi}"' in app_js
    assert '<td class="result-project-code">${escapeHtml(item.project_code)}</td>' in app_js
    assert 'style="font-family:Consolas;color:#061623;"' not in app_js
    assert "function hasSelectedResultText()" in app_js
    assert 'const mainRow = e.target.closest(".result-main-row");' in body
    assert "if (!btn && hasSelectedResultText()) return;" in body
    assert 'resultBody.querySelectorAll(".detail-row").forEach((detailRow) => {' in body
    assert "if (detailRow === row) return;" in body
    assert "detailRow.hidden = true;" in body
    assert 'resultBody.querySelectorAll(".result-main-row").forEach((otherRow) => {' in body
    assert 'otherRow.classList.remove("is-expanded");' in body
    assert 'resultBody.querySelectorAll(".expand-btn").forEach((otherBtn) => {' in body
    assert "if (otherBtn === currentBtn) return;" in body
    assert 'otherBtn.textContent = "+";' in body
    assert "row.hidden = !wasHidden;" in body
    assert 'mainRow?.classList.toggle("is-expanded", wasHidden);' in body
    assert ".result-table tbody tr.result-main-row" in css
    assert "cursor: pointer;" in css
    assert ".result-table tbody tr.result-main-row td" in css
    assert "user-select: text;" in css
    assert ".result-project-code" in css
    assert '[data-color-mode="dark"] .result-project-code' in css
    assert '[data-color-mode="dark"] .result-table tbody td' in css
    assert '[data-color-mode="dark"] .result-table tbody tr:hover' in css
    assert ".result-table tbody tr.result-main-row.is-expanded" in css
    assert ".detail-row td {\n  padding: 10px 18px 14px 58px;" in css


def test_result_detail_uses_report_asset_total_label_everywhere():
    app_js = _read(APP_JS)
    export_detail_js = _read(EXPORT_DETAIL_JS)
    server_py = _read(ROOT / "src" / "auto_check" / "app" / "server.py")
    readme = _read(README_MD)

    assert '"label": "资负报表资产合计"' in server_py
    assert 'displayDetailLabel(r.label)' in app_js
    assert 'return label === "zf_detail 资产合计" ? "资负报表资产合计" : label;' in app_js
    assert 'rowValueAny(rows, ["资负报表资产合计", "zf_detail 资产合计"])' in export_detail_js
    assert "资产核对：资负报表资产=" in export_detail_js
    assert "结果列表支持点击项目所在行展开或收回详情" in readme


def test_space_tech_result_detail_title_icon_uses_gradient_theme_color():
    css = _read(STYLES_CSS)

    result_icon = re.search(r'(?m)^\[data-theme="space-tech"\] \.result-card \.card-title-icon\s*\{(?P<body>.*?)\}', css, re.S)
    assert result_icon is not None
    body = result_icon.group("body")
    assert "linear-gradient(135deg, #3b82f6, #06b6d4, #8b5cf6)" in body
    assert "background-clip: text" in body
    assert "-webkit-text-fill-color: transparent" in body
    assert "drop-shadow" in body


def test_difference_direction_is_kept_in_detail_payload():
    server_py = _read(SERVER_PY)

    assert '{"label": "差异方向", "value": result.direction}' in server_py


def test_no_runtime_reference_to_removed_balance_checker_directory():
    for path in [
        ROOT / "pyproject.toml",
        ROOT / "src" / "auto_check" / "__main__.py",
        ROOT / "src" / "auto_check" / "app" / "server.py",
    ]:
        assert "balance_checker" not in _read(path)


def test_session_expire_setting_replaces_default_run_date_setting():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)

    assert 'id="sessionExpireHours"' in html
    assert "会话过期时间" in html
    assert "默认运行日期" not in html
    assert 'id="defaultRunDate"' not in html
    assert "sessionExpireHours" in app_js
    assert "session_expire_hours" in app_js
    assert "defaultRunDate" not in app_js
    assert "default_run_date: normalized" not in app_js
    assert 'runDate.value = d.default_run_date || settingsPayload?.api_default_run_date || "";' in app_js


def test_home_auto_refresh_setting_controls_chart_reload():
    app_js = _read(APP_JS)

    assert "function shouldAutoRefreshHome()" in app_js
    assert "function syncDefaultSettingsControls()" in app_js
    assert '["visualEffects", "autoRefreshHome"].forEach((id)' in app_js
    assert 'name === "home" && (options.forceHomeRefresh || shouldAutoRefreshHome() || homeChartsNeedThemeRefresh)' in app_js
    assert "homeChartsNeedThemeRefresh = false;" in app_js
    assert "renderHomeStats(); renderChart(); renderTrendChart();" in app_js
    assert 'switchPage(savedPage, { forceHomeRefresh: savedPage === "home" })' in app_js
    assert 'switchPage("home", { forceHomeRefresh: true })' in app_js


def test_home_dashboard_uses_clickable_reconcile_stats_and_keeps_line_charts():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)
    readme = _read(README_MD)

    for label, stat_id, stat_key in [
        ("总差异数", "homeStatTotalDiff", "total"),
        ("未解释", "homeStatUnresolved", "unresolved"),
        ("已解释", "homeStatExplained", "explained"),
        ("实收本金不一致", "homeStatPaidIn", "paidIn"),
        ("标的代码不一致", "homeStatTargetCode", "targetCode"),
        ("报告期", "homeStatReportPeriod", "reportPeriod"),
    ]:
        assert label in html
        assert f'id="{stat_id}"' in html
        assert f'data-home-stat="{stat_key}"' in html

    assert 'id="homeStatReportRunAt"' in html
    for delta_id in [
        "homeStatTotalDiffDelta",
        "homeStatUnresolvedDelta",
        "homeStatExplainedDelta",
        "homeStatPaidInDelta",
        "homeStatTargetCodeDelta",
    ]:
        assert f'id="{delta_id}"' in html
    assert html.index('data-home-stat="reportPeriod"') < html.index('data-home-stat="total"')
    assert 'id="homeQualityScope"' in html
    assert 'id="chartCanvas"' in html
    assert 'id="trendCanvas"' in html
    assert "执行趋势" in html
    assert "最新趋势" not in html
    assert "多指标统计" not in html
    assert 'card-title card-title--trend' in html
    assert 'class="trend-legend" aria-label="指标颜色说明"' in html
    assert "trend-legend-dot--first-run" in html
    assert "trend-legend-dot--avg" not in html
    assert "trend-legend-dot--runs" in html
    assert "近12期" in html
    assert "差异类型分布" in html
    assert "高频差异项目" in html
    assert "重点差异项目" not in html
    assert "drawGlassChart(canvas, values, labels, renderChartAnimId, true, tooltipItems)" in app_js
    assert "tooltipItems = []" in app_js
    assert "差异数: ${formatMoney(r.total_count || 0)}" in app_js
    assert "function drawGlassMultiMetricChart" in app_js
    assert "drawGlassMultiMetricChart(canvas, [" in app_js
    assert "function trendFirstRunMetricStyle()" in app_js
    assert 'document.documentElement.getAttribute("data-theme") === "space-tech"' in app_js
    assert 'color: firstRunStyle.color' in app_js
    assert 'endColor: firstRunStyle.endColor' in app_js
    assert 'shadow: firstRunStyle.shadow' in app_js
    assert "function refreshHomeChartsForTheme()" in app_js
    assert "refreshHomeChartsForTheme();" in app_js
    assert "const sharedMaxVal = Math.max(...series.flatMap((metric) => metric.values), 1);" in app_js
    assert "series.forEach((metric) => { metric.maxVal = sharedMaxVal; });" in app_js
    assert "function drawLegend" not in app_js
    assert "drawLegend();" not in app_js
    assert "每期差异个数" in html
    assert "每期首次执行差异个数" not in html
    assert "每期平均差异个数" not in html
    assert "每期差异个数" in app_js
    assert "每期首次执行差异个数" not in app_js
    assert "每期平均差异个数" not in app_js
    assert "每期执行次数" in app_js
    assert "firstRunDiff" in app_js
    assert "averageDiff" not in app_js
    assert "executionCount" in app_js
    assert "totalDiff / executionCount" not in app_js
    assert "const firstRun = [...dateRuns].sort(compareHomeRunTimeAsc)[0];" in app_js
    assert "firstRunDiff: Number(firstRun?.total_count || 0)" in app_js
    assert "function formatMetricChartNumber(metric = {}, value)" in app_js
    assert "if (metric.integerValues) return String(Math.round(Number(value || 0)));" in app_js
    assert "const firstRunValues = filtered.map((item) => Math.round(item.firstRunDiff));" in app_js
    assert "integerValues: true" in app_js
    assert "function formatChartRunAtLabel(runAt = \"\", fallbackDate = \"\")" in app_js
    assert "const labels = dateRuns.map((r) => formatChartRunAtLabel(r.run_at, targetDate));" in app_js
    assert "bezierCurveTo" in app_js
    assert "chart-bar" not in html

    assert "const HOME_REASON_DEFS" in app_js
    assert "function homeDetailReasonText(details = [])" in app_js
    assert "function homeDisplayDetailReasonText(displayDetails = [])" in app_js
    assert "homeDetailReasonText(item.details)" in app_js
    assert "homeDisplayDetailReasonText(item.display_details)" in app_js
    assert '"specific_reason", "reason", "check_result", "reason_text", "basis"' in app_js
    assert "function homeSpecificReasonMatchesPaidIn(item = {})" in app_js
    assert 'text.includes("4001与c1000存在差异")' in app_js
    assert 'text.includes("4001-c1000差额正好解释主差异")' in app_js
    assert "function homeSpecificReasonMatchesTargetCode(item = {})" in app_js
    assert 'text.includes("fa/am标的不一致")' in app_js
    assert 'text.includes("fa与am标的不一致")' in app_js
    assert 'text.includes("fa和am标的不一致")' in app_js
    assert "function homeTargetCodeMismatchCount(item = {})" in app_js
    assert 'detail?.kind === "fa_am"' in app_js
    assert "summary.targetCode += homeTargetCodeMismatchCount(item);" in app_js
    assert "function homeReasonCategoryFromItem(item = {})" in app_js
    assert "function homeResultCountsAsUnresolved(item = {})" in app_js
    assert '["未解释", "候选不唯一"].includes(String(item.match_status || ""))' in app_js
    assert "const HOME_STATUS_ORDER" in app_js
    assert "buildHomeResultGroups(results)" in app_js
    assert "recentHomePeriodDates(runs, 12)" in app_js
    assert "homeRunsForPeriodDates(runs, recentPeriodDates)" in app_js
    assert "Promise.all(recentPeriodSummaries.map((run) => loadHomeRunDetail(run)))" in app_js
    assert "homeDifferenceTypeParts" in app_js
    assert "averageHomeSummaryByPeriod(recentPeriodRuns, homeStatusCountsForRun)" in app_js
    assert "averageHomeSummaryByPeriod(recentPeriodRuns, homeDifferenceTypeSummaryForRun)" in app_js
    assert "formatHomeRoundedCount(item.count)" in app_js
    assert "renderHomeQualityRows(\n      periodStatusCounts," in app_js
    assert "renderHomeReasonList(\n      periodTypeSummary," in app_js
    assert "buildHomeFrequencyItems(recentPeriodRuns, recentPeriodDates)" in app_js
    assert "renderHomeFrequencyList(frequencyItems, recentPeriodDates.length)" in app_js
    assert "const totalText = `近${periodCount}期 ${item.periodCount}次`;" in app_js
    assert "按报告期去重累计 ${item.periodCount} 次" in app_js
    assert "至少 2 期后分析高频项目" in app_js
    assert "等待首次核对后生成质量分布" in app_js
    assert "等待首次核对后统计差异类型" in app_js
    assert "const periodScopeText = `近${recentPeriodDates.length}期`;" in app_js
    assert 'data-home-stat="periodExplained"' not in html
    assert 'data-home-stat="periodUnresolved"' not in html
    assert 'data-home-stat="frequent"' not in html
    assert "homeStatsState = {" in app_js
    assert "function findHomeStatsBaselineRun" in app_js
    assert "return { run: samePeriodRuns[currentIndex - 1], label: \"较上次\" };" in app_js
    assert "const previousPeriodRun = [...runs]" in app_js
    assert "String(run.run_date || \"\") < currentDate" in app_js
    assert "return previousPeriodRun ? { run: previousPeriodRun, label: \"较上期\" } : { run: null, label: \"较上期\" };" in app_js
    assert "const deltaText = delta >= 0 ? `+${delta}` : String(delta);" in app_js
    assert "el.hidden = true;" in app_js
    assert "el.textContent = \"\";" in app_js
    assert "el.hidden = false;" in app_js
    assert "暂无对比" not in app_js
    assert 'el.innerHTML = `${escapeHtml(label)} <span class="home-stat-delta-value">${escapeHtml(deltaText)}</span>`;' in app_js
    assert "renderHomeStatDeltas(" in app_js
    assert "counts: {" in app_js
    assert "showHomeStatResults" in app_js
    assert "reportRuns: reportPeriodRuns" in app_js
    assert "run.run_date === latestRun.run_date" in app_js
    assert "function summarizeHomeRunForReport(run = {})" in app_js
    assert "function renderHomeReportPeriodTable(periodRuns = [])" in app_js
    assert '<th class="col-run-at">执行时间</th>' in app_js
    assert '<th class="col-total">差异数</th>' in app_js
    assert '<th class="col-paid-in">实收本金不一致</th>' in app_js
    assert '<th class="col-target-code">标的代码不一致</th>' in app_js
    assert 'const isReportPeriod = key === "reportPeriod";' in app_js
    assert 'const modalTitle = isReportPeriod ? "报送期差异数详情" : `${label}项目明细`;' in app_js
    assert "报送期 ${run?.run_date || \"--\"}，共 ${reportRuns.length} 次执行，按执行时间倒序。" in app_js
    assert 'id="infoDetailAction"' in html
    assert "HOME_TOP_STAT_KEYS" in app_js
    assert "openHomeStatResultList" in app_js
    assert 'trigger.closest(".home-stats-row")' in app_js
    assert "detailActionLabel: \"查看明细\"" in app_js
    assert 'const reasonValue = `home-category:${key}`' in app_js
    assert 'const reasonValue = "home-status:unresolved";' in app_js
    assert 'ensureSelectOption(reasonFilter, reasonValue, "未解释/候选不唯一");' in app_js
    assert 'String(selectedReason) === "home-status:unresolved"' in app_js
    assert '["paidIn", "targetCode"].includes(key)' in app_js
    assert "resultMatchesReasonFilter(item, reason)" in app_js
    assert "resultFilterHint" in app_js
    assert "结果列表已筛选" in app_js
    assert "clearHomeResultFilter" in app_js
    assert "resultRestoreHistoryMeta" in app_js
    assert "结果列表已恢复到历史数据：报告期" in app_js
    assert "restoreLatestResults" in app_js
    assert "回到最新结果" in app_js
    assert "function restoreLatestResultsToResultList()" in app_js
    assert 'setStatus("结果列表已还原到最新结果")' in app_js
    assert 'showToast("结果列表已还原到最新结果", "success")' in app_js
    assert "function hasActiveResultListFilter()" in app_js
    assert "const hadExistingFilter = hasActiveResultListFilter();" in app_js
    assert 'applyHomeResultListFilter(key, { hadExistingFilter });' in app_js
    assert 'key === "total"' in app_js
    assert 'homeResultListFilterLabel = hadExistingFilter ? (HOME_STAT_LABELS[key] || "") : "";' in app_js
    assert '<span class="result-filter-hint" id="resultFilterHint" hidden></span>' in html
    assert 'home-focus-item home-stat-click-target' not in app_js
    assert 'data-home-stat="${escapeHtml(statKey)}"' not in app_js
    assert "const fullName" in app_js
    assert 'title="${escapeHtml(itemTitle)}"' in app_js
    assert "home-focus-title-row" in app_js
    assert "home-focus-total" in app_js
    assert 'const totalText = `近${periodCount}期 ${item.periodCount}次`;' in app_js
    assert 'const detailText = `${periodText} · 最近类型：${reason}`;' in app_js
    assert '<td class="col-name" title="${escapeHtml(nameText)}">' in app_js
    assert '<th class="col-code">' in app_js
    assert '<th class="col-asset">' in app_js
    assert '<th class="col-liability">' in app_js
    assert '<th class="col-specific">' not in app_js
    assert '<td class="col-code" title="${escapeHtml(codeText)}">' in app_js
    assert "home-stat-modal-table" in css
    assert "table-layout: fixed;" in css
    assert ".home-stat-modal-table .col-asset" in css
    assert ".home-stat-modal-table .col-liability" in css
    assert ".home-stat-modal-table .col-run-at" in css
    assert ".home-stat-modal-table .col-target-code" in css
    assert ".home-stat-modal-table .col-specific" not in css
    assert ".home-stat-modal-table td.num {\n  text-align: left;" in css
    assert '[data-color-mode="dark"] .home-stat-modal-table-wrap' in css
    assert '[data-color-mode="dark"] .home-stat-modal-table th' in css
    assert '[data-color-mode="dark"] .home-stat-modal-table td' in css
    assert ".info-detail-action" in css
    assert ".result-filter-hint" in css
    assert ".result-filter-clear" in css
    assert ".home-stat-subvalue" in css
    assert ".home-stat-delta" in css
    assert ".home-stat-delta-value" in css
    assert ".home-stat-delta--up" in css
    assert ".home-stat-delta--down" in css
    assert ".result-card .card-title-left {\n  display: flex;" in css
    assert ".trend-legend" in css
    assert ".card-title--trend .card-title-icon" in css
    assert "display: none;" in css
    assert ".trend-legend-dot--first-run" in css
    assert ".trend-legend-dot--avg" not in css
    assert "background: linear-gradient(90deg, var(--secondary), var(--on-secondary-container))" in css
    assert '[data-theme="space-tech"] .trend-legend-dot--first-run' in css
    assert "background: linear-gradient(90deg, #3b82f6, #06b6d4)" in css
    assert ".trend-legend-dot--runs" in css
    assert "grid-template-columns: minmax(0, 0.92fr) minmax(0, 1fr) minmax(0, 1.08fr)" in css
    assert ".home-quality-track--sys" in css
    assert "grid-template-columns: 22px minmax(0, 1fr)" in css
    assert ".home-focus-title-row" in css
    assert ".home-focus-total" in css
    assert ".home-focus-detail" in css
    assert ".home-analysis-card:hover" in css
    assert "transform: translateY(-2px);" in css
    assert ':root[data-page="home"] body' in css
    assert "grid-template-columns: repeat(6, minmax(0, 1fr))" in css
    page_home_rule = re.search(r"(?m)^#page-home\s*\{(?P<body>.*?)\}", css, re.S)
    home_grid_rule = re.search(r"(?m)^\.home-grid\s*\{(?P<body>.*?)\}", css, re.S)
    assert page_home_rule is not None
    assert home_grid_rule is not None
    assert "--home-card-glow-gutter: 12px;" in page_home_rule.group("body")
    assert "overflow: visible;" in page_home_rule.group("body")
    assert "padding: var(--home-card-glow-gutter);" in home_grid_rule.group("body")
    assert "margin: calc(-1 * var(--home-card-glow-gutter));" in home_grid_rule.group("body")
    assert "overflow: visible;" in home_grid_rule.group("body")
    assert "首页调整为自动对数概览工作台" in readme
    assert "首页底部对数质量、差异类型分布和高频差异项目均展示实际统计期数" in readme
    assert "同报告期第二次及以后执行对比同报告期上一次执行" in readme
    assert "当期首次执行且存在上一报告期时显示“较上期”" in readme
    assert "首页执行趋势改用“月/日 时:分”展示横轴时间并支持悬浮查看执行时间和差异数" in readme
    assert "无任何对比基准时隐藏小字" in readme
    assert "多指标统计按核对日期展示每期差异个数" in readme
    assert "按每期首次执行记录取数" in readme
    assert "多指标统计按核对日期真实计算每期平均差异个数" not in readme
    assert "首页高频差异项目恢复连续/出现期数小字" in readme
    assert "项目名称右侧展示近 X 期按报告期去重后的出现次数" in readme
    assert "首页“实收本金不一致”仅统计具体原因中 `4001 - c1000` 差额正好解释主差异的项目" in readme
    assert "“标的代码不一致”仅统计具体原因中包含 FA/AM 标的不一致的项目" in readme
    assert "首页统计中“候选不唯一”归入“未解释”" in readme
    assert "不影响结果列表原始状态、历史和导出" in readme
    assert "首页报送期统计弹框改为展示该报送期内全部执行记录" in readme
    assert "顶部首位展示报告期统计卡片" in readme
    assert "沉稳主题下差异个数线和图例使用沉稳主题色" in readme
    assert "在“结果详情”标题后同行展示筛选说明" in readme
    assert "总差异数跳转时若结果列表原本已是全部差异则不显示筛选说明" in readme
    assert "底部最多统计近 12 个报告期，对数质量和差异类型按每期全部执行次数先取平均后汇总" in readme
    assert "某期最后一次执行差异归零时，同期前序执行中出现过的差异仍纳入平均统计和出现期统计" in readme
    assert "按每期首次执行记录取数并按整数展示" in readme
    assert "顶部统计项可查看项目明细并跳转到自动对数结果列表自动筛选" in readme
    assert "长项目名称在边界内省略并支持鼠标悬浮查看全称" in readme


def test_home_report_period_stat_card_fits_scale_ratio_changes():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert "home-stat-card--report-period" in html
    assert html.index("home-stat-card--report-period") < html.index('data-home-stat="total"')
    assert ".home-stat-card--report-period {\n  min-width: 0;\n}" in css
    assert ".home-stat-card--report-period .home-stat-value" in css
    assert "font-size: var(--home-report-period-font-size, 24px);" in css
    assert "const HOME_REPORT_PERIOD_MIN_FONT_SIZE = 16;" in app_js
    assert "const HOME_REPORT_PERIOD_MAX_FONT_SIZE = 25;" in app_js
    assert "function fitHomeReportPeriodValue()" in app_js
    assert 'value.style.setProperty("--home-report-period-font-size", `${size}px`);' in app_js
    assert "value.scrollWidth > value.clientWidth + 1" in app_js
    assert 'if (id === "homeStatReportPeriod") fitHomeReportPeriodValue();' in app_js
    assert 'window.addEventListener("resize", fitHomeReportPeriodValue);' in app_js
    assert "\u9996\u9875\u62a5\u544a\u671f\u7edf\u8ba1\u5361\u7247\u6309\u5b9e\u9645\u663e\u793a\u6bd4\u4f8b\u81ea\u9002\u5e94\u5b57\u53f7" in _read(README_MD)


def test_home_charts_rerender_after_scale_ratio_changes():
    app_js = _read(APP_JS)
    readme = _read(README_MD)

    assert "let homeChartsResizeTimer = null;" in app_js
    assert "const HOME_CHARTS_RESIZE_DEBOUNCE_MS = 160;" in app_js
    assert "function scheduleHomeChartsResize()" in app_js
    assert 'document.documentElement.getAttribute("data-page") !== "home"' in app_js
    assert "window.clearTimeout(homeChartsResizeTimer);" in app_js
    assert "homeChartsResizeTimer = window.setTimeout(() => {" in app_js
    assert "renderChart();" in app_js
    assert "renderTrendChart();" in app_js
    assert 'window.addEventListener("resize", scheduleHomeChartsResize);' in app_js
    assert "canvas" in readme


def test_home_analysis_cards_keep_height_in_short_scale_ratio_viewports():
    css = _read(STYLES_CSS)
    readme = _read(README_MD)

    assert "@media (max-width: 1200px) and (max-height: 700px)" in css
    assert ":root[data-page=\"home\"] body" in css
    assert ":root[data-page=\"home\"] .main-content" in css
    assert "#page-home,\n  #page-home .home-grid" in css
    assert ".home-charts-row,\n  .home-analysis-row {\n    flex: none;" in css
    assert ".home-analysis-card {\n    height: auto;\n    min-height: 160px;" in css
    assert "1366" in readme
    assert "125%" in readme


def test_saving_page_size_immediately_rerenders_results():
    app_js = _read(APP_JS)
    save_settings = re.search(r"function saveSettings\(\) \{(?P<body>.*?)function resetSettings", app_js, re.S)

    assert save_settings is not None
    assert "currentPage = 1" in save_settings.group("body")
    assert "renderResults()" in save_settings.group("body")


def test_run_page_has_stop_button_logs_and_background_job_polling():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert 'id="stopRunBtn"' in html
    assert 'class="stop-icon"' in html
    assert 'id="runLogPanel"' in html
    assert 'id="runLogList"' in html
    assert 'id="runLogToggleBtn"' in html
    assert 'api("/api/run/start"' in app_js
    assert 'api(`/api/run/status/${encodeURIComponent(jobId)}`)' in app_js
    assert 'api("/api/run/cancel"' in app_js
    assert "function renderRunLogs" in app_js
    assert "function buildRunCompletionNotice" in app_js
    assert "function buildRunCompletionLogMessage" in app_js
    assert 'formatHistoryDiffCount(history, "added_count")' in app_js
    assert 'formatHistoryDiffCount(history, "removed_count")' in app_js
    assert "上次执行时间 ${baselineRunAt || \"无\"}" in app_js
    assert "appendRunLog(buildRunCompletionLogMessage(completionNotice, h));" in app_js
    assert "runLogPanel.hidden = true" in app_js
    assert "if (!logs.length && runLogPanel.hidden) return;" in app_js
    assert 'runLogPanel.classList.toggle("collapsed")' in app_js
    assert ".btn-stop" in css
    assert ".run-log-panel" in css
    assert ".run-log-panel.collapsed .run-log-list" in css
    assert "display: none" not in re.search(r"\.run-log-panel\.collapsed \.run-log-list\s*\{(?P<body>.*?)\}", css, re.S).group("body")
    assert "max-height" in re.search(r"\.run-log-list\s*\{(?P<body>.*?)\}", css, re.S).group("body")
    assert "opacity" in re.search(r"\.run-log-panel\.collapsed \.run-log-list\s*\{(?P<body>.*?)\}", css, re.S).group("body")
    assert "transform" in re.search(r"\.run-log-panel\.collapsed \.run-log-list\s*\{(?P<body>.*?)\}", css, re.S).group("body")
    assert "@keyframes runLogTogglePop" in css
    assert "@keyframes runLogLineFloatIn" in css
    assert "@media (prefers-reduced-motion: reduce)" in css


def test_combination_limit_is_configurable_in_default_settings():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)

    assert 'id="combinationLimit"' in html
    assert "组合候选阈值" in html
    assert "function getCombinationLimit()" in app_js
    assert "defaultSettings.combinationLimit || \"50\"" in app_js
    assert 'api("/api/settings/defaults"' in app_js
    assert 'localStorage.removeItem("autoCheckSettings")' in app_js
    assert "max_combination_rows: getCombinationLimit()" in app_js


def test_visual_effects_setting_replaces_page_size_control():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert 'id="pageSize"' not in html
    assert "每页显示条数" not in html
    assert 'id="visualEffects"' in html
    assert "动画效果" in html
    assert "visualEffects" in app_js
    assert "visual_effects" in app_js
    assert "function visualEffectsEnabled()" in app_js
    assert "function applyVisualEffectsSetting()" in app_js
    assert 'dataVisualEffects' not in app_js
    assert 'dataset.visualEffects' in app_js
    assert '[data-visual-effects="off"]' in css


def test_latest_history_results_load_by_default_and_last_run_time_is_retained():
    app_js = _read(APP_JS)

    assert "function formatDisplayTime(value)" in app_js
    assert 'return String(value).replace("T", " ")' in app_js
    assert 'const displayTime = formatDisplayTime(value || "");' in app_js
    assert "if (!displayTime) return;" in app_js
    assert "latestRunAt = displayTime;" in app_js
    assert "async function loadLatestHistoryResults()" in app_js
    assert "await loadLatestHistoryResults()" in app_js
    assert 'if (lastRunTime.textContent && !resultRestoreHistoryMeta && !hideLastRunTimeForNoSourceData) lastRunTime.hidden = false;' in app_js
    assert "lastRunTime.hidden = Boolean(resultRestoreHistoryMeta) || hideLastRunTimeForNoSourceData;" in app_js
    set_last_run = re.search(r"function setLastRunTime\(value, executorName = \"\"\) \{(?P<body>.*?)\n\}", app_js, re.S)
    assert set_last_run is not None
    assert "hideLastRunTimeForNoSourceData = false;" in set_last_run.group("body")
    assert "setLastRunTime(latestHistory.run_at, historyExecutorName(latestHistory))" in app_js
    assert "normalizeExecutorDisplayName" in app_js
    assert 'executorName: normalizeExecutorDisplayName(extra.executorName || latestRunExecutor, "")' in app_js
    assert "if (!latestRunAt) setLastRunTime(formatLastRunTime())" not in app_js


def test_frontend_dates_use_beijing_time_helpers():
    app_js = _read(APP_JS)

    assert 'const BEIJING_TIME_ZONE = "Asia/Shanghai";' in app_js
    assert "function formatBeijingDate(" in app_js
    assert "function formatBeijingDateTime(" in app_js
    assert "function shiftBeijingDate(" in app_js
    assert 'trendDateStart = shiftBeijingDate({ months: -6 });' in app_js
    assert "formatClockTime()" in app_js
    assert "return formatBeijingTime();" in app_js
    assert 'const displayTime = formatDisplayTime(value || "");' in app_js
    assert "latestRunAt = displayTime;" in app_js
    assert "return formatBeijingDateTime();" in app_js
    assert "savedAt: formatBeijingDateTime()" in app_js
    assert "`users-${formatBeijingDate()}.csv`" in app_js
    assert "`auto-check-configs-${formatBeijingDate()}.json`" in app_js
    assert "new Date().toISOString().slice(0, 10)" not in app_js


def test_latest_history_results_uses_history_sort_order():
    app_js = _read(APP_JS)

    assert "function compareHistoryRunsDesc(a, b)" in app_js
    assert "function compareHistoryRunsByRunAtDesc(a, b)" in app_js
    assert "const sorted = getFilteredHistoryRuns().sort(compareHistoryRunsDesc);" in app_js
    assert "const latest = [...runs].sort(compareHistoryRunsByRunAtDesc)[0];" in app_js


def test_history_page_has_pagination_controls_and_logic():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert 'id="historyReportFilter"' in html
    assert 'id="historyExecutorFilter"' in html
    assert 'class="history-toolbar"' in html
    assert 'type="date"' in html
    assert '<select id="historyExecutorFilter" class="filter-select history-filter-input">' in html
    assert '<option value="">全部执行人</option>' in html
    assert 'id="clearHistoryReportFilter"' in html
    assert 'id="clearHistoryExecutorFilter"' in html
    assert 'id="clearKeywordFilter"' in html
    assert 'id="clearReasonFilter"' in html
    assert 'id="clearStatusFilter"' in html
    assert 'class="filter-clear-shell filter-clear-shell--select result-reason-filter-shell"' in html
    assert html.index('id="historyReportFilter"') < html.index('id="historyRefreshBtn"')
    assert html.index('id="historyExecutorFilter"') < html.index('id="historyRefreshBtn"')
    assert 'id="historyPageInfo"' in html
    assert 'id="historyPrevPage"' in html
    assert 'id="historyNextPage"' in html
    assert 'id="historyPageCurrent"' in html
    assert 'id="historyJumpPage"' in html
    assert '跳至 <input id="historyJumpPage" type="number" min="1" /> 页' in html
    history_pagination = re.search(r'id="historyPagination"(?P<body>.*?)</div>\s*</section>', html, re.S)
    assert history_pagination is not None
    assert "sysInfoFeedback" not in history_pagination.group("body")
    assert "let historyCurrentPage = 1;" in app_js
    assert "function getHistoryFilterValues()" in app_js
    assert "function getFilteredHistoryRuns()" in app_js
    assert "function updateHistoryExecutorOptions()" in app_js
    assert "executors.set(name.toLowerCase(), name);" in app_js
    assert "updateHistoryExecutorOptions();" in app_js
    assert "run.run_date !== filters.reportDate" in app_js
    assert 'executorText !== filters.executor' in app_js
    assert "暂无符合条件的历史记录" in app_js
    assert 'historyReportFilter?.addEventListener("change"' in app_js
    assert 'historyExecutorFilter?.addEventListener("change"' in app_js
    assert "clearHistoryFilterControl(historyReportFilter)" in app_js
    assert "clearHistoryFilterControl(historyExecutorFilter)" in app_js
    assert "clearResultFilterControl(keywordFilter)" in app_js
    assert "clearResultFilterControl(reasonFilter)" in app_js
    assert "clearResultFilterControl(statusFilter)" in app_js
    assert "function updateFilterClearButtons()" in app_js
    assert "function getHistoryPageItems()" in app_js
    assert "function updateHistoryPagination()" in app_js
    assert "historyPrevPageBtn?.addEventListener" in app_js
    assert "historyNextPageBtn?.addEventListener" in app_js
    assert "historyJumpPage?.addEventListener" in app_js
    assert ".history-toolbar" in css
    assert ".history-filter-field" in css
    assert ".history-filter-input" in css
    assert ".filter-clear-shell" in css
    assert ".filter-clear-button" in css
    assert ".filter-clear-button::before" in css
    assert ".filter-clear-button::after" in css
    result_reason_shell = re.search(
        r"(?m)^\.result-card \.filters-row \.result-reason-filter-shell\s*\{(?P<body>.*?)\}",
        css,
        re.S,
    )
    assert result_reason_shell is not None
    assert "width: 220px" in result_reason_shell.group("body")
    assert ".result-card .filters-row .filter-clear-shell--text" not in css
    assert ".result-card .filters-row .filter-clear-shell--select" not in css
    history_field = re.search(r"(?m)^\.history-filter-field\s*\{(?P<body>.*?)\}", css, re.S)
    assert history_field is not None
    assert "white-space: nowrap" in history_field.group("body")
    assert ".history-filter-field > span:first-child" in css
    assert "flex: 0 0 150px" in css
    history_date_shell = re.search(
        r"(?m)^\.history-filter-clear-shell\.filter-clear-shell--date\s*\{(?P<body>.*?)\}",
        css,
        re.S,
    )
    assert history_date_shell is not None
    assert "flex: 0 0 176px" in history_date_shell.group("body")
    assert "width: 176px" in history_date_shell.group("body")
    assert ".filter-clear-shell:hover .filter-clear-button.is-visible" in css
    assert ".filter-clear-shell--select .custom-select-trigger" in css


def test_system_info_actions_show_running_and_completion_feedback():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert 'id="sysInfoFeedback"' in html
    assert "async function runSystemInfoAction" in app_js
    assert "setSystemInfoFeedback" in app_js
    assert 'id="testAllConnBtn"' not in html
    assert "testAllConnBtn" not in app_js
    assert 'refreshInfoBtn?.addEventListener("click"' in app_js
    assert "button.textContent = pendingText" in app_js
    assert "button.disabled = true" in app_js
    assert ".sys-info-feedback" in css
    assert ".sys-info-feedback--running" in css
    assert ".sys-info-feedback--success" in css
    assert ".sys-info-feedback--error" in css


def test_changelog_documents_latest_setting_and_cleanup_changes():
    app_js = _read(APP_JS)

    for text in [
        "v1.3.0",
        "新增后台执行、停止执行和执行日志。",
        "新增默认设置持久化、历史分页和系统信息操作反馈。",
        "新增估值表资产合计列、导出详情和 1541 财产权核对。",
        "v1.2.1",
        "2026-06-01",
        "系统优化及BUG修复。",
        "v1.2.0",
        "v1.1.0",
        "新增系统设置、业务设置、主题和图表能力。",
        "v1.0.0",
        "初始版本：自动对数、历史记录、多数据源和 Excel 导出。",
    ]:
        assert text in app_js

    for verbose_text in [
        "执行过程中新增后台控制台日志和可折叠页面执行日志，细化到",
        "资产缺失/重复新增 1541 财产权合同投融资核对：",
        "统一使用 fa_valuationreport_dws.c_projcode",
        "后台执行、停止执行和执行日志优化。",
        "优化工作台布局、进度条和结果详情区域。",
        "资产科目匹配、名称匹配和组合候选规则优化。",
    ]:
        assert verbose_text not in app_js


def test_changelog_and_readme_document_pbc_import_and_space_nav_updates():
    app_js = _read(APP_JS)
    readme = _read(README_MD)

    for text in [
        "新增工具页面与人行全量产品一键导入能力。",
        "系统优化及BUG修复。",
    ]:
        assert text in app_js

    for text in [
        "人行全量产品一键导入增强",
        "上传支持 zip/rar/7z/xlsx/xls/csv",
        "字段映射区布局优化",
        "太空主题滚动效果优化",
        "内容越过导航栏时增加高透明内容模糊遮罩",
    ]:
        assert text in readme


def test_version_206_documents_db_validation_engine_update():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    readme = _read(README_MD)

    assert 'const DEFAULT_VERSION = "v2.1";' in app_js
    assert 'id="statusText">v2.1</span>' in html
    assert 'id="topNavStatus" title="v2.1">v2.1</span>' in html

    for text in [
        "v2.1",
        "v2.0.8",
        "新增监管智核品牌名称和系统 Logo。",
        "首页组合图表指标改为每期差异个数。",
        "v2.0.7",
        "新增流程链配置、手工执行及执行记录查看。",
        "流程链配置支持从流程表选择流程。",
        "自动对数新增3001共同类科目与实收本金多次重复识别。",
        "v2.0.6",
        "新增人行逐笔校验引擎公开信息校验、模板校验和规则说明能力。",
        "自动对数差异原因调整为固定基础分类，细分原因在详情展示。",
        "自动对数资产缺失细分新增多资产格式化具体原因和详情表格。",
        "自动对数资产重复新增私募产品细分原因和详情表格。",
        "自动对数资产差异新增贷款及财产权合同细分原因和详情表格。",
        "自动对数资产端组合候选过多时支持科目分组组合，并新增债券DM证券余额差异细分。",
        "自动对数资产差异和负债权益科目差异新增逆/正回购金额比对。",
        "自动对数资产差异解释后支持继续核对剩余差额并展示组合差异类型。",
        "自动对数差异类型筛选支持组合差异类型匹配。",
        "自动对数资产端和负债权益主差异多组候选时展示候选不唯一。",
        "自动对数资产缺失候选不唯一时支持AM复核确认候选组，实收本金缺失/重复新增c1000防误判判断。",
        "自动对数导出Excel新增组合差异备注列。",
        "自动对数处理脚本支持多个FA/AM标的不一致生成。",
        "自动对数负债权益正回购差异新增具体原因。",
        "自动对数结果列表和导出字段改为差异类型，并新增具体原因列。",
        "自动对数历史详情同步展示具体原因。",
        "自动对数结果详情改为单行展开查看。",
        "自动对数实收本金差异与负债权益混合场景支持剩余差额核对。",
        "自动对数实收本金差异新增TA差异细分原因。",
        "自动对数负债权益和实收本金新增格式化具体原因和详情表格。",
        "系统优化及BUG修复。",
    ]:
        assert text in app_js

    for text in [
        "v2.0.7",
        "自动对数资产端候选新增 `3001.XX` 正数共同类科目",
        "自动对数实收本金重复支持多次重复计入识别",
        "新增流程执行工具",
        "流程链支持弹窗新增/编辑",
        "流程顺序可从申报平台流程表中选择",
        "流程链配置弹框点击空白遮罩不再关闭",
        "sp_task.end_time",
        "仅支持手工执行",
        "流程功能独立于自动对数",
        "v2.0.6",
        "人行逐笔校验引擎新增数据库逐笔校验能力",
        "新增公开信息交叉校验",
        "新增模板交叉校验",
        "baseinfo.table_name_zh",
        "baseinfo.template_json",
        "支持按 `baseinfo` 英文表名生成和读取 30 张物理模板表",
        "ZG09/ZG10 模板交叉校验对齐旧程序口径",
        "`cpkj=1` 分别对比 `balance_sheet_info`、`balance_sheet_info2`",
        "`cpkj=2` 分别对比 `balance_sheet_info_zcglxt`、`balance_sheet_info2_zcglxt`",
        "历史改为按真实执行时间倒序展示",
        "规则说明同步更新为最新代码口径",
        "自动对数差异原因调整为固定基础分类",
        "资产端解释后仍有剩余差额时可组合展示多个差异类型",
        "自动对数资产缺失细分扩展为",
        "自动对数资产重复细分扩展为",
        "自动对数资产差异新增贷款/财产权合同逐一核对",
        "自动对数资产差异新增逆回购金额比对",
        "`subcode LIKE '7%'` 的 `buyback_money + expenses`",
        "资产差异细分",
        "命中 `1101.05.06.01*` 时核查 AM 标的表 `c_spv_type` 和 `c_assettype`",
        "特定目的载体范围扩展至信托、银行理财、保险理财、场外证券理财产品、场外基金理财产品和期货",
        "自动对数导出处理脚本支持从“资产缺失细分”表中识别多条 FA/AM 标的不一致记录",
        "特定目的载体、债券、股票、公募基金、私募基金、逆回购、贷款、股权投资、信托计划收益权、资产收益权",
        "资产缺失细分",
        "正回购差异",
        "自动对数负债及权益科目差异新增正回购金额比对",
        "匹配状态为 `候选不唯一`",
        "资产缺失方向支持继续用 AM 标的和合同投融资余额复核唯一确认候选组",
        "实收本金缺失/重复新增 `c1000` 防误判闸门",
        "自动对数导出 Excel 新增“备注”列",
        "`subcode LIKE '8%'` 的 `buyback_money - expenses`",
        "负债及权益科目细分",
        "导出 Excel 在“差异类型”后新增“具体原因”列",
        "结果页展开详情和导出 Excel 同步展示“具体原因”",
        "自动对数结果详情改为单行展开查看",
        "合同投融资余额非 0",
        "继续核查 SPV DM 表和报表明细",
        "实收本金差异与负债权益混合场景",
        "`a0001-d0000-(4001-c1000)` 的剩余差额",
        "自动对数实收本金缺失、重复、差异的具体原因改为",
        "实收本金细分",
        "`currency_report_24.currency_detail_project_2_1_8`",
        "自动对数“实收本金差异”新增 TA 细分原因",
        "DM TA 表与 DWS TA 表份额余额+待结转收益汇总",
        "客户类型依赖字段为空记录",
        "load-local-pg-20260601-formatted-reason-scenarios.ps1",
        "load-local-pg-20260614-16-reconcile-scenarios.ps1",
        "seed_current_reconcile_20260614_16.py",
        "seed_current_home_frequency_reports.py",
        "seed_current_history_delta_20260622.py",
        "高频差异项目",
        "按报告期和执行人筛选",
        "执行人下拉按现有历史记录去重生成",
        "悬浮小叉快速清除",
        "保留输入框、日期框和下拉框的粒子悬浮效果",
        "结果列表仅加宽差异类型筛选框",
        "避免执行人文字被日期图标区遮挡",
        "历史详情弹窗移除内容区边缘线",
        "底部“恢复到结果页”按钮区域固定在弹窗底部",
        "报表对应日期无数据时隐藏顶部“最近执行”提示",
        "新增差异 10 条、减少差异 10 条",
        "DELTA20260622",
        "实收本金不一致",
        "标的代码不一致",
        "HFJST2026",
        "AC20260614",
        "AC20260615",
        "AC20260616",
        "3001 共同类资产/负债",
        "债券 DM 余额差异",
    ]:
        assert text in readme


def test_version_208_documents_regulatory_intelligence_core_brand_update():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    login_html = _read(ROOT / "src" / "auto_check" / "web" / "login.html")
    logo = _read(ROOT / "src" / "auto_check" / "web" / "assets" / "logo-full.svg")
    login_logo = _read(ROOT / "src" / "auto_check" / "web" / "assets" / "logo-login.svg")
    login_dark_logo = _read(ROOT / "src" / "auto_check" / "web" / "assets" / "logo-login-dark.svg")
    favicon_asset = _read(ROOT / "src" / "auto_check" / "web" / "assets" / "favicon-64x64.svg")
    readme = _read(README_MD)

    assert "<title>监管智核</title>" in html
    assert "<title>监管智核</title>" in login_html
    assert 'href="/assets/favicon-64x64.svg?v=2.0.8-regulatory-intelligence-core"' in html
    assert 'href="/assets/favicon-64x64.svg?v=2.0.8-regulatory-intelligence-core"' in login_html
    assert 'class="brand-wordmark-main">监管智核</span>' in html
    assert 'class="brand-wordmark-sub">监管报送核验平台</span>' in html
    assert 'src="/assets/logo-login.svg?v=2.0.8-regulatory-intelligence-core-horizontal" alt="监管智核"' in login_html
    assert 'src="/assets/logo-login-dark.svg?v=2.0.8-regulatory-intelligence-core-horizontal" alt="监管智核"' in login_html
    assert 'alt="监管智核 Logo"' in html
    assert "准星" not in html
    assert "准星" not in login_html
    assert 'viewBox="0 0 520 160"' in login_logo
    assert "监管智核横向标志" in login_logo
    assert "ric-horizontal" in login_logo
    assert "ric-stacked" not in login_logo
    assert 'viewBox="0 0 520 160"' in login_dark_logo
    assert "监管智核深色横向标志" in login_dark_logo
    assert "ric-horizontal-dark" in login_dark_logo
    assert "ric-stacked" not in login_dark_logo

    for asset in [logo, favicon_asset, login_logo, login_dark_logo]:
        assert "ric-" in asset
        assert "监管智核" in asset
        assert any(color in asset for color in ("#3466d9", "#4f7cff"))
        assert any(color in asset for color in ("#ffbd38", "#f0a12b"))
        assert "scheme-a" not in asset
        assert "scheme-a-zx-grid-hit" not in asset
        assert "A compact ZX monogram" not in asset

    for text in [
        "v2.0.8",
        "新增监管智核品牌名称和系统 Logo。",
        "新增点击 Logo 切换主题能力。",
        "新增登录进入主界面动效。",
        "系统优化及BUG修复。",
    ]:
        assert text in app_js

    for text in [
        "v2.0.8",
        "系统对外名称更新为“监管智核”",
        "使用 `logo/regulatory-intelligence-core` 资源包中的双环对勾设计替换系统 Logo",
        "主应用、登录页、关于系统和浏览器页签品牌文案同步调整",
        "点击侧边栏或顶部导航 Logo 切换活力/沉稳主题",
        "侧边栏与顶部导航之间的衔接过渡动画",
        "登录成功进入主界面时新增一次性入场动画",
        "浅色登录页品牌区同步加入暗色模式浮动圆形动效",
        "前端静态测试同步更新监管智核品牌和 Logo 资源断言",
    ]:
        assert text in readme


def test_version_21_documents_reconcile_schema_and_flow_updates():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    readme = _read(README_MD)

    assert 'const DEFAULT_VERSION = "v2.1";' in app_js
    assert 'id="statusText">v2.1</span>' in html
    assert 'id="topNavStatus" title="v2.1">v2.1</span>' in html
    assert "- 应用界面版本：`v2.1`" in readme

    change_items = [
        "人行逐笔校验执行历史新增执行人展示",
        "自动对数 AM 复核在名称无法匹配时新增兜底",
        "首页最新趋势横轴改为展示每次自动对数的执行日期和时间",
        "兜底明细与资产缺失细分明细重复计数",
        "流程链配置可选流程列表保留 500 条初始展示上限",
        "流程链停止按钮改为按后台任务",
        "自动对数导出处理脚本按 AM 合同来源判断",
        "自动对数仓储查询支持在系统设置页面通过表单维护表名、字段名和表级数据源",
        "表字段配置保存失败弹框按缺失字段逐行展示",
        "自动对账表字段配置新增“标准中文名”输入框",
    ]
    assert "`v2.1` (2026-07-02) 主要变化：" in readme
    assert '<span class="changelog-version">v2.1</span>' in app_js
    assert '<span class="changelog-date">2026-07-02</span>' in app_js
    for text in change_items:
        assert text in readme
        assert text in app_js

    for text in [
        "重复启动本地服务时检测默认端口占用",
        "本地 SQLite 旧库结构迁移前自动生成",
        "系统设置和工具页的配置加载改为模块间互不阻塞",
        "系统信息改用轻量统计接口",
        "避免切页或刷新时拉取全量历史记录",
        "逐笔字段映射加载结果少于系统内置表单",
        "旧历史结构化迁移从普通查询链路移除",
        "改为管理员在“本地数据查询”页面手动触发",
        "SQLite 锁等待",
        "历史记录写入当前登录用户的姓名、账号和用户 ID",
    ]:
        assert text in readme
    assert "系统优化及BUG修复。" in app_js


def test_version_205_documents_scheme_a_logo_update():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    logo = _read(ROOT / "src" / "auto_check" / "web" / "assets" / "logo-full.svg")
    favicon_asset = _read(ROOT / "src" / "auto_check" / "web" / "assets" / "favicon-64x64.svg")
    readme = _read(README_MD)

    assert 'const DEFAULT_VERSION = "v2.1";' in app_js
    assert 'id="statusText">v2.1</span>' in html
    assert 'id="topNavStatus" title="v2.1">v2.1</span>' in html

    for text in [
        "v2.0.5",
        "系统优化及BUG修复。",
    ]:
        assert text in app_js

    for text in [
        "v2.0.5",
        "系统 Logo 采用方案 A",
        "ZX 数据网格设计",
        "绿色命中点",
        "favicon 同步改为方案 A 的小尺寸简化版本",
        "修复数据源测试连接长时间未返回后关闭弹窗",
        "人行逐笔校验引擎保存配置后自动刷新字段映射",
        "全站下拉框统一为方案 5 粒子悬浮风格",
        "修复首页趋势日期下拉菜单滚动时被关闭的问题",
        "适当加宽日期下拉框",
        "系统输入框同步加入粒子悬浮与毛玻璃聚焦效果",
        "默认太空主题和暗色模式风格一致",
        "用户创建/编辑弹框移除多余隐藏下拉框",
        "关于系统品牌区仅保留 Logo",
        "日期选择组件采用太空粒子风格",
        "日期选择弹层同步替换为自定义方案 B 日历面板",
        "统一运行日期和人行逐笔报告期",
        "修复用户创建/编辑弹框输入框和人行逐笔报告期日期组件",
        "调整系统 Logo 与 favicon 图案重心",
        "浏览器页签 favicon 引用增加版本参数",
        "沉稳主题下输入框、下拉框和日期选择组件描边统一使用沉稳主题色",
        "活力主题保持蓝青紫粒子风格",
        "侧边栏品牌区移除“精准核对 · 合规报送”标语",
        "自动对数原因“缺失资产在AM信息中正常，需排除生成数据SQL”调整为“缺失资产在投资端信息无异常，请核查报表是否正常生成”",
        "自动对数导出 Excel 改为 `.xlsx` 工作簿格式",
        "表头行高固定为 30",
        "金额列写入为数值格式",
        "差异原因详情”点击公式栏查看时保留原始换行格式",
        "自动对数导出按钮增加导出中进度反馈和成功/失败提示",
        "活力主题下结果详情标题图标改为蓝青紫渐变",
        "顶部导航和侧边栏用户头像改为风格 B 彩色首字母头像",
        "系统默认设置中的“默认运行日期”替换为“会话过期时间”",
        "前端静态测试同步增加方案 A Logo 资源断言",
    ]:
        assert text in readme


def test_home_chart_date_select_keeps_scrollable_wider_dropdown():
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    chart_select_rule = re.search(r"(?m)^\.chart-date-select\s*\{(?P<body>.*?)\}", css, re.S)
    assert chart_select_rule is not None
    assert "min-width: 150px" in chart_select_rule.group("body")

    assert 'target.closest(".custom-select-dropdown")' in app_js
    assert "const dropdownWidth = Math.min(Math.max(rect.width + 24, rect.width)" in app_js
    assert "const openAbove = availableBelow < 160 && availableAbove > availableBelow;" in app_js


def test_version_204_documents_tab_and_brand_hierarchy_update():
    app_js = _read(APP_JS)
    readme = _read(README_MD)

    for text in [
        "v2.0.4",
        "新增浏览器页签品牌精简显示。",
        "系统优化及BUG修复。",
    ]:
        assert text in app_js

    for text in [
        "v2.0.4",
        "浏览器页签标题精简为“准星”",
        "开启您的智能工作台",
        "小字监管报送助手",
        "关于系统品牌区仅保留 Logo",
        "移除中点分隔",
    ]:
        assert text in readme


def test_version_203_documents_brand_logo_update():
    app_js = _read(APP_JS)
    readme = _read(README_MD)

    for text in [
        "v2.0.3",
        "新增准星·监管报送助手品牌名称和系统 Logo。",
        "系统优化及BUG修复。",
    ]:
        assert text in app_js

    for text in [
        "v2.0.3",
        "系统对外名称更新为“准星·监管报送助手”",
        "使用 `logo/scheme-D-zx-grid` 资源包中的 ZX 数据网格设计替换系统 Logo",
        "登录页功能卡片中的旧闪电符号替换为校验符号",
        "前端静态测试同步更新品牌、版本和 Logo 资源断言",
    ]:
        assert text in readme


def test_version_202_documents_security_login_update():
    app_js = _read(APP_JS)
    readme = _read(README_MD)

    for text in [
        "v2.0.2",
        "导出 Excel 新增处理脚本列。",
        "新增用户姓名，导航用户按钮、用户列表和执行历史优先显示姓名。",
        "新增对数任务全局互斥和一键导入同表冲突提示。",
        "系统优化及BUG修复。",
    ]:
        assert text in app_js

    for text in [
        "v2.0.2",
        "自动对数导出 Excel 新增“处理脚本”列",
        "系统时间统一按北京时间生成和展示",
        "核对历史按核对日期倒序、同日按执行时间倒序排列",
        "登录页页签标题与主应用保持英文一致",
        "登录和用户管理密码规则调整为至少 6 位且包含字母",
        "首页趋势和核对历史展示全部对数记录",
        "MySQL 数据源隐藏 Schema 输入",
        "一键导入上传解析支持自动跳过模板标题区",
        "用户列表进入页面时使用稳定骨架加载态",
    ]:
        assert text in readme

    for verbose_text in [
        "FA 与 AM 标的不一致时生成修正 SQL",
        "执行日志显示失败原因、正在执行用户和可再次执行提示",
        "登录页浅色和暗色模式按钮、品牌图标、特性图标统一",
        "沉稳主题下系统设置栏目图标背景统一",
        "导出、历史详情、执行日志和登录体验优化。",
        "默认数据源切换增加即时反馈，用户列表加载更稳定。",
        "默认数据源切换先在本地置顶并播放切换动画",
    ]:
        assert verbose_text not in app_js


def test_version_201_documents_confirm_button_update():
    app_js = _read(APP_JS)
    readme = _read(README_MD)

    for text in [
        "v2.0.1",
        "系统优化及BUG修复。",
    ]:
        assert text in app_js

    for verbose_text in [
        "导入确认弹窗、系统设置和业务设置布局优化。",
        "主题滚动层次和暗色模式对比度优化。",
    ]:
        assert verbose_text not in app_js

    for text in [
        "v2.0.1",
        "导入确认弹窗按钮更清晰",
        "系统设置改为太空科技三列卡片布局",
        "太空主题导航上下内容模糊感加重",
    ]:
        assert text in readme


def test_business_settings_displays_current_table_field_mapping():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)
    readme = _read(README_MD)

    assert 'id="businessSettingsBody"' in html
    assert 'id="businessSettingsContent"' in html
    assert 'id="initReconcileSchemaFromFileBtn"' in html
    assert 'id="reconcileSchemaForm"' in html
    assert html.index('id="initReconcileSchemaFromFileBtn"') < html.index('id="reconcileSchemaForm"')
    business_card = re.search(
        r'<section class="card settings-dashboard-card card-business admin-only">(?P<body>.*?)</section>',
        html,
        re.S,
    )
    assert business_card is not None
    business_header = re.search(
        r'<div class="card-header">(?P<body>.*?)</div>\s*<div id="businessSettingsBody"',
        business_card.group("body"),
        re.S,
    )
    assert business_header is not None
    assert 'id="initReconcileSchemaFromFileBtn"' in business_header.group("body")
    assert 'id="saveReconcileSchemaBtn"' in business_header.group("body")
    schema_panel_head = business_card.group("body")[
        business_card.group("body").index('<div class="reconcile-settings-panel reconcile-schema-panel">'):
        business_card.group("body").index('<div id="reconcileSchemaForm"')
    ]
    assert 'id="initReconcileSchemaFromFileBtn"' not in schema_panel_head
    assert 'id="saveReconcileSchemaBtn"' not in schema_panel_head
    assert 'id="reconcileSchemaEditor"' not in html
    assert "function renderBusinessSettings()" in app_js
    assert "function loadReconcileSchemaSettings()" in app_js
    assert "function renderReconcileSchemaForm(" in app_js
    assert "function readReconcileSchemaForm()" in app_js
    assert "function loadReconcileTableColumns(" in app_js
    assert "function currentBusinessFieldGroups()" in app_js
    assert "function filterReconcileColumnOptions(" in app_js
    assert "function renderReconcileFieldOptions(" in app_js
    assert "function splitFrontendReconcileSchemaMissingItems(" in app_js
    assert "function parseReconcileSchemaErrorItem(" in app_js
    assert "function formatReconcileSchemaSaveErrors(" in app_js
    assert "function showReconcileSchemaSaveError(" in app_js
    assert "function readTrimmedControlValue(" in app_js
    assert "const fallback = optional ? tableConfig.fields : tableConfig.optional_fields;" in app_js
    assert "function validateReconcileSchemaRequiredFields(" in app_js
    assert "function markReconcileSchemaRequiredError(" in app_js
    assert "function clearReconcileSchemaRequiredErrors(" in app_js
    assert "function expandReconcileSchemaTable(" in app_js
    assert "function reconcileSchemaVisibleControl(" in app_js
    assert "function selectReconcileSchemaFieldOption(" in app_js
    assert "function reconcileSchemaFieldOptionsOpen(" in app_js
    assert "function openReconcileFieldOptionsForInput(" in app_js
    assert "reconcile-schema-required-error" in app_js
    assert "reconcile-schema-error-message" in app_js
    assert "v2.1" in app_js
    assert "scrollIntoView" in app_js
    assert 'querySelector("select.reconcile-schema-source")' in app_js
    assert 'querySelector("input.reconcile-schema-display-name")' in app_js
    assert 'querySelector("input.reconcile-schema-table-name")' in app_js
    assert 'input.reconcile-schema-field-search' in app_js
    assert 'tableEl.querySelector(".reconcile-schema-source")' not in app_js
    assert 'tableEl.querySelector(".reconcile-schema-display-name")' not in app_js
    assert 'tableEl.querySelector(".reconcile-schema-table-name")' not in app_js
    assert 'loadReconcileTableColumns(key, { openCombo: combo' in app_js
    assert "reconcile-schema-load-columns" not in app_js
    assert ">读取字段</button>" not in app_js
    assert "loadReconcileTableColumns(key, { openCombo: combo" in app_js
    assert "reconcile-schema-field-combobox" in app_js
    assert "reconcile-schema-display-name" in app_js
    assert "标准中文名" in app_js
    assert "function currentReconcileTableDisplayName(" in app_js
    assert "displayName: currentReconcileTableDisplayName(primaryKey, group.table)" in app_js
    assert "<strong>${escapeHtml(group.displayName || group.table)}</strong>" in app_js
    assert "display_name: displayName" in app_js
    assert "reconcile-schema-field-search" in app_js
    assert '<div class="reconcile-schema-field-row">' in app_js
    assert '<label class="reconcile-schema-field-row">' not in app_js
    assert "reconcile-schema-field-option-name" in app_js
    assert "reconcile-schema-field-option-comment" in app_js
    assert 'optionalFields: [["data_source"' not in app_js
    assert 'optionalFields: [["contract_start_date"' not in app_js
    assert "delete optionalFields[fieldKey];" in app_js
    assert 'reconcileSchemaForm?.addEventListener("mousedown"' in app_js
    assert app_js.index('reconcileSchemaForm?.addEventListener("mousedown"') < app_js.index('reconcileSchemaForm?.addEventListener("focusin"')
    assert 'if (event.target.closest(".reconcile-schema-field-option")) return;' in app_js
    assert 'event.target.closest("input.reconcile-schema-field-search")' in app_js
    assert "_reconcileSuppressNextInputClick" in app_js
    assert "openReconcileFieldOptionsForInput(fieldInput)" in app_js
    assert 'reconcileSchemaForm?.addEventListener("keydown"' in app_js
    assert 'if (event.key === "Escape") closeReconcileFieldOptions(reconcileSchemaForm);' in app_js
    assert 'closeReconcileFieldOptions(reconcileSchemaForm);' in app_js[app_js.index('const toggle = event.target.closest(".reconcile-schema-toggle");'):app_js.index('reconcileSchemaForm?.addEventListener("input"')]
    assert "event.preventDefault();" in app_js[app_js.index('const option = event.target.closest(".reconcile-schema-field-option[data-value]");'):app_js.index('const toggle = event.target.closest(".reconcile-schema-toggle");')]
    assert "showInfo(title, `" in app_js
    assert "modal-info--reconcile-schema-error" in app_js
    assert "reconcile-schema-save-error" in app_js
    assert "reconcile-schema-save-error-table" in app_js
    assert "reconcile-schema-field-select" not in app_js
    assert "<datalist" not in app_js
    assert 'querySelector(`.reconcile-schema-field-combobox[data-field-key="${fieldKey}"] .reconcile-schema-field-search`)?.value.trim()' not in app_js
    assert "grid-template-columns: repeat(2, minmax(360px, 1fr));" in css
    assert "text-overflow: ellipsis;" in css
    assert "#page-settings .reconcile-schema-required-error" in css
    assert "#page-settings .reconcile-schema-error-message" in css
    assert ".modal-info--reconcile-schema-error" in css
    assert ".reconcile-schema-save-error pre" in css
    assert ".reconcile-schema-save-error-table" in css
    assert "white-space: normal;" in css
    assert "overflow-wrap: anywhere;" in css
    assert "#page-settings .card-header-actions" in css
    assert "向数据库校验表和字段是否真实存在" in readme
    assert "自动对数后台失败日志展示真实错误摘要" in readme
    assert "表字段配置保存失败弹框按缺失字段逐行展示" in readme
    assert "标准中文名" in readme
    assert "/api/settings/reconcile-schema/init-from-file" in app_js
    assert "/api/settings/reconcile-schema/columns" in app_js
    assert "/api/settings/reconcile-schema" in app_js
    assert 'setupSettingsDashboardCollapsible("businessSettingsToggle", "businessSettingsBody")' not in app_js

    for text in [
        "zf_detail_2024",
        "fa_valuationreport_dws",
        "c_projcode",
        "fa_accountbalance_dws",
        "dm.ta_pact_survamt_day_zgxg_dm",
        "ta_pact_detail_dws",
        "am_pactasset_dws",
        "am_projinvest_dws",
        "dm.fa_security_balance_zgxg_dm",
        "dm.am_projinvest_zgxg_dm",
        "dm.am_projinvest_spv_zgxg_dm",
        "zgxg_zhbs.ccqxx",
        "ass_man_reg.ex_pledge_back",
        "currency_report_24.currency_detail_project_2_1_*",
        "currency_report_duration",
        "projinnercode",
        "a0001",
        "f_marketvalue",
        "tpm_clientkind_tusp",
        "tpm_clientkindex",
        "tpm_spvtype",
        "f_alltincom",
        "c_stockcode",
        "c_spv_type",
        "c_assettype",
        "c_datasource",
        "f_acbalance",
        "d_bdate",
        "sbm_seclas_h2024",
        "sbm_gpgqtype_h",
        "sbm_fundtype",
        "pin_gqtype_h",
        "svd_assettype",
        "buyback_money",
        "expenses",
        "每次表名或字段调整时，需要同步更新此业务设置",
    ]:
        assert text in app_js

    assert "c_procode" not in app_js


def test_business_settings_body_scrolls_inside_fixed_dashboard_card():
    css = _read(STYLES_CSS)
    html = _read(INDEX_HTML)

    rule = re.search(
        r"#page-settings \.card-business \.settings-business-scroll\s*\{(?P<body>.*?)\}",
        css,
        re.S,
    )
    assert rule is not None
    assert "overflow-y: auto" in rule.group("body")
    assert 'id="businessSettingsBody" class="card-body settings-business-scroll"' in html
    assert "#businessSettingsBody:not(.collapsed)" not in css


def test_settings_page_uses_space_tech_dashboard_layout_without_extra_theme_modes():
    html = _read(INDEX_HTML)
    css = _read(STYLES_CSS)
    app_js = _read(APP_JS)
    readme = _read(README_MD)
    settings_section = re.search(
        r'<section class="page" id="page-settings">(?P<body>.*?)\n      </section>\n\n      <!-- 确认弹窗 -->',
        html,
        re.S,
    )
    assert settings_section is not None
    settings_html = settings_section.group("body")

    for text in [
        'class="settings-container"',
        'class="page-header settings-page-header"',
        'class="dashboard-grid settings-dashboard-grid"',
        'class="card settings-dashboard-card card-system-info"',
        'class="card settings-dashboard-card card-default"',
        'class="card settings-dashboard-card card-db-validation admin-only"',
        'class="card settings-dashboard-card card-flow admin-only"',
        'class="card settings-dashboard-card card-business"',
        'class="card settings-dashboard-card card-datasource"',
        'class="card settings-dashboard-card card-data admin-only"',
        'class="card settings-dashboard-card card-about"',
        'id="sysInfoBody"',
        'id="defaultSettingsBody"',
        'id="dbValidationSettingsBody"',
        'id="businessSettingsBody"',
        'id="configBody"',
    ]:
        assert text in settings_html

    assert "card-theme" not in settings_html
    assert "主题设置" not in settings_html
    assert 'id="themeBody"' not in settings_html
    system_info_pos = settings_html.index('class="card settings-dashboard-card card-system-info"')
    data_pos = settings_html.index('class="card settings-dashboard-card card-data admin-only"')
    default_pos = settings_html.index('class="card settings-dashboard-card card-default admin-only"')
    db_validation_pos = settings_html.index('class="card settings-dashboard-card card-db-validation admin-only"')
    flow_pos = settings_html.index('class="card settings-dashboard-card card-flow admin-only"')
    datasource_pos = settings_html.index('class="card settings-dashboard-card card-datasource admin-only"')
    business_pos = settings_html.index('class="card settings-dashboard-card card-business admin-only"')
    about_pos = settings_html.index('class="card settings-dashboard-card card-about"')
    assert system_info_pos < data_pos < default_pos < db_validation_pos < flow_pos < datasource_pos < business_pos < about_pos
    assert 'id="businessSettingsBody" class="card-body settings-business-scroll"' in settings_html
    assert "settings-collapsed-card" not in settings_html
    assert "settings-collapsible-body" not in settings_html
    assert "<h2>系统设置</h2>" in settings_html
    about_card = re.search(
        r'<section class="card settings-dashboard-card card-about">(?P<body>.*?)</section>',
        settings_html,
        re.S,
    )
    assert about_card is not None
    assert "about-features" in about_card.group("body")
    assert "about-tech" in about_card.group("body")
    assert "主要功能" in about_card.group("body")
    assert "技术栈" in about_card.group("body")

    assert 'name="theme"' not in html
    assert 'id="themeToggle"' not in html
    assert 'value="dark"' not in html
    assert 'value="auto"' not in html

    dashboard_grid_rule = re.search(
        r"#page-settings \.settings-dashboard-grid\s*\{(?P<body>.*?)\}",
        css,
        re.S,
    )
    assert dashboard_grid_rule is not None
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in dashboard_grid_rule.group("body")
    assert "align-items: stretch" in dashboard_grid_rule.group("body")
    space_container_rule = re.search(
        r"\[data-theme=\"space-tech\"\] #page-settings \.settings-container\s*\{(?P<body>.*?)\}",
        css,
        re.S,
    )
    assert space_container_rule is not None
    assert "max-width: none" in space_container_rule.group("body")
    assert "[data-theme=\"space-tech\"] #page-settings .settings-page-header" in css
    assert "display: none" in re.search(
        r"\[data-theme=\"space-tech\"\] #page-settings \.settings-page-header\s*\{(?P<body>.*?)\}",
        css,
        re.S,
    ).group("body")

    for pattern in [
        r"#page-settings \.settings-container\s*\{",
        r"#page-settings \.settings-dashboard-card\s*\{",
        r"#page-settings \.card-business \.settings-business-scroll\s*\{",
        r"#page-settings \.card-business,\s*#page-settings \.card-about\s*\{",
        r"#page-settings \.config-item-name\s*\{",
        r"#page-settings \.config-item-info\s*\{",
        r"#page-settings \.config-item-actions\s*\{",
        r"#page-settings \.reconcile-settings-panel\s*\{",
        r"#page-settings \.db-validation-source-row\s*\{",
        r"\[data-theme=\"space-tech\"\] #page-settings \.settings-dashboard-card\s*\{",
        r"\[data-theme=\"space-tech\"\]\[data-color-mode=\"dark\"\] #page-settings \.settings-dashboard-card\s*\{",
    ]:
        assert re.search(pattern, css) is not None

    assert "对账业务设置" in html
    assert "function getReconcileBusinessSourceName()" in app_js
    assert "function loadReconcileSchemaSettings()" in app_js
    assert "/api/settings/reconcile-schema/init-from-file" in app_js
    assert "filterRunsByReconcileBusinessSource" not in app_js
    assert "全部数据源" in app_js
    assert "defaultConfigSwitchAnimationName" not in app_js
    assert 'config-item--default-switched' not in app_js
    assert "function applyDefaultConfigLocally" not in app_js
    assert "设为默认" not in html
    assert "modalSetDefault" not in html

    span_one_rule = re.search(
        r"#page-settings \.card-system-info,\s*#page-settings \.card-data,\s*#page-settings \.card-default,\s*#page-settings \.card-flow,\s*#page-settings \.card-about\s*\{(?P<body>.*?)\}",
        css,
        re.S,
    )
    span_two_rule = re.search(
        r"#page-settings \.card-datasource,\s*#page-settings \.card-business\s*\{(?P<body>.*?)\}",
        css,
        re.S,
    )
    db_validation_rule = re.search(
        r"#page-settings \.card-db-validation\s*\{(?P<body>.*?)\}",
        css,
        re.S,
    )
    assert span_one_rule is not None
    assert span_two_rule is not None
    assert db_validation_rule is not None
    assert "grid-column: span 1" in span_one_rule.group("body")
    assert "grid-column: span 2" in span_two_rule.group("body")
    assert "grid-column: 1 / -1" in db_validation_rule.group("body")
    assert "db-validation-settings-grid" in settings_html
    assert settings_html.count('class="db-validation-source-row') == 4
    assert settings_html.index("报表信息配置数据源") < settings_html.index("逐笔数据源")
    assert "字段匹配数据源" not in settings_html
    assert settings_html.count('<span class="setting-label">报送子系统编号</span>') == 3
    assert settings_html.count('<span class="setting-label">分类编号</span>') == 3
    assert settings_html.count("填写报送子系统编号，多个用;分隔") == 3
    assert settings_html.count("填写分类编号，多个用;分隔") == 3
    assert "对账报表库数据源" not in settings_html
    assert "对账业务库数据源" not in settings_html
    assert '<span class="setting-label">sys_manage_id</span>' not in settings_html
    assert '<span class="setting-label">classification_id</span>' not in settings_html
    assert 'id="dbValidationBaseinfoTable" type="hidden"' in settings_html
    assert 'id="dbValidationFieldInfoTable" type="hidden"' in settings_html
    assert 'id="dbValidationPublicInfoTable" type="hidden"' in settings_html
    assert '<span class="setting-label">公开信息表</span>' not in settings_html
    assert "minmax(240px, 320px)" in css
    assert "minmax(260px, 1fr)" in css
    assert ".db-validation-filter-input:last-of-type" in css
    assert "人行逐笔校验引擎独占整行" in readme
    assert "数据管理移动至原主题设置位置" in readme
    assert "对账业务设置前移至数据源配置后" in readme
    assert "对账业务设置隐藏旧版全局对账数据源选择" in readme
    assert "自动对数执行以表字段配置中的表级数据源为准" in readme
    assert "系统信息改为展示历史核对次数、登录用户和首页自动刷新等运行指标" in readme
    assert "系统设置中的“对账业务设置”" in readme
    equal_height_rule = re.search(
        r"#page-settings \.card-business,\s*#page-settings \.card-about\s*\{(?P<body>.*?)\}",
        css,
        re.S,
    )
    assert equal_height_rule is not None
    assert "height: 800px" in equal_height_rule.group("body")
    assert "overflow-y: auto" in re.search(
        r"#page-settings \.card-business \.settings-business-scroll\s*\{(?P<body>.*?)\}",
        css,
        re.S,
    ).group("body")
    about_body_rule = re.search(
        r"#page-settings \.card-about \.card-body\s*\{(?P<body>.*?)\}",
        css,
        re.S,
    )
    assert about_body_rule is not None
    assert "overflow-y: auto" not in about_body_rule.group("body")
    assert "overflow: visible" in about_body_rule.group("body")
    assert 'setupSettingsDashboardCollapsible("businessSettingsToggle", "businessSettingsBody")' not in app_js
    assert "settings-expanded-card" not in css
    assert "settings-expanded-card" not in app_js
    assert "<h4>主要功能</h4>" in app_js
    assert "<h4>技术栈</h4>" in app_js

    assert 'class="settings-header"' not in html
    assert ".settings-header" not in css
    assert 'if (!toggle.classList.contains("collapsible")) return;' in app_js
    assert 'if (!configToggle.classList.contains("collapsible")) return;' in app_js


def test_settings_dark_mode_keeps_business_codes_and_about_links_readable():
    css = _read(STYLES_CSS)

    assert '[data-theme="space-tech"][data-color-mode="dark"] #page-settings .business-field-table code' in css
    assert '[data-theme="space-tech"][data-color-mode="dark"] #page-settings .about-links a' in css
    dark_code_rule = re.search(
        r'\[data-theme="space-tech"\]\[data-color-mode="dark"\] #page-settings \.business-field-table code\s*\{(?P<body>.*?)\}',
        css,
        re.S,
    )
    dark_link_rule = re.search(
        r'\[data-theme="space-tech"\]\[data-color-mode="dark"\] #page-settings \.about-links a\s*\{(?P<body>.*?)\}',
        css,
        re.S,
    )
    assert dark_code_rule is not None
    assert dark_link_rule is not None
    assert "color: #dbeafe" in dark_code_rule.group("body")
    assert "color: #7dd3fc" in dark_link_rule.group("body")


def test_home_chart_empty_state_keeps_centered_chart_structure():
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert "function setChartEmptyState" in app_js
    for function_name in ["renderChart", "renderTrendChart"]:
        body = re.search(rf"async function {function_name}\(\) \{{(?P<body>.*?)\n\}}", app_js, re.S)
        assert body is not None
        assert "container.innerHTML" not in body.group("body")
        assert "setChartEmptyState" in body.group("body")

    placeholder_rule = re.search(
        r"\.chart-container \.placeholder-text\s*\{(?P<body>.*?)\}",
        css,
        re.S,
    )
    assert placeholder_rule is not None
    rule_body = placeholder_rule.group("body")
    assert "position: absolute" in rule_body
    assert "inset: 0" in rule_body
    assert "align-items: center" in rule_body
    assert "justify-content: center" in rule_body


def test_home_chart_loading_state_is_animated():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert 'class="chart-loading-indicator"' in html
    assert "function setChartLoadingState" in app_js
    assert 'setChartLoadingState(container, true);' in app_js
    assert 'setChartLoadingState(container, false);' in app_js
    assert ".chart-loading-indicator" in css
    assert "@keyframes chartLoadingPulse" in css


def test_home_trend_curve_control_points_stay_inside_plot_area():
    app_js = _read(APP_JS)
    smooth_curve = re.search(
        r"function smoothCurveThrough\(ctx, pts, tension = 0\.35, bounds = null\) \{(?P<body>.*?)\n\}",
        app_js,
        re.S,
    )

    assert "function clampNumber" in app_js
    assert smooth_curve is not None
    assert "clampNumber(cp1y" in smooth_curve.group("body")
    assert "clampNumber(cp2y" in smooth_curve.group("body")
    assert "{ top: pad.top, bottom: pad.top + ph }" in app_js


def test_space_tech_theme_has_structural_top_navigation_and_switching():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert 'class="top-nav"' in html
    for page in ["home", "auto-check", "history", "settings"]:
        assert f'class="top-nav-item" data-page="{page}"' in html
    assert html.count('data-theme-toggle-logo') == 2
    assert 'class="brand-theme-toggle sidebar-brand-theme-toggle"' in html
    assert 'class="brand-theme-toggle top-nav-mark"' in html
    assert 'aria-label="切换主题"' in html
    assert 'name="theme"' not in html
    assert 'name="theme" value="dark"' not in html
    assert 'name="theme" value="auto"' not in html

    for text in [
        'theme === "space-tech"',
        'document.documentElement.setAttribute("data-theme", "space-tech")',
        "function syncNavState",
        "topNavItems",
        "async function saveAndApplyTheme",
        "function runThemeShellTransition",
        "function applyThemeWithTransition",
        "document.startViewTransition",
        "function getNextTheme",
        "function toggleThemeFromLogo",
        "theme-shell-transitioning",
        "theme-shell-to-space-tech",
        "theme-shell-to-light",
        "theme-shell-view-transitioning",
        'document.querySelectorAll("[data-theme-toggle-logo]")',
    ]:
        assert text in app_js
    assert 'document.querySelectorAll(".theme-option")' not in app_js

    for selector in [
        '[data-theme="space-tech"] .top-nav',
        '[data-theme="space-tech"] .sidebar',
        '[data-theme="space-tech"] .main-content',
        '[data-theme="space-tech"] .top-nav-status',
        '.theme-shell-transitioning .sidebar',
        '.theme-shell-transitioning .top-nav',
        '.theme-shell-transitioning .main-content',
        '.theme-shell-to-space-tech .sidebar',
        '.theme-shell-to-space-tech .top-nav',
        '.theme-shell-to-space-tech .main-content',
        '.theme-shell-to-light .sidebar',
        '.theme-shell-to-light .top-nav',
        '.theme-shell-to-light .main-content',
        '.theme-shell-view-transitioning .main-content',
        '@keyframes sidebarToTopNav',
        '@keyframes topNavToSidebar',
        '@keyframes mainContentExpandLeft',
        '@keyframes mainContentContractRight',
        '::view-transition-old(root)',
        '::view-transition-new(root)',
        '@keyframes themeViewOldToSpace',
        '@keyframes themeViewNewToLight',
    ]:
        assert selector in css

    main_transition = re.search(r"\.theme-shell-transitioning \.main-content\s*\{(?P<body>.*?)\}", css, re.S)
    shell_transition = re.search(
        r"\.theme-shell-transitioning \.sidebar,\s*"
        r"\.theme-shell-transitioning \.top-nav\s*\{(?P<body>.*?)\}",
        css,
        re.S,
    )
    expand_keyframes = re.search(r"@keyframes mainContentExpandLeft\s*\{(?P<body>.*?)\n\}", css, re.S)
    contract_keyframes = re.search(r"@keyframes mainContentContractRight\s*\{(?P<body>.*?)\n\}", css, re.S)
    assert shell_transition is not None
    assert main_transition is not None
    assert expand_keyframes is not None
    assert contract_keyframes is not None
    assert "display: flex !important" not in shell_transition.group("body")
    assert "will-change: transform, opacity" in main_transition.group("body")
    assert "margin-left" not in main_transition.group("body")
    assert "margin-left" not in expand_keyframes.group("body")
    assert "margin-left" not in contract_keyframes.group("body")
    assert "scaleX" not in expand_keyframes.group("body")
    assert "scaleX" not in contract_keyframes.group("body")
    assert "translate3d(220px, 0, 0)" in expand_keyframes.group("body")
    assert "translate3d(-220px, 0, 0)" in contract_keyframes.group("body")
    view_transition_live_rule = re.search(
        r"\.theme-shell-view-transitioning \.sidebar,\s*"
        r"\.theme-shell-view-transitioning \.top-nav,\s*"
        r"\.theme-shell-view-transitioning \.main-content\s*\{(?P<body>.*?)\}",
        css,
        re.S,
    )
    assert view_transition_live_rule is not None
    assert "animation: none !important" in view_transition_live_rule.group("body")

    top_nav_brand = re.search(r'\[data-theme="space-tech"\] \.top-nav-brand\s*\{(?P<body>.*?)\}', css, re.S)
    assert top_nav_brand is not None
    assert "flex: 1 1 auto" in top_nav_brand.group("body")
    assert "max-width: calc(100% - 600px)" in top_nav_brand.group("body")

    top_nav_tabs = re.search(r'\[data-theme="space-tech"\] \.top-nav-tabs\s*\{(?P<body>.*?)\}', css, re.S)
    assert top_nav_tabs is not None
    assert "flex: 0 0 auto" in top_nav_tabs.group("body")

    top_status = re.search(r'\[data-theme="space-tech"\] \.top-nav-status\s*\{(?P<body>.*?)\}', css, re.S)
    assert top_status is not None
    assert "flex: 0 0 auto" in top_status.group("body")
    assert "max-width: 200px" in top_status.group("body")

    top_notice_status = re.search(
        r'\[data-theme="space-tech"\] \.top-nav-status\.top-nav-status--notice\s*\{(?P<body>.*?)\}',
        css,
        re.S,
    )
    assert top_notice_status is not None
    assert "flex: 0 1 auto" in top_notice_status.group("body")
    assert "max-width: min(680px, 42vw)" in top_notice_status.group("body")
    assert 'topNavStatus.classList.toggle("top-nav-status--notice", nextText !== DEFAULT_VERSION);' in app_js
    assert 'topNavStatus.classList.remove("top-nav-status--notice");' in app_js


def test_space_tech_theme_uses_reference_light_palette():
    css = _read(STYLES_CSS)
    theme = re.search(r"\[data-theme=\"space-tech\"\]\s*\{(?P<body>.*?)\}", css, re.S)

    assert theme is not None
    body = theme.group("body")
    for text in [
        "color-scheme: light",
        "--surface: #f8fafc",
        "--surface-container-lowest: #ffffff",
        "--on-surface: #0f172a",
        "--secondary: #3b82f6",
        "--space-gradient-primary: linear-gradient(135deg, #3b82f6, #06b6d4, #8b5cf6)",
    ]:
        assert text in body
    assert '[data-theme="space-tech"] body' in css
    assert "rgba(255, 255, 255, 0.72)" in css


def test_space_tech_theme_hides_in_page_heading_text_and_tightens_gap():
    css = _read(STYLES_CSS)

    assert '[data-theme="space-tech"] .page-header h2' in css
    assert '[data-theme="space-tech"] .page-header' in css
    assert "padding: 76px 32px 32px" in css
    assert "padding: 86px 14px 18px" in css


def test_theme_is_saved_per_user_without_updating_global_defaults():
    app_js = _read(APP_JS)

    for text in [
        'theme: "space-tech"',
        'darkMode: "false"',
        "function normalizeDarkMode",
        "darkMode === true",
        "const THEME_ACTIVE_USER_KEY",
        "function themeStorageKey(baseKey)",
        "function saveUserThemePreference(keyBase, value)",
        "function withSavedUserTheme(settings = {})",
        "let serverDefaultSettings",
        "activateThemeUserStorage();",
        "applySavedUserTheme();",
        "theme: settings.theme",
        "darkMode: normalizeDarkMode(settings.darkMode)",
        "theme: normalized.theme",
        "dark_mode: normalized.darkMode",
        "async function saveAndApplyTheme",
        "async function saveAndApplyDarkMode",
        "defaultSettings.theme = theme",
        "defaultSettings.darkMode = darkMode",
        "theme: serverDefaultSettings.theme",
        "darkMode: serverDefaultSettings.darkMode",
    ]:
        assert text in app_js

    save_theme = re.search(r"async function saveAndApplyTheme\(theme, options = \{\}\) \{(?P<body>.*?)\n\}", app_js, re.S)
    save_dark = re.search(r"async function saveAndApplyDarkMode\(darkMode\) \{(?P<body>.*?)\n\}", app_js, re.S)
    assert save_theme is not None
    assert save_dark is not None
    assert 'api("/api/settings/defaults"' not in save_theme.group("body")
    assert 'api("/api/settings/defaults"' not in save_dark.group("body")


def test_theme_is_applied_before_stylesheet_and_keeps_local_boot_cache():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)

    assert 'id="initialThemeScript"' in html
    assert html.index('id="initialThemeScript"') < html.index('href="/styles.css"')
    for text in ["autoCheckTheme", "autoCheckDarkMode", "data-theme", "data-color-mode"]:
        assert text in html

    assert "function syncThemeBootCache" in app_js
    assert 'const activeThemeUser = localStorage.getItem("autoCheckThemeUserKey") || "";' in html
    assert 'localStorage.setItem(themeKey, defaultSettings.theme)' in app_js
    assert 'localStorage.setItem(darkModeKey, defaultSettings.darkMode)' in app_js
    assert 'localStorage.removeItem("autoCheckTheme")' not in app_js
    assert 'localStorage.removeItem("autoCheckDarkMode")' not in app_js


def test_latest_result_detail_list_is_restored_from_local_snapshot_before_history_fetch():
    app_js = _read(APP_JS)

    for text in [
        "const LATEST_RESULTS_SNAPSHOT_KEY",
        "function saveLatestResultsSnapshot",
        "function restoreLatestResultsSnapshot",
        "function clearLatestResultsSnapshot",
        "autoCheckLatestResults",
        "saveLatestResultsSnapshot(",
    ]:
        assert text in app_js

    initial_load = re.search(r"// Initial load(?P<body>.*?loadSystemInfo\(\);)", app_js, re.S)
    assert initial_load is not None
    body = initial_load.group("body")
    assert body.index("restoreLatestResultsSnapshot()") < body.index("await loadLatestHistoryResults()")


def test_tool_and_settings_page_loaders_are_isolated():
    app_js = _read(APP_JS)

    assert "async function loadPageSection" in app_js
    assert "async function loadToolsPageData" in app_js
    assert "async function loadSettingsPageData" in app_js

    tools_loader = re.search(r"async function loadToolsPageData\(\) \{(?P<body>.*?)\n\}", app_js, re.S)
    assert tools_loader is not None
    tools_body = tools_loader.group("body")
    assert "Promise.all" in tools_body
    assert 'loadPageSection("PBC导入配置", loadPbcImportSettings)' in tools_body
    assert 'loadPageSection("逐笔校验配置", loadDbValidationSettings)' in tools_body
    assert 'loadPageSection("流程执行配置", loadFlowSettings)' in tools_body

    settings_loader = re.search(r"async function loadSettingsPageData\(\) \{(?P<body>.*?)\n\}", app_js, re.S)
    assert settings_loader is not None
    settings_body = settings_loader.group("body")
    assert "Promise.all" in settings_body
    assert 'loadPageSection("系统信息", loadSystemInfo)' in settings_body
    assert 'loadPageSection("数据源配置", loadConfigList)' in settings_body
    assert 'loadPageSection("逐笔校验配置", loadDbValidationSettings)' in settings_body
    assert 'loadPageSection("流程执行配置", loadFlowSettings)' in settings_body
    assert 'loadPageSection("业务字段配置", loadReconcileSchemaSettings)' in settings_body
    assert "applySettingsRoleAccess();" in settings_body

    switch_page = re.search(r"async function switchPage\(name, options = \{\}\) \{(?P<body>.*?)\n\}", app_js, re.S)
    assert switch_page is not None
    switch_body = switch_page.group("body")
    assert 'if (name === "tools") loadToolsPageData();' in switch_body
    assert 'if (name === "settings") loadSettingsPageData();' in switch_body
    assert 'if (name === "tools") await loadToolsPageData();' not in switch_body
    assert 'if (name === "settings") await loadSettingsPageData();' not in switch_body
    assert 'await loadPbcImportSettings(); await loadDbValidationSettings(); await loadFlowSettings();' not in switch_body


def test_system_info_uses_lightweight_summary_api():
    app_js = _read(APP_JS)

    load_system_info = re.search(r"async function loadSystemInfo\(\) \{(?P<body>.*?)\n\}", app_js, re.S)
    assert load_system_info is not None
    body = load_system_info.group("body")
    assert 'api("/api/system-info")' in body
    assert 'api("/api/history")' not in body


def test_tool_settings_load_failures_render_visible_placeholders():
    app_js = _read(APP_JS)

    assert "function renderDbValidationSettingsLoading" in app_js
    assert "function renderDbValidationSettingsError" in app_js
    assert "正在加载逐笔校验配置" in app_js
    assert "逐笔校验配置加载失败" in app_js

    assert "function renderFlowSettingsLoadError" in app_js
    assert "流程链配置加载失败" in app_js
    assert "flowStartBtn.disabled = true" in app_js


def test_db_validation_field_mapping_warns_when_metadata_is_partial():
    app_js = _read(APP_JS)

    assert "少于系统内置表单" in app_js
    assert "请检查字段映射数据源、baseinfo/field_info 或筛选条件" in app_js


def test_pbc_import_tool_is_exposed_in_tools_page():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)

    assert 'data-page="tools"' in html
    assert 'id="page-tools"' in html
    assert 'id="toolCardPbc"' in html
    assert 'id="pbcModalOverlay"' in html
    for element_id in [
        "pbcZipFile",
        "pbcUploadArea",
        "pbcFileList",
        "pbcDataSource",
        "pbcTargetTable",
        "pbcMappingList",
        "pbcImportLog",
        "pbcProgressFill",
        "pbcProgressPercent",
        "pbcNextBtn",
        "pbcFinishBtn",
    ]:
        assert f'id="{element_id}"' in html

    for endpoint in [
        "/api/tools/pbc-import/settings",
        "/api/tools/pbc-import/upload",
        "/api/tools/pbc-import/columns",
        "/api/tools/pbc-import/start",
        "/api/tools/pbc-import/status/",
    ]:
        assert endpoint in app_js


def test_pbc_import_tool_is_generic_one_click_import_with_upload_progress():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert "一键导入工具" in html
    assert "支持任何数据批量导入，自动校验数据完整性与格式合规性，快速完成导入流程。" in html
    assert "支持人行产品数据批量导入" not in html
    assert "人行全量产品一键导入" not in html
    assert 'id="pbcUploadProgress"' in html
    assert 'id="pbcUploadProgressFill"' in html
    assert "function setPbcUploadState" in app_js
    assert "function uploadPbcFileWithProgress" in app_js
    assert "xhr.upload.onprogress" in app_js
    assert "setPbcUploadState(true" in app_js
    assert ".pbc-upload-area.uploading" in css
    assert ".pbc-upload-progress" in css


def test_pbc_target_table_defaults_to_recent():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)

    assert 'placeholder=""' in html
    assert "function getPbcTargetTable" in app_js
    assert "pbcTargetTable.placeholder" not in app_js
    assert "target_table: getPbcTargetTable()" in app_js
    mapping_handler = re.search(
        r'pbcLoadMappingsBtn\?\.addEventListener\("click", async \(\) => \{(?P<body>.*?)\n\}\);',
        app_js,
        re.S,
    )
    assert mapping_handler is not None
    assert "请填写目标表名" not in mapping_handler.group("body")


def test_pbc_import_modal_flow_and_defaults_do_not_skip_mapping_step():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert '<option value="replace" selected>清空后导入</option>' in html
    assert 'pbcModalOverlay?.addEventListener("click"' not in app_js
    assert "pbcNextBtn.onclick" not in app_js
    assert 'if (pbcCurrentStep === 1) goToStep(2);' in app_js
    assert "function hasPbcActiveMappings()" in app_js
    assert "(pbcCurrentStep === 2 && !hasPbcActiveMappings())" in app_js
    assert "pbcNextBtn?.addEventListener(\"click\", async () => {" in app_js
    assert 'const confirmed = await showConfirm("确认导入", "即将开始数据导入，是否确认？");' in app_js
    assert "if (!confirmed) return;" in app_js
    assert re.search(r"else if \(pbcCurrentStep === 2\) \{(?P<body>.*?)goToStep\(3\);", app_js, re.S)
    assert "updatePbcStepUI();" in re.search(r"async function handlePbcFileUpload\(file\) \{(?P<body>.*?)function renderPbcFileList", app_js, re.S).group("body")
    assert "updatePbcStepUI();" in re.search(r"pbcFileListBody\?\.addEventListener\(\"click\", \(e\) => \{(?P<body>.*?)\}\);", app_js, re.S).group("body")
    assert "updatePbcStepUI();" in re.search(r"function renderPbcMappings\(\) \{(?P<body>.*?)\n\}", app_js, re.S).group("body")

    assert "#confirmModal" in css
    assert "z-index: 3000" in css
    assert 'id="confirmOk" class="btn-confirm-primary"' in html
    assert ".modal-confirm .modal-footer" in css
    assert ".btn-confirm-primary" in css
    assert '[data-color-mode="dark"] .btn-confirm-primary' in css


def test_pbc_import_job_completion_routes_success_and_failure_explicitly():
    app_js = _read(APP_JS)

    assert "function finishPbcImportSuccess(job, targetTable)" in app_js
    assert "function finishPbcImportFailure(job)" in app_js

    success_body = re.search(
        r"function finishPbcImportSuccess\(job, targetTable\) \{(?P<body>.*?)\n\}",
        app_js,
        re.S,
    )
    assert success_body is not None
    assert "pbcCurrentStep = 4;" in success_body.group("body")
    assert "updatePbcStepUI();" in success_body.group("body")
    assert "loadPbcImportSettings();" in success_body.group("body")

    failure_body = re.search(r"function finishPbcImportFailure\(job\) \{(?P<body>.*?)\n\}", app_js, re.S)
    assert failure_body is not None
    assert 'appendPbcLog(`导入失败: ${message}`, "error");' in failure_body.group("body")
    assert 'showToast(`导入失败: ${message}`, "error");' in failure_body.group("body")
    assert "pbcImportFailed = true;" in failure_body.group("body")
    assert 'setPbcImportProgressState("导入失败"' in failure_body.group("body")
    assert "pbcCurrentStep = 3;" in failure_body.group("body")
    assert "updatePbcStepUI();" in failure_body.group("body")

    poll_body = re.search(r"async function pollPbcImportJob\(jobId, targetTable\) \{(?P<body>.*?)\n\}", app_js, re.S)
    assert poll_body is not None
    assert "finishPbcImportFailure(job);" in poll_body.group("body")
    assert "finishPbcImportSuccess(job, targetTable);" in poll_body.group("body")


def test_pbc_file_list_counts_and_actions_are_centered():
    css = _read(STYLES_CSS)

    file_list = re.search(r"(?m)^\.pbc-file-list\s*\{(?P<body>.*?)\}", css, re.S)
    assert file_list is not None
    assert "--pbc-file-cols-width" in file_list.group("body")
    assert "--pbc-file-action-width" in file_list.group("body")
    assert "--pbc-file-scrollbar-width" in file_list.group("body")

    header_layout = re.search(r"(?m)^\.pbc-file-list-header\s*\{(?P<body>.*?)\}", css, re.S)
    assert header_layout is not None
    assert "minmax(0, 1fr)" in header_layout.group("body")
    assert "var(--pbc-file-cols-width)" in header_layout.group("body")
    assert "var(--pbc-file-action-width)" in header_layout.group("body")
    assert "var(--pbc-file-scrollbar-width)" in header_layout.group("body")

    body_layout = re.search(r"(?m)^#pbcFileListBody\s*\{(?P<body>.*?)\}", css, re.S)
    assert body_layout is not None
    assert "scrollbar-gutter: stable" in body_layout.group("body")

    row_layout = re.search(r"(?m)^\.pbc-file-list-row\s*\{(?P<body>.*?)\}", css, re.S)
    assert row_layout is not None
    assert "minmax(0, 1fr)" in row_layout.group("body")
    assert "var(--pbc-file-cols-width)" in row_layout.group("body")
    assert "var(--pbc-file-action-width)" in row_layout.group("body")

    header_centering = re.search(r"(?m)^\.pbc-file-list-header span:nth-child\(2\),\s*\n\.pbc-file-list-header span:nth-child\(3\)\s*\{(?P<body>.*?)\}", css, re.S)
    assert header_centering is not None
    assert "text-align: center" in header_centering.group("body")

    row_centering = re.search(r"(?m)^\.pbc-file-list-row > span:nth-child\(2\),\s*\n\.pbc-file-list-row > span:nth-child\(3\)\s*\{(?P<body>.*?)\}", css, re.S)
    assert row_centering is not None
    row_body = row_centering.group("body")
    assert "display: flex" in row_body
    assert "justify-content: center" in row_body
    assert "align-items: center" in row_body


def test_toast_deduplicates_same_message_and_type():
    app_js = _read(APP_JS)

    start = app_js.index('function showToast(message, type = "info")')
    end = app_js.index("// Theme Settings", start)
    body = app_js[start:end]
    assert "toast.dataset.message = message;" in app_js
    assert "toast.dataset.type = type;" in app_js
    assert 'toastContainer.querySelector(`[data-message="${cssEscape(message)}"][data-type="${cssEscape(type)}"]`)' in body
    assert "${message}</span>" not in body
    assert "messageEl.textContent = message;" in body


def test_login_page_uses_gradient_glass_light_default_and_dark_toggle():
    login_html = _read(ROOT / "src" / "auto_check" / "web" / "login.html")

    assert "<title>监管智核</title>" in login_html
    assert 'class="login-container"' in login_html
    assert 'class="left-panel"' in login_html
    assert 'class="right-panel"' in login_html
    assert 'class="light-brand"' in login_html
    assert '<img class="login-brand-logo" src="/assets/logo-login.svg?v=2.0.8-regulatory-intelligence-core-horizontal" alt="监管智核" />' in login_html
    assert "开启您的智能工作台" not in login_html
    assert '<h1>欢迎登录</h1>' not in login_html
    assert "<p>开启您的智能工作台</p>" not in login_html
    assert '<h2 class="welcome-title" id="loginTitle">欢迎登录</h2>' in login_html
    assert '<p class="welcome-subtitle" id="loginSubtitle">请输入管理员密码继续访问系统。</p>' in login_html
    assert 'document.querySelector(".light-brand h1")' not in login_html
    assert 'document.querySelector(".light-brand p")' not in login_html
    assert 'document.getElementById("loginTitle").textContent = titleText;' in login_html
    assert 'document.getElementById("loginSubtitle").textContent = subtitleText;' in login_html
    assert 'class="deco deco-1"' in login_html
    assert "linear-gradient(135deg, #f0fdf4 0%, #ecfeff 30%, #fdf2f8 60%, #fefce8 100%)" in login_html
    assert "backdrop-filter: blur(20px);" in login_html
    assert "border-radius: 24px;" in login_html
    assert "overflow: hidden;" in login_html
    assert "max-width: 440px;" in login_html
    assert "padding: 34px 32px 34px;" in login_html
    assert "text-align: left;" in login_html
    assert "margin-bottom: 14px;" in login_html
    assert "width: min(360px, 100%);" in login_html
    assert "margin: 0;" in login_html
    assert "还没有账户？" in login_html
    assert "去联系管理员" in login_html
    assert 'class="feature-card"' in login_html
    assert 'class="social-login"' in login_html
    assert 'class="forgot-password"' in login_html
    assert 'id="loginThemeToggle"' in login_html
    assert "max-width: 860px;" in login_html
    assert "min-height: 500px;" in login_html
    assert "padding: 52px 44px;" in login_html
    assert '<img class="login-brand-logo login-brand-logo--dark" src="/assets/logo-login-dark.svg?v=2.0.8-regulatory-intelligence-core-horizontal" alt="监管智核" />' in login_html
    assert "width: min(300px, 88%);" in login_html
    assert ':root[data-login-theme="dark"] .welcome-title,' in login_html
    assert ':root[data-login-theme="dark"] .welcome-subtitle {' in login_html
    assert 'class="title brand-wordmark' not in login_html
    assert '<div class="feature-icon">\U0001f4ca</div>' in login_html
    assert '<div class="feature-icon">\u2713</div>' in login_html
    assert '<div class="feature-icon">\U0001f512</div>' in login_html
    assert '<button class="social-btn" type="button" title="\u5fae\u4fe1" data-provider="\u5fae\u4fe1">\U0001f4ac</button>' in login_html
    assert '<button class="social-btn" type="button" title="\u9489\u9489" data-provider="\u9489\u9489">\U0001f4f1</button>' in login_html
    assert '<button class="social-btn" type="button" title="LDAP" data-provider="LDAP">\U0001f510</button>' in login_html
    assert '<html lang="zh-CN" data-login-theme="light">' in login_html
    assert ':root[data-login-theme="dark"] .login-container' in login_html
    assert ':root[data-login-theme="dark"] .form-input:-webkit-autofill' in login_html
    assert "-webkit-text-fill-color: var(--text-primary)" in login_html
    assert "0 0 0 1000px #20242d inset" in login_html
    assert '"/api/auth/login"' in login_html
    assert '"/api/auth/setup"' in login_html
    assert "暂不支持" in login_html


def test_login_page_light_brand_reuses_dark_mode_floating_circle():
    login_html = _read(ROOT / "src" / "auto_check" / "web" / "login.html")
    light_brand = re.search(r"\.light-brand\s*\{(?P<body>.*?)\n      \}", login_html, re.S)
    light_brand_layers = re.search(r"\.light-brand::before,\s*\n      \.light-brand::after\s*\{(?P<body>.*?)\n      \}", login_html, re.S)
    light_brand_circle = re.search(r"\.light-brand::before\s*\{(?P<body>.*?)\n      \}", login_html, re.S)
    login_logo = re.search(r"\.login-brand-logo\s*\{(?P<body>.*?)\n      \}", login_html, re.S)

    assert light_brand is not None
    light_brand_body = light_brand.group("body")
    assert "min-height: 128px;" in light_brand_body
    assert "display: flex;" in light_brand_body
    assert "align-items: center;" in light_brand_body
    assert light_brand_layers is not None
    layer_body = light_brand_layers.group("body")
    assert 'content: "";' in layer_body
    assert "top: 6px;" in layer_body
    assert "left: 12px;" in layer_body
    assert "border-radius: 50%;" in layer_body
    assert "transform-origin: center;" in layer_body
    assert "will-change: transform, opacity;" in layer_body
    assert "animation: lightBrandBubbleFloat 14s linear infinite alternate;" in layer_body
    assert light_brand_circle is not None
    circle_body = light_brand_circle.group("body")
    assert "background: linear-gradient(135deg, rgba(37, 99, 235, 0.18), rgba(6, 182, 212, 0.12), rgba(124, 58, 237, 0.16));" in circle_body
    assert "@keyframes lightBrandBubbleFloat" in login_html
    assert "0%, 10% { transform: translate3d(-28px, 7px, 0)" in login_html
    assert "translate3d(-8px, -22px, 0)" in login_html
    assert "translate3d(22px, 7px, 0)" in login_html
    assert "translate3d(52px, -22px, 0)" in login_html
    assert "translate3d(58px, -16px, 0)" in login_html
    assert "translate3d(63px, -5px, 0)" in login_html
    assert "96%, 100% { transform: translate3d(68px, 7px, 0)" in login_html
    assert "@keyframes lightBrandBubbleWarmth" in login_html
    assert "rgba(37, 99, 235, 0.18)" in login_html
    assert "96%, 100% { opacity: 0.46;" in login_html
    assert "rgba(245, 158, 11, 0.34)" in login_html
    assert "lightBrandBubbleWarmth 14s linear infinite alternate" in login_html
    assert login_logo is not None
    assert "z-index: 1;" in login_logo.group("body")
    assert ":root[data-login-theme=\"dark\"] .light-brand {" in login_html


def test_login_page_light_default_password_copy_and_eye_toggle_are_stable():
    login_html = _read(ROOT / "src" / "auto_check" / "web" / "login.html")

    assert '<html lang="zh-CN" data-login-theme="light">' in login_html
    assert 'applyTheme(localStorage.getItem("autoCheckLoginTheme") || "light")' in login_html
    assert 'placeholder="请输入密码"' in login_html
    assert 'id="loginPasswordToggle"' in login_html
    assert 'class="password-toggle"' in login_html
    assert "function togglePasswordVisibility" in login_html
    assert 'passwordInput.type = passwordInput.type === "password" ? "text" : "password";' in login_html
    assert "::-ms-reveal" in login_html


def test_auth_password_rule_copy_requires_six_chars_and_letter():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    login_html = _read(ROOT / "src" / "auto_check" / "web" / "login.html")
    readme = _read(README_MD)

    for text in [html, app_js, login_html, readme]:
        assert "至少 6 位且包含字母" in text
        assert "至少 8 位" not in text
        assert "至少 8 位密码" not in text

    assert "password must be at least 6 characters and include a letter" in app_js
    assert "密码长度至少 6 位，且需包含至少 1 个字母。" in app_js
    assert "password must be at least 6 characters and include a letter" in login_html
    assert "密码长度至少 6 位，且需包含至少 1 个字母。" in login_html


def test_login_page_uses_same_favicon_as_main_app():
    html = _read(INDEX_HTML)
    login_html = _read(ROOT / "src" / "auto_check" / "web" / "login.html")
    logo = ROOT / "src" / "auto_check" / "web" / "assets" / "logo-full.svg"
    favicon_asset = ROOT / "src" / "auto_check" / "web" / "assets" / "favicon-64x64.svg"

    favicon = re.search(r'<link rel="icon" href="(?P<href>[^"]+)" />', html)
    login_favicon = re.search(r'<link rel="icon" href="(?P<href>[^"]+)" />', login_html)
    assert favicon is not None
    assert login_favicon is not None
    assert login_favicon.group("href") == favicon.group("href")
    assert favicon.group("href") == "/assets/favicon-64x64.svg?v=2.0.8-regulatory-intelligence-core"
    assert logo.exists()
    assert favicon_asset.exists()


def test_login_remember_me_stores_username_without_defaulting_to_admin():
    login_html = _read(ROOT / "src" / "auto_check" / "web" / "login.html")

    assert 'const rememberLogin = document.getElementById("rememberLogin");' in login_html
    assert 'const REMEMBERED_USERNAME_KEY = "autoCheckRememberedUsername";' in login_html
    assert "function loadRememberedUsername()" in login_html
    assert 'localStorage.getItem(REMEMBERED_USERNAME_KEY)' in login_html
    assert 'localStorage.setItem(REMEMBERED_USERNAME_KEY, username);' in login_html
    assert 'localStorage.removeItem(REMEMBERED_USERNAME_KEY);' in login_html
    assert 'usernameInput.value = setupRequired ? "admin" : (usernameInput.value || loadRememberedUsername());' in login_html
    assert 'const username = setupRequired ? "admin" : usernameInput.value.trim();' in login_html
    assert 'usernameInput.value || "admin"' not in login_html
    assert 'usernameInput.value.trim() || "admin"' not in login_html


def test_login_submit_button_is_guarded_while_request_is_pending():
    login_html = _read(ROOT / "src" / "auto_check" / "web" / "login.html")

    assert "let loginSubmitting = false;" in login_html
    assert 'const MAIN_ENTRY_ANIMATION_KEY = "autoCheckMainEntryAnimation";' in login_html
    submit_handler = re.search(
        r'form\.addEventListener\("submit", async \(event\) => \{(?P<body>.*?)\n      \}\);',
        login_html,
        re.S,
    )
    assert submit_handler is not None
    body = submit_handler.group("body")
    assert "if (loginSubmitting) return;" in body
    assert "loginSubmitting = true;" in body
    assert "submitBtn.disabled = true;" in body
    assert body.index("loginSubmitting = true;") < body.index("submitBtn.disabled = true;")
    assert "let loginSucceeded = false;" in body
    assert "loginSucceeded = true;" in body
    assert 'sessionStorage.setItem(MAIN_ENTRY_ANIMATION_KEY, "login");' in body
    assert body.index("loginSucceeded = true;") < body.index('sessionStorage.setItem(MAIN_ENTRY_ANIMATION_KEY, "login");')
    assert "if (!loginSucceeded) {" in body
    assert "loginSubmitting = false;" in body
    assert "submitBtn.disabled = false;" in body


def test_index_hides_home_until_auth_check_finishes():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert '<html lang="zh-CN" class="auth-pending">' in html
    assert ".auth-pending body" in css
    assert 'const MAIN_ENTRY_ANIMATION_KEY = "autoCheckMainEntryAnimation";' in app_js
    assert "function consumeMainEntryAnimationFlag()" in app_js
    assert "function revealAuthenticatedApp()" in app_js
    assert 'sessionStorage.removeItem(MAIN_ENTRY_ANIMATION_KEY);' in app_js
    assert 'document.documentElement.classList.add("main-entry-animate");' in app_js
    assert 'document.documentElement.classList.remove("auth-pending");' in app_js
    assert 'document.documentElement.classList.remove("main-entry-animate");' in app_js
    assert ".main-entry-animate .sidebar" in css
    assert ".main-entry-animate .top-nav" in css
    assert ".main-entry-animate .main-content" in css
    assert "@keyframes mainEntryContent" in css


def test_api_helper_sends_csrf_token_for_mutating_requests():
    app_js = _read(APP_JS)

    start = app_js.index("async function api(path, options = {})")
    end = app_js.index("function setStatus", start)
    body = app_js[start:end]
    assert '"X-CSRF-Token"' in body
    assert "authState.csrfToken" in body
    assert 'window.location.href = "/login.html";' in body


def test_logout_controls_exist_for_space_and_light_themes():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert 'class="sidebar-footer-main"' in html
    assert 'id="sidebarUserMenu"' in html
    assert 'id="topUserMenu"' in html
    assert 'class="user-menu-trigger"' in html
    assert 'class="user-menu-panel"' in html
    assert 'data-current-username' in html
    assert 'data-logout-btn' in html
    assert "退出登录" in html
    assert "/api/auth/logout" in app_js
    assert "async function logout()" in app_js
    assert 'await showConfirm(' in app_js
    logout_body = app_js[app_js.index("async function logout()"):app_js.index("function userDisplayRole")]
    assert "window.confirm" not in logout_body
    assert 'window.location.href = "/login.html";' in app_js
    assert 'document.querySelectorAll("[data-logout-btn]")' in app_js
    assert ".sidebar-footer-main" in css
    assert ".user-menu-trigger" in css
    assert ".user-menu:hover .user-menu-panel" in css
    assert ".user-menu-panel" in css


def test_browser_native_dialogs_are_replaced_by_app_modals():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert 'id="confirmModal"' in html
    assert 'id="promptModal"' in html
    assert 'id="promptInput"' in html
    assert "function showConfirm(title, message)" in app_js
    assert "function showPrompt(title, message, options = {})" in app_js
    assert 'await showPrompt("重置密码"' in app_js
    assert 'await showConfirm("删除历史记录"' in app_js
    assert 'await showConfirm("删除数据源"' in app_js
    assert "#promptModal" in css
    assert ".prompt-input" in css
    assert not re.search(r"\b(?:alert|confirm|prompt)\s*\(", app_js)
    assert "window.alert" not in app_js
    assert "window.confirm" not in app_js
    assert "window.prompt" not in app_js


def test_user_management_page_and_role_based_navigation_are_present():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert 'data-page="users"' in html
    assert 'id="page-users"' in html
    assert 'id="userManagementPage"' in html
    assert 'id="userTableBody"' in html
    assert 'id="userModal"' in html
    assert 'id="userPassword"' in html
    assert 'class="nav-item admin-only" data-page="users"' in html
    assert 'class="top-nav-item admin-only" data-page="users"' in html
    assert "function applyRoleAccess" in app_js
    assert 'document.querySelectorAll(".admin-only")' in app_js
    assert 'authState.user?.role === "admin"' in app_js
    assert 'api("/api/users"' in app_js
    assert 'api(`/api/users/${encodeURIComponent(userId)}`' in app_js
    assert 'api(`/api/users/${encodeURIComponent(userId)}/reset-password`' in app_js
    assert ".user-management" in css
    assert ".user-stats" in css
    assert ".user-table-card" in css
    assert ".role-badge" in css


def test_user_management_table_keeps_action_column_compact():
    html = _read(INDEX_HTML)
    css = _read(STYLES_CSS)

    assert '<th class="user-actions-heading">' in html
    assert '<td class="user-actions-cell">' in _read(APP_JS)
    assert ".user-table col.user-actions-col" in css


def test_admin_local_storage_browser_page_and_api_hooks_are_present():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)
    readme = _read(README_MD)

    assert 'class="nav-item admin-only" data-page="local-storage"' in html
    assert 'class="top-nav-item admin-only" data-page="local-storage"' in html
    assert '<span>本地数据查询</span>' in html
    assert 'data-page="local-storage" href="#">本地数据查询</a>' in html
    assert '<h2>本地数据查询</h2>' in html
    assert 'id="page-local-storage"' in html
    assert 'id="localStorageTableList"' in html
    assert 'id="localStorageDataHead"' in html
    assert 'id="localStorageSchemaBody"' in html
    assert 'id="localStorageInfoPanel"' in html
    assert 'id="localStorageJsonDrawer"' in html
    assert 'id="localStorageExportSchemaBtn"' in html
    assert 'id="localStorageMigrateHistoryBtn"' in html
    assert 'id="localStorageMigrationStatus"' in html
    assert 'id="localStorageExportTableBtn"' in html
    assert 'id="localStorageBackupBtn"' in html
    assert 'id="localStorageRefreshBtn"' in html
    assert 'data-storage-tab="data">数据</button>' in html
    assert 'data-storage-tab="schema">字段</button>' in html
    assert 'data-storage-tab="info">说明</button>' in html
    assert "分页数据按敏感字段脱敏只读展示" in html
    assert "<textarea" not in html
    assert "contenteditable" not in html
    assert 'placeholder="SQL' not in html

    for endpoint in [
        "/api/admin/storage/health",
        "/api/admin/storage/tables",
        "/api/admin/storage/history-migration",
        "/api/admin/storage/schema-export",
        "/api/admin/storage/backup",
        "/export",
    ]:
        assert endpoint in app_js

    assert "function loadLocalStorageBrowser" in app_js
    assert "function localStorageColumnLabel" in app_js
    assert "function isLocalStorageBooleanField" in app_js
    assert "function formatLocalStorageDateTimeValue(value)" in app_js
    assert "formatLocalStorageValue(field, value)" in app_js
    assert "formatLocalStorageDateTimeValue(value)" in app_js
    assert '["enabled", "is_default"]' in app_js
    assert 'if (isLocalStorageBooleanField(field) && value === 1) return "是";' in app_js
    assert "return meta?.cn_name || field;" in app_js
    assert '<th title="${escapeHtml(field)}">${escapeHtml(localStorageColumnLabel(field, fieldMeta[field]))}</th>' in app_js
    assert "localStorageExportTableBtn" in app_js
    assert "localStorageMigrateHistoryBtn" in app_js
    assert "renderLocalStorageMigrationStatus" in app_js
    assert "async function loadLocalStorageMigrationStatus" in app_js
    assert "旧历史迁移已完成" in app_js
    assert "migration.can_migrate" in app_js
    assert "encodeURIComponent(localStorageBrowserState.selectedTable)" in app_js
    assert "分页数据敏感字段脱敏展示" in app_js
    assert 'name === "local-storage" && authState.user?.role !== "admin"' in app_js
    assert 'document.querySelectorAll(".admin-only")' in app_js

    assert ':root[data-page="local-storage"] #page-local-storage' in css
    assert ':root[data-page="local-storage"] body' in css
    assert ':root[data-page="local-storage"] .main-content' in css
    assert ':root[data-page="local-storage"] .top-nav-item[data-page="local-storage"]' in css
    assert "#page-local-storage .local-storage-browser-grid" in css
    assert "#page-local-storage .local-storage-search span" in css
    assert "#page-local-storage .local-storage-search input" in css
    assert "#page-local-storage .local-storage-search:focus-within span" not in css
    assert "#page-local-storage .local-storage-search:has(input:not(:placeholder-shown)) span" not in css
    local_storage_toolbar = re.search(
        r"#page-local-storage \.local-storage-data-toolbar\s*\{(?P<body>.*?)\}",
        css,
        re.S,
    )
    assert local_storage_toolbar is not None
    assert "justify-content: flex-start;" in local_storage_toolbar.group("body")
    local_storage_export_button = re.search(
        r"#page-local-storage \.local-storage-data-toolbar #localStorageExportTableBtn\s*\{(?P<body>.*?)\}",
        css,
        re.S,
    )
    assert local_storage_export_button is not None
    assert "height: 34px;" in local_storage_export_button.group("body")
    assert "min-height: 34px;" in local_storage_export_button.group("body")
    assert "border-radius: 8px;" in local_storage_export_button.group("body")
    local_storage_page_size = re.search(
        r"#page-local-storage \.local-storage-page-size\s*\{(?P<body>.*?)\}",
        css,
        re.S,
    )
    assert local_storage_page_size is not None
    assert "margin-left: auto;" in local_storage_page_size.group("body")
    assert "#page-local-storage .local-storage-action-status" in css
    assert ".btn-outline:disabled" in css
    assert "#page-local-storage .local-storage-table-list" in css and "overflow: auto" in css
    assert "#page-local-storage .local-storage-table-wrap" in css and "overflow: auto" in css
    assert "#page-local-storage table" in css and "table-layout: auto" in css
    assert "#page-local-storage th" in css and "min-width: var(--local-storage-col-min)" in css
    assert "--local-storage-col-min" in css
    assert "max-width: 260px" not in css
    space_storage_page = re.search(r'\[data-theme="space-tech"\] #page-local-storage\s*\{(?P<body>.*?)\}', css, re.S)
    assert space_storage_page is not None
    assert "padding: 0;" in space_storage_page.group("body")
    space_storage_title = re.search(
        r'\[data-theme="space-tech"\] #page-local-storage \.local-storage-toolbar > div:first-child\s*\{(?P<body>.*?)\}',
        css,
        re.S,
    )
    assert space_storage_title is not None
    assert "display: none;" in space_storage_title.group("body")
    assert '[data-theme="space-tech"][data-color-mode="dark"] #page-local-storage' in css

    assert "本地数据查询" in readme
    assert "管理员可只读查看本地 `auto-check.db`" in readme
    assert "敏感字段脱敏展示" in readme
    assert "检索输入展示和日期时间展示优化" in readme
    assert "导出当前表数据" in readme
    assert "手动触发旧历史迁移" in readme
    assert "旧历史迁移完成或未发现旧历史时按钮禁用" in readme
    assert ".user-actions-cell" in css
    assert "white-space: nowrap" in css
    assert "overflow-wrap: anywhere" in css


def test_user_management_cards_and_rows_have_theme_glow_hover_motion():
    css = _read(STYLES_CSS)
    readme = _read(README_MD)

    for selector in [
        r"\.user-stat-card:hover",
        r"\.user-filter-bar:hover",
        r"\.user-table-card:hover",
        r"\.user-table tbody tr:not\(\.user-loading-row\):hover",
    ]:
        rule = re.search(rf"(?m)^{selector}\s*\{{(?P<body>.*?)\}}", css, re.S)
        assert rule is not None
        body = rule.group("body")
        assert "var(--card-hover-glow)" in body
        assert "var(--card-hover-shadow" in body
        assert "transform:" in body
        assert "rgba(0, 0, 0" not in body

    for selector in [
        r"\.user-stat-card",
        r"\.user-filter-bar",
        r"\.user-table-card",
        r"\.user-table tbody tr:not\(\.user-loading-row\)",
    ]:
        rule = re.search(rf"(?m)^{selector}\s*\{{(?P<body>.*?)\}}", css, re.S)
        assert rule is not None
        assert "transition:" in rule.group("body")

    assert "用户管理统计卡、筛选区和用户行加入主题化光晕及轻弹动效" in readme


def test_user_management_retains_reference_stats_filters_export_and_icon_actions():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    for text in ['id="exportUsersBtn"', 'id="userStatDisabled"', 'class="user-filter-pills"', 'data-user-filter="all"']:
        assert text in html
    for text in ["导出列表", "已停用", "全部"]:
        assert text in html
    assert "function exportUsers" in app_js
    assert "function setUserQuickFilter" in app_js
    assert 'document.querySelectorAll("[data-user-filter]")' in app_js
    assert 'class="user-icon-action edit-user"' in app_js
    assert 'class="user-icon-action toggle-user"' in app_js
    assert 'class="user-icon-action delete-user"' in app_js
    assert ".user-stat-card--disabled" in css
    assert ".user-filter-pills" in css
    assert ".user-icon-action" in css


def test_user_csv_export_escapes_formula_values():
    app_js = _read(APP_JS)

    assert "function escapeCsvValue" in app_js
    assert "formulaPrefixPattern.test(text.trimStart())" in app_js
    export_users = re.search(r"function exportUsers\(\) \{(?P<body>.*?)\n\}", app_js, re.S)
    assert export_users is not None
    assert "row.map(escapeCsvValue)" in export_users.group("body")
    assert 'String(value).replace(/"/g, \'""\')' not in export_users.group("body")


def test_user_menu_uses_random_initial_avatar_when_name_updates():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)
    login_html = _read(ROOT / "src" / "auto_check" / "web" / "login.html")

    assert 'class="user-menu-icon user-initial-avatar" data-current-user-avatar' in html
    assert '<span class="user-menu-icon" aria-hidden="true"><svg' not in html
    assert 'data-current-username-text' in html
    assert "const USER_AVATAR_SESSION_KEY = \"autoCheckUserAvatarVariant\";" in app_js
    assert "const USER_AVATAR_GRADIENTS = [" in app_js
    assert "function userAvatarInitial(value)" in app_js
    assert "function currentUserAvatarGradient()" in app_js
    assert "sessionStorage.getItem(USER_AVATAR_SESSION_KEY)" in app_js
    assert "sessionStorage.setItem(USER_AVATAR_SESSION_KEY, String(index));" in app_js
    assert "sessionStorage.removeItem(USER_AVATAR_SESSION_KEY)" in app_js
    assert 'querySelector("[data-current-username-text]")' in app_js
    assert 'querySelector("[data-current-user-avatar]")' in app_js
    username_body = re.search(r"function updateCurrentUsername\(\) \{(?P<body>.*?)\n\}", app_js, re.S)
    assert username_body is not None
    assert "item.textContent = username" not in username_body.group("body")
    assert "avatar.textContent = initial;" in username_body.group("body")
    assert 'avatar.style.setProperty("--avatar-from", from);' in username_body.group("body")
    assert 'avatar.style.setProperty("--avatar-to", to);' in username_body.group("body")
    assert ".user-menu-icon" in css
    assert "linear-gradient(135deg, var(--avatar-from, #6366f1), var(--avatar-to, #4338ca))" in css
    assert ".user-menu-icon svg" not in css
    dark_user_icon = re.search(r'\[data-color-mode="dark"\] \.user-menu-icon\s*\{(?P<body>.*?)\}', css, re.S)
    assert dark_user_icon is not None
    assert "var(--avatar-from, #6366f1)" in dark_user_icon.group("body")
    assert "box-shadow" in dark_user_icon.group("body")
    assert "const USER_AVATAR_SESSION_KEY = \"autoCheckUserAvatarVariant\";" in login_html
    assert "function refreshUserAvatarVariant()" in login_html
    assert "refreshUserAvatarVariant();" in login_html


def test_user_management_nav_icon_is_subtle_css_icon_in_light_and_dark_modes():
    html = _read(INDEX_HTML)
    css = _read(STYLES_CSS)

    assert '<span class="nav-icon nav-icon-users" aria-hidden="true"></span>' in html
    assert '&#128101;' not in html
    assert ".nav-icon-users::before" in css
    assert ".nav-icon-users::after" in css
    assert "[data-color-mode=\"dark\"] .nav-icon-users" in css


def test_regular_user_settings_are_compact_without_changing_admin_about_details():
    html = _read(INDEX_HTML)
    css = _read(STYLES_CSS)

    assert 'class="about-features about-admin-detail"' in html
    assert 'class="about-tech about-admin-detail"' in html
    assert "[data-role=\"user\"] #page-settings .about-admin-detail" in css
    assert "[data-role=\"user\"] #page-settings .card-about" in css
    assert "[data-role=\"user\"] #page-settings .card-system-info" in css
    user_grid = re.search(r'\[data-role="user"\] #page-settings \.settings-dashboard-grid\s*\{(?P<body>.*?)\}', css, re.S)
    assert user_grid is not None
    assert "align-items: stretch" in user_grid.group("body")
    user_cards = re.search(
        r'\[data-role="user"\] #page-settings \.card-system-info,\s*'
        r'\[data-role="user"\] #page-settings \.card-about\s*\{(?P<body>.*?)\}',
        css,
        re.S,
    )
    assert user_cards is not None
    assert "height: 100%" in user_cards.group("body")
    assert "#page-settings .card-business,\n#page-settings .card-about {\n  height: 800px;" in css


def test_pbc_import_footer_shows_uploaded_file_total_near_next_button():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    footer = re.search(r'<div class="pbc-modal-footer" id="pbcModalFooter">(?P<body>.*?)</div>', html, re.S)
    assert footer is not None
    assert 'id="pbcUploadSummary"' in footer.group("body")
    assert 'id="pbcClearFilesBtn"' in footer.group("body")
    assert footer.group("body").index('id="pbcUploadSummary"') < footer.group("body").index('id="pbcNextBtn"')
    assert footer.group("body").index('id="pbcClearFilesBtn"') < footer.group("body").index('id="pbcNextBtn"')
    assert "function updatePbcUploadSummary()" in app_js
    assert 'pbcUploadSummary.textContent = `共 ${fileCount} 个文件`;' in app_js
    assert "function clearPbcUploadedFiles()" in app_js
    assert 'pbcClearFilesBtn.disabled = fileCount === 0;' in app_js
    assert "updatePbcUploadSummary();" in app_js
    assert ".pbc-upload-summary" in css
    assert ".pbc-btn--ghost" in css


def test_user_avatars_show_online_current_badge_and_reference_stat_icon():
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert "const isCurrentUser = user.id && user.id === authState.user?.id;" in app_js
    assert 'user-avatar-wrap' in app_js
    assert 'user-avatar-status' in app_js
    assert 'current-user-badge' in app_js
    assert '.user-avatar-wrap' in css
    assert '.user-avatar.is-online' in css
    assert '.user-avatar-status' in css
    assert '.current-user-badge' in css
    total_icon = re.search(r"(?m)^\.user-stat-icon--blue\s*\{(?P<body>.*?)\}", css, re.S)
    assert total_icon is not None
    assert "#eef2ff" in total_icon.group("body")
    assert "[data-theme=\"space-tech\"] .user-avatar" in css


def test_user_edit_modal_matches_reference_layout_and_does_not_close_on_blank_overlay():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    modal = re.search(r'<div class="modal-overlay" id="userModal" hidden>(?P<body>.*?)</div>\s*</div>\s*<!--', html, re.S)
    assert modal is not None
    for token in [
        "user-modal-header",
        "user-modal-title",
        "user-modal-icon",
        "user-modal-form",
        "user-role-card",
        "user-enable-row",
        "user-modal-footer",
    ]:
        assert token in modal.group("body")
        assert f".{token}" in css
    assert '<input id="userRole" type="hidden" value="user" />' in modal.group("body")
    assert '<input id="userEnabled" type="hidden" value="true" />' in modal.group("body")
    assert '<select id="userRole"' not in modal.group("body")
    assert '<select id="userEnabled"' not in modal.group("body")
    assert 'type="radio" name="userRoleChoice" value="admin"' in modal.group("body")
    assert 'type="radio" name="userRoleChoice" value="user"' in modal.group("body")
    assert "function syncUserRoleCards()" in app_js
    assert "function syncUserEnabledSwitch()" in app_js
    assert "function isDelegatedAdminSession()" in app_js
    assert "初始管理员角色不可修改" in app_js
    assert "委派管理员不可创建或设置管理员" in app_js
    assert 'api(`/api/users/${encodeURIComponent(targetUserId)}/reset-password`' in app_js
    assert 'autocomplete="new-name"' in modal.group("body")
    assert 'const displayNameValue = isEdit ? userDisplayName(user) : "";' in app_js
    assert 'if (!userId.value && userDisplayNameInput) userDisplayNameInput.value = "";' in app_js
    user_events = re.search(
        r"userModalClose\?\.addEventListener\(\"click\", closeUserModal\);(?P<body>.*?)userModalSave\?\.addEventListener",
        app_js,
        re.S,
    )
    assert user_events is not None
    assert 'userModal?.addEventListener("click"' not in user_events.group("body")


def test_user_management_space_theme_toolbar_and_actions_match_reference():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert 'class="user-filter-actions-space"' in html
    assert 'data-new-user-btn' in html
    assert 'data-export-users-btn' in html
    assert '[data-theme="space-tech"] #page-users .user-toolbar-text' in css
    assert "display: none" in re.search(
        r'\[data-theme="space-tech"\] #page-users \.user-toolbar-text\s*\{(?P<body>.*?)\}',
        css,
        re.S,
    ).group("body")
    assert '[data-theme="space-tech"] #page-users .user-toolbar-actions' in css
    assert '[data-theme="space-tech"] #page-users .user-filter-actions-space' in css
    assert "border-radius: 999px" in re.search(
        r'\[data-theme="space-tech"\] #page-users \.user-filter-actions-space \.btn-outline,\s*\n\[data-theme="space-tech"\] #page-users \.user-filter-actions-space \.btn-primary\s*\{(?P<body>.*?)\}',
        css,
        re.S,
    ).group("body")
    assert 'document.querySelectorAll("[data-new-user-btn]")' in app_js
    assert 'document.querySelectorAll("[data-export-users-btn]")' in app_js


def test_user_management_list_uses_display_fields_pagination_and_admin_guards():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert "最近登录时间" in html
    assert "更新时间" not in html[html.index('id="page-users"'):html.index('id="page-settings"')]
    assert 'id="userPagination"' in html
    assert 'id="userPrevPage"' in html
    assert 'id="userNextPage"' in html
    assert "user-loading-row" in html
    assert "function renderUsersLoading()" in app_js
    assert "loadUsers({ force = false } = {})" in app_js
    assert "renderUsersLoading();" in app_js
    assert ".user-loading-row" in css
    assert ".user-skeleton" in css
    assert "function paginatedUsers" in app_js
    assert "let userCurrentPage = 1" in app_js
    assert "last_login_at" in app_js
    assert "role-badge-icon" in app_js
    assert 'id="userDisplayName"' in html
    assert "function userDisplayName" in app_js
    assert "const isInitialAdmin = user.username === \"admin\";" in app_js
    assert "const isAdminUser = role === \"admin\";" not in app_js
    assert 'button.classList.contains("reset-user")' not in app_js
    render_body = re.search(r"function renderUsers\(\) \{(?P<body>.*?)\n\}\n\nfunction renderUsersLoading", app_js, re.S).group("body")
    assert "const displayName = userDisplayName(user);" in render_body
    assert 'class="user-name-line"' in render_body
    assert '<span class="user-name-line">' in render_body
    assert "<strong>${escapeHtml(displayName)}</strong>" in render_body
    assert "<small>${escapeHtml(user.username || \"\")}</small>" in render_body
    assert "reset-user" not in render_body
    assert "disabled" in render_body
    assert 'title="${isAdminUser ? "管理员不可停用"' not in render_body
    assert 'title="${isAdminUser ? "管理员不可删除"' not in render_body
    assert "初始管理员不可停用" in render_body
    assert "初始管理员不可删除" in render_body
    assert "#page-users .user-management" in css
    page_users = re.search(r"(?m)^#page-users\s*\{(?P<body>.*?)\}", css, re.S)
    assert page_users is not None
    assert "height: 100%" in page_users.group("body")
    user_management = re.search(r"(?m)^\.user-management\s*\{(?P<body>.*?)\}", css, re.S)
    assert user_management is not None
    assert "flex: 1" in user_management.group("body")
    assert "min-height: 0" in user_management.group("body")
    assert ".user-pagination" in css


def test_user_display_name_drives_navigation_and_user_export():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)

    assert "data-current-username-text" in html
    username_body = re.search(r"function updateCurrentUsername\(\) \{(?P<body>.*?)\n\}", app_js, re.S)
    assert username_body is not None
    assert "const displayName = userDisplayName(authState.user);" in username_body.group("body")
    assert "nameText.textContent = displayName" in username_body.group("body")
    assert "item.title = `${displayName} (${username})`" in username_body.group("body")
    assert 'const headers = ["用户姓名", "用户账号", "角色", "状态", "创建时间", "最近登录时间"];' in app_js


def test_run_history_displays_executor_and_recent_run_summary():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)

    history_head = html[html.index('id="historyBody"') - 600:html.index('id="historyBody"')]
    assert history_head.index("报告期") < history_head.index("执行时间")
    assert "执行人" in history_head
    assert '<th class="admin-only">数据源</th>' in history_head
    assert history_head.index("<th>总差异</th>") < history_head.index("<th>已解释</th>")
    assert history_head.index("<th>已解释</th>") < history_head.index("<th>新增差异</th>")
    assert history_head.index("<th>新增差异</th>") < history_head.index("<th>减少差异</th>")
    assert "<th>未解释</th>" not in history_head
    assert '<tr><td colspan="9" class="empty">' in html
    assert 'historySummaryItem("报告期", run.run_date)' in app_js
    assert 'historySummaryItem("执行时间", run.run_at)' in app_js
    assert '<td>${escapeHtml(run.run_date)}</td>' in app_js
    assert "<td>${escapeHtml(historyExecutorName(run))}</td>" in app_js
    assert 'function historyColumnCount() {\n  return canSeeHistorySource() ? 9 : 8;\n}' in app_js
    assert 'formatHistoryDiffCount(run, "added_count", { unit: false })' in app_js
    assert 'formatHistoryDiffCount(run, "removed_count", { unit: false })' in app_js
    assert '<td class="money-cell">${formatMoney(unresolved)}</td>' not in app_js
    row_start = app_js.index('return `<tr class="history-main-row"')
    row_end = app_js.index("</tr>`;", row_start)
    row_body = app_js[row_start:row_end]
    assert row_body.index("<td class=\"money-cell\">${formatMoney(run.total_count)}</td>") < row_body.index("<td class=\"money-cell\">${formatMoney(explained)}</td>")
    assert row_body.index("<td class=\"money-cell\">${formatMoney(explained)}</td>") < row_body.index("history-added")
    assert row_body.index("history-added") < row_body.index("history-removed")
    assert 'setLastRunTime(latestHistory.run_at, historyExecutorName(latestHistory))' in app_js
    assert 'lastRunTime.textContent = `最近执行：${executor}  ${latestRunAt}`;' in app_js

    css = _read(STYLES_CSS)
    added = re.search(r"(?m)^\.history-added\s*\{(?P<body>.*?)\}", css, re.S)
    removed = re.search(r"(?m)^\.history-removed\s*\{(?P<body>.*?)\}", css, re.S)
    assert added is not None
    assert removed is not None
    assert "color: var(--error)" in added.group("body")
    assert "color: var(--success-text)" in removed.group("body")


def test_history_restore_marks_result_list_and_keeps_latest_snapshot():
    app_js = _read(APP_JS)

    restore_history = re.search(r"function restoreHistoryRun\(run\) \{(?P<body>.*?)\n\}", app_js, re.S)
    assert restore_history is not None
    body = restore_history.group("body")
    assert "setResultHistoryRestoreState(run, results.length);" in body
    assert "setLastRunTime(run.run_at" not in body
    assert "saveLatestResultsSnapshot" not in body
    assert "lastRunTime.hidden = true;" in app_js
    assert 'showToast("结果列表已恢复到历史数据", "info")' in body
    assert "historyRestoreHintText(resultRestoreHistoryMeta, results.length)" in body

    restore_latest = re.search(r"async function restoreLatestResultsToResultList\(\) \{(?P<body>.*?)\n\}", app_js, re.S)
    assert restore_latest is not None
    latest_body = restore_latest.group("body")
    assert "const restored = await loadLatestHistoryResults();" in latest_body
    assert 'setStatus("结果列表已还原到最新结果")' in latest_body
    assert 'showToast("结果列表已还原到最新结果", "success")' in latest_body

    load_latest = re.search(r"async function loadLatestHistoryResults\(\) \{(?P<body>.*?)\n\}", app_js, re.S)
    assert load_latest is not None
    latest_loader = load_latest.group("body")
    assert "clearResultHistoryRestoreState();" in latest_loader
    assert 'homeResultListFilterLabel = "";' in latest_loader
    assert "setLastRunTime(latestHistory.run_at, historyExecutorName(latestHistory))" in latest_loader


def test_history_detail_opens_in_modal_and_respects_permissions():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert 'id="historyDetailCard"' not in html
    assert "let selectedHistoryId" in app_js
    assert "let historyDetailLoadingId" not in app_js
    assert "function historyDetailRow(innerHtml)" not in app_js
    assert "function renderHistoryDetailLoading(id)" in app_js
    assert "function renderHistoryDetailContent(run)" in app_js
    assert "function showHistoryDetailModal(id)" in app_js
    assert 'showInfo("历史详情", renderHistoryDetailLoading(id), { modalClass: "modal-info--history-detail", closeOnBackdrop: false });' in app_js
    assert 'showInfo("历史详情", renderHistoryDetailContent(history), { modalClass: "modal-info--history-detail", closeOnBackdrop: false });' in app_js
    assert "rowHtml += historyDetailRow" not in app_js
    assert 'class="history-main-row"' in app_js
    assert 'class="history-detail-row"' not in app_js
    assert 'class="history-detail-title"' not in app_js
    assert 'class="btn-close close-history-detail"' not in app_js
    assert 'class="btn-outline btn-xs restore-history"' not in app_js
    assert 'class="btn-primary btn-sm restore-history-detail"' in app_js
    assert "历史详情 -" not in app_js
    assert "function historyBaselineText(run = {})" in app_js
    assert "`${baselineRunAt}执行的同报告期记录`" in app_js
    assert "function historyHasBaseline(run = {})" in app_js
    assert "function formatHistoryDiffCount(run = {}, field = \"\", options = {})" in app_js
    assert "function historyDiffItems(run = {}, field = \"\")" in app_js
    detail_start = app_js.index("function renderHistoryDetailContent(run)")
    detail_end = app_js.index("function renderHistoryDetailLoading", detail_start)
    detail_body = app_js[detail_start:detail_end]
    assert detail_body.index('historySummaryItem("报告期", run.run_date)') < detail_body.index('historySummaryItem("执行人", historyExecutorName(run))')
    assert detail_body.index('historySummaryItem("执行人", historyExecutorName(run))') < detail_body.index('historySummaryItem("执行时间", run.run_at)')
    assert detail_body.index('historySummaryItem("执行时间", run.run_at)') < detail_body.index('historySummaryItem("基准记录", historyBaselineText(run))')
    assert 'historySummaryItem("基准记录", historyBaselineText(run))' in app_js
    assert 'historySummaryItem("规则版本"' not in app_js
    assert 'historySummaryItem("执行人", historyExecutorName(run))' in app_js
    assert 'historySummaryItem("总差异", formatMoney(run.total_count))' not in app_js
    assert 'historySummaryItem("数据源", formatHistorySourceName(run))' not in app_js
    assert 'historySummaryItem("新增差异", formatMoney(run.added_count))' not in app_js
    assert 'historySummaryItem("减少差异", formatMoney(run.removed_count))' not in app_js
    assert "const sourceSummary = canSeeHistorySource()" not in app_js
    assert "function canManageHistory()" in app_js
    assert "function canSeeHistorySource()" in app_js
    assert "function historyColumnCount()" in app_js
    assert "const deleteAction = canManageHistory()" in app_js
    assert 'if (!canManageHistory()) {' in app_js
    assert '<td class="admin-only">${escapeHtml(formatHistorySourceName(run))}</td>' in app_js
    history_result_table = re.search(r"function historyResultTable\(items\) \{(?P<body>.*?)\n\}", app_js, re.S)
    assert history_result_table is not None
    assert "<th>差异类型</th><th>状态</th>" in history_result_table.group("body")
    assert "具体原因" not in history_result_table.group("body")
    assert "specificReasonText(item)" not in history_result_table.group("body")

    load_detail = re.search(r"async function loadHistoryDetail\(id\) \{(?P<body>.*?)\n\}", app_js, re.S)
    assert load_detail is not None
    assert "historyDetailLoadingId" not in load_detail.group("body")
    assert "renderHistoryList();" not in load_detail.group("body")
    assert "await api(" in load_detail.group("body")
    assert "options.closeOnBackdrop === false" in app_js

    assert ".history-detail-card" in css
    assert ".history-detail-card .history-detail" in css
    assert ".history-detail-card .history-detail-footer" in css
    assert ".modal-info.modal-info--history-detail" in css
    assert "[data-color-mode=\"dark\"] .history-detail-card" in css
    assert "var(--surface-container-lowest)" in css
    assert "var(--on-surface)" in css
    assert "history-section--full-results" in app_js
    assert 'items.length > 10 ? " history-section--scroll" : ""' in app_js


def test_history_detail_modal_layout_keeps_tables_readable():
    css = _read(STYLES_CSS)

    card = re.search(r"(?m)^\.history-detail-card\s*\{(?P<body>.*?)\}", css, re.S)
    assert card is not None
    assert "display: flex" in card.group("body")
    assert "max-height" not in card.group("body")
    assert "overflow: hidden" in card.group("body")
    assert "border: 1px solid" not in card.group("body")
    assert "box-shadow" not in card.group("body")

    modal = re.search(r"(?m)^\.modal-info\.modal-info--history-detail\s*\{(?P<body>.*?)\}", css, re.S)
    assert modal is not None
    assert "width: min(1240px, 94vw)" in modal.group("body")
    assert "max-height: 92vh" in modal.group("body")
    assert "display: flex" in modal.group("body")
    assert "flex-direction: column" in modal.group("body")

    modal_body = re.search(r"(?m)^\.modal-info\.modal-info--history-detail \.modal-body\s*\{(?P<body>.*?)\}", css, re.S)
    assert modal_body is not None
    assert "flex: 1 1 auto" in modal_body.group("body")
    assert "min-height: 0" in modal_body.group("body")
    assert "overflow: hidden" in modal_body.group("body")

    summary_grid = re.search(r"(?m)^\.history-summary-grid\s*\{(?P<body>.*?)\}", css, re.S)
    assert summary_grid is not None
    assert "repeat(auto-fit, minmax(220px, 1fr))" in summary_grid.group("body")

    detail = re.search(r"(?m)^\.history-detail-card \.history-detail\s*\{(?P<body>.*?)\}", css, re.S)
    assert detail is not None
    assert "flex: 1 1 auto" in detail.group("body")
    assert "overflow: auto" in detail.group("body")

    footer = re.search(r"(?m)^\.history-detail-card \.history-detail-footer\s*\{(?P<body>.*?)\}", css, re.S)
    assert footer is not None
    assert "flex: 0 0 auto" in footer.group("body")
    assert "position: relative" in footer.group("body")
    assert "border-top" in footer.group("body")

    section = re.search(r"(?m)^\.history-section\s*\{(?P<body>.*?)\}", css, re.S)
    assert section is not None
    assert "flex: 0 0 auto" in section.group("body")

    section_table = re.search(r"(?m)^\.history-section-table\s*\{(?P<body>.*?)\}", css, re.S)
    assert section_table is not None
    assert "height:" not in section_table.group("body")
    assert "max-height:" not in section_table.group("body")
    assert "overflow-x: auto" in section_table.group("body")
    assert "overflow-y: visible" in section_table.group("body")

    scroll_table = re.search(
        r"(?m)^\.history-section--scroll \.history-section-table\s*\{(?P<body>.*?)\}",
        css,
        re.S,
    )
    assert scroll_table is not None
    assert "max-height: 360px" in scroll_table.group("body")
    assert "overflow: auto" in scroll_table.group("body")

    result_header = re.search(r"(?m)^\.history-result-table th\s*\{(?P<body>.*?)\}", css, re.S)
    assert result_header is not None
    assert "position: static" in result_header.group("body")

    summary_value = re.search(r"(?m)^\.history-summary-item strong\s*\{\s*min-width: 0;(?P<body>.*?)\}", css, re.S)
    assert summary_value is not None
    assert "overflow-wrap: break-word" in summary_value.group("body")
    assert "word-break: normal" in summary_value.group("body")
    assert '[data-color-mode="dark"] .history-summary-item' in css
    assert '[data-color-mode="dark"] .history-result-table td' in css
    assert '[data-color-mode="dark"] .history-count-item strong' in css


def test_history_detail_counts_are_one_row():
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert "function historyDetailCounts(run)" in app_js
    assert "${historyDetailCounts(run)}" in app_js
    assert "historyCountItem(\"本次新增差异\", historyHasBaseline(run) ? (run.added_results || []) : null)" in app_js
    assert "historyCountItem(\"本次减少差异\", historyHasBaseline(run) ? (run.removed_results || []) : null)" in app_js
    assert "historyCountItem(\"本次完整核对结果\", run.results || [])" in app_js
    assert 'if (items === null)' in app_js
    assert '<strong>-</strong>' in app_js

    counts = re.search(r"(?m)^\.history-detail-counts\s*\{(?P<body>.*?)\}", css, re.S)
    assert counts is not None
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in counts.group("body")


def test_history_list_shows_loading_animation_while_fetching():
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert "function renderHistoryLoading()" in app_js
    load_history = re.search(r"async function loadHistoryList\(resetPage = false\) \{(?P<body>.*?)\n\}", app_js, re.S)
    assert load_history is not None
    assert "renderHistoryLoading();" in load_history.group("body")
    assert load_history.group("body").index("renderHistoryLoading();") < load_history.group("body").index('api("/api/history")')
    assert "getReconcileBusinessSourceName()" not in load_history.group("body")
    assert "filterRunsByReconcileBusinessSource" not in load_history.group("body")
    assert "historyRuns = payload.history || [];" in load_history.group("body")
    assert 'class="history-loading-row"' in app_js
    assert 'colspan="${historyColumnCount()}"' in app_js
    assert 'class="loading-spinner history-loading-spinner"' in app_js
    assert "加载核对历史..." in app_js

    assert ".history-loading-row td" in css
    assert ".history-loading-spinner" in css


def test_run_and_pbc_import_conflict_feedback_is_visible():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)

    assert "对数任务正在执行，请等待当前任务完成后再开始。" in app_js
    assert "showToast(message, \"warning\")" in app_js
    assert "您的执行失败，原因：有正在执行的任务" in app_js
    assert "用户正在执行中" in app_js
    assert "用户执行完成，您可再次执行。" in app_js
    assert "pollActiveRunConflict" in app_js
    assert "error.payload = p" in app_js
    assert "handlePbcImportStartError" in app_js
    assert "待插入表正在导入，请等待上一个任务完成后再导入。" in app_js
    assert 'id="pbcProgressTitle"' in html
    assert 'id="pbcRetryBtn"' in html
    assert "稍后再试" in app_js
    assert "pbcRetryBtn.hidden = false" in app_js
    assert "pbcRetryBtn?.addEventListener" in app_js


def test_db_validation_frontend_tool_settings_and_api_are_wired():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    for item_id in [
        'id="toolCardDbValidation"',
        'id="dbValidationModalOverlay"',
        'id="dbValidationReportDate"',
        'id="dbValidationPublicInfoCheck"',
        'id="dbValidationTableList"',
        'id="dbValidationRulesDocBtn"',
        'id="dbValidationDetailSource"',
        'id="dbValidationDetailSysManageId"',
        'id="dbValidationDetailClassificationId"',
        'id="dbValidationPublicInfoSource"',
        'id="dbValidationPublicInfoSysManageId"',
        'id="dbValidationPublicInfoClassificationId"',
        'id="dbValidationTemplateSource"',
        'id="dbValidationTemplateSysManageId"',
        'id="dbValidationTemplateClassificationId"',
        'id="dbValidationMetadataSource"',
        'id="dbValidationBaseinfoTable"',
        'id="dbValidationFieldInfoTable"',
        'id="dbValidationPublicInfoTable"',
        'id="dbValidationRefreshFieldMappingBtn"',
    ]:
        assert item_id in html

    assert 'id="dbValidationDataSource"' not in html
    assert 'class="db-validation-date-field"' in html
    assert 'id="dbValidationTemplateCheck"' in html
    assert 'id="dbValidationTemplateCheck" disabled' not in html

    for text in [
        "人行逐笔校验引擎",
        "/api/tools/db-validation/settings",
        "/api/tools/db-validation/start",
        "/api/tools/db-validation/status/",
        "/api/tools/db-validation/download/",
        "/api/tools/db-validation/history",
        "/api/tools/db-validation/history/download/",
        "/api/tools/db-validation/rules-document",
        "/api/tools/db-validation/field-mapping/refresh",
        "function loadDbValidationSettings",
        "function startDbValidation",
        "function pollDbValidationJob",
        "function openDbValidationHistory",
        "function renderDbValidationHistory",
        "function saveDbValidationSettings",
        "function refreshDbValidationFieldMapping",
        "function renderDbValidationFieldMappingStatus",
        "function readDbValidationDatasetSettings",
        "enable_public_info_check",
        "enable_template_check",
        "field_mapping_source_id",
        "unmapped_field_count",
        "public_info_table",
    ]:
        assert text in app_js

    save_start = app_js.index("async function saveDbValidationSettings")
    save_end = app_js.index("async function refreshDbValidationFieldMapping", save_start)
    save_body = app_js[save_start:save_end]
    assert "const refreshMapping = options.refreshMapping !== false;" in save_body
    assert 'api("/api/tools/db-validation/field-mapping/refresh", { method: "POST" })' in save_body
    assert "已保存，正在刷新字段映射" in save_body
    assert "数据库校验配置已保存，字段映射已刷新" in save_body

    refresh_start = app_js.index("async function refreshDbValidationFieldMapping")
    refresh_end = app_js.index("function appendDbValidationLog", refresh_start)
    refresh_body = app_js[refresh_start:refresh_end]
    assert "await saveDbValidationSettings({ quiet: true, refreshMapping: false });" in refresh_body

    assert ".tool-card-db-validation" in css
    assert ".db-validation-grid" in css
    assert ".db-validation-table-list" in css
    assert 'id="dbValidationHistoryBtn"' in html
    assert 'id="dbValidationHistoryBody"' in html
    assert "<th>执行人</th>" in html
    assert "db-validation-history-count-link" in app_js
    assert "function dbValidationHistoryExecutorName" in app_js
    assert "dbValidationHistoryExecutorName(run)" in app_js
    assert "function formatDbValidationHistoryTime" in app_js
    assert '.replace("T", " ")' in app_js
    assert ".db-validation-history-modal" in css
    history_wrap = re.search(r"(?m)^\.db-validation-history-table-wrap\s*\{(?P<body>.*?)\}", css, re.S)
    assert history_wrap is not None
    assert "overflow-x: hidden;" in history_wrap.group("body")
    assert ".db-validation-history-table {\n  table-layout: fixed;" in css
    assert ".db-validation-history-count-link" in css


def test_packaged_exe_includes_db_validation_resource_package():
    spec = _read(PYINSTALLER_SPEC)

    assert "src/auto_check/resources" in spec
    assert "auto_check/resources" in spec
    assert "'auto_check.resources'" in spec
    assert "'auto_check.resources.data'" in spec


def test_db_validation_history_sorts_by_execution_time_desc():
    app_js = _read(APP_JS)

    load_history = re.search(r"async function loadDbValidationHistory\(\) \{(?P<body>.*?)\n\}", app_js, re.S)
    assert load_history is not None
    assert "const sortedHistory = [...(payload.history || [])].sort(compareDbValidationHistoryRunsDesc);" in load_history.group("body")
    assert "renderDbValidationHistory(sortedHistory);" in load_history.group("body")
    assert "function compareDbValidationHistoryRunsDesc" in app_js
    assert "function dbValidationHistoryExecutionTimeValue" in app_js
    assert "const raw = dbValidationHistoryExecutionTime(run);" in app_js
    assert "Date.UTC(" in app_js
    assert "dbValidationHistoryExecutionTimeValue(right) - dbValidationHistoryExecutionTimeValue(left)" in app_js


def test_selects_use_scheme_5_glass_style_without_particles():
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert "custom-input-particle" not in app_js
    assert "custom-select-particle" not in app_js
    assert "custom-input-particle" not in css
    assert "custom-select-particle" not in css
    assert "float-particle" not in css

    for text in [
        "function initializeCustomSelects()",
        "function enhanceCustomSelect(select)",
        "function enhanceCustomInput(input)",
        "function shouldEnhanceCustomInput(input)",
        "function renderCustomDatePicker(input)",
        "function openCustomDatePicker(input)",
        "function enhanceCustomDateInput(input, shell)",
        "const CUSTOM_INPUT_TYPES = new Set",
        "const customDateStates = new WeakMap();",
        "const CUSTOM_DATE_WEEKDAYS",
        "const customSelectStates = new WeakMap();",
        "custom-select-shell",
        "custom-select-trigger",
        "custom-select-dropdown",
        "custom-select-option",
        "custom-input-shell",
        "custom-input-native",
        "custom-date-shell",
        "custom-date-dropdown",
        "custom-date-day",
        "customSelectMeasure(select, shell)",
        "customInputMeasure(input, shell)",
        "shell.style.setProperty(\"--select-width\"",
        "shell.style.setProperty(\"--select-height\"",
        "shell.style.setProperty(\"--input-width\"",
        "shell.style.setProperty(\"--input-height\"",
        "const CUSTOM_INPUT_TYPES = new Set([\"text\", \"search\", \"number\", \"date\"",
        "if (type === \"date\") shell.classList.add(\"custom-date-shell\");",
        "input.type = \"text\";",
        "input.readOnly = true;",
        "input.classList.add(\"custom-date-input\");",
        "event.stopPropagation();",
        "positionCustomDateDropdown(input);",
        "setCustomDateValue(input, day.dataset.date || \"\")",
        "CUSTOM_INPUT_TYPES.has(type) && !input.hidden",
        "select.dispatchEvent(new Event(\"change\", { bubbles: true }))",
        "target.closest(\".custom-select-dropdown\")",
        "const dropdownWidth = Math.min(Math.max(rect.width + 24, rect.width)",
        "enhanceCustomControls();",
        "initializeCustomSelects();",
    ]:
        assert text in app_js

    select_rule = re.search(r"(?m)^select\s*\{(?P<body>.*?)\}", css, re.S)
    assert select_rule is not None
    select_body = select_rule.group("body")
    for text in [
        "padding-right: 40px",
        "border-radius: 8px",
        "radial-gradient(circle at 12% 28%",
        "backdrop",
        "-webkit-appearance: none",
        "appearance: none",
    ]:
        assert text in select_body

    assert "select:hover" in css
    assert "select:focus" in css
    assert "select option" in css
    assert "select option:checked" in css
    assert '[data-color-mode="dark"] select' in css
    assert '[data-color-mode="dark"] select option:checked' in css
    assert "rgba(129, 140, 248, 0.30)" in css

    for selector in [
        ".custom-select-shell",
        ".custom-select-native",
        ".custom-select-trigger",
        ".custom-select-trigger::after",
        ".custom-input-shell",
        "input.custom-input-native",
        ".custom-date-shell",
        ".date-picker .custom-date-shell",
        ".db-validation-date-field",
        ".db-validation-date-field .custom-date-shell",
        ".user-form-group .custom-input-shell.user-form-control",
        "input.custom-date-input",
        ".custom-date-shell::after",
        ".custom-date-shell::before",
        ".custom-date-dropdown",
        ".custom-date-head",
        ".custom-date-weekdays",
        ".custom-date-days",
        ".custom-date-day.active",
        ".custom-date-actions",
        ".custom-input-shell:focus-within input.custom-input-native",
        ".custom-select-dropdown",
        ".custom-select-option",
        ".custom-select-option::before",
        ".custom-select-option.active::after",
        '[data-color-mode="dark"] input.custom-input-native',
        '[data-color-mode="dark"] input.custom-date-input',
        '[data-color-mode="dark"] .custom-date-dropdown',
        '[data-color-mode="dark"] .custom-date-shell::after',
        ':root:not([data-theme="space-tech"]) input.custom-input-native',
        ':root:not([data-theme="space-tech"]) .custom-select-trigger',
        ':root:not([data-theme="space-tech"]) input.custom-date-input',
        ':root:not([data-theme="space-tech"]) .custom-date-day.active',
        '[data-color-mode="dark"] .custom-select-trigger',
        '[data-color-mode="dark"] .custom-select-dropdown',
        '[data-color-mode="dark"] .custom-select-option.active',
    ]:
        assert selector in css

    for text in [
        "width: var(--select-width)",
        "height: var(--select-height)",
        "width: var(--input-width)",
        "height: var(--input-height)",
        "flex: 0 0 180px",
        "width: 180px",
        "height: 38px",
        "overflow: hidden",
        "overscroll-behavior: contain",
        "scrollbar-gutter: stable",
        "background: rgba(255, 255, 255, 0.90)",
        "background: rgba(255, 255, 255, 0.88)",
        "rgba(15, 23, 42, 0.76)",
        "radial-gradient(circle at 18% 22%, rgba(6, 182, 212, 0.15)",
        "radial-gradient(circle at 84% 72%, rgba(139, 92, 246, 0.13)",
        "backdrop-filter: blur(10px)",
        "border: 1px solid rgba(59, 130, 246, 0.30)",
        "border: 1px solid rgba(59, 130, 246, 0.24)",
        "border: 1.5px solid #06b6d4",
        "filter: drop-shadow(0 0 6px rgba(6, 182, 212, 0.50))",
        "grid-template-columns: repeat(7, 1fr)",
        "background: linear-gradient(135deg, #3b82f6, #06b6d4)",
        "border-color: color-mix(in srgb, var(--secondary) 46%, transparent)",
        "border-color: color-mix(in srgb, var(--secondary) 52%, transparent)",
        "background: linear-gradient(135deg, var(--secondary), color-mix(in srgb, var(--secondary) 72%, var(--primary)))",
        "filter: drop-shadow(0 0 3px #3b82f6)",
        "animation: dropdown-slide 0.3s ease-out",
        "padding-left: 24px",
        "content: \"✓\"",
        "@keyframes check-bounce",
    ]:
        assert text in css


def test_settings_uses_single_data_source_model():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)

    for item_id in [
        'id="mdSourceType"',
        'id="mdSourceHost"',
        'id="mdSourceDb"',
        'id="mdSourceSchemaField"',
        'id="mdSourceSchema"',
        'id="mdSourceUser"',
        'id="mdSourcePwd"',
    ]:
        assert item_id in html

    for removed_id in [
        'id="mdDwsType"',
        'id="mdBizType"',
        'id="dwsToggle"',
        'id="bizToggle"',
        'id="modalSetDefault"',
        'id="reconcileDwsSource"',
        'id="reconcileBusinessSource"',
        'id="saveReconcileSourcesBtn"',
        'id="reconcileSourcesStatus"',
    ]:
        assert removed_id not in html

    assert "function loadReconcileDataSourceSettings" not in app_js
    assert "function renderReconcileDataSourceSettings" not in app_js
    assert '"/api/settings/reconcile-data-sources", {' not in app_js
    assert "function syncDataSourceSchemaVisibility(prefix)" in app_js
    assert "function defaultPortForDataSourceType(type)" in app_js
    assert 'return String(type || "").toLowerCase() === "mysql" ? 3306 : 5432;' in app_js
    assert "function syncDataSourcePortForType(prefix, options = {})" in app_js
    assert 'document.getElementById("mdSourceType")?.addEventListener("change"' in app_js
    assert 'syncDataSourcePortForType("mdSource", { force: true });' in app_js
    assert 'schema: document.getElementById(prefix + "Type").value === "postgresql"' in app_js
    assert "source_id" in app_js
    assert "field_mapping_source_id" in app_js
    assert "set-def" not in app_js
    assert "设为默认" not in app_js
    assert "function parseDbValidationSource" not in app_js
    assert "field_mapping_config_name: selected.configName" not in app_js
    assert 'return `${item.config_name || ""}::${item.source || "dws"}`;' not in app_js


def test_user_name_stack_places_account_under_display_name():
    css = _read(STYLES_CSS)

    user_name_stack = re.search(r"(?m)^\.user-name-stack\s*\{(?P<body>.*?)\}", css, re.S)
    assert user_name_stack is not None
    assert "flex-direction: column" in user_name_stack.group("body")
    assert "align-items: flex-start" in user_name_stack.group("body")
    user_name_line = re.search(r"(?m)^\.user-name-line\s*\{(?P<body>.*?)\}", css, re.S)
    assert user_name_line is not None
    assert "display: inline-flex" in user_name_line.group("body")
    assert "align-items: center" in user_name_line.group("body")


def test_user_modal_explains_username_supported_characters():
    app_js = _read(APP_JS)

    assert "function userFriendlyError(message = \"\")" in app_js
    assert "username contains unsupported characters" in app_js
    assert "用户名仅支持英文字母、数字、下划线(_)、中横线(-)和点(.)" in app_js
    assert "不支持中文、空格及其他特殊字符" in app_js
    assert "userModalStatus.textContent = userFriendlyError(error.message);" in app_js


def test_history_action_column_keeps_table_cell_alignment():
    css = _read(STYLES_CSS)

    actions = re.search(r"(?m)^\.history-actions\s*\{(?P<body>.*?)\}", css, re.S)
    assert actions is not None
    assert "display: flex" not in actions.group("body")
    assert "text-align: center" in actions.group("body")
    assert "vertical-align: middle" in actions.group("body")
    assert ".history-actions .btn-xs" in css


def test_system_info_shows_runtime_status_and_history_count():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)

    start = app_js.index("async function loadSystemInfo()")
    end = app_js.index("function setSystemInfoFeedback", start)
    body = app_js[start:end]
    assert 'id="historyRunCount"' in html
    assert 'id="sessionStatusInfo"' not in html
    assert 'id="loginUserInfo"' in html
    assert 'id="autoRefreshInfo"' in html
    assert 'id="testAllConnBtn"' not in html
    assert 'id="dwsStatus"' not in html
    assert 'id="bizStatus"' not in html
    assert 'id="historyCount"' not in html
    assert 'api("/api/system-info")' in body
    assert 'api("/api/history")' not in body
    assert "historyRunCount" in body
    assert "authState.authenticated" not in body
    assert "userDisplayName(authState.user || {})" in body
    assert "settings.autoRefreshHome" in body
    assert 'api("/api/connection-status")' not in body
    assert "async function testConnectionStatusForFeedback()" not in app_js
    assert 'api("/api/connection-status")' not in app_js
    assert "仅管理员可测试" not in body
    assert 'if (authState.user?.role !== "admin")' not in body


def test_auth_passwords_are_encrypted_before_transport():
    login_html = _read(ROOT / "src" / "auto_check" / "web" / "login.html")
    index_html = _read(INDEX_HTML)
    app_js = _read(APP_JS)

    assert '"/api/auth/key"' in login_html
    assert "async function encryptPasswordForTransport" in login_html
    assert '<script src="/crypto_fallback.js"></script>' in login_html
    assert '<script src="/crypto_fallback.js"></script>' in index_html
    assert "window.autoCheckCrypto.encryptPasswordForTransport" in login_html
    assert "window.autoCheckCrypto.encryptPasswordForTransport" in app_js
    assert "password_encrypted" in login_html
    assert "body: JSON.stringify({ username, password_encrypted: encryptedPassword })" in login_html
    assert "body: JSON.stringify({ password_encrypted: encryptedPassword })" in login_html
    assert "body: JSON.stringify({ password })" not in login_html
    assert '"/api/auth/key"' in app_js
    assert "async function encryptPasswordForTransport" in app_js
    assert "password_encrypted" in app_js
    assert "password: userPassword.value" not in app_js


def test_data_source_passwords_are_encrypted_before_transport():
    app_js = _read(APP_JS)

    assert "async function encryptDataSourcePasswordsForTransport" in app_js
    assert "password_encrypted" in app_js
    assert "delete payload.password;" in app_js
    assert 'password: document.getElementById(prefix + "Pwd").value' not in app_js
    assert "body: JSON.stringify(await encryptDataSourcePasswordsForTransport(cfg))" in app_js
    assert "body: JSON.stringify(await encryptDataSourcePasswordsForTransport(body))" in app_js


def test_data_source_test_connection_modal_resets_pending_state():
    app_js = _read(APP_JS)

    assert "let modalTestRequestToken = 0;" in app_js
    assert "function resetModalTestConnectionState()" in app_js
    assert "if (modalTestBtn) modalTestBtn.disabled = false;" in app_js
    assert "function closeConfigModal()" in app_js
    assert "modalClose.addEventListener(\"click\", closeConfigModal);" in app_js

    open_start = app_js.index("function openModal(config)")
    open_end = app_js.index("function fillDs", open_start)
    open_body = app_js[open_start:open_end]
    assert "resetModalTestConnectionState();" in open_body

    test_start = app_js.index("modalTestBtn.addEventListener")
    test_end = app_js.index("modalSaveBtn.addEventListener", test_start)
    test_body = app_js[test_start:test_end]
    assert "const requestToken = ++modalTestRequestToken;" in test_body
    assert "if (requestToken !== modalTestRequestToken || configModal.hidden) return;" in test_body
    assert "if (requestToken === modalTestRequestToken && !configModal.hidden) modalStatus.textContent = e.message;" in test_body
    assert "if (requestToken === modalTestRequestToken && !configModal.hidden) modalTestBtn.disabled = false;" in test_body

    save_start = app_js.index("modalSaveBtn.addEventListener")
    save_end = app_js.index("/* ===== Tools: PBC full product import", save_start)
    save_body = app_js[save_start:save_end]
    assert "closeConfigModal();" in save_body


def test_login_error_messages_are_mapped_for_common_failures():
    login_html = _read(ROOT / "src" / "auto_check" / "web" / "login.html")

    assert "function getLoginErrorMessage" in login_html
    assert "账号或密码不正确" in login_html
    assert "账号已停用" in login_html
    assert "密码传输加密失败" in login_html
    assert "网络连接异常" in login_html


def test_regular_user_settings_are_limited_and_readonly_for_system_actions():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    for card in ["card-default", "card-db-validation", "card-data", "card-datasource", "card-business"]:
        assert f'class="card settings-dashboard-card {card} admin-only"' in html
    assert 'id="testAllConnBtn"' not in html
    assert 'id="refreshInfoBtn" type="button" class="btn-outline btn-sm admin-action"' in html
    assert "function applySettingsRoleAccess" in app_js
    assert 'document.querySelectorAll(".admin-action")' in app_js
    assert "[data-role=\"user\"] .admin-only" in css


def test_pbc_completed_step_and_importing_text_are_centered_and_green():
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert "const isDone = s < pbcCurrentStep || (pbcCurrentStep === 4 && s === 4);" in app_js
    assert 'el.classList.toggle("pbc-step--done", isDone);' in app_js

    progress_header = re.search(r"(?m)^\.pbc-progress-header\s*\{(?P<body>.*?)\}", css, re.S)
    assert progress_header is not None
    progress_header_body = progress_header.group("body")
    assert "justify-content: center" in progress_header_body
    assert "text-align: center" in progress_header_body

    assert "[data-color-mode=\"dark\"] .pbc-step--done .pbc-step-num" in css
    assert "[data-theme=\"space-tech\"][data-color-mode=\"dark\"] .pbc-step--done .pbc-step-num" in css


def test_pbc_import_dark_mode_and_mapping_layout_are_readable():
    app_js = _read(APP_JS)
    html = _read(INDEX_HTML)
    css = _read(STYLES_CSS)

    assert 'id="pbcColumnNotice"' in html
    assert "let pbcTableColumns = [];" in app_js
    assert "pbcTableColumns = payload.table_columns || [];" in app_js
    assert "const targetOptions = pbcTableColumns.map((target) =>" in app_js
    assert "pbcTableColumns.find((column) => column.name === target)" in app_js
    assert "function renderPbcColumnNotice()" in app_js
    assert "function hidePbcColumnNotice()" in app_js
    assert "function syncPbcUploadAggregate()" in app_js
    assert "function getPbcUploadIds()" in app_js
    assert "upload_ids: getPbcUploadIds()" in app_js
    assert "payload.upload_inspections" in app_js
    assert "pbcUploadedFiles = pbcUploadedFiles.map" in app_js
    assert "missingByFile" in app_js
    assert "renderPbcColumnNotice();" in app_js
    assert "pbcColumnNotice.title = fullDetails;" in app_js
    assert "hidePbcColumnNotice();" in re.search(r"pbcLoadMappingsBtn\?\.addEventListener\(\"click\", async \(\) => \{(?P<body>.*?)\n\}\);", app_js, re.S).group("body")
    assert ".pbc-column-notice" in css

    mapping_config = re.search(r"(?m)^\.pbc-mapping-config\s*\{(?P<body>.*?)\}", css, re.S)
    assert mapping_config is not None
    assert "minmax(300px, 0.42fr) minmax(430px, 0.58fr)" in mapping_config.group("body")
    assert "gap: 16px" in mapping_config.group("body")
    assert ".pbc-mapping-config-left,\n.pbc-mapping-config-right" in css

    mapping_item = re.search(r"(?m)^\.pbc-mapping-item\s*\{(?P<body>.*?)\}", css, re.S)
    assert mapping_item is not None
    assert "minmax(108px" in mapping_item.group("body")
    assert "minmax(0, 1.42fr)" in mapping_item.group("body")
    assert "22px" in mapping_item.group("body")
    assert "gap: 4px" in mapping_item.group("body")

    mapping_action = re.search(r"(?m)^\.pbc-mapping-action\s*\{(?P<body>.*?)\}", css, re.S)
    assert mapping_action is not None
    assert "width: 22px" in mapping_action.group("body")
    assert "height: 22px" in mapping_action.group("body")

    assert '[data-color-mode="dark"] .pbc-step-connector' in css
    assert '[data-theme="space-tech"][data-color-mode="dark"] .pbc-step-connector' in css
    assert '[data-color-mode="dark"] .pbc-import-log' in css
    assert '[data-color-mode="dark"] .pbc-log-entry' in css
    for variant in ["primary", "secondary", "success"]:
        assert f'[data-color-mode="dark"] .pbc-btn--{variant} {{' in css
        variant_rule = re.search(rf'\[data-color-mode="dark"\] \.pbc-btn--{variant}\s*\{{(?P<body>.*?)\}}', css, re.S)
        assert variant_rule is not None
        assert "background:" in variant_rule.group("body")
        assert "border:" in variant_rule.group("body")
        assert f'[data-color-mode="dark"] .pbc-btn--{variant}:hover' in css
    assert '[data-color-mode="dark"] .pbc-btn--primary:disabled' in css
    disabled_primary = re.search(r'\[data-color-mode="dark"\] \.pbc-btn--primary:disabled,\s*\n\[data-color-mode="dark"\] \.pbc-btn--primary:disabled:hover\s*\{(?P<body>.*?)\}', css, re.S)
    assert disabled_primary is not None
    assert "background:" in disabled_primary.group("body")
    assert "opacity: 1" in disabled_primary.group("body")
    assert '[data-color-mode="dark"] .pbc-btn:disabled' in css


def test_pbc_auto_mapping_remove_can_be_restored_without_affecting_manual_rows():
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert "function normalizePbcAutoMappings" in app_js
    assert "auto_target_column" in app_js
    assert "manual_unmapped_from_auto" in app_js
    assert "const canRestore = !mapping.target_column && mapping.auto_target_column && mapping.manual_unmapped_from_auto;" in app_js
    assert 'data-action="${canRestore ? "restore" : "remove"}"' in app_js
    assert 'title="${canRestore ? "还原自动映射" : "移除列"}"' in app_js
    assert "restorePbcAutoMapping(index);" in app_js
    assert "removePbcMapping(index);" in app_js
    assert "pbcMappings = normalizePbcAutoMappings(payload.mappings || []);" in app_js
    assert ".pbc-mapping-restore" in css
    assert ".pbc-mapping-action" in css


def test_pbc_mapping_modal_avoids_horizontal_clipping():
    css = _read(STYLES_CSS)

    modal = re.search(r"(?m)^\.pbc-modal\s*\{(?P<body>.*?)\}", css, re.S)
    assert modal is not None
    modal_body = modal.group("body")
    assert "width: 860px" in modal_body
    assert "max-width: 96vw" in modal_body

    mapping_config = re.search(r"(?m)^\.pbc-mapping-config\s*\{(?P<body>.*?)\}", css, re.S)
    assert mapping_config is not None
    mapping_config_body = mapping_config.group("body")
    assert "minmax(300px, 0.42fr) minmax(430px, 0.58fr)" in mapping_config_body

    mapping_list = re.search(r"(?m)^\.pbc-mapping-list\s*\{(?P<body>.*?)\}", css, re.S)
    assert mapping_list is not None
    assert "overflow-x: hidden" in mapping_list.group("body")

    mapping_item = re.search(r"(?m)^\.pbc-mapping-item\s*\{(?P<body>.*?)\}", css, re.S)
    assert mapping_item is not None
    mapping_item_body = mapping_item.group("body")
    assert "minmax(108px, 0.58fr) 10px minmax(0, 1.42fr) 22px" in mapping_item_body
    assert "min-width: 0" in mapping_item_body


def test_space_tech_top_nav_aligns_with_content_padding():
    css = _read(STYLES_CSS)
    app_js = _read(APP_JS)

    top_nav = re.search(r"(?m)^\.top-nav\s*\{(?P<body>.*?)\}", css, re.S)
    assert top_nav is not None
    assert "left: 32px" in top_nav.group("body")
    assert "right: 32px" in top_nav.group("body")

    assert "const topNav = document.querySelector(\".top-nav\");" in app_js
    assert "const mainContent = document.querySelector(\".main-content\");" in app_js
    assert "function updateSpaceTopNavFrost()" in app_js
    assert "mainContent?.scrollTop || 0" in app_js
    assert 'document.documentElement.classList.toggle("space-nav-over-content", shouldFrost);' in app_js
    assert 'window.addEventListener("scroll", updateSpaceTopNavFrost, { passive: true });' in app_js
    assert 'mainContent?.addEventListener("scroll", updateSpaceTopNavFrost, { passive: true });' in app_js

    frosted_nav = re.search(
        r"\[data-theme=\"space-tech\"\]\.space-nav-over-content \.top-nav\s*\{(?P<body>.*?)\}",
        css,
        re.S,
    )
    assert frosted_nav is not None
    frosted_nav_body = frosted_nav.group("body")
    assert "linear-gradient" in frosted_nav_body
    assert "backdrop-filter: blur(24px)" in frosted_nav_body
    assert "-webkit-backdrop-filter: blur(24px)" in frosted_nav_body

    frosted_nav_after = re.search(
        r"\[data-theme=\"space-tech\"\]\.space-nav-over-content \.top-nav::after\s*\{(?P<body>.*?)\}",
        css,
        re.S,
    )
    assert frosted_nav_after is not None
    assert "linear-gradient" in frosted_nav_after.group("body")

    content_frost = re.search(
        r"\[data-theme=\"space-tech\"\]\.space-nav-over-content body::before\s*\{(?P<body>.*?)\}",
        css,
        re.S,
    )
    assert content_frost is not None
    content_frost_body = content_frost.group("body")
    assert "position: fixed" in content_frost_body
    assert "pointer-events: none" in content_frost_body
    assert "z-index: 29" in content_frost_body
    assert "background: rgba(239, 248, 255, 0.26)" in content_frost_body
    assert "backdrop-filter: blur(30px) saturate(1.22)" in content_frost_body
    assert "-webkit-backdrop-filter: blur(30px) saturate(1.22)" in content_frost_body

    assert "mask-image" in content_frost_body

    mobile_top_nav = re.search(
        r"\[data-theme=\"space-tech\"\] \.top-nav\s*\{(?P<body>.*?)\}",
        css[css.index("@media (max-width: 900px)") :],
        re.S,
    )
    assert mobile_top_nav is not None
    assert "left: 14px" in mobile_top_nav.group("body")
    assert "right: 14px" in mobile_top_nav.group("body")

    mobile_content_frost = re.search(
        r"\[data-theme=\"space-tech\"\]\.space-nav-over-content body::before\s*\{(?P<body>.*?)\}",
        css[css.index("@media (max-width: 900px)") :],
        re.S,
    )
    assert mobile_content_frost is not None
    assert "left: 14px" in mobile_content_frost.group("body")
    assert "right: 14px" in mobile_content_frost.group("body")

    compact_css = css[css.index("@media (max-width: 640px)") :]
    compact_top_nav = re.search(
        r"\[data-theme=\"space-tech\"\] \.top-nav\s*\{(?P<body>.*?)\}",
        compact_css,
        re.S,
    )
    assert compact_top_nav is not None
    assert "max-width: calc(100vw - 20px)" in compact_top_nav.group("body")
    compact_tabs = re.search(
        r"\[data-theme=\"space-tech\"\] \.top-nav-tabs\s*\{(?P<body>.*?)\}",
        compact_css,
        re.S,
    )
    assert compact_tabs is not None
    assert "overflow-x: auto" in compact_tabs.group("body")
    compact_subtitle = re.search(
        r"\[data-theme=\"space-tech\"\] \.top-nav-wordmark \.brand-wordmark-sub\s*\{(?P<body>.*?)\}",
        compact_css,
        re.S,
    )
    assert compact_subtitle is not None
    assert "display: none" in compact_subtitle.group("body")


def test_flow_chain_ui_is_manual_only_and_uses_editor_modal_with_scrollable_list():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    server_py = _read(SERVER_PY)
    css = _read(STYLES_CSS)

    for element_id in [
        "flowChainEditorOverlay",
        "flowChainEditorName",
        "flowChainEditorEnabled",
        "flowDefinitionSearch",
        "flowDefinitionRefreshBtn",
        "flowDefinitionTable",
        "flowSelectedStepList",
        "flowChainEditorSave",
    ]:
        assert f'id="{element_id}"' in html

    for removed_element_id in [
        "flowChainEditorCron",
        "flowCronConfigBtn",
        "flowCronOverlay",
        "flowCronTabs",
        "flowCronPreview",
        "flowCronConfirm",
        "flowChainEditorScheduleEnabled",
        "flowChainEditorSteps",
    ]:
        assert f'id="{removed_element_id}"' not in html

    assert "flowChainEditorOverlay" in app_js
    assert "openFlowChainEditor" in app_js
    assert "/api/tools/flow/definitions" in app_js
    assert "loadFlowDefinitionsForEditor" in app_js
    assert "renderFlowDefinitionTable" in app_js
    assert "renderFlowSelectedSteps" in app_js
    assert "flowChainEditorSelectedSteps" in app_js
    assert "add-flow-definition" in app_js
    assert "move-step-up" in app_js
    assert "remove-selected-step" in app_js
    assert "/api/tools/flow/start" in app_js
    assert "/api/tools/flow/history" in app_js
    assert "schedule_cron" not in app_js
    assert "schedule_enabled" not in app_js
    assert "openFlowCronBuilder" not in app_js
    assert "renderFlowCronBuilder" not in app_js
    assert "parseFlowCronExpression" not in app_js
    assert "start_flow_scheduler" not in server_py
    assert "due_scheduled_chains" not in server_py
    assert 'trigger_type="scheduled"' not in server_py

    settings_list = re.search(r"(?m)^\.flow-chain-settings-list\s*\{(?P<body>.*?)\}", css, re.S)
    assert settings_list is not None
    assert "max-height:" in settings_list.group("body")
    assert "overflow-y: auto" in settings_list.group("body")

    editor_modal = re.search(r"(?m)^\.flow-chain-editor-modal\s*\{(?P<body>.*?)\}", css, re.S)
    assert editor_modal is not None
    assert "max-width:" in editor_modal.group("body")
    for selector in [
        ".flow-step-builder",
        ".flow-definition-table",
        ".flow-selected-step-list",
    ]:
        assert selector in css
    assert ".flow-cron-modal" not in css
    assert ".flow-cron-specific-grid" not in css


def test_flow_chain_editor_shows_only_flow_name_in_available_table():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)

    assert 'id="flowDefinitionTable"' in html
    assert 'id="flowManualFlowId"' in html
    assert 'id="addManualFlowBtn"' in html
    assert "搜索流程名称或 flow_id" in html
    assert "renderFlowDefinitionTable" in app_js
    assert "_renderFlowDefinitionTable" in app_js
    assert "renderFlowDefinitionLimitHint" in app_js
    assert "payload.truncated" in app_js
    assert "仅展示前 500 条" in app_js
    table_function = re.search(
        r"function _renderFlowDefinitionTable\(flows\) \{(?P<body>.*?)\n\}",
        app_js,
        re.S,
    )
    assert table_function is not None
    table_body = table_function.group("body")
    assert "<th>流程名称</th>" in table_body
    assert "<th>flow_id</th>" not in table_body
    assert "flow.name" in table_body
    assert "data-flow-id" in table_body
    assert "data-flow-name" in table_body


def test_flow_chain_editor_add_flow_uses_button_payload_fallback():
    app_js = _read(APP_JS)

    click_handler = re.search(
        r"flowDefinitionTable\?\.addEventListener\(\"click\", \(e\) => \{(?P<body>.*?)\n\}\);",
        app_js,
        re.S,
    )
    assert click_handler is not None
    click_body = click_handler.group("body")
    assert "addFlowDefinitionToSelected({" in click_body
    assert "flow_id: button.dataset.flowId" in click_body
    assert "name: button.dataset.flowName" in click_body
    assert "addFlowDefinitionToSelected(button.dataset.flowId" not in click_body

    add_function = re.search(
        r"function addFlowDefinitionToSelected\(flowInput = \{\}\) \{(?P<body>.*?)\n\}",
        app_js,
        re.S,
    )
    assert add_function is not None
    add_body = add_function.group("body")
    assert "const requestedFlow = normalizeFlowStep(flowInput);" in add_body
    assert "|| requestedFlow" in add_body
    assert "未找到该流程，请刷新流程列表后重试" in add_body
    assert "addManualFlowBtn?.addEventListener" in app_js
    assert "flowManualFlowId.value" in app_js


def test_flow_chain_editor_modal_fields_are_not_squeezed_by_global_modal_field_layout():
    css = _read(STYLES_CSS)

    editor_field = re.search(r"(?m)^\.flow-chain-editor-modal \.modal-field\s*\{(?P<body>.*?)\}", css, re.S)
    assert editor_field is not None
    editor_field_body = editor_field.group("body")
    assert "display: grid" in editor_field_body
    assert "align-items: stretch" in editor_field_body

    editor_field_label = re.search(r"(?m)^\.flow-chain-editor-modal \.modal-field span\s*\{(?P<body>.*?)\}", css, re.S)
    assert editor_field_label is not None
    assert "width: auto" in editor_field_label.group("body")

    editor_input = re.search(r"(?m)^\.flow-chain-editor-modal \.setting-input\s*\{(?P<body>.*?)\}", css, re.S)
    assert editor_input is not None
    editor_input_body = editor_input.group("body")
    assert "width: 100%" in editor_input_body
    assert "min-height: 38px" in editor_input_body

    editor_textarea = re.search(r"(?m)^\.flow-chain-editor-modal textarea\.setting-input\s*\{(?P<body>.*?)\}", css, re.S)
    assert editor_textarea is not None
    assert "min-height: 128px" in editor_textarea.group("body")


def test_flow_chain_editor_save_uses_single_function_set_and_visible_feedback():
    app_js = _read(APP_JS)

    for function_name in [
        "renderFlowChainSettings",
        "readFlowSettingsFromForm",
        "addFlowChainConfig",
    ]:
        assert app_js.count(f"function {function_name}") == 1

    save_function = re.search(
        r"function saveFlowChainFromEditor\(\) \{(?P<body>.*?)\n\}\n\ntoolCardFlow",
        app_js,
        re.S,
    )
    assert save_function is not None
    body = save_function.group("body")
    assert "setFlowChainEditorStatus(" in body
    assert "showToast(" in body
    assert "renderFlowChainSettings(chains)" in body
    assert "closeFlowChainEditor()" in body


def test_flow_chain_editor_blank_overlay_click_does_not_close_modal():
    app_js = _read(APP_JS)

    assert 'flowChainEditorOverlay?.addEventListener("click"' not in app_js


def test_flow_settings_source_select_uses_name_only_and_shows_execute_url_rule():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)

    source_select = re.search(r"function fillFlowSourceSelect\(select, dataSources, selected = \"\"\) \{(?P<body>.*?)\n\}\n\nasync function loadFlowSettings", app_js, re.S)
    assert source_select is not None
    source_select_body = source_select.group("body")
    assert "const label = item.name || value;" in source_select_body
    assert "item.db_type" not in source_select_body
    assert "item.database" not in source_select_body

    assert "系统会自动追加 ?id=flow_id" in html
    assert "validateFlowExecuteUrl" in app_js


def test_dark_mode_is_separate_from_theme_choices_and_has_nav_toggles():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert 'name="theme"' not in html
    assert html.count('data-theme-toggle-logo') == 2
    assert 'id="topDarkModeToggle"' in html
    assert 'id="sidebarDarkModeToggle"' in html
    assert html.index('id="topDarkModeToggle"') < html.index('class="top-nav-item" data-page="home"')
    assert html.index('id="sidebarDarkModeToggle"') < html.index('id="statusText"')

    for text in [
        "const topDarkModeToggle",
        "const sidebarDarkModeToggle",
        "function toggleThemeFromLogo",
        "function applyDarkMode",
        "function syncDarkModeButtons",
        'document.documentElement.setAttribute("data-color-mode", "dark")',
    ]:
        assert text in app_js

    assert "[data-color-mode=\"dark\"]" in css
    assert ".dark-mode-toggle" in css
    assert "[data-theme=\"space-tech\"] .top-nav .dark-mode-toggle" in css


def test_flow_chain_background_toast_has_container_and_theme_styles():
    html = _read(INDEX_HTML)
    app_js = _read(APP_JS)
    css = _read(STYLES_CSS)

    assert 'id="flowToastContainer"' in html
    assert "loadFlowToastStatus" in app_js
    assert "/api/flow-chain/status" in app_js
    assert "data-action=\"toggle-flow-toast\"" in app_js
    assert "data-action=\"close-flow-toast\"" in app_js
    assert "if (flowBgRunBtn) flowBgRunBtn.hidden = !flowCurrentJobId;" in app_js
    assert "流程任务正在提交" in app_js
    assert ".flow-toast-container" in css
    assert ".flow-toast.flow-toast--vitality.running .flow-toast-header" in css
    assert ".flow-toast.flow-toast--calm.running .flow-toast-header" in css
    assert "@keyframes flow-pulse-blue" in css
    assert "@keyframes flow-pulse-teal" in css
    assert "[data-color-mode=\"dark\"] .flow-toast" in css


def test_flow_modal_supports_background_progress_mode():
    app_js = _read(APP_JS)

    assert "showFlowModalProgressMode" in app_js
    assert "startFlowModalBackgroundPoll" in app_js
    assert "已提交，流程在后台运行中" in app_js
    assert "flowBgRunBtn" in app_js
    assert "后台运行" in app_js


def test_flow_cancel_uses_job_id_and_disables_button_while_stopping():
    app_js = _read(APP_JS)

    cancel_flow = re.search(r"async function cancelFlowChain\(\) \{(?P<body>.*?)\n\}", app_js, re.S)
    assert cancel_flow is not None
    body = cancel_flow.group("body")
    assert 'body: JSON.stringify({ job_id: flowCurrentJobId })' in body
    assert "if (flowCancelBtn?.disabled) return;" in body
    assert "flowCancelBtn.disabled = true" in body
    assert "停止中" in body
