from copy import deepcopy
from unittest.mock import patch

import pytest

from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.preview_memory import selected_baseline
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request
from tests.modules.data_validation.test_category_numeric_reviews import REQUEST, setup_rules
from tests.modules.data_validation.test_shared_analysis_reuse import analyze


def analysis_with_choices():
    rules, model = setup_rules()
    done = analyze(rules, user("first"), REQUEST)
    candidate = done["result"]
    chosen = deepcopy(candidate)
    metric, scope = [q for q in candidate["questions"] if q["id"] != "null_policy"]
    for part in chosen["expression"]["conditions"]:
        part["left"] = "total"
    selection = next(o["selection"] for o in scope["options"] if o["selection"]["field"] == "orig")
    chosen.update(questions=[], filters=[selection], null_policy="skip",
                  uncertainty_resolutions=["明确选择 total", "明确选择 orig"])
    return rules, model, candidate, {
        "definition": chosen, "analysis_id": done["analysis_id"], "analysis_context": candidate["analysis_context"],
        "model_id": "model-1", "analysis_request_text": REQUEST,
    }


def test_only_successfully_previewed_choices_are_shared_as_unconfirmed_evidence():
    rules, model, original, payload = analysis_with_choices()
    context = rules._analysis_inputs(user("first"), _request(request_text=REQUEST))["context"]
    def examples():
        return [entry["baseline"] for entry in rules.storage.find_analysis_memories(context, REQUEST)]
    before = examples()
    pending = rules.preview_candidate(user("first"), {**payload, "definition": original}, return_questions=True)
    assert not pending.get("sql_preview") and examples() == before
    preview = rules.preview_candidate(user("first"), payload, return_questions=True)
    assert preview["sql_preview"]
    selected = [b for b in examples() if {v["field"] for v in b["field_bindings"]} == {"total", "orig"}]
    assert selected and all(b["requires_selection"] for b in selected)
    assert all("sql" not in b and "uncertainty_resolutions" not in b for b in selected)
    model.payloads.append({"reuse_decision": "adapt", "memory_index": 0, "target": {"table": "project_report"},
                           "draft": preview["definition"]})
    other = analyze(rules, user("second"), REQUEST)["result"]
    assert {q["id"] for q in other["questions"]} >= {"expression.conditions.0.left", "filters.0"}
    assert other.get("preview") is None


def test_expired_or_other_owners_analysis_allows_independent_preview_without_remembering():
    rules, _, _, payload = analysis_with_choices()
    with patch.object(rules.storage, "remember_analysis_memory") as remember:
        for owner, body in [(user("second"), payload), (user("first"), {**payload, "analysis_id": "expired"})]:
            assert rules.preview_candidate(owner, body, return_questions=True)["sql_preview"]
        remember.assert_not_called()


def test_origin_is_bound_to_request_and_context_changes_disallow_old_preview():
    rules, _, _, payload = analysis_with_choices()
    with patch.object(rules.storage, "remember_analysis_memory") as remember:
        for key, value in [("analysis_request_text", REQUEST + "变更"), ("analysis_context", "tampered")]:
            with pytest.raises(AppError, match="ANALYSIS_CONTEXT_CHANGED"):
                rules.preview_candidate(user("first"), {**payload, key: value}, return_questions=True)
        rules.save_prompt(user("admin", "admin"), "business_scope", "以月末业务日对齐。")
        with pytest.raises(AppError, match="ANALYSIS_CONTEXT_CHANGED"):
            rules.preview_candidate(user("first"), payload, return_questions=True)
        remember.assert_not_called()


def test_only_the_offered_bare_metric_clarification_may_extend_the_description():
    fields = [{"field_name": name} for name in ("nav", "total")]
    original = {"description": "净值", "rule_type": "field_compare", "source_id": "src", "table_name": "projects",
                "expression": {"left": "nav", "op": "is_null"}, "questions": [
                    {"id": "check_requirement", "options": [{"value": "not_empty"}]},
                    {"id": "expression.left", "options": [{"value": "nav"}, {"value": "total"}]},
                ]}
    verified = {**original, "description": "净值不得为空", "expression": {"left": "total", "op": "is_null"}}
    assert selected_baseline(original, verified, fields)["field_bindings"] == [{"role": "metric", "field": "total"}]
    assert selected_baseline(original, {**verified, "description": "净值不得为空且必须为零"}, fields) is None
