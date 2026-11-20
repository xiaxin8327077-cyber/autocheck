import pytest

from auto_check.modules.data_validation.parallel_checks import parse_mixed_group, parse_number_comparison, parse_numeric_group
from auto_check.modules.data_validation.query_grounding import check_request_coverage


@pytest.mark.parametrize(("subject", "label", "op", "limit"), [
    ("单位净值不得为空且一般不大于10", "单位净值", "gt", 10),
    ("当期收益率不能为空，并且通常不低于-2.5", "当期收益率", "lt", -2.5),
    ("期末余额必填且原则上不得超过500", "期末余额", "gt", 500),
])
def test_nonempty_and_qualified_limit_require_both_violations_on_the_named_measure(subject, label, op, limit):
    fields = [{"field_name": name, "field_cn": caption, "data_type": "numeric"}
              for name, caption in (("value", label), ("other", "其他指标"))]
    empty = {"left": "value", "op": "is_null"}
    violation = {"left": "value", "op": op, "right_type": "value", "right": limit}
    complete = {"logic": "any", "conditions": [violation, empty]}

    def issue(expression):
        return check_request_coverage({"description": subject, "expression": expression}, fields, [])

    assert not issue(complete)
    for invalid in (violation, empty, {**complete, "logic": "all"},
                    {**complete, "conditions": [violation, {**empty, "left": "other"}]},
                    {**complete, "conditions": [{**violation, "right": limit + 1}, empty]}):
        assert issue(invalid)
    assert parse_number_comparison(subject) is None


@pytest.mark.parametrize(("prefix", "suffix"), [
    ("", "，已终止项目除外"), ("", "万元"), ("", "且按币种汇总"),
    ("除停用项外", ""), ("按币种汇总的", ""),
])
def test_additional_restrictions_cannot_be_dropped_from_a_mixed_group(prefix, suffix):
    fields = [{"field_name": "bal", "field_cn": "余额", "data_type": "numeric"}]
    expression = {"logic": "any", "conditions": [
        {"left": "bal", "op": "is_null"},
        {"left": "bal", "op": "gt", "right_type": "value", "right": 80},
    ]}
    rule = {"description": prefix + "余额不得为空且通常不大于80" + suffix, "expression": expression}
    assert check_request_coverage(rule, fields, [])


def test_both_checks_must_use_one_documented_balance_when_multiple_measures_fit():
    fields = [{"field_name": name, "field_cn": label, "data_type": "numeric"} for name, label in
              (("opening", "期初余额"), ("closing", "期末余额"), ("fee", "费用"))]
    for name in ("opening", "closing", "fee"):
        expression = {"logic": "any", "conditions": [{"left": name, "op": "is_null"},
                      {"left": name, "op": "gt", "right_type": "value", "right": 12}]}
        issue = check_request_coverage({"description": "余额不能为空且一般不大于12", "expression": expression}, fields, [])
        assert bool(issue) == (name == "fee")


def test_an_independent_limit_can_still_reference_a_name_containing_required():
    assert parse_number_comparison("必填项数量不得低于1") == (["必填项数量"], "lt", 1)


def test_repeated_nonempty_requirement_after_limit_still_uses_either_violation():
    fields = [{"field_name": "qty", "field_cn": "当期数量", "data_type": "numeric"}]
    conditions = [{"left": "qty", "op": "lt", "right_type": "value", "right": 5},
                  {"left": "qty", "op": "is_null"}]
    rule = {"description": "当期数量通常不低于5，并且不得为空", "expression": {"logic": "any", "conditions": conditions}}
    assert not check_request_coverage(rule, fields, [])
    rule["expression"]["logic"] = "all"
    assert check_request_coverage(rule, fields, [])


@pytest.mark.parametrize(("subject", "expected"), [
    ("单位净值一般不大于0且一定不能为空", [("单位净值", "gt", 0), ("单位净值", "is_null", None)]),
    ("期末余额通常不低于-2.5，并务必非空", [("期末余额", "lt", -2.5), ("期末余额", "is_null", None)]),
    ("合并余额原则上不得超过5且必须要不为空", [("合并余额", "gt", 5), ("合并余额", "is_null", None)]),
    ("期末余额一定不能为空并务必不超过18", [("期末余额", "is_null", None), ("期末余额", "gt", 18)]),
    ("发行日必须非空且期末余额一般不大于15", [("发行日", "is_null", None), ("期末余额", "gt", 15)]),
    ("期末余额一般不大于15并且发行日一定不能为空", [("期末余额", "gt", 15), ("发行日", "is_null", None)]),
])
def test_modifiers_belong_to_the_predicate_and_only_an_omitted_subject_is_inherited(subject, expected):
    assert parse_mixed_group(subject) == ("any", expected)


@pytest.mark.parametrize("subject", [
    "期末余额通常不大于0且发行日一定不能为空", "发行日务必不为空并期末余额通常不大于0",
])
def test_two_explicitly_named_metrics_cannot_be_replaced_with_one(subject):
    fields = [{"field_name": "bal", "field_cn": "期末余额", "data_type": "numeric"},
              {"field_name": "day", "field_cn": "发行日", "data_type": "date"}]
    limit = {"left": "bal", "op": "gt", "right_type": "value", "right": 0}
    empty = {"left": "day", "op": "is_null"}
    def issue(*parts):
        return check_request_coverage({"description": subject, "expression": {"logic": "any", "conditions": list(parts)}}, fields, [])
    assert not issue(empty, limit)
    assert issue({**empty, "left": "bal"}, limit)
    assert issue(empty, {**limit, "left": "day"})


@pytest.mark.parametrize("subject", [
    "期末余额一般不大于0元并务必非空", "期末余额一般不大于0且按合同汇总并一定不能为空",
    "期末余额不大于5且不低于1且务必不能为空", "期末余额不得超过8且一定不能为空，续期合同除外",
    "期末余额务必非空、另按业务币种折算后再检查阈值",
])
def test_unknown_units_additional_predicates_and_exclusions_cannot_be_lost(subject):
    fields = [{"field_name": "bal", "field_cn": "期末余额", "data_type": "numeric"}]
    expression = {"logic": "any", "conditions": [{"left": "bal", "op": "is_null"},
                  {"left": "bal", "op": "gt", "right_type": "value", "right": 0}]}
    assert check_request_coverage({"description": subject, "expression": expression}, fields, [])
    assert parse_mixed_group(subject) is None


def test_a_qualified_predicate_without_a_field_can_only_refer_to_its_preceding_subject():
    assert parse_number_comparison("一般不大于10") is None
    assert parse_numeric_group("期末余额不得大于100且一般不低于10") == (
        "any", [("期末余额", "gt", 100), ("期末余额", "lt", 10)])


def test_an_aging_bucket_in_a_metric_name_can_still_be_compared():
    assert parse_number_comparison("小于90天的贷款余额通常不得低于3") == (["小于90天的贷款余额"], "lt", 3)
