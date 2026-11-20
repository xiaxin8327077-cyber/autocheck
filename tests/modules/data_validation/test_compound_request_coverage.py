from copy import deepcopy

import pytest

from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.query_grounding import check_request_coverage
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _generate_payload, _request, _rules_with_doc, _select_payload


FIELDS = [("row_id", "编号", "varchar", "Y"), ("report_date", "报送日期", "date", ""),
          ("bal", "期末余额", "numeric", ""), ("closing", "截止日", "date", ""),
          ("issue", "发行日", "date", ""), ("posting", "入账日", "date", "")]
VALUE = {"left": "bal", "op": "gt", "right_type": "value", "right": 100}
LOW = {**VALUE, "op": "lt", "right": 0}
DATE = {"left": "closing", "op": "lt", "right_type": "field", "right": "issue"}
OTHER = {**DATE, "right": "posting"}


@pytest.mark.parametrize(("request_text", "logic", "conditions"), [
    ("期末余额必须在0到100之间", "any", [VALUE, LOW]),
    ("期末余额不能超过100，也不能低于0", "any", [VALUE, LOW]),
    ("期末余额不能超过100，不能低于0", "any", [VALUE, LOW]),
    ("期末余额应大于等于0且小于等于100", "any", [VALUE, LOW]),
    ("期末余额介于0至100之间（不含端点）", "any", [{**VALUE, "op": "gte"}, {**LOW, "op": "lte"}]),
    ("截止日同时早于发行日和入账日时列为异常", "all", [DATE, OTHER]),
    ("截止日早于发行日或入账日时列为异常", "any", [OTHER, DATE]),
    ("截止日不得早于发行日和入账日", "any", [OTHER, DATE]),
    ("截止日不得同时早于发行日和入账日", "all", [DATE, OTHER]),
    ("期末余额不得大于100或为空", "any", [VALUE, {"left": "bal", "op": "is_null"}]),
    ("期末余额大于100或为空时列为异常", "any", [VALUE, {"left": "bal", "op": "is_null"}]),
])
def test_incomplete_draft_cannot_preview_or_save_while_complete_group_round_trips(request_text, logic, conditions):
    group = {"logic": logic, "conditions": conditions}
    def parse(expression):
        draft = _generate_payload(expression=expression, null_policy="skip", equality_policy="allow_equal")
        rules, _ = _rules_with_doc([_select_payload(), draft], fields=FIELDS)
        return rules, rules.parse_rule_request(user(), _request(request_text=request_text))
    _, incomplete = parse(conditions[0])
    assert not incomplete["preview"]
    rules, candidate = parse(group)
    definition = candidate["preview"]["definition"]
    assert rules.save_draft(user(), definition)["id"]
    for change in [conditions[0], {**group, "logic": "any" if logic == "all" else "all"}]:
        wrong = {**definition, "expression": change}
        assert not rules.preview_candidate(user(), wrong, return_questions=True).get("sql_preview")
        with pytest.raises(AppError):
            rules.save_draft(user(), wrong)


def test_literal_units_must_match_documented_storage_units_before_accepting_thresholds():
    description = "期末余额必须在0元到100万元之间"
    fields = [{"field_name": "bal", "field_cn": "期末余额", "data_type": "numeric", "logic": "单位：元。"}]
    # A conversion with no documentary evidence cannot quietly reuse the raw number.
    rule = {"description": description, "expression": VALUE}
    assert check_request_coverage(rule, fields, [])
    rule["expression"] = {"logic": "any", "conditions": [LOW, {**VALUE, "right": 1000000}]}
    assert not check_request_coverage(rule, fields, [])
    undocumented = deepcopy(fields)
    undocumented[0]["logic"] = ""
    assert check_request_coverage(rule, undocumented, [])
    rule["description"] = "期末余额应在1至100万元之间"
    rule["expression"]["conditions"][0] = {**LOW, "right": 10000}
    assert not check_request_coverage(rule, fields, [])
