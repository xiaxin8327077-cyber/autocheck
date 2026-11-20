import pytest

from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request
from tests.modules.data_validation.test_followup_service_bridge import _rules
from tests.modules.data_validation.test_semantic_generation import FIELDS, draft


@pytest.mark.parametrize("two_bound_tables", [False, True], ids=["one-bound", "two-bound"])
def test_cross_table_suggestions_preserve_pending_business_question(two_bound_tables):
    question = "乙表的复核条件是什么？"
    plans = [{"target": {"table": "test_table"}, "draft": draft()}]
    extra = [{"name": "other_table", "cn": "乙表", "dimension": "设备",
              "fields": [("row_id", "编号", "varchar", "Y"), ("other", "剩余量", "numeric", ""),
                         ("business_day", "数据日期", "date", "")]}]
    request_text = "检查测试表份额低于19，同时帮我看一下乙表。"
    if two_bound_tables:
        plans.append({"target": {"table": "detail_table"}, "draft": draft("weight")})
        extra.append({"name": "detail_table", "cn": "称重表", "dimension": "设备",
                      "fields": [("row_id", "编号", "varchar", "Y"), ("weight", "重量", "numeric", ""),
                                 ("business_day", "数据日期", "date", "")]})
        request_text = "检查测试表份额和称重表重量低于19，同时帮我看一下乙表。"
    plans.append({"target": {"table": "other_table"}, "draft": {
        "rule_type": None, "expression": {},
        "semantic_intent": {"metrics": [], "scopes": [], "open_questions": [question]},
    }})
    proposal = {"plan_mode": "parallel", "plans": plans}
    suggestion = {"category": "consistency", "kind": "review", "title": "核实份额与重量统计范围",
                  "references": [{"table_name": "test_table", "field_name": "amount"},
                                 {"table_name": "detail_table", "field_name": "weight"}]}
    rules, model = _rules([proposal, proposal, {"ai_suggestions": [suggestion]}], fields=FIELDS,
                          dimension="设备", extra_tables=extra)
    complete = model.complete_with_options

    def complete_with_usage(*args, **kwargs):
        reply = complete(*args, **kwargs)
        return {**reply, "usage": {"completion_tokens": 500}}

    model.complete_with_options = complete_with_usage
    result = rules.parse_rule_request(user(), _request(request_text=request_text, analysis_protocol=2))
    cards = {o["candidate"]["table_name"]: o["candidate"] for o in result["candidate_options"]}
    assert len(cards) == len(plans)
    assert cards["other_table"]["rule_type"] is None
    assert cards["other_table"]["uncertainties"] == [question]
    assert all(not card.get("preview") for card in cards.values())
    for table, field in [("test_table", "amount")] + ([("detail_table", "weight")] if two_bound_tables else []):
        bound = cards[table]
        assert bound["expression"] == {"left": field, "op": "lt", "right_type": "value", "right": 19}
        preview = rules.preview_candidate(user(), {**bound, "name": bound["rule_name"]}, return_questions=True)
        assert preview["sql_preview"]
    supplement_prompts = [call["messages"][0]["content"] for call in model.calls
                          if "本轮只提出独立补充校验建议" in call["messages"][0]["content"]]
    if two_bound_tables:
        prompt, = supplement_prompts
        assert "other_table" not in prompt and "test_table" in prompt and "detail_table" in prompt
        assert [item["title"] for item in result["ai_suggestions"]] == [suggestion["title"]]
    else:
        assert not supplement_prompts and not result["ai_suggestions"]
