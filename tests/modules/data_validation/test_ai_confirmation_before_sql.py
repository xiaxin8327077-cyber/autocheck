from unittest.mock import patch

import pytest

from auto_check.modules.data_validation.contracts import AppError
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _generate_payload, _request, _rules_with_doc, _select_payload
from tests.modules.data_validation.test_followup_service_bridge import _project_definition, _rules


FIELDS = [("row_id", "合同编号", "varchar", "Y"), ("deadline", "到期日期", "date", ""),
          ("start_day", "起始日期", "date", ""), ("report_date", "报送日期", "date", "")]


@pytest.mark.parametrize("extra", [
    {"uncertainties": ["是否仅限已复核合同？"]},
    {"unsupported_requirements": ["还需按上期汇总。"]},
    {"null_policy": "unresolved"},
])
def test_business_confirmation_precedes_even_the_first_compiler_call(extra):
    draft = _generate_payload(expression={"left": "deadline", "op": "lt", "right": "start_day"},
                              null_policy="skip")
    draft.update(extra)
    rules, _ = _rules_with_doc([_select_payload(), draft], fields=FIELDS)
    with patch("auto_check.modules.data_validation.candidate_preview.compile_rule",
               side_effect=AssertionError("pending business decision reached SQL generation")):
        candidate = rules.parse_rule_request(user(), _request(request_text="合同到期日期不得早于起始日期"))
        assert candidate["preview"] is None
        assert candidate["questions"] or candidate["uncertainties"] or candidate["unsupported_requirements"]
        assert not candidate["can_enable"]
        stale = {**candidate, "generation_mode": "manual", "sql_preview": "SELECT old",
                 "content_sha256": "stale", "preview": {"sql_preview": "SELECT old"}}
        response = rules.preview_candidate(user(), {"definition": stale}, return_questions=True)
        assert response["status"] == "needs_confirmation"
        assert response["definition"]["generation_mode"] == "ai"
        for key in ("sql_preview", "preview", "content_sha256", "cases", "sql_params"):
            assert key not in response and key not in response["definition"]
        with pytest.raises(AppError):
            rules.preview_candidate(user(), candidate)
        with pytest.raises(AppError):
            rules.test_candidate(user(), {"definition": stale})

    if extra.get("null_policy") == "unresolved":
        assert any(item["id"] == "null_policy" for item in candidate["questions"])
    if not candidate["unsupported_requirements"]:
        decision = {**candidate, "questions": [], "null_policy": "skip",
                    "uncertainty_resolutions": ["全部合同"] * len(candidate["uncertainties"])}
        assert rules.preview_candidate(user(), decision)["sql_preview"]


def test_document_preflight_collects_independent_questions_and_waits_for_the_last_answer():
    fields = [("c_pactid", "合同编号", "varchar", "Y"), ("project_code", "项目编号", "varchar", ""), *FIELDS[1:]]
    dim = [("project_code", "项目编号", "varchar", "Y"), ("project_name", "项目名称", "varchar", ""),
           ("report_date", "报送日期", "date", "Y")]
    rules, _ = _rules([], table="contract", table_cn="合同明细", dimension="合同", fields=fields,
                      extra_tables=[{"name": "projects", "cn": "项目维表", "dimension": "项目", "fields": dim}])
    context = {"mode": "lookup", "code_field": "project_code", "name_field": "project_name",
               "table_name": "projects", "key": {"left": "project_code", "right": "project_code"},
               "date_field": "report_date", "unique_evidence": {"kind": "pk", "fields": ["project_code", "report_date"],
                                                                "confirmed": True}, "confirmed": False}
    definition = _project_definition(context=context, expression={"left": "deadline", "op": "lt", "right": "start_day"})
    definition["null_policy"] = "unresolved"
    with patch("auto_check.modules.data_validation.candidate_preview.compile_rule",
               side_effect=AssertionError("SQL generated before final answer")):
        first = rules.preview_candidate(user(), definition, return_questions=True)
        assert {q["id"] for q in first["questions"]} == {"null_policy", "project_context.confirmed"}
        partial = {**first["definition"], "null_policy": "skip"}
        second = rules.preview_candidate(user(), partial, return_questions=True)
        assert [q["id"] for q in second["questions"]] == ["project_context.confirmed"]
        assert all("sql_preview" not in result and "cases" not in result for result in (first, second))
    ready = second["definition"]
    ready["project_context"]["confirmed"] = True
    assert rules.preview_candidate(user(), ready, return_questions=True)["sql_preview"]


def test_preview_explains_which_business_scope_is_missing_before_compilation():
    from tests.modules.data_validation.test_conditional_candidate_options import REQUEST, _conditional_rules

    rules, _ = _conditional_rules()
    ready = rules.parse_rule_request(user(), _request(request_text=REQUEST))["preview"]["definition"]
    with patch("auto_check.modules.data_validation.candidate_preview.compile_rule",
               side_effect=AssertionError("SQL generated with missing filter")):
        pending = rules.preview_candidate(user(), {**ready, "filters": []}, return_questions=True)
    assert pending["status"] == "needs_confirmation" and "sql_preview" not in pending
    assert any("净值型" in note and "筛选" in note for note in pending["uncertainties"])


def test_scope_only_identifies_the_dictionary_candidates_and_asks_what_to_check():
    from tests.modules.data_validation.test_conditional_candidate_options import PROJECT, _conditional_rules

    rules, model = _conditional_rules()
    with patch("auto_check.modules.data_validation.candidate_preview.compile_rule",
               side_effect=AssertionError("SQL generated for a scope without an assertion")):
        result = rules.parse_rule_request(user(), _request(request_text="净值型项目"))
        assert result["rule_type"] is None and result.get("preview") is None
        assert result["table_name"] == PROJECT and any("检查" in q for q in result["uncertainties"])
        assert len(model.calls) == 1
        assert "1=开放式净值型" in model.calls[0]["messages"][0]["content"]


@pytest.mark.parametrize("generation", [
    _generate_payload(expression={"left": "acc_nav", "op": "is_null"}),
    {"rule_type": None, "uncertainties": ["只给出了指标，没有指定如何校验。"]},
])
def test_metric_name_alone_requires_check_and_preserves_all_documented_choices(generation):
    fields = [("row_id", "记录编号", "varchar", "Y"), ("unit_nav", "单位净值", "numeric", ""),
              ("acc_nav", "累计净值", "numeric", ""), ("nav_date", "单位净值日期", "date", ""),
              ("report_date", "报送日期", "date", "")]
    rules, _ = _rules_with_doc([_select_payload(status="needs_clarification"), generation], fields=fields)
    with patch("auto_check.modules.data_validation.candidate_preview.compile_rule",
               side_effect=AssertionError("SQL generated for an unspecified check")):
        result = rules.parse_rule_request(user(), _request(request_text="净值"))
        assert result.get("preview") is None and not result["can_enable"]
        purpose, metric = result["questions"]
        assert purpose["id"] == "check_requirement" and purpose["options"][0]["value"] == "not_empty"
        assert metric["id"] == "expression.left" and {o["value"] for o in metric["options"]} == {"unit_nav", "acc_nav"}
        spoof = {**result, "questions": [], "uncertainties": [], "uncertainty_resolutions": []}
        assert rules.preview_candidate(user(), spoof, return_questions=True)["questions"][0]["id"] == "check_requirement"
        with pytest.raises(AppError):
            rules.preview_candidate(user(), spoof)
    for option in metric["options"]:
        definition = {**result, "description": "净值不得为空", "questions": [],
                      "uncertainty_resolutions": ["已明确选择"] * len(result["uncertainties"]),
                      "expression": {"left": option["value"], "op": "is_null"}}
        assert rules.preview_candidate(user(), definition)["sql_preview"]


def test_explicit_check_keeps_the_models_field_recommendation_without_an_expression():
    fields = [("row_id", "记录编号", "varchar", "Y"), ("unit_nav", "单位净值", "numeric", ""),
              ("acc_nav", "累计净值", "numeric", ""), ("report_date", "报送日期", "date", "")]
    draft = {"rule_type": None, "field_choices": [{"side": "left", "term": "净值",
             "fields": ["unit_nav", "acc_nav"], "recommended": "acc_nav"}]}
    rules, _ = _rules_with_doc([_select_payload(), draft], fields=fields)
    with patch("auto_check.modules.data_validation.candidate_preview.compile_rule",
               side_effect=AssertionError("SQL generated before field selection")):
        result = rules.parse_rule_request(user(), _request(request_text="净值不得为空"))
    question, = result["questions"]
    assert question["id"] == "expression.left" and result["preview"] is None
    assert [o["value"] for o in question["options"] if o.get("tag") == "模型建议"] == ["acc_nav"]


@pytest.mark.parametrize("extra", ["", "另需确认统计范围。"])
def test_only_unit_nav_resolves_model_field_question_without_user_input(extra):
    fields = [("row_id", "记录编号", "varchar", "Y"), ("unit_nav", "单位净值", "numeric", ""),
              ("nav_day", "单位净值日期", "date", ""), ("report_date", "报送日期", "date", "")]
    draft = _generate_payload(expression={"left": "unit_nav", "op": "is_null"},
                              uncertainties=["请确认净值是否指单位净值（unit_nav）。" + extra])
    rules, _ = _rules_with_doc([_select_payload(), draft], fields=fields)
    candidate = rules.parse_rule_request(user(), _request(request_text="净值不得为空"))
    assert not candidate["questions"]
    if extra:
        assert candidate["preview"] is None and len(candidate["uncertainties"]) == 1
        assert "统计范围" in candidate["uncertainties"][0] and "unit_nav" not in candidate["uncertainties"][0]
    else:
        assert candidate["uncertainties"] == []
        assert 'unit_nav' in candidate["preview"]["sql_preview"]
