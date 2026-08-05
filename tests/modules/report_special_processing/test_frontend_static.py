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
    for capability in ("context.root", "context.api", "context.user", "context.notify", "context.confirm", "context.navigate"):
        assert capability in source
    assert "window." not in "\n".join(read(path) for path in ("index.js", "api.js", "state.js"))
    assert "AbortController" in read("api.js")
    assert "cancelAll" in read("api.js")


def test_api_contract_covers_catalog_ledger_actions_conflicts_and_audit():
    source = read("api.js")

    for endpoint in (
        '"/catalog"',
        '"/records"',
        '"/summary"',
        '"/status"',
        '"/void"',
        '"/reopen"',
        '"/audit"',
    ):
        assert endpoint in source
    assert "record_version_conflict" in source
    assert "记录已被其他人更新，请刷新后重试" in source
    assert "409" in source
    assert "internal_error" in source


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
    assert "users.map" in source
    assert 'role: "tablist"' in source
    assert 'role: "tab"' in source
    assert "aria-selected" in source
    assert 'tabIndex: "0"' in source
    assert 'event.key === "Enter"' in source or "ArrowLeft" in source
    assert "关联报送" in source
    assert "涉及报表" in source
    assert "处理摘要" in source
    assert "特殊处理时间" in source
    drawer = read("components/record_drawer.js")
    assert 'labeledField(documentRef, "特殊处理时间"' not in drawer
    assert "nowHandlingAt" in drawer
    assert 'labeledField(documentRef, "所处报送期", fields.period)' in drawer
    assert 'labeledField(documentRef, "处理人", fields.handler)' in drawer
    assert "rsp-form-grid-basic" in drawer
    assert "defaultHandlerId" in drawer
    assert "!creating" in drawer
    assert 'labeledField(documentRef, "操作原因"' in drawer
    assert "rsp-workflow-state" in drawer
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

    assert "root.replaceChildren(intro, availability, createTabs(), layout)" not in source
    assert "root.replaceChildren(...[intro, availability, createTabs(), layout, modal].filter(Boolean))" in source
    assert "rsp-catalog-warning" in source
    assert "rsp-record-modal" in source


def test_editor_supports_draft_record_status_admin_and_audit_pagination():
    source = read("components/record_drawer.js")

    for label in ("保存草稿", "保存记录", "保存修改", "完成", "作废", "重开", "操作留痕"):
        assert label in source
    for action in ("saveDraft", "saveRecord", "completeRecord", "voidRecord", "reopenRecord", "loadAudit"):
        assert action in source
    assert "row_version" in source
    assert "can_admin" in source
    assert "catalogAvailable" in source
    assert "disabled" in source
    assert 'aria-modal": "true"' in source
    assert "rsp-record-modal-overlay" in source
    assert "收起详情" not in source
    assert "Escape" in source


def test_ledger_table_empty_state_and_list_layout_align_with_system_lists():
    table_source = read("components/record_table.js")
    css = read("styles.css")
    scope = '.auto-check-module[data-module="report_special_processing"]'

    assert 'className: "rsp-empty-row"' in table_source
    assert 'colspan: "7"' in table_source
    assert "没有符合条件的特殊处理记录" in table_source
    assert "wrap.append(element(documentRef, \"div\", { className: \"rsp-empty\"" not in table_source
    assert "formatDisplayDateTime" in table_source
    assert "formatDisplayDateTime(record.special_handling_at)" in table_source
    assert 'replace("T", " ")' in table_source

    assert f"{scope} .rsp-filters" in css
    assert "display: flex" in css
    assert f"{scope} .rsp-ledger-table th" in css
    assert "text-align: center" in css
    assert "min-height: 280px" not in css
    assert "min-height: max(520px, calc(100vh - 270px))" not in css
    assert "calc(100vh - 270px)" not in css
    assert "flex: 1 1 auto" in css
    assert "grid-template-rows: minmax(0, 1fr)" in css
    assert "grid-template-rows: auto minmax(0, 1fr) auto" in css
    assert f"{scope} .rsp-empty-row td" in css
    assert "margin: 0 20px 12px" not in css
    assert "margin: 0 20px 24px" not in css
    assert "margin: 0 20px 10px" not in css
    assert "background: transparent" in css
    assert "padding: 4px 0 12px" in css
    assert "margin: 0 0 16px" in css
    assert "padding: 12px 20px" in css
    assert "padding: 8px 20px" in css
    assert "padding-left: 20px" in css
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
