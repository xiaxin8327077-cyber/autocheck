from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "src" / "auto_check" / "modules" / "data_validation" / "web"


def read(*parts: str) -> str:
    return (WEB.joinpath(*parts)).read_text(encoding="utf-8")


def test_grounding_contract_is_wired_without_restoring_technical_form() -> None:
    form = read("components", "rule_form.js")
    candidate = read("components", "ai_candidate.js")
    panel = read("components", "test_panel.js")
    state = read("state.js")

    # operator 名与后端精确一致，不得出现旧/自造名。
    for op in ("lt", "lte", "gt", "gte", "eq", "neq", "in", "not_in", "is_null", "is_not_null"):
        assert f'"{op}"' in form
    assert "notnull" not in form

    # 表单必须保留新结构，不能白名单读丢。
    for token in ('filters', 'join', 'unmatched_policy', 'relationship_confirmed', 'related_columns', 'right_table'):
        assert token in form
    assert "readFilters()" in form and "readJoin()" in form
    assert "clearRelationEvidence()" in form, "切换数据源/表必须清理旧 query spec"
    assert "signature()" in form

    # 一元空值判断：canonical expression 只含 left/op，默认 violate/allow_equal。
    assert "isUnaryExpressionOp" in form
    assert 'if (isUnaryExpressionOp(comparison.op)) return comparison;' in form
    assert 'null_policy: unaryExpression ? "violate"' in form
    assert 'equality_policy: unaryExpression' in form

    # 业务摘要展示筛选/关联/日期，不恢复技术表单。
    for token in ("candidateFiltersText", "candidateJoinText", "candidateDateText", "适用范围", "关联核对", "检查日期"):
        assert token in candidate
    assert "candidateCondition" in candidate and "is_not_null" in candidate

    # 关系样本可读渲染，旧 flat 样本保留。
    assert "formatSample" in panel
    assert "row.base" in panel and "row.related" in panel and "report_date" in panel
    assert "[object Object]" not in panel

    # 确认门禁覆盖 filters/join。
    assert "筛选条件未确认" in state
    assert "关联关系尚未确认" in state
    assert "未匹配记录的处理口径尚未确认" in state
