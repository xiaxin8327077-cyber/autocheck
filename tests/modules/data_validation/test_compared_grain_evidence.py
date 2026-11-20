from copy import deepcopy

import pytest

from auto_check.modules.data_validation.candidate_preview import run_preview_cases
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.document_evidence import DocumentEvidence
from auto_check.modules.data_validation.semantic_generation import SemanticAnalysis
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request
from tests.modules.data_validation.test_project_driver_binding import document_tables, make_rules


KEY = {"left": "project_key", "right": "funding_owner"}
DATE = {"left": "day", "right": "day"}


def compared_sources(*, shared_alias, join_keys, another_metric=False):
    project, _, funding, _ = document_tables()
    fields = {f["field_name"]: f for f in funding["fields"]}
    fields["day"].update(source_table="mart.project_snapshot", source_field="day")
    fields["funding_owner"]["is_pk"] = "Y"
    project_measure = next(f for f in project["fields"] if f["field_name"] == "project_received")
    project_measure["logic"] = "业务别名：项目实收。"
    fields["funding_received"].update(field_cn="募集实收" if shared_alias else "募集份额",
                                      logic="业务别名：募集实收。" if shared_alias else "")
    if another_metric:
        funding["fields"].append({**fields["funding_received"], "field_name": "other_received", "field_cn": "其他实收"})
    proposal = {
        "business_key": "project_key", "project_driver": {"version": 1, "table_role": "base"},
        "rule_name": "实收与募集份额合计一致", "rule_type": "field_compare", "null_policy": "zero",
        "violation_message": "项目实收与同日募集份额合计不一致",
        "expression": {"left": "project_received", "op": "neq", "right_type": "field",
                       "right_table": "related", "right": "funding_received"},
        "join": {"table_name": "funding_rows", "on": deepcopy(join_keys), "report_date_field": "day",
                 "relationship_confirmed": True, "unmatched_policy": "review", "right_aggregate": "sum"},
        "semantic_intent": {"metrics": [
            {"side": "left", "term": "项目实收", "fields": ["project_received"]},
            {"side": "right", "term": "募集份额", "fields": ["funding_received"]},
        ], "scopes": [], "open_questions": []},
    }
    selection = {"target": {"table": "project_snapshot"}, "related_target": {"table": "funding_rows"}}
    rules, model = make_rules([{**selection, "draft": proposal}], tables=[project, funding])
    request = _request(request_text="对比项目和募集表中的实收是否一致", analysis_protocol=2)
    return rules, model, request


@pytest.mark.parametrize(("shared_alias", "join_keys"), [(True, [KEY]), (False, [DATE, KEY]), (True, [KEY, DATE])])
def test_bound_right_operand_and_proven_period_compile_the_first_aggregate(shared_alias, join_keys):
    rules, model, request = compared_sources(shared_alias=shared_alias, join_keys=join_keys)
    result = rules.parse_rule_request(user(), request)
    assert len(model.calls) == 1
    assert result["preview"] and not result["questions"] and not result.get("candidate_options")
    definition = result["preview"]["definition"]
    assert definition["expression"] == {"left": "project_received", "op": "neq", "right_type": "field",
                                         "right_table": "related", "right": "funding_received"}
    assert definition["join"]["right_aggregate"] == "sum"
    verified = run_preview_cases(result["preview"])
    assert verified["passed_count"] and not verified["failed_count"] and not verified["not_run_count"]


@pytest.mark.parametrize("bad_keys", [
    [KEY, DATE, DATE], [DATE], [KEY, {"left": "project_key", "right": "funding_id"}],
    [KEY, {"left": "project_key", "right": "day"}],
])
def test_aggregate_preview_rejects_unproven_or_duplicate_keys(bad_keys):
    rules, _, request = compared_sources(shared_alias=False, join_keys=[KEY])
    version = rules.parse_rule_request(user(), request)["preview"]["definition"]
    bad = deepcopy(version)
    bad["join"]["on"] = deepcopy(bad_keys)
    bad["semantic_intent"]["expected_join"]["on"] = deepcopy(bad_keys)
    with pytest.raises(AppError, match="VALIDATION_ERROR"):
        rules.preview_candidate(user(), {"definition": bad})


@pytest.mark.parametrize("right_owner", ["related", "base"])
def test_opposite_operand_covers_only_its_exact_field_and_owner(right_owner):
    rules, model, request = compared_sources(shared_alias=True, join_keys=[KEY], another_metric=True)
    proposal = deepcopy(model.payloads[0])
    proposal["draft"]["expression"]["right_table"] = right_owner
    analysis = SemanticAnalysis(rules, user(), rules._analysis_inputs(user(), request), request["request_text"], None, None)
    analysis.index = DocumentEvidence(analysis.tables, analysis.fields, analysis.request)
    _, pending = analysis.expand_interpretation_evidence(proposal)
    assert pending
    missing_left = {item["field"] for item in analysis.interpretation_checks
                    if item["side"] == "left" and item["table"] == "funding_rows"}
    assert "other_received" in missing_left
    assert ("funding_received" in missing_left) == (right_owner == "base")
