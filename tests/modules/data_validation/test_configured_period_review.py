from copy import deepcopy
from types import SimpleNamespace

from auto_check.modules.data_validation.documented_choices import document_choices
from auto_check.modules.data_validation.prompt_defaults import DEFAULT_PROMPTS
from tests.modules.data_validation.test_ai_latency_pipeline import combined, run
from tests.modules.data_validation.test_ai_service import _rules_with_doc
from tests.modules.data_validation.test_documented_ambiguity_fast_review import measure, set_field
from tests.modules.data_validation.test_semantic_generation import FIELDS


def test_fast_choices_cannot_skip_a_period_field_named_in_current_business_policy():
    names = ["unit", "total", "opening"]
    fields = [{"field_name": name, "field_cn": label, "data_type": "numeric"}
              for name, label in zip(names, ["单笔耗量", "累计耗量", "期初耗量"])]
    table = {"id": 1, "table_name": "readings"}
    analysis = SimpleNamespace(resolve=lambda *args: table, fields={1: fields},
                               index=SimpleNamespace(details={1: set(names)}), request="耗量不得为空",
                               prompts={"business_scope": "已确认主选项为unit、total、opening。"})
    plan = {"rule_type": "field_compare", "expression": {"left": "unit", "op": "is_null"},
            "semantic_intent": {"metrics": [{"side": "left", "term": "耗量", "fields": names[:2]}],
                                "scopes": [], "open_questions": []}}
    pending = [{"kind": "metrics", "candidates": [{"table_id": 1, "fields": names}]}]
    assert document_choices(analysis, {"target": {"table": "readings"}, "draft": plan}, pending,
                            lambda *args: None) is None


def test_explicit_business_policy_for_period_field_requires_document_review():
    fields = [*FIELDS, ("unit", "单笔耗量", "numeric", ""), ("total", "累计耗量", "numeric", ""),
              ("opening", "期初耗量", "numeric", ""), ("state", "运输状态", "varchar", "")]
    plans = [measure("unit", "单笔耗量"), measure("total", "累计耗量")]
    reviewed = {"plans": [*deepcopy(plans), measure("opening", "期初耗量")], "plan_mode": "parallel"}
    rules, model = _rules_with_doc([combined({"plans": plans, "plan_mode": "parallel"}), reviewed,
                                    {"ai_suggestions": []}], fields=fields)
    set_field(rules, "state", dictionary="Y-在途\nN-到站")
    rules.storage.save_prompt("business_scope", DEFAULT_PROMPTS["business_scope"] +
                              "\n已确认耗量检查包含单笔、累计和期初耗量opening三个主选项。", "test")
    result = run(rules, "在途的耗量不得小于等于-7")
    assert {c["candidate"]["expression"]["left"] for c in result["candidate_options"]} == {
        "unit", "total", "opening"}
    assert any("期初耗量" in call["messages"][0]["content"] and
               "待核实编号" in call["messages"][0]["content"] for call in model.calls)
