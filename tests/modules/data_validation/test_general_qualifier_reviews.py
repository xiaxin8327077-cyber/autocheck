import pytest

from auto_check.modules.data_validation.generation_policy import remaining_qualifier_reviews
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request
from tests.modules.data_validation.test_category_numeric_reviews import setup_rules


BOUND_NOTE = "需求中'一般不大于0'的校验阈值未明确，需确认是否仅检查非空还是需检查单位净值是否大于0"
DIRECTION_NOTE = ("需求中'一般不大于0'的阈值未明确，需确认是否还需检查单位净值小于等于0或大于0；"
                  "当前仅实现非空检查")
MEASURE = {"field_name": "f_unit", "field_cn": "单位净值", "data_type": "numeric"}
COMPLETE = {"logic": "any", "conditions": [
    {"left": "f_unit", "op": "gt", "right_type": "value", "right": 0}, {"left": "f_unit", "op": "is_null"},
]}


@pytest.mark.parametrize("request_text", ["单位净值一般不大于0且一定不能为空", "单位净值不得为空且一般不大于0"])
def test_threshold_reviews_use_the_verified_null_and_numeric_predicates(request_text):
    independent = "需确认取值截止日期是否为月末"
    notes = [BOUND_NOTE, DIRECTION_NOTE + "；" + independent]
    assert remaining_qualifier_reviews(request_text, COMPLETE, notes, fields=[MEASURE]) == [independent]
    extra = "另一个指标尚待核实；当前仅实现非空检查"
    assert remaining_qualifier_reviews(request_text, COMPLETE, [extra], fields=[MEASURE]) == [extra]


@pytest.mark.parametrize("unresolved", ["需确认是否检查单位净值是否大于1", "是否还需检查累计净值是否大于0",
                                         "需确认是否不检查单位净值大于0", "需确认是否还需检查单位净值小于0或大于0",
                                         "需确认是否排除清算记录", "当前仅实现按月非空检查"])
def test_mixed_reviews_keep_unknown_subject_bound_negation_or_filter(unresolved):
    subject = "单位净值不得为空且一般不大于0"
    assert remaining_qualifier_reviews(subject, COMPLETE, [BOUND_NOTE + "；" + unresolved], fields=[MEASURE]) == [unresolved]
    for bad in (COMPLETE["conditions"][0], {**COMPLETE, "logic": "all"},
                {**COMPLETE, "conditions": [COMPLETE["conditions"][0], {"left": "f_other", "op": "is_null"}]}):
        assert remaining_qualifier_reviews(subject, bad, [BOUND_NOTE], fields=[MEASURE]) == [BOUND_NOTE]


def test_review_on_a_negative_decimal_lower_bound_uses_its_own_documented_field_and_complement():
    request = "当期收益率通常不低于-2.5且一定不能为空"
    field = {"field_name": "yield_rate", "field_cn": "当期收益率", "data_type": "numeric"}
    expression = {"logic": "any", "conditions": [
        {"left": "yield_rate", "op": "is_null"}, {"left": "yield_rate", "op": "lt", "right_type": "value", "right": -2.5},
    ]}
    note = "需求中‘通常不低于-2.5’的阈值未明确，需确认是否检查yield_rate大于等于-2.5或低于-2.5"
    assert remaining_qualifier_reviews(request, expression, [note], fields=[field]) == []
    assert remaining_qualifier_reviews(request, expression, [note], fields=[MEASURE]) == [note]


@pytest.mark.parametrize(("qualifier", "requirement", "violation", "op", "value"), [
    ("一般", "不大于10", "大于10", "gt", 10),
    ("通常", "不低于-2.5", "低于-2.5", "lt", -2.5),
    ("原则上", "不得超过500", "超过500", "gt", 500),
])
def test_documented_threshold_and_manual_review_resolve_only_the_qualifier(
        qualifier, requirement, violation, op, value):
    request = f"目标指标不得为空且{qualifier}{requirement}"
    expression = {"logic": "any", "conditions": [
        {"left": "measure", "op": "is_null"},
        {"left": "measure", "op": op, "right_type": "value", "right": value},
    ]}
    note = f"需求中‘{qualifier}{requirement}’的‘{qualifier}’未定义排除规则，需确认是否将{violation}作为异常候选处理"
    extra = "报送范围中需排除清算状态，折算币种及截止日期待确认"
    assert remaining_qualifier_reviews(request, expression, [note, extra]) == [extra]
    assert remaining_qualifier_reviews(request, expression, [note + "；" + extra]) == [extra]
    wrong_note = note.replace(violation + "作为", "大于99作为")
    assert any("大于99" in item for item in remaining_qualifier_reviews(request, expression, [wrong_note]))
    assert remaining_qualifier_reviews("排除清算记录，" + request, expression, [note]) == [note]
    expression["conditions"][1]["right"] = value + 1
    assert remaining_qualifier_reviews(request, expression, [note]) == [note]


def test_two_model_stages_keep_original_notes_and_only_ask_for_documented_choices():
    note = "需求中‘通常不低于3’的‘通常’未定义排除规则，需确认是否将低于3作为异常候选处理"
    independent = "需确认是否按月末截止"
    rules, _ = setup_rules(notes=[note], draft={"rule_type": None, "uncertainties": [note, independent]})
    result = rules.parse_rule_request(user(), _request(request_text="非净值型项目的净值通常不低于3"))
    for stage in ("select_table", "generate_rule"):
        assert note in result["model_judgments"][stage]["uncertainties"]
    assert note not in result["uncertainties"]
    assert independent in result["uncertainties"] and result["preview"] is None
    assert any("合理例外" in item for item in result["notices"])
