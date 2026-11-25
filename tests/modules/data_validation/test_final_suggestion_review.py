import json
from types import SimpleNamespace

import pytest

from auto_check.modules.data_validation.semantic_generation import SemanticAnalysis
from tests.modules.data_validation.test_ai_latency_pipeline import combined, run
from tests.modules.data_validation.test_ai_service import _rules_with_doc
from tests.modules.data_validation.test_semantic_generation import FIELDS, draft


def test_special_review_uses_relevant_policy_paragraph_and_knowledge_entry_only():
    unrelated = "另对重量进行质量复核"
    policy = "已确认装载率应对首运设备开工载荷另提期间建议。该字段不能替换为重量。"
    other_rule = "重量调整使用weight和adjusted_weight。不得采用装载率与工资的乘积。"
    knowledge = {"条目": [{"topic": "运输费", "summary": unrelated}, {"topic": "开工时点", "summary": "首运装载率按启用日计算。附带日期和工资等十八个词。"}]}
    candidate = {"table_name": "cargo", "expression": {"left": "mass", "op": "is_null"},
                 "semantic_intent": {"metrics": [{"term": "装载率", "side": "left", "fields": ["mass"]}]},
                 "columns": [{"column_name": "mass", "field_cn": "载量", "logic": "业务别名：装载率。"},
                             {"column_name": "start_load", "field_cn": "开工载荷"}, {"column_name": "weight", "field_cn": "重量"}]}
    calls = []
    model = SimpleNamespace(prefix=unrelated, request="装载率不能为空", prompts={"business_scope": "\n".join([policy, unrelated, other_rule])},
                            inputs={"source": {"name": "运输"}, "knowledge_prefix": "条目如下\n" + json.dumps(knowledge, ensure_ascii=False)},
                            round_number=1, output_tokens_used=100, call=lambda prompt, stage: calls.append(prompt) or {"ai_suggestions": []})
    assert SemanticAnalysis.supplement_suggestions(model, [candidate]) is None
    prompt, = calls
    assert policy in prompt and "首运装载率按启用日计算" in prompt and "start_load" in prompt
    assert unrelated not in prompt and '"field_name":"weight"' not in prompt
    assert other_rule not in prompt and "十八个词" not in prompt


def test_bound_request_metric_retrieves_policy_when_document_label_differs():
    candidate = {"table_name": "cargo", "expression": {"left": "mass", "op": "is_null"},
                 "semantic_intent": {"metrics": [{"term": "装载率", "side": "left", "fields": ["mass"]}]},
                 "columns": [{"column_name": "mass", "field_cn": "期末载荷"}]}
    calls = []
    policy = "业务确认如下，按实际登记分类选择对应分支。分支A在相反范围对装载率另提建议。"
    analysis = SimpleNamespace(request="装载率不能为空", prompts={"business_scope": policy},
        inputs={"source": {"name": "运输"}}, round_number=1, output_tokens_used=0,
        call=lambda prompt, stage: calls.append(prompt) or {"ai_suggestions": [], "no_suggestion_reason": "当前范围已覆盖。"})
    assert SemanticAnalysis.supplement_suggestions(analysis, [candidate]) == []
    assert len(calls) == 1 and policy in calls[0]


def test_unexplained_empty_review_keeps_bound_initial_target_and_marks_incomplete():
    plan = draft()
    target = {"table_name": "test_table", "expression": {"left": "amount", "op": "gt", "right_type": "value", "right": 99}}
    advice = {"category": "consistency", "kind": "field_compare_binary", "title": "另核份额上限",
              "reason": "已有独立上限检查要求", "scope_replacements": [], "check_target": target,
              "references": [{"table_name": "test_table", "field_name": "amount"}]}
    plan["ai_suggestions"] = [advice]
    rules, model = _rules_with_doc([combined(plan), {"ai_suggestions": []}], fields=FIELDS)
    result = run(rules, "份额小于19")
    assert result["ai_suggestions_status"] == "incomplete" and len(model.calls) == 2
    item, = result["ai_suggestions"]
    assert item["adoption"] and item["check_target"] == target and item["references"] == advice["references"]


@pytest.mark.parametrize("outcome", ["corrected", "unsupported", "not_applicable"])
def test_final_list_replaces_wrong_kind_wrong_direction_and_cached_input(outcome):
    plan = draft()
    initial = {"category": "consistency", "kind": "aggregate_consistency", "title": "无依据的相反方向和求和",
               "references": [{"table_name": "test_table", "field_name": "amount"}]}
    corrected = {**initial, "kind": "field_compare_binary", "category": "coverage_gap", "title": "按确认分类检查实际份额"}
    plan["ai_suggestions"] = [initial]
    reviewed = {"ai_suggestions": [corrected] if outcome == "corrected" else []}
    if outcome == "not_applicable":
        reviewed["no_suggestion_reason"] = "主案已采用同一对象、同一阈值和同一期间，无另一项有据的检查。"
    rules, model = _rules_with_doc([combined(plan), reviewed], fields=FIELDS)
    result = run(rules, "份额小于19")
    assert len(model.calls) == 2
    assert "无依据的相反方向和求和" in model.calls[1]["messages"][0]["content"]
    assert [s["title"] for s in result["ai_suggestions"]] == ([corrected["title"]] if outcome == "corrected" else [])
    assert bool(result.get("ai_suggestions_status") == "incomplete") == (outcome == "unsupported")
    assert result["preview"]
    if outcome != "unsupported":
        replay = run(rules, "份额小于19")
        assert len(model.calls) == 2 and replay["ai_suggestions"] == result["ai_suggestions"]
