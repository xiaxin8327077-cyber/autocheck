"""A scoped threshold and mandatory nonempty condition retain their own documented subjects."""
import pytest

from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request
from tests.modules.data_validation.test_explicit_scope_compound_preview import _project_rules


@pytest.mark.parametrize(("second_term", "null_field"), [("", "f_netvalue"), ("累计净值", "f_totalnetvalue"), ("数据日期", "d_cdate")])
def test_model_order_and_each_documented_operand_survive_parse_and_preview(second_term, null_field):
    request = f"原始运行方式为净值型的项目的单位净值一般不大于0且{second_term}一定不能为空"
    expression = {"logic": "any", "conditions": [
        {"left": null_field, "op": "is_null"},
        {"left": "f_netvalue", "op": "gt", "right_type": "value", "right": 0},
    ]}
    rules, model = _project_rules({"target": {"table": "proj_info_dtl_pboc"}},
                                  {"rule_type": "field_compare", "expression": expression})
    candidate = rules.parse_rule_request(user(), _request(request_text=request))
    assert not candidate["questions"] and not candidate["uncertainties"], candidate
    definition = candidate["preview"]["definition"]
    assert definition["expression"] == expression
    assert definition["filters"][0]["field"] == "c_oper_mode_orig" and definition["filters"][0]["value"] == ["1", "3"]
    assert " IS NULL" in candidate["preview"]["sql_preview"] and " OR " in candidate["preview"]["sql_preview"]
    assert rules.preview_candidate(user(), definition, return_questions=True)["sql_preview"] == candidate["preview"]["sql_preview"]
    assert len(model.calls) == 2


def test_undocumented_independent_operand_cannot_be_replaced_by_the_first_metric():
    request = "原始运行方式为净值型的项目的单位净值一般不大于0且内部审批日期一定不能为空"
    rules, _ = _project_rules({"target": {"table": "proj_info_dtl_pboc"}}, {"rule_type": "field_compare", "expression": {
        "logic": "any", "conditions": [{"left": "f_netvalue", "op": "gt", "right_type": "value", "right": 0},
                                     {"left": "f_netvalue", "op": "is_null"}]}})
    candidate = rules.parse_rule_request(user(), _request(request_text=request))
    assert not candidate["preview"]
    assert "内部审批日期" in str(candidate["uncertainties"])
    assert all("不大于0且" not in q["text"] for q in candidate["questions"])


def test_old_preview_rechecks_generated_null_field_issue_against_the_complete_expression():
    request = "原始运行方式为净值型的项目的单位净值一般不大于0且一定不能为空"
    stale = "需确认「单位净值一般不大于0且一定」对应的文档字段及非空检查。"
    other = "还需核对清算期例外。"
    rules, _ = _project_rules({"target": {"table": "proj_info_dtl_pboc"}}, {"rule_type": "field_compare", "expression": {
        "logic": "any", "conditions": [{"left": "f_netvalue", "op": "gt", "right_type": "value", "right": 0},
                                     {"left": "f_netvalue", "op": "is_null"}]}})
    candidate = rules.parse_rule_request(user(), _request(request_text=request))
    definition = {**candidate["preview"]["definition"], "uncertainties": [stale], "uncertainty_resolutions": [""]}
    assert rules.preview_candidate(user(), definition, return_questions=True).get("sql_preview")
    definition.update(uncertainties=[stale, other], uncertainty_resolutions=["", ""])
    blocked = rules.preview_candidate(user(), definition, return_questions=True)
    assert not blocked.get("sql_preview") and blocked["definition"]["uncertainties"] == [other]
