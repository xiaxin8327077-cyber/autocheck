from copy import deepcopy

import pytest

from auto_check.modules.data_validation.semantic_grounding import ground_semantic_candidate, semantic_coverage_issue


FIELDS = [
    {"field_name": "method", "field_cn": "形态", "data_type": "varchar",
     "dictionary": "1-甲种标准类\n2-非标准类\n3-乙种标准类"},
    {"field_name": "original", "field_cn": "设立形态", "data_type": "int", "dictionary": "6-标准类\n8-非标准类"},
    {"field_name": "units", "field_cn": "单位价值", "data_type": "numeric"},
    {"field_name": "total", "field_cn": "总价值", "data_type": "numeric"},
    {"field_name": "flag", "field_cn": "状态", "data_type": "int", "dictionary": "5-正常\n9-终止"},
]
INTENT = {
    "metrics": [{"term": "价值", "side": "left", "fields": ["units", "total"], "recommended": "units"}],
    "scopes": [{"category": "标准类", "fields": ["method", "original"], "recommended": "original",
                "memberships": {"method": {"include": [1, 3], "exclude": [2]},
                                "original": {"include": ["6"], "exclude": ["8"]}}}],
    "open_questions": [],
}
FLAG = {"table": "base", "field": "flag", "op": "eq", "value": 5, "confirmed": True}


def generate(intent=INTENT, filters=(), fields=FIELDS, expression=None):
    candidate = {"expression": expression or {"left": "units", "op": "is_null"},
                 "questions": [], "uncertainties": []}
    ground_semantic_candidate(candidate, {"semantic_intent": deepcopy(intent), "filters": list(filters)}, fields, [])
    return candidate


def issue(definition, fields=FIELDS):
    return semantic_coverage_issue(definition, definition["semantic_intent"], fields, [])


def test_documented_model_alternatives_and_all_explicit_predicates_survive_confirmation():
    candidate = generate(filters=[{"field": "method", "op": "eq", "value": "1"}, FLAG])
    questions = {q["id"]: q for q in candidate["questions"]}
    assert {o["value"] for o in questions["expression.left"]["options"]} == {"units", "total"}
    choice = questions["filters.0"]["options"]
    assert [(o["selection"]["field"], o["selection"]["value"]) for o in choice] == [
        ("method", ["1", "3"]), ("original", 6)]
    assert not candidate["filters"][0]["confirmed"] and candidate["filters"][1] == FLAG
    for option in choice:
        confirmed = {**candidate, "expression": {"left": "total", "op": "is_null"},
                     "filters": [option["selection"], FLAG]}
        assert not issue(confirmed)
        assert issue({**confirmed, "filters": [option["selection"]]})
        assert issue({**confirmed, "filters": [FLAG, {**option["selection"], "value": "1"}]})
        assert issue({**confirmed, "expression": {"left": "total", "op": "is_not_null"}})
        assert issue({**confirmed, "expression": {"left": "flag", "op": "is_null"}})


def test_unique_documented_scope_uses_its_full_mapping_at_generation_and_retry():
    intent = {**INTENT, "metrics": [], "scopes": [{"category": "模型确定的分类", "fields": ["method"],
                 "memberships": {"method": {"include": [1, 3], "exclude": [2]}}}]}
    candidate = generate(intent)
    assert not candidate["questions"] and not issue(candidate)
    assert candidate["filters"] == [{"table": "base", "field": "method", "value": ["1", "3"], "op": "in",
                                     "confirmed": True}]
    changed = [{**FIELDS[0], "dictionary": "4-标准类"}, *FIELDS[1:]]
    assert issue(candidate, changed)
    relabeled = [{**FIELDS[0], "dictionary": FIELDS[0]["dictionary"].replace("甲种", "临时")}, *FIELDS[1:]]
    assert issue(candidate, relabeled)
    missing = [{**FIELDS[0], "dictionary": "【只有编号】"}, *FIELDS[1:]]
    assert generate(intent, fields=missing)["preview_error"]


@pytest.mark.parametrize("partition", [None, {"include": [1, 3]}, {"include": [1], "exclude": [2]},
                                       {"include": [1, 2], "exclude": [2, 3]},
                                       {"include": [1, 1, 3], "exclude": [2]},
                                       {"include": [1, 3], "exclude": [2, 6]}])
def test_every_documented_code_must_belong_to_exactly_one_model_group(partition):
    scope = {"category": "标准类", "fields": ["method"], "memberships": {"method": partition}}
    assert generate({**INTENT, "scopes": [scope]})["preview_error"]


def test_numeric_dictionary_normalizes_numeric_spellings_and_text_codes_keep_leading_zeros():
    fields = [{**FIELDS[0], "data_type": "decimal", "dictionary": "1.00-甲\n2.00-乙"}, *FIELDS[1:]]
    partition = {"include": ["1"], "exclude": [2]}
    intent = {"scopes": [{"category": "目标", "fields": ["method"], "memberships": {"method": partition}}]}
    candidate = generate(intent, fields=fields)
    assert candidate["filters"][0]["value"] == 1.0
    fields[0] = {**FIELDS[0], "dictionary": "01-甲\n02-乙"}
    assert generate(intent, fields=fields)["preview_error"]
    partition.update(include=["01"], exclude=["02"])
    assert generate(intent, fields=fields)["filters"][0]["value"] == "01"


@pytest.mark.parametrize("raw", [{**FLAG, "value": 3}, {**FLAG, "value": "5"}, {**FLAG, "field": "missing"},
                                  {**FLAG, "table": "related"}])
def test_unbound_model_filter_keeps_sql_blocked(raw):
    assert generate(filters=[raw])["preview_error"]


def test_open_questions_are_preserved_and_grouped_metrics_share_only_the_named_operand():
    expression = {"logic": "any", "conditions": [
        {"left": "units", "op": "is_null"}, {"left": "units", "op": "gt", "right_type": "value", "right": 8},
        {"left": "flag", "op": "is_null"}]}
    intent = {**INTENT, "open_questions": ["是否限定月末？"]}
    candidate = generate(intent, expression=expression)
    question = next(q for q in candidate["questions"] if q["id"].startswith("expression"))
    assert question["targets"] == ["expression.conditions.0.left", "expression.conditions.1.left"]
    assert "是否限定月末？" in candidate["uncertainties"]


def test_pending_question_cannot_be_removed_from_the_reviewed_result():
    candidate = generate({"metrics": [], "scopes": [], "open_questions": ["校验期以哪天为准？"]})
    assert issue({**candidate, "uncertainties": []})
    assert not issue({**candidate, "uncertainty_resolutions": ["报送日"]})


def test_conflicting_predicate_on_category_field_needs_model_correction():
    assert generate(filters=[{"field": "method", "op": "eq", "value": "2"}])["preview_error"]


def test_join_receipts_and_additional_filters_use_their_own_table():
    related = [{"field_name": "join_id", "field_cn": "标识", "data_type": "numeric"},
               {"field_name": "day", "field_cn": "业务日期", "data_type": "date"}, FIELDS[-1]]
    draft = {"semantic_intent": {}, "join": {"table_name": "related_data",
             "on": [{"left": "units", "right": "join_id"}], "relationship_confirmed": True, "unmatched_policy": "exclude"},
             "filters": [{**FLAG, "table": "related"}]}
    candidate = {"expression": {"left": "units", "op": "is_null"}}
    ground_semantic_candidate(candidate, draft, FIELDS, related)
    assert candidate["join"]["relationship_confirmed"] is True and candidate["join"]["unmatched_policy"] == "exclude"
    assert not candidate["questions"]
    assert candidate["filters"] == [{**FLAG, "table": "related"}]
    confirmed = {**candidate, "join": {**candidate["join"], "relationship_confirmed": True, "unmatched_policy": "exclude"}}
    assert not semantic_coverage_issue(confirmed, candidate["semantic_intent"], FIELDS, related)
    changed = {**confirmed, "filters": [FLAG]}
    assert semantic_coverage_issue(changed, candidate["semantic_intent"], FIELDS, related)


def test_related_category_uses_its_own_table_dictionary_when_column_names_overlap():
    related = [{"field_name": "join_id", "field_cn": "标识", "data_type": "numeric"},
               {"field_name": "day", "field_cn": "业务日期", "data_type": "date"},
               {**FIELDS[0], "dictionary": "A-开通\nC-关闭"}]
    scope = {"category": "可用", "table": "related", "fields": ["method"],
             "memberships": {"method": {"include": ["A"], "exclude": ["C"]}}}
    draft = {"semantic_intent": {"scopes": [scope]}, "join": {"table_name": "related_data",
             "on": [{"left": "units", "right": "join_id"}]},
             "filters": [{"table": "related", "field": "method", "op": "eq", "value": "A"}]}
    candidate = {"expression": {"left": "units", "op": "is_null"}}
    ground_semantic_candidate(candidate, draft, FIELDS, related)
    assert candidate["filters"] == [{"table": "related", "field": "method", "op": "eq", "value": "A",
                                     "confirmed": True}]
    assert not semantic_coverage_issue(candidate, candidate["semantic_intent"], FIELDS, related)


def test_sum_join_offers_supported_matched_only_and_review_policies():
    related = [{"field_name": "join_id", "field_cn": "编号", "data_type": "numeric"},
               {"field_name": "day", "field_cn": "业务日期", "data_type": "date"}, FIELDS[3]]
    candidate = {"expression": {"left": "units", "op": "neq", "right_table": "related", "right": "total"}}
    draft = {"semantic_intent": {}, "join": {"table_name": "related_data", "right_aggregate": "sum",
             "on": [{"left": "units", "right": "join_id"}]}}
    ground_semantic_candidate(candidate, draft, FIELDS, related)
    policy = next(q for q in candidate["questions"] if q["id"] == "join.unmatched_policy")
    assert {o["value"] for o in policy["options"]} == {"review", "exclude"}


@pytest.mark.parametrize("join", [
    {"on": [{"left": ["units"], "right": "contract_key"}]},
    {"on": [{"left": "units", "right": "contract_key"}]},
    {"on": [{"left": "method", "right": "contract_key"}], "join_type": "CROSS"},
])
def test_unverified_join_shapes_never_become_confirmable_selections(join):
    candidate = {"expression": {"left": "units", "op": "is_null"}}
    related = [{"field_name": "contract_key", "field_cn": "合同编号", "data_type": "varchar"}]
    draft = {"semantic_intent": {}, "join": {"table_name": "contracts", **join}}
    ground_semantic_candidate(candidate, draft, FIELDS, related)
    assert candidate["preview_error"] and "semantic_intent" not in candidate
