from copy import deepcopy

import pytest
from sqlalchemy import update

from auto_check.modules.data_validation.candidate_preview import preview_definition
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.storage import DOC_FIELDS
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request, _rules_with_doc, _select_payload
from tests.modules.data_validation.test_model_common_choices import rules_with_choices
from tests.modules.data_validation.test_semantic_generation import draft


def metric_choice(policy):
    rules, model = rules_with_choices(metrics=["amount", "other_amount"])
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "amount").values(logic="空值视为0"))
    model.payloads[0]["draft"].update(null_policy=policy, expression={
        "left": "amount", "op": "eq", "right": 0, "right_type": "value",
    })
    candidate = rules.parse_rule_request(user(), _request(request_text="转让项目的金额不能为0", analysis_protocol=2))
    assert candidate["null_policy"] == "zero"
    assert {q["id"] for q in candidate["questions"]} == {"expression.left"}
    selected = {**candidate, "name": "另一口径金额校验", "questions": [],
                "expression": {**candidate["expression"], "left": "other_amount"},
                "uncertainty_resolutions": ["明确选择 other_amount"] * len(candidate["uncertainties"])}
    # The form posts the selected field and policy. Non-grouped expressions omit derived evidence.
    selected.pop("null_handling", None)
    selected.pop("null_evidence", None)
    return rules, selected


@pytest.mark.parametrize("model_policy", ["review", "zero", "skip"])
def test_selected_metric_rebinds_its_own_null_policy_through_preview_and_save(model_policy):
    rules, selected = metric_choice(model_policy)
    preview = rules.preview_candidate(user(), {"definition": selected}, return_questions=True)
    assert preview["definition"]["null_policy"] == model_policy
    alias = "d" if selected.get("project_driver") else "t"
    assert (f'COALESCE({alias}."other_amount", 0)' in preview["sql_preview"]) == (model_policy == "zero")
    saved = rules.save_draft(user(), preview["definition"])
    stored = rules.storage.latest_version(saved["id"])
    assert stored["content_sha256"] == preview["content_sha256"]
    assert stored["sql_text"] == preview["sql_preview"]


def test_old_ambiguous_selection_requires_fresh_analysis_but_frozen_version_retests_unchanged():
    rules, old = metric_choice("zero")
    old["semantic_intent"].pop("expected_null_policy", None)
    old.pop("model_judgments", None)
    with pytest.raises(AppError, match="ANALYSIS_CONTEXT_CHANGED"):
        rules.preview_candidate(user(), {"definition": old}, return_questions=True)

    # The old stored representation of an explicit rule-level zero used an empty evidence list.
    old["null_evidence"] = []
    frozen = preview_definition(old, old["columns"], old["related_columns"])
    rechecked = rules.preview_candidate(user(), {"definition": frozen["definition"]}, preserve_result_fields=True)
    assert rechecked["content_sha256"] == frozen["content_sha256"]
    assert rechecked["sql_preview"] == frozen["sql_preview"]


@pytest.mark.parametrize(("original", "repaired"), [("zero", "review"), ("review", "zero"), ("skip", "zero")])
def test_full_repair_after_early_parallel_error_cannot_change_a_valid_numeric_policy(original, repaired):
    rules, model = rules_with_choices()
    selection = model.payloads[0]
    plan = selection.pop("draft")
    plan.update(null_policy=original, uncertainties="应为数组")
    other = deepcopy(plan)
    other.update(uncertainties=[], expression={"left": "amount", "op": "gt", "right_type": "value", "right": 10})
    invalid = {"plans": [plan, other], "plan_mode": "parallel"}
    correction = deepcopy(invalid)
    correction["plans"][0].update(null_policy=repaired, uncertainties=[])
    model.payloads = [selection, invalid, correction]
    with pytest.raises(AppError, match="MODEL_RESPONSE_INVALID"):
        rules.parse_rule_request(user(), _request(request_text="转让项目的金额需要按两种条件核查", analysis_protocol=2))
    assert len(model.calls) == 3


@pytest.mark.parametrize("invalid_policy", ["zero", "review"])
def test_date_comparison_can_repair_invalid_numeric_policy(invalid_policy):
    fields = [("row_id", "业务编号", "varchar", "Y"), ("opened", "开始日期", "date", ""),
              ("closed", "终止日期", "date", ""), ("business_day", "数据日期", "date", "")]
    original = draft(business_key="row_id")
    original.update(null_policy=invalid_policy, expression={"left": "opened", "op": "gt", "right": "closed"})
    original["semantic_intent"]["metrics"] = [{"side": "left", "term": "开始日期", "fields": ["opened"]},
                                             {"side": "right", "term": "终止日期", "fields": ["closed"]}]
    rules, model = _rules_with_doc([_select_payload(), original, {**original, "null_policy": "skip"}], fields=fields)
    result = rules.parse_rule_request(user(), _request(request_text="开始日期不能晚于终止日期", analysis_protocol=2))
    assert result.get("preview") and result["null_policy"] == "skip"
    assert len(model.calls) == 3
