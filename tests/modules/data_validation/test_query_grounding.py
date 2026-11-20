from copy import deepcopy

import pytest

from auto_check.modules.data_validation.query_grounding import (
    dictionary_options, documented_scope_comparison, field_profiles, ground_candidate_query, project_mart_target,
)


FIELDS = [
    {"field_name": "project_code", "field_cn": "项目编号", "data_type": "varchar", "is_pk": "Y"},
    {"field_name": "status", "field_cn": "项目状态", "data_type": "varchar", "dictionary": "【D1】\n0-已完结\n1-存续", "logic": "原始项目状态"},
    {"field_name": "report_status", "field_cn": "项目状态", "data_type": "varchar", "dictionary": "【D2】\n0-本月销户\n1-已完结未销户\n2-存续", "logic": "报送范围口径"},
    {"field_name": "loan_status", "field_cn": "贷款状态", "data_type": "varchar", "dictionary": "0-异常\n1-正常"},
    {"field_name": "amount", "field_cn": "实收金额", "data_type": "numeric"},
    {"field_name": "business_day", "field_cn": "业务日期", "data_type": "date"},
]


def candidate():
    return {"questions": [], "uncertainties": [], "can_enable": False}


def test_dictionary_preserves_text_codes_and_rejects_dictionary_heading():
    assert dictionary_options(FIELDS[1]) == [{"value": "0", "label": "已完结"}, {"value": "1", "label": "存续"}]
    assert dictionary_options({"data_type": "int", "dictionary": "-1-未知\n1-有效"}) == [
        {"value": -1, "label": "未知"}, {"value": 1, "label": "有效"}]


def test_same_business_label_in_two_dictionaries_is_not_one_assumed_code():
    result = candidate()
    draft = {"filters": [{"table": "base", "field": "status", "op": "eq", "value": "1", "confirmed": True}]}
    ground_candidate_query(result, draft, FIELDS, [], "存续项目实收一般不为0，贷款正常")
    assert result["filters"][0]["confirmed"] is False
    question = result["questions"][0]
    assert question["id"] == "filters.0"
    choices = [item["selection"] for item in question["options"]]
    assert {(item["field"], item["value"]) for item in choices} == {("status", "1"), ("report_status", "2")}
    assert all(item["confirmed"] for item in choices)
    assert all(item["field"] != "loan_status" for item in choices)
    assert draft["filters"][0]["confirmed"] is True  # input is not mutated


def test_document_scope_can_supply_a_choice_without_inventing_state_codes():
    result = candidate()
    ground_candidate_query(result, {}, FIELDS, [], "存续项目实收不为0")
    assert result["filters"][0]["confirmed"] is False
    assert len(result["questions"][0]["options"]) == 2
    already_scoped = candidate()
    ground_candidate_query(already_scoped, {}, FIELDS, [], "存续项目实收不为0", scope_confirmed=True)
    assert "filters" not in already_scoped


def test_still_active_projects_use_the_existing_document_scope():
    result = candidate()
    ground_candidate_query(result, {}, [FIELDS[1]], [], "仍存续项目的实收不得小于0")
    assert result["filters"] == [{"table": "base", "field": "status", "op": "eq", "value": "1", "confirmed": True}]
    assert result["questions"] == []


@pytest.mark.parametrize(("label", "dictionary", "request_text", "value"), [
    ("是否已复核", "7-是\n0-否", "请检查已复核客户的余额不得小于0", "7"),
    ("客户类型", "02-企业\n03-个人", "企业客户的余额不得小于0", "02"),
])
def test_unique_documented_scope_uses_dictionary_without_business_specific_branches(label, dictionary, request_text, value):
    field = {"field_name": "scope_code", "field_cn": label, "data_type": "varchar", "dictionary": dictionary}
    result = candidate()
    ground_candidate_query(result, {}, [field], [], request_text)
    assert result["filters"] == [{"table": "base", "field": "scope_code", "op": "eq", "value": value, "confirmed": True}]
    assert result["questions"] == []


def test_constant_check_needs_a_documented_measure_not_a_reference_in_another_calculation():
    fields = [
        {"field_name": "reviewed", "field_cn": "是否已复核", "dictionary": "A-是\nB-否"},
        {"field_name": "amount", "field_cn": "科目余额", "data_type": "decimal",
         "logic": "按科目编号为2123-留存收益，取科目余额。"},
    ]
    request = "请检查已复核客户的留存收益原则上不得小于 12.5"
    assert documented_scope_comparison(request, fields) == {
        "term": "留存收益", "entity": "客户",
        "expression": {"left": "amount", "op": "lt", "right_type": "value", "right": 12.5},
        "filter": {"table": "base", "field": "reviewed", "op": "eq", "value": "A", "confirmed": True},
    }
    for logic in ["不包含留存收益", "取总额减去留存收益的差值。", "当留存收益大于0时取1，否则取0。"]:
        assert documented_scope_comparison(request, [fields[0], {**fields[1], "logic": logic}]) is None


def test_constant_check_keeps_qualifiers_and_incompletely_documented_scope_alternatives():
    fields = [FIELDS[1], FIELDS[4]]
    assert documented_scope_comparison("上期存续项目的实收金额不得小于0", fields) is None
    ambiguous = [*fields, {"field_name": "report_status", "field_cn": "项目状态", "dictionary": ""}]
    assert documented_scope_comparison("存续项目的实收金额不得小于0", ambiguous) is None
    conflicting = [{**FIELDS[1], "dictionary": "1-存续\n1-终止"}, FIELDS[4]]
    assert documented_scope_comparison("存续项目的实收金额不得小于0", conflicting) is None


def test_conflicting_documented_scope_fields_are_not_resolved_by_model_or_field_order():
    fields = [{"field_name": name, "field_cn": "是否已复核", "dictionary": f"{value}-是"}
              for name, value in [("reviewed", "1"), ("report_reviewed", "2")]]
    result = candidate()
    ground_candidate_query(result, {"filters": [{"field": "report_reviewed", "op": "eq", "value": "2"}]},
                           fields, [], "已复核客户的余额不得小于0")
    assert [item["selection"]["field"] for item in result["questions"][0]["options"]] == ["reviewed", "report_reviewed"]
    assert result["filters"][0]["confirmed"] is False


def test_single_model_suggested_filter_is_not_evidence_of_an_explicit_user_scope():
    field = {"field_name": "reviewed", "field_cn": "是否已复核", "dictionary": "1-是\n0-否"}
    result = candidate()
    ground_candidate_query(result, {"filters": [{"field": "reviewed", "op": "eq", "value": "1"}]},
                           [field], [], "所有客户的余额不得小于0")
    assert result["filters"] == []
    assert result["questions"] == []


@pytest.mark.parametrize("model_operator", ["eq", "neq"])
@pytest.mark.parametrize("request_text", [
    "当期终止项目的实收不得大于0，排除资产证券化服务信托",
    "当期终止项目的实收不得大于0，且信托产品类型不等于3",
])
def test_explicit_product_type_exclusion_uses_the_unique_documented_value(request_text, model_operator):
    fields = [
        {"field_name": "terminated_in_period", "field_cn": "是否当期终止", "dictionary": "7-是\n0-否"},
        {"field_name": "trust_type", "field_cn": "信托产品类型", "dictionary": "3-资产证券化服务信托\n6-资产管理信托"},
    ]
    result = candidate()
    ground_candidate_query(result, {"filters": [{"field": "trust_type", "op": model_operator, "value": "6"}]},
                           fields, [], request_text)
    assert result["questions"] == []
    assert [(item["field"], item["op"], item["value"], item["confirmed"]) for item in result["filters"]] == [
        ("terminated_in_period", "eq", "7", True), ("trust_type", "neq", "3", True),
    ]


def test_explicit_exclusion_without_document_evidence_blocks_a_broader_preview():
    result = candidate()
    ground_candidate_query(result, {}, FIELDS, [], "检查实收金额，排除特殊项目")
    assert result["questions"] == []
    assert result["preview_error"] in result["uncertainties"]


PROJECT_STATES = [
    {"field_name": "c_projstatus", "field_cn": "项目状态", "dictionary": "0-已完结\n1-存续"},
    {"field_name": "pro_status", "field_cn": "项目状态", "dictionary": "0-本月销户\n2-存续"},
    {"field_name": "pro_isclose", "field_cn": "信托产品存续标识", "dictionary": "0-已销户\n1-存续（未完结）\n2-已完结未销户"},
    {"field_name": "unrelated", "field_cn": "其他", "dictionary": "9-非存续"},
]


@pytest.mark.parametrize("seed", [None, ("c_projstatus", 1), ("pro_status", "2"), ("pro_isclose", "1"), ("c_projstatus", "6")])
def test_scope_choices_are_stable_for_each_model_proposal(seed):
    result = candidate()
    draft = {"filters": [{"field": seed[0], "op": "eq", "value": seed[1]}]} if seed else {}
    ground_candidate_query(result, draft, PROJECT_STATES, [], "存续的项目，实收信托一般不为0")
    assert [(item["selection"]["field"], item["selection"]["value"]) for item in result["questions"][0]["options"]] == [
        ("c_projstatus", "1"), ("pro_status", "2"), ("pro_isclose", "1"),
    ]
    assert result["filters"] == [{"table": "base", "field": "c_projstatus", "op": "eq", "value": "1", "confirmed": False}]
    assert result["uncertainties"] == [result["questions"][0]["uncertainty"]]


@pytest.mark.parametrize("request_text", ["项目状态不能为空", "检查项目是否完结", "检查项目是否存续"])
def test_project_status_terms_find_field_evidence_without_assuming_active(request_text):
    table = {"id": 1, "table_name": "reg_pub_project_info"}
    hints = field_profiles([table], {1: PROJECT_STATES}, request_text)
    assert all(field["field_name"] in hints for field in PROJECT_STATES[:3])
    result = candidate()
    ground_candidate_query(result, {}, PROJECT_STATES, [], request_text)
    assert "filters" not in result


def test_mart_target_is_specific_to_project_grain_and_authorized_source():
    table = {"table_name": "reg_pub_project_info"}
    assert project_mart_target("监管报送集市", [table], "存续的项目，实收信托一般不为0") is table
    assert project_mart_target("监管报送集市", [table], "项目维度与合同金额关联核实") is table
    assert project_mart_target("监管报送集市", [table], "项目合同的状态不能为空") is None
    assert project_mart_target("监管报表", [table], "项目维度实收不能为0") is None


def test_membership_filter_requires_user_values_and_keeps_the_explicit_set():
    result = candidate()
    values = ["0", "1"]
    draft = {"filters": [{"field": "status", "op": "in", "value": values}]}
    ground_candidate_query(result, draft, FIELDS, [], "仅检查项目状态属于两个值的记录")
    assert result["questions"] == [] and result["preview_error"] in result["uncertainties"]
    explicit = candidate()
    ground_candidate_query(explicit, draft, FIELDS, [], "仅检查 status 属于 0、1 的记录")
    assert explicit["questions"] == []
    assert explicit["filters"] == [{"table": "base", "field": "status", "op": "in", "value": values, "confirmed": True}]


def test_join_model_confirmations_and_date_guesses_are_reset():
    result = candidate()
    draft = {"join": {"table_name": "related", "on": [{"left": "project_code", "right": "project_code"}],
                      "report_date_field": "business_day", "relationship_confirmed": True, "unmatched_policy": "exclude"}}
    original = deepcopy(draft)
    ground_candidate_query(result, draft, FIELDS, FIELDS, "关联校验")
    assert result["join"]["relationship_confirmed"] is False
    assert result["join"]["unmatched_policy"] == "unresolved"
    # 关联表唯一明确期间列自动采用，不再要求用户重复确认显然的日期口径。
    assert result["join"]["report_date_field"] == "business_day"
    assert [item["id"] for item in result["questions"]] == [
        "join.relationship_confirmed", "join.unmatched_policy"]
    assert draft == original


def _join_draft():
    return {"join": {"table_name": "related", "on": [{"left": "project_code", "right": "project_code"}],
                     "report_date_field": "day_a", "relationship_confirmed": True, "unmatched_policy": "exclude"}}


def test_join_date_question_retained_when_period_candidates_are_not_unique():
    fields = [
        {"field_name": "day_a", "field_cn": "业务日期", "data_type": "date"},
        {"field_name": "day_b", "field_cn": "数据日期", "data_type": "date"},
    ]
    result = candidate()
    ground_candidate_query(result, _join_draft(), FIELDS, fields, "关联校验")
    assert result["join"]["report_date_field"] == ""
    assert "join.report_date_field" in {item["id"] for item in result["questions"]}


def test_join_date_question_retained_for_event_only_date():
    fields = [{"field_name": "d_begin", "field_cn": "项目开始日", "data_type": "date"}]
    result = candidate()
    ground_candidate_query(result, _join_draft(), FIELDS, fields, "关联校验")
    assert result["join"]["report_date_field"] == ""
    question = next(item for item in result["questions"] if item["id"] == "join.report_date_field")
    assert [option["value"] for option in question["options"]] == ["d_begin"]
