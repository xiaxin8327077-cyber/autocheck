import pytest

from auto_check.modules.data_validation.query_grounding import check_request_coverage, ground_candidate_query


FIELDS = [
    {"field_name": name, "field_cn": label, "data_type": kind}
    for name, label, kind in [
        ("init_nav", "当期新发项目初始净值", "numeric"), ("unit_nav", "单位净值", "numeric"),
        ("acc_nav", "累计净值", "decimal"), ("opening_acc", "期初累计净值", "numeric"),
        ("nav_day", "单位净值日期", "date"), ("nav_kind", "累计净值类型", "varchar"),
        ("growth", "累计净值增长率", "numeric"), ("mislabelled", "模拟净值", "date"),
        ("converted", "资产净值折人民币", "numeric"),
    ]
]


@pytest.mark.parametrize("phrase", ["净值不得为空", "净值不能为空"])
def test_plain_nav_uses_all_documented_measures_and_preserves_independent_reviews(phrase):
    issue = "另需确认是否纳入特殊合同。"
    candidate = {"expression": {"left": "unit_nav", "op": "is_null"}, "questions": [], "uncertainties": [issue]}
    ground_candidate_query(candidate, {}, FIELDS, [], phrase)
    question, = candidate["questions"]
    assert question["id"] == "expression.left"
    choices = {option["value"] for option in question["options"]}
    assert choices == {"init_nav", "unit_nav", "acc_nav", "opening_acc"}
    assert set(candidate["uncertainties"]) == {issue, question["uncertainty"]}
    for field in choices:
        assert not check_request_coverage({"description": phrase, "expression": {"op": "is_null", "left": field}},
                                          FIELDS, [])
    for invalid in ["nav_day", "nav_kind", "growth", "converted", "mislabelled"]:
        assert check_request_coverage({"description": phrase, "expression": {"op": "is_null", "left": invalid}},
                                      FIELDS, [])


def test_incomplete_model_field_list_expands_to_all_grounded_choices_but_exact_name_wins():
    for term, expected in [("净值", {"unit_nav", "acc_nav", "init_nav", "opening_acc"}), ("累计净值", {"acc_nav"})]:
        candidate = {"expression": {"left": "acc_nav", "op": "is_null"}, "uncertainties": [],
                     "questions": [{"id": "expression.left", "text": "采用哪个字段？", "options": [
                         {"value": "unit_nav", "label": "单位净值"}, {"value": "acc_nav", "label": "累计净值"}]}]}
        ground_candidate_query(candidate, {}, FIELDS, [], term + "不得为空")
        if len(expected) > 1:
            assert {o["value"] for o in candidate["questions"][0]["options"]} == expected
        else:
            assert candidate["questions"] == [] and candidate["expression"]["left"] == "acc_nav"


def test_all_nav_choices_retain_the_same_explicit_business_scope():
    fields = [*FIELDS, {"field_name": "method", "field_cn": "原始运行方式", "data_type": "varchar",
                        "dictionary": "1-开放式净值型\n2-非净值型\n3-封闭式净值型"}]
    phrase = "项目原始运行方式为净值型时，净值不得为空"
    candidate = {"expression": {"left": "unit_nav", "op": "is_null"}, "uncertainties": [], "questions": []}
    ground_candidate_query(candidate, {}, fields, [], phrase)
    fields_to_check = {item["value"] for item in candidate["questions"][0]["options"]}
    assert fields_to_check == {"init_nav", "unit_nav", "acc_nav", "opening_acc"}
    assert candidate["filters"][0]["value"] == ["1", "3"]
    for name in fields_to_check:
        definition = {**candidate, "description": phrase, "expression": {"left": name, "op": "is_null"}}
        assert not check_request_coverage(definition, fields, [])


def test_plain_requirement_rejects_extra_scopes_joins_or_changed_predicates_at_preview():
    phrase = "累计净值不得为空"
    predicate = {"left": "acc_nav", "op": "is_null"}
    filter_ = {"table": "base", "field": "nav_kind", "op": "eq", "value": "1", "confirmed": True}
    for unexpected in [{"filters": [filter_]}, {"join": {"table_name": "elsewhere"}},
                       {"expression": {"left": "acc_nav", "op": "is_not_null"}},
                       {"expression": {"left": "opening_acc", "op": "is_null"}}]:
        assert check_request_coverage({"description": phrase, "expression": predicate, **unexpected}, FIELDS, [])
    candidate = {"expression": predicate.copy(), "uncertainties": [], "questions": []}
    ground_candidate_query(candidate, {"filters": [filter_]}, FIELDS, [], phrase)
    assert not candidate.get("filters")
