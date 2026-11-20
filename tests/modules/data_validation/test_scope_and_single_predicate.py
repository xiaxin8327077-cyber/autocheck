import pytest
from sqlalchemy import update

from auto_check.modules.data_validation.candidate_preview import run_preview_cases
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.storage import DOC_FIELDS
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request, _rules_with_doc, _select_payload
from tests.modules.data_validation.test_semantic_generation import FIELDS, draft


@pytest.mark.parametrize("subject", ["光学型记录", "请核查光学型产品。"])
def test_documented_category_with_no_requirement_asks_for_one(subject):
    check = draft()
    rules, model = _rules_with_doc([{**_select_payload(), "draft": check}], fields=FIELDS)
    with rules.storage.database.begin() as connection:
        connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "row_id").values(
            dictionary="A-主动光学型\nB-被动光学型\nC-机械型"))
    payload = _request(request_text=subject, analysis_protocol=2)
    pending = rules.parse_rule_request(user(), payload)
    assert not model.calls and not pending.get("preview") and not pending.get("rule_type")
    assert "异常条件" in pending["uncertainties"][0]
    answered = rules.parse_rule_request(user(), {**payload, "clarification_answers": [{
        "question_id": "condition", "question": pending["uncertainties"][0], "answer": "按份额低于19检查",
    }]})
    assert answered["expression"] == check["expression"] and answered["preview"]


@pytest.mark.parametrize("logic", ["any", "all"])
def test_single_condition_group_materializes_the_same_predicate(logic):
    check = draft()
    condition = check["expression"]
    check["expression"] = {"logic": logic, "conditions": [condition]}
    check["semantic_intent"]["metrics"][0]["condition_index"] = 0
    rules, model = _rules_with_doc([{**_select_payload(), "draft": check}], fields=FIELDS)
    result = rules.parse_rule_request(user(), _request(request_text="份额低于19时提醒", analysis_protocol=2))
    assert len(model.calls) == 1 and result["expression"] == condition
    tests = run_preview_cases(result["preview"])
    assert tests["passed_count"] > 0 and tests["failed_count"] == tests["not_run_count"] == 0


@pytest.mark.parametrize("null_marker", ["null", None])
def test_question_with_multiple_documented_metrics_does_not_request_executable_plans(null_marker):
    question = "请明确要检查读数的什么异常。"
    check = {"rule_type": null_marker, "expression": {}, "semantic_intent": {
        "metrics": [{"side": "left", "term": "读数", "fields": [name]}
                    for name in ("sample", "cumulative")],
        "scopes": [], "open_questions": [question]}}
    fields = [*FIELDS, ("sample", "瞬时读数", "numeric", ""), ("cumulative", "累计读数", "numeric", "")]
    rules, model = _rules_with_doc([{**_select_payload(), "draft": check}], fields=fields)
    result = rules.parse_rule_request(user(), _request(request_text="读数", analysis_protocol=2))
    assert len(model.calls) == 1 and result["uncertainties"] == [question]
    assert result["rule_type"] is None and not result.get("preview") and not result.get("candidate_options")


@pytest.mark.parametrize("outer", ["missing", "same", "conflict"])
def test_misnested_filter_keeps_exact_operand_and_null_direction(outer):
    check = draft()
    scope = {"table": "base", "field": "technician", "op": "is_null", "value": None}
    check["semantic_intent"]["filters"] = [scope.copy()]
    if outer != "missing":
        check["filters"] = [scope if outer == "same" else {**scope, "op": "is_not_null"}]
    rules, model = _rules_with_doc([{**_select_payload(), "draft": check}],
                                   fields=[*FIELDS, ("technician", "记录员", "varchar", "")])
    request = _request(request_text="记录员为空时检查份额是否低于19", analysis_protocol=2)
    if outer == "conflict":
        with pytest.raises(AppError, match="MODEL_RESPONSE_INVALID"):
            rules.parse_rule_request(user(), request)
        return
    result = rules.parse_rule_request(user(), request)
    assert len(model.calls) == 1 and result["expression"] == check["expression"] and result["preview"]
    assert result["preview"]["definition"]["filters"] == [{**scope, "confirmed": True}]
