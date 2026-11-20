"""Document-backed named categories apply to both branches of a compound metric check."""
from copy import deepcopy

import pytest

from auto_check.modules.data_validation.conditional_reviews import category_numeric_check, conditional_null_check, plain_null_check
from auto_check.modules.data_validation.query_grounding import check_request_coverage, dictionary_options, ground_candidate_query


FIELDS = [
    {"field_name": "class_now", "field_cn": "评级", "dictionary": "0-普通\n1-特别", "data_type": "int"},
    {"field_name": "original_class", "field_cn": "评级（原始）", "dictionary": "8-甲类特别\n9-乙类特别\n7-非特别", "data_type": "int"},
    {"field_name": "book", "field_cn": "账面余额", "data_type": "numeric"},
    {"field_name": "available", "field_cn": "可用余额", "data_type": "numeric"},
]
SCOPE = {"field": "original_class", "table": "base", "op": "in", "value": [8, 9], "confirmed": True}
OPERANDS = [{"left": "book", "op": "is_null"}, {"left": "book", "op": "gt", "right_type": "value", "right": 12.5}]


@pytest.mark.parametrize("scope", ["原始评级为特别的账户的", "当原始评级为特别时，", "original_class等于特别时，账户的"])
def test_named_category_resolves_one_dictionary_and_both_comparisons(scope):
    request = scope + "账面余额不得为空且一般不大于12.5"
    check = category_numeric_check(request, FIELDS, dictionary_options, dimension="账户")
    assert check.scope.selections == [SCOPE]
    expression = check.expression("book")
    assert expression == {"logic": "any", "conditions": OPERANDS}
    assert not check.expression_issue({"logic": "any", "conditions": list(reversed(OPERANDS))})
    definition = {"description": request, "filters": [SCOPE], "expression": expression}
    assert not check_request_coverage(definition, FIELDS, [], dimension="账户")
    for wrong in [{**SCOPE, "field": "class_now"}, {**SCOPE, "value": [8]}, {**SCOPE, "value": [7, 8]}]:
        assert check_request_coverage({**definition, "filters": [wrong]}, FIELDS, [], dimension="账户")
    for wrong in [OPERANDS[0], {**expression, "logic": "all"}, {"logic": "any", "conditions": [
        OPERANDS[0], {**OPERANDS[1], "right": 13}]}, {"logic": "any", "conditions": [
        {**OPERANDS[0], "left": "available"}, OPERANDS[1]]}]:
        assert check.expression_issue(wrong)


def test_shared_metric_questions_and_scope_evidence_leave_a_separate_review_open():
    request = "原始评级为特别的账户的余额不得为空且一般不大于12.5"
    check = category_numeric_check(request, FIELDS, dictionary_options, dimension="账户")
    note = "原始评级字段original_class中'特别'对应的具体码值未在文档中明确，需进一步确认；仍需核实币种折算。"
    result = {"expression": check.expression("book"), "uncertainties": [note], "questions": []}
    assert ground_candidate_query(result, {}, FIELDS, [], request, dimension="账户")
    question, = result["questions"]
    assert set(question["targets"]) == {"expression.conditions.0.left", "expression.conditions.1.left"}
    assert {o["value"] for o in question["options"]} == {"book", "available"}
    assert result["uncertainties"] == ["仍需核实币种折算", question["text"]]
    assert result["filters"] == [SCOPE]


def test_a_different_row_owner_and_broken_dictionary_cannot_supply_the_scope():
    request = "原始评级为特别的账户的账面余额不得为空且一般不大于12.5"
    for dimension, dictionary in [("合同", FIELDS[1]["dictionary"]), ("账户", "8-甲类特别\n8-非特别")]:
        fields = deepcopy(FIELDS)
        fields[1]["dictionary"] = dictionary
        check = category_numeric_check(request, fields, dictionary_options, dimension=dimension)
        assert not check.scope.selections
        assert check.coverage_issue({"expression": check.expression("book"), "filters": [SCOPE]})


def test_a_specific_exception_after_the_compound_check_remains_unresolved():
    request = "原始评级为特别的账户的账面余额不得为空且一般不大于12.5，但已冻结账户除外"
    assert not category_numeric_check(request, FIELDS, dictionary_options, dimension="账户")
    incomplete = conditional_null_check(request, FIELDS, dictionary_options, dimension="账户")
    assert "已冻结账户除外" in incomplete.extra
    assert "已冻结账户除外" in check_request_coverage(
        {"expression": {"logic": "any", "conditions": OPERANDS}, "filters": [SCOPE], "description": request},
        FIELDS, [], dimension="账户",
    )


@pytest.mark.parametrize("predicate", ["一般不大于0且一定", "超过内部限额且", "不得为空或"])
def test_comparison_clause_never_becomes_a_null_check_field(predicate):
    term = f"账面余额{predicate}"
    fields = [*FIELDS, {"field_name": "coincidental_label", "field_cn": term, "data_type": "numeric"}]
    assert plain_null_check(term + "不能为空", fields) is None
    check = conditional_null_check("原始评级为特别的账户的" + term + "不能为空", fields, dictionary_options,
                                   dimension="账户")
    assert check is None or (check.term == "账面余额" and check.extra == "或不能为空")


def test_named_scope_and_two_different_operands_are_verified_independently():
    request = "当原始评级为特别时，账面余额一般不大于0且可用余额一定不能为空"
    check = category_numeric_check(request, FIELDS, dictionary_options, dimension="账户")
    conditions = [{"left": "available", "op": "is_null"}, {"left": "book", "op": "gt", "right_type": "value", "right": 0}]
    definition = {"description": request, "filters": [SCOPE], "expression": {"logic": "any", "conditions": conditions}}
    assert check and not check.coverage_issue(definition)
    assert not check_request_coverage(definition, FIELDS, [], dimension="账户")
    assert check_request_coverage({**definition, "filters": []}, FIELDS, [], dimension="账户")
    wrong = {"logic": "any", "conditions": [{**conditions[0], "left": "book"}, conditions[1]]}
    assert "可用余额" in check.expression_issue(wrong)
    unknown_request = request.replace("可用余额", "内部风控额度")
    unknown = category_numeric_check(unknown_request, FIELDS, dictionary_options, dimension="账户")
    assert "内部风控额度" in unknown.coverage_issue(definition)
