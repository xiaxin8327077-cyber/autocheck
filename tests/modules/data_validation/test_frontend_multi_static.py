from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "src" / "auto_check" / "modules" / "data_validation" / "web"


def read(*parts: str) -> str:
    return WEB.joinpath(*parts).read_text(encoding="utf-8")


def test_multi_candidate_contract_is_real() -> None:
    api = read("api.js")
    workbench = read("pages", "workbench.js")
    options = read("components", "candidate_options.js")
    styles = read("styles.css")

    assert "batchSaveCandidates" in api and "/ai/candidates/batch-save" in api
    assert "candidate_options" in workbench and "comparison_suggestions" in workbench
    assert "setupMultiOptions" in workbench and "activateOption" in workbench and "toggleOption" in workbench
    assert "saveSelectedOptions" in workbench and "saveOptionAndEnable" in workbench
    assert "requestKeyRegistry" in workbench and "createRequestKeyRegistry" in workbench
    assert "workbench-preview" in workbench and "workbench-test" in workbench

    assert "发现多个有依据的校验方案" in options
    assert "dv-ai-option-check" in options and "dv-ai-option-card" in options
    assert "查看/完善此方案" in options and "保存当前方案并启用" in options and "完善并启用此方案" in options
    assert "检查粒度" in options and "dv-ai-option-current" in options and "原始文档证据" in options
    assert "dv-ai-option-detail-slot" in options and "getSlotEl" in options
    assert "shortObjectLabel" in options
    assert "保存所选" in options and "dv-ai-saved-results" in options
    assert "可进一步检查的一致性" in options
    for token in ("grain", "table_label", "field_label", "match_reason", "differences", "recommended", "gates", "locked"):
        assert token in options
    assert "footerBulk" in workbench and "optionGate" in workbench and "batchSaveCandidates" in workbench
    assert "ai_suggestions" in workbench and "dv-ai-supplements" in workbench and "renderSuggestions" in workbench
    assert "suggestionScopeReady()" in workbench and "page.suggestionsSection.hidden = !list.length" in workbench
    assert "当前文档尚不足以给出可靠的额外建议" not in workbench
    form = read("components", "rule_form.js")
    state = read("state.js")
    assert "review" in form and "系统处理：缺值单列核查" in form
    assert "project_columns" in form and 'field === "mapping"' in form
    assert "NULL按0仅支持数值字段或有限数值常量比较" in form
    assert "NULL按0仅支持数值字段比较或有限数值常量" in state
    for token in ("project_context", "project_context.", "projectContext"):
        assert token in form
    assert "项目上下文口径尚未确认" in state

    for token in ("dv-ai-options", "dv-ai-option-card", "dv-ai-option-check", "dv-ai-suggestions", "dv-ai-saved-results", "dv-ai-result"):
        assert token in styles
    for var in ("--ui-radius", "--ui-panel-surface", "--ui-subsection-surface", "--ui-content-border"):
        assert var in styles


def test_option_checkbox_cannot_inherit_full_width_global_input_style() -> None:
    styles = read("styles.css")
    checkbox = styles.split('.dv-ai-option-check {', 1)[1].split('}', 1)[0]
    assert "width: 16px" in checkbox
    assert "flex: 0 0 16px" in checkbox
    assert "padding: 0" in checkbox
