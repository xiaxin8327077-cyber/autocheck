from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "src" / "auto_check" / "modules" / "report_special_processing" / "web"


def read(name: str) -> str:
    return (WEB / name).read_text(encoding="utf-8")


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

    assert "report_processes.map" in source
    assert "users.map" in source
    assert 'role: "tablist"' in source
    assert 'role: "tab"' in source
    assert "aria-selected" in source
    assert 'tabIndex: "0"' in source
    assert 'event.key === "Enter"' in source
    assert "关联报送" in source
    assert "涉及报表" in source
    assert "处理摘要" in source
    assert "特殊处理时间" in source
    assert "处理人" in source
    assert "状态" in source
    assert "操作" in source
    assert "special_handling_from" not in source
    assert "special_handling_to" not in source
    assert "脚本仅保存留痕，不在系统内执行。" in source
    assert "复制脚本" in source
    assert "执行脚本" not in source
    assert "提交审批" not in source


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


def test_module_css_is_scoped_light_only_and_keeps_overlay_drawer():
    css = read("styles.css")
    scope = '.auto-check-module[data-module="report_special_processing"]'

    assert scope in css
    for forbidden in ("\nbutton {", "\ninput {", "\ntable {", "prefers-color-scheme", "dark-mode", "text-shadow"):
        assert forbidden not in css
    assert "position: fixed" in css
    assert "right: 0" in css
    assert "width: clamp(680px, 46vw, 860px)" in css
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
