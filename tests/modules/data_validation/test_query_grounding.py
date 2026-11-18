from copy import deepcopy

import pytest

from auto_check.modules.data_validation.query_grounding import (
    dictionary_options, field_profiles, ground_candidate_query, project_mart_target,
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


def test_membership_filter_does_not_turn_a_requested_set_into_a_single_state():
    result = candidate()
    values = ["0", "1"]
    ground_candidate_query(result, {"filters": [{"field": "status", "op": "in", "value": values}]}, FIELDS, [], "状态属于两个值")
    assert result["questions"][0]["options"][0]["selection"]["value"] == values


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
