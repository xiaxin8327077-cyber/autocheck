from unittest.mock import patch
from copy import deepcopy

import pytest
from sqlalchemy import update

from auto_check.modules.data_validation.candidate_preview import candidate_definition
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.project_context import project_semantics_required
from auto_check.modules.data_validation.storage import DOC_FIELDS
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request, _rules_with_doc
from tests.modules.data_validation.test_conditional_candidate_options import PROJECT, _conditional_rules


def _definition():
    expression = {"left": "reading", "op": "is_null"}
    return {
        "analysis_protocol": 2, "source_id": "src", "table_name": "test_table",
        "name": "缺值核查", "description": "给我捞一捞空着的那几笔", "generation_mode": "ai",
        "rule_type": "field_compare", "business_key": "row_id", "report_date_field": "day",
        "expression": expression, "violation_message": "请核实读数", "null_policy": "violate",
        "semantic_intent": {"metrics": [{"term": "读数", "side": "left", "fields": ["reading"]}],
                            "scopes": [], "open_questions": [], "explicit_filters": [],
                            "expected_expression": expression},
    }


def _rules():
    return _rules_with_doc([], fields=[("row_id", "行编号", "varchar", "Y"),
                                       ("day", "数据日期", "date", ""),
                                       ("reading", "读数", "decimal", "")])[0]


def test_v2_preview_save_and_edit_keep_model_intent_without_interpreting_description():
    rules = _rules()
    definition = _definition()
    with patch("auto_check.modules.data_validation.service.check_request_coverage",
               side_effect=AssertionError("rule text parsed a second time")):
        preview = rules.preview_candidate(user(), definition, return_questions=True)
        assert "IS NULL" in preview["sql_preview"]
        payload = preview["definition"]
        assert payload["analysis_protocol"] == 2 and payload["semantic_intent"] == definition["semantic_intent"]
        saved = rules.save_draft(user(), payload)
        edited = dict(payload, name="读数缺失")
        del edited["semantic_intent"], edited["analysis_protocol"]
        rules.save_draft(user(), edited, saved["id"])
        assert rules.storage.latest_version(saved["id"])["definition"]["semantic_intent"] == definition["semantic_intent"]


def test_v2_requires_intent_instead_of_falling_back_to_parsing_words():
    rules = _rules()
    definition = _definition()
    del definition["semantic_intent"]
    with pytest.raises(AppError, match="VALIDATION_ERROR"):
        rules.preview_candidate(user(), definition, return_questions=True)


def test_active_analysis_keeps_the_original_model_interpretation_on_recheck(monkeypatch):
    rules = _rules()
    definition = _definition()
    original = {**definition, "analysis_context": "snapshot"}
    monkeypatch.setattr(rules.analyses, "completed_result", lambda *_: original)
    monkeypatch.setattr(rules, "_check_preview_context", lambda *_, **__: {})
    context = {"analysis_id": "analysis", "analysis_context": "snapshot", "model_id": "model-1",
               "analysis_request_text": definition["description"]}
    edited = deepcopy(definition)
    edited["expression"]["op"] = "is_not_null"
    edited["semantic_intent"]["expected_expression"] = edited["expression"]
    with pytest.raises(AppError, match="ANALYSIS_CONTEXT_CHANGED"):
        rules.preview_candidate(user(), {**context, "definition": edited}, return_questions=True)
    del edited["analysis_protocol"], edited["semantic_intent"]
    with pytest.raises(AppError, match="ANALYSIS_CONTEXT_CHANGED"):
        rules.preview_candidate(user(), {**context, "definition": edited}, return_questions=True)


def test_model_rule_project_context_depends_on_document_and_bound_identity():
    definition = {**_definition(), "description": "账户异常送项目组复核"}
    assert not project_semantics_required(definition, {"dimension": "账户"})
    assert project_semantics_required(definition, {"dimension": "项目"})
    assert candidate_definition(definition)["semantic_intent"] == definition["semantic_intent"]


def test_supplement_uses_its_own_issued_expression_when_rechecked_in_primary_analysis(monkeypatch):
    rules, model = _conditional_rules()
    request = _request(request_text="请按文档口径核实", analysis_protocol=2)
    model.payloads[1].update(
        expression={"left": "f_totalnetvalue", "op": "is_null"},
        semantic_intent={"metrics": [{"term": "累计净值", "side": "left", "fields": ["f_totalnetvalue"]}],
                         "scopes": [], "open_questions": []},
    )
    supplement = {"name": "其他指标缺失", "description": "其他指标缺失", "table_name": PROJECT,
                  "source_id": request["source_id"], "rule_type": "field_compare", "null_policy": "violate",
                  "expression": {"left": "f_start_totalnetvalue", "op": "is_null"}, "violation_message": "请核实"}
    monkeypatch.setattr("auto_check.modules.data_validation.semantic_generation.build_ai_suggestions",
                        lambda *_, **kw: [{"definition": supplement}])
    # This test isolates the issued definition from the optional model-review RPC.
    monkeypatch.setattr("auto_check.modules.data_validation.semantic_generation.SemanticAnalysis.supplement_suggestions",
                        lambda self, candidates, previous=(): list(previous))
    result = rules.parse_rule_request(user(), request)
    issued = result["ai_suggestions"][0]["definition"]
    assert issued["semantic_intent"]["expected_expression"] == supplement["expression"]
    assert issued["semantic_intent"] != result["semantic_intent"]
    monkeypatch.setattr(rules.analyses, "completed_result", lambda *_: result)
    monkeypatch.setattr(rules, "_check_preview_context", lambda *_, **__: {})
    payload = {"analysis_id": "id", "analysis_context": result["analysis_context"], "model_id": request["model_id"],
               "analysis_request_text": request["request_text"], "definition": {
                   **issued, "business_key": result["business_key"], "report_date_field": result["report_date_field"],
                   "project_context": result.get("project_context"), "report_category": result["report_category"],
               }}
    assert "f_start_totalnetvalue" in rules.preview_candidate(user(), payload, return_questions=True)["sql_preview"]


def test_v2_analysis_memory_and_target_are_independent_of_legacy_sentence_parser():
    rules = _rules()
    req = _request()
    original = rules._analysis_inputs(user(), req)
    with patch("auto_check.modules.data_validation.service.project_mart_target",
               side_effect=AssertionError("legacy sentence selected a table")):
        semantic = rules._analysis_inputs(user(), {**req, "analysis_protocol": 2})
    assert semantic["project_target"] is None
    assert semantic["context"]["prompt_fingerprint"] != original["context"]["prompt_fingerprint"]


def test_nav_metric_and_running_method_choices_reach_preview_and_synthetic_cases():
    rules, model = _conditional_rules()
    with rules.storage.database.begin() as connection:
        connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "f_start_totalnetvalue")
                           .values(field_name="f_netvalue", field_cn="单位净值"))
    model.payloads[1].update(
        expression={"left": "f_netvalue", "op": "is_null"},
        semantic_intent={
            "metrics": [{"side": "left", "term": "净值", "fields": ["f_netvalue", "f_totalnetvalue"]}],
            "scopes": [{"category": "净值型", "fields": ["c_oper_mode", "c_oper_mode_orig"],
                        "memberships": {col: {"include": ["1", "3"], "exclude": ["2", "4"]}
                                        for col in ("c_oper_mode", "c_oper_mode_orig")}}],
            "open_questions": [],
        },
    )
    result = rules.parse_rule_request(user(), _request(request_text="项目为净值型时，净值不得为空", analysis_protocol=2))
    qs = {q["id"]: q for q in result["questions"]}
    assert set(qs) == {"expression.left", "filters.0"} and not result["preview"]
    for metric in qs["expression.left"]["options"]:
        partial = deepcopy(result)
        partial.update(questions=[qs["filters.0"]], expression={"left": metric["value"], "op": "is_null"})
        partial["uncertainty_resolutions"] = [metric["label"] if text == qs["expression.left"]["uncertainty"] else ""
                                              for text in partial["uncertainties"]]
        pending = rules.preview_candidate(user(), partial, return_questions=True)
        assert [q["id"] for q in pending["questions"]] == ["filters.0"] and not pending.get("sql_preview")
        for scope in qs["filters.0"]["options"]:
            chosen = {**partial, "questions": [], "filters": [scope["selection"]],
                      "uncertainty_resolutions": [answer or scope["label"] for answer in partial["uncertainty_resolutions"]]}
            preview = rules.preview_candidate(user(), chosen, return_questions=True)
            assert not preview.get("questions") and PROJECT in preview["sql_preview"] and "IS NULL" in preview["sql_preview"]
            assert metric["value"] in preview["sql_preview"] and scope["selection"]["field"] in preview["sql_preview"]
            assert preview["definition"]["filters"][0]["value"] == ["1", "3"]
            tested = rules.test_candidate(user(), {"definition": preview["definition"], "expected_hash": preview["content_sha256"]})
            assert tested["passed_count"] and tested["failed_count"] == tested["not_run_count"] == 0
    assert len(model.calls) == 2
