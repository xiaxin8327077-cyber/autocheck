"""An unchanged workbook can acquire a different meaning through active application settings."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from auto_check.modules.data_validation.preview_memory import selected_baseline
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_explicit_scope_compound_preview import _project_rules
from tests.modules.data_validation.test_shared_analysis_reuse import FIRST, PROPOSAL, REVISED, SELECT, analyze


@pytest.mark.parametrize("change", ["category_added", "category_renamed", "knowledge_activated"])
def test_external_changes_invalidate_both_shared_and_current_dialog_history(change):
    rules, model = _project_rules(SELECT, PROPOSAL)
    categories = [SimpleNamespace(code="east5", name="East5报送", active=True)]
    rules.report_navigation = SimpleNamespace(list_report_processes=lambda: list(categories))
    owner = user("analyst")
    first = analyze(rules, owner, FIRST)
    assert first["result"]["preview"]

    if change == "category_added":
        categories.append(SimpleNamespace(code="new_group", name="其他报送", active=True))
    elif change == "category_renamed":
        categories[0].name = "其他报送"
    else:
        knowledge = rules.knowledge
        # Even these entries which do not match the current request belong to a new active version.
        entry = dict(knowledge.settings()["draft"][0], keywords=["国内采购付款账期"])
        knowledge.save(user("setup", "admin"), {"expected_revision": 0, "entries": [entry]})
        knowledge.save(user("setup", "admin"), {"expected_revision": 1, "enabled": True}, activation=True)

    model.payloads.extend([SELECT, PROPOSAL])
    result = analyze(rules, owner, REVISED, revision_of=first["analysis_id"])["result"]
    assert not result.get("analysis_reused") and len(model.calls) == 4
    for call in model.calls[2:]:
        assert all("reuse_decision" not in msg["content"] for msg in call["messages"])


def test_model_can_adapt_when_the_new_request_removes_a_previously_unresolved_exception():
    first_draft = {**PROPOSAL, "uncertainties": ["节假日是否排除需核对"]}
    rules, model = _project_rules(SELECT, first_draft)
    first = analyze(rules, user(), FIRST + "，节假日可能例外")
    assert first["result"]["uncertainties"] and not first["result"].get("preview")
    corrected = deepcopy(PROPOSAL)
    corrected["expression"]["conditions"][1]["right"] = 10
    model.payloads.append({**SELECT, "memory_index": 0, "reuse_decision": "adapt", "draft": corrected})
    current = analyze(rules, user(), REVISED, revision_of=first["analysis_id"])["result"]
    assert len(model.calls) == 3 and current["analysis_reused"]
    assert current["preview"] and not current["uncertainties"]


def test_remembering_a_selected_category_binds_the_chosen_worksheet():
    fields = [{"field_name": "metric"}]
    rule = {"source_id": "source", "table_name": "report", "description": "指标不能为空", "rule_type": "field_compare",
            "expression": {"left": "metric", "op": "is_null"}, "report_category": ""}
    question = {"id": "report_category", "options": [{"value": "audit"}, {"value": "rating"}]}
    old = {**rule, "questions": [question]}
    verified = {**rule, "report_category": "rating"}
    result = selected_baseline(old, verified, fields)
    assert result["report_category"] == "rating" and result["requires_selection"]
    alternatives = {"candidate_options": [{"candidate": {**old, "report_category": code}} for code in ["audit", "rating"]]}
    assert selected_baseline(alternatives, verified, fields)["report_category"] == "rating"
    assert selected_baseline(old, {**rule, "report_category": "unoffered"}, fields) is None
