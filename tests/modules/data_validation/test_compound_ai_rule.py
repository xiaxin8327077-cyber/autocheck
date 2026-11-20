import copy

import pytest

from auto_check.modules.data_validation.ai_service import refine_candidate
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.query_grounding import check_request_coverage
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _generate_payload, _request, _rules_with_doc, _select_payload


def bounds(field="nav", logic="any"):
    return {"logic": logic, "conditions": [
        {"left": field, "op": "gt", "right_type": "value", "right": 1},
        {"left": field, "op": "lt", "right_type": "value", "right": 0},
    ]}


def test_ai_numeric_range_preview_test_and_save_round_trip():
    fields = [("row_id", "编号", "varchar", "Y"), ("nav", "单位净值", "numeric", ""),
              ("report_date", "报送日期", "date", "")]
    draft = _generate_payload(expression=bounds("单位净值", "OR"), null_policy="skip", equality_policy="allow_equal")
    rules, model = _rules_with_doc([_select_payload(), draft], fields=fields)
    result = rules.parse_rule_request(user(), _request(request_text="单位净值不得大于1或小于0"))
    assert len(model.calls) == 2
    assert result["expression"] == bounds()
    assert result["model_judgments"]["generate_rule"]["expression"] == bounds("单位净值")
    assert not result["questions"] and not result["uncertainties"]
    preview = result["preview"]
    assert preview and " OR " in preview["sql_preview"]
    definition = preview["definition"]
    tested = rules.test_candidate(user(), {"definition": definition, "expected_hash": preview["content_sha256"]})
    assert tested["passed_count"] == len(tested["cases"]) > 0
    saved = rules.save_draft(user(), definition)
    assert rules.storage.latest_version(saved["id"])["definition"]["expression"] == bounds()


def test_shared_metric_choice_applies_to_both_bounds_and_precedes_sql():
    columns = [{"column_name": "unit", "comment": "单位净值", "data_type": "numeric"},
               {"column_name": "total", "comment": "累计净值", "data_type": "numeric"}]
    rule = _generate_payload(expression=bounds("净值"))
    result = refine_candidate(rule, columns=columns, dialect="postgresql", existing=[])
    assert len(result["questions"]) == 1
    question = result["questions"][0]
    assert question["targets"] == ["expression.conditions.0.left", "expression.conditions.1.left"]
    assert {item["value"] for item in question["options"]} == {"unit", "total"}


def test_all_comparisons_between_date_fields_can_be_saved_as_one_rule():
    fields = [("row_id", "编号", "varchar", "Y"), ("report_date", "报送日期", "date", ""),
              ("end_day", "截止日", "date", ""), ("issue_day", "发行日", "date", ""),
              ("posted_day", "入账日", "date", "")]
    expr = {"logic": "all", "conditions": [
        {"left": "end_day", "op": "lt", "right_type": "field", "right": "issue_day"},
        {"left": "end_day", "op": "lt", "right_type": "field", "right": "posted_day"},
    ]}
    draft = _generate_payload(expression=expr, null_policy="skip")
    rules, _ = _rules_with_doc([_select_payload(), draft], fields=fields)
    result = rules.parse_rule_request(user(), _request(request_text="截止日同时早于发行日和入账日时列为异常"))
    assert result["expression"] == expr and result["preview"]
    preview = result["preview"]
    assert "issue_day" in preview["sql_preview"] and "posted_day" in preview["sql_preview"]
    saved = rules.save_draft(user(), preview["definition"])
    assert rules.storage.latest_version(saved["id"])["definition"]["expression"] == expr


def test_model_guess_cannot_skip_documented_balance_choices():
    fields = [("row_id", "编号", "varchar", "Y"), ("report_date", "报送日期", "date", ""),
              ("opening", "期初余额", "numeric", ""), ("closing", "期末余额", "numeric", "")]
    draft = _generate_payload(expression=bounds("closing"), null_policy="skip")
    rules, _ = _rules_with_doc([_select_payload(), draft], fields=fields)
    ambiguous = rules.parse_rule_request(user(), _request(request_text="余额不得大于1或小于0"))
    assert not ambiguous["preview"]
    question, = ambiguous["questions"]
    assert question["targets"] == ["expression.conditions.0.left", "expression.conditions.1.left"]
    assert {item["value"] for item in question["options"]} == {"opening", "closing"}
    rules, _ = _rules_with_doc([_select_payload(), draft], fields=fields)
    explicit = rules.parse_rule_request(user(), _request(request_text="期末余额不得大于1或小于0"))
    assert explicit["preview"] and not explicit["questions"]


def test_explicit_range_checks_require_both_bounds_on_same_field():
    columns = [{"field_name": "nav", "field_cn": "单位净值", "data_type": "numeric"}]
    rule = {"description": "单位净值不得大于1或小于0", "expression": bounds()}
    assert not check_request_coverage(rule, columns, [])
    for key, value in (("logic", "all"), ("conditions", [bounds()["conditions"][0]])):
        changed = {**rule, "expression": {**bounds(), key: value}}
        assert check_request_coverage(changed, columns, [])
    wrong = copy.deepcopy(rule)
    wrong["expression"]["conditions"][1]["left"] = "other"
    assert check_request_coverage(wrong, columns, [])


@pytest.mark.parametrize("expr", [
    {"logic": "any", "conditions": []},
    {"logic": "any", "conditions": [bounds(), bounds()]},
    {"logic": "xor", "conditions": bounds()["conditions"]},
])
def test_invalid_model_group_cannot_silently_become_a_single_comparison(expr):
    with pytest.raises(AppError) as caught:
        refine_candidate(_generate_payload(expression=expr), columns=[], dialect="mysql", existing=[])
    assert caught.value.code == "MODEL_RESPONSE_INVALID"
