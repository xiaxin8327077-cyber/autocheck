from copy import deepcopy

import pytest
from sqlalchemy import update

from auto_check.modules.data_validation.storage import DOC_FIELDS
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request
from tests.modules.data_validation.test_explicit_scope_compound_preview import _project_rules
from tests.modules.data_validation.test_followup_service_bridge import _add_table


SCOPE = "原始运行方式为净值型的项目的"
FIRST = SCOPE + "单位净值一般不大于0且一定不能为空"
REVISED = SCOPE + "单位净值不得为空且通常不超过10"
SELECT = {"target": {"table": "proj_info_dtl_pboc"}}
PROPOSAL = {"rule_type": "field_compare", "rule_name": "只适用于旧阈值0的名称",
            "expression": {"logic": "any", "conditions": [{"left": "f_netvalue", "op": "is_null"},
                           {"left": "f_netvalue", "op": "gt", "right_type": "value", "right": 0}]}}


def analyze(rules, owner, text, **extras):
    job = rules.start_analysis(owner, _request(request_text=text, **extras))
    rules.analyses.join()
    done = rules.get_analysis(owner, job["analysis_id"])
    assert done["status"] == "completed", done
    return done


@pytest.mark.parametrize("shared", [False, True])
def test_model_can_adapt_a_previous_analysis_and_generate_in_one_call(shared):
    rules, model = _project_rules(SELECT, PROPOSAL)
    old = analyze(rules, user(), FIRST)
    before = old["result"]["preview"]
    form = {**deepcopy(before["definition"]), "sql_preview": "client input", "violation_message": "过期口径",
            "filters": [], "rule_name": "过期名称"}
    options = {} if shared else {"revision_of": old["analysis_id"], "revised_definition": form}
    proposal = deepcopy(PROPOSAL)
    proposal["expression"]["conditions"][1]["right"] = 10
    proposal["rule_name"] = "单位净值校验"
    proposal["filters"] = before["definition"]["filters"]
    model.payloads.append({**SELECT, "reuse_decision": "adapt", "memory_index": 0, "draft": proposal})
    candidate = analyze(rules, user("second") if shared else user(), REVISED, **options)["result"]
    assert len(model.calls) == 3 and candidate["analysis_reused"] is True
    assert candidate["preview"] and candidate["description"] == REVISED
    assert candidate["memory_decision"] == "adapt" and candidate["verification_status"] == "not_run"
    assert "reuse_decision" in model.calls[-1]["messages"][0]["content"]
    assert candidate["rule_name"] != PROPOSAL["rule_name"] and "过期" not in candidate["violation_message"]
    preview = candidate["preview"]
    assert preview["content_sha256"] != before["content_sha256"]
    assert 10 in preview["sql_params"].values() and " OR " in preview["sql_preview"]
    assert preview["definition"]["filters"] == before["definition"]["filters"]
    assert not rules.storage.visible_rules("second")


@pytest.mark.parametrize("change", ["source_model", "scope", "metric", "free_text"])
def test_context_and_semantic_changes_go_through_the_model(change):
    rules, model = _project_rules(SELECT, PROPOSAL)
    old = analyze(rules, user(), FIRST)
    model.payloads.extend([SELECT, PROPOSAL])
    text = {"metric": REVISED.replace("单位净值", "累计净值"), "scope": REVISED.replace("净值型的", "非净值型的"),
            "free_text": REVISED + "，但排除已清算合同"}.get(change, REVISED)
    options = {"model_id": "model-2"} if change == "source_model" else {}
    changed = analyze(rules, user(), text, revision_of=old["analysis_id"], **options)["result"]
    assert not changed.get("analysis_reused") and len(model.calls) == 4


@pytest.mark.parametrize("problem", ["stale_threshold", "bad_index", "invalid_expr", "declined"])
def test_history_never_supersedes_current_coverage_or_the_model_decision(problem):
    rules, model = _project_rules(SELECT, PROPOSAL)
    analyze(rules, user(), FIRST)
    draft = deepcopy(PROPOSAL)
    draft["expression"]["conditions"][1]["right"] = 10
    combined = {**SELECT, "reuse_decision": "adapt", "memory_index": 0, "draft": deepcopy(draft)}
    if problem == "stale_threshold":
        combined["draft"] = PROPOSAL
    elif problem == "invalid_expr":
        combined["draft"]["expression"] = {"bad_argument": True}
    elif problem == "bad_index":
        combined["memory_index"] = 100
    else:
        combined["reuse_decision"] = "fresh"
    model.payloads.extend([combined, draft])
    revised = analyze(rules, user("2"), REVISED)["result"]
    assert revised["memory_decision"] == "fresh" and not revised["analysis_reused"] and len(model.calls) == 4
    assert 10 in revised["preview"]["sql_params"].values()


@pytest.mark.parametrize("same_owner", [True, False])
def test_shared_history_never_confirms_another_users_ambiguous_metric_choice(same_owner):
    rules, model = _project_rules(SELECT, PROPOSAL)
    old = analyze(rules, user(), FIRST.replace("单位净值", "净值"))
    first = old["result"]
    assert any(q["id"].startswith("expression.") for q in first["questions"])
    edited = {key: deepcopy(first[key]) for key in ("table_name", "expression", "filters")}
    for condition in edited["expression"]["conditions"]:
        condition["left"] = "f_totalnetvalue"
    proposal = deepcopy(PROPOSAL)
    proposal["expression"] = deepcopy(edited["expression"])
    for part in proposal["expression"]["conditions"]:
        if part["op"] == "gt":
            part["right"] = 10
    model.payloads.append({**SELECT, "reuse_decision": "adapt", "memory_index": 0, "draft": proposal})
    revised = analyze(rules, user() if same_owner else user("other"), REVISED.replace("单位净值", "净值"),
                      revision_of=old["analysis_id"], revised_definition=edited)["result"]
    assert len(model.calls) == 3 and revised["analysis_reused"]
    assert bool(revised["preview"]) == same_owner
    assert bool(revised["questions"]) != same_owner


def test_mid_generation_dictionary_update_discards_old_decision_and_rechecks_the_new_codes():
    rules, model = _project_rules(SELECT, PROPOSAL)
    analyze(rules, user(), FIRST)
    draft = deepcopy(PROPOSAL)
    draft["expression"]["conditions"][1]["right"] = 10
    model.payloads.extend([{**SELECT, "reuse_decision": "adapt", "memory_index": 0, "draft": draft}, SELECT, draft])
    original = model.complete
    def complete(*args, **kwargs):
        answer = original(*args, **kwargs)
        if len(model.calls) == 3:
            with rules.storage.database.begin() as connection:
                connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "c_oper_mode_orig")
                                   .values(dictionary="6-开放式净值型\n8-封闭式净值型\n9-非净值型"))
        return answer
    model.complete = complete
    revised = analyze(rules, user("second"), REVISED)["result"]
    assert len(model.calls) == 5 and not revised.get("analysis_reused")
    assert revised["filters"][0]["value"] == ["6", "8"] and revised["preview"]


def test_source_fingerprint_is_independent_of_which_eighty_tables_the_selector_receives():
    rules, _ = _project_rules(SELECT, PROPOSAL)
    for index in range(79):
        _add_table(rules, name=f"spare_{index}", cn=f"其他{index}", dimension="记录", fields=[("extra", "备用字段", "varchar", "")])
    for name, cn in (("billing", "账单流水"), ("archive", "归档凭据")):
        _add_table(rules, name=name, cn=cn, dimension="记录", fields=[("extra", cn, "varchar", "")])
    old = rules._analysis_inputs(user(), _request(request_text="项目信息的单位净值与账单流水"))
    new = rules._analysis_inputs(user(), _request(request_text="项目信息的单位净值与归档凭据"))
    assert len(old["shortlist"]) == len(new["shortlist"]) == 80
    assert {t["id"] for t in old["shortlist"]} != {t["id"] for t in new["shortlist"]}
    assert old["context"] == new["context"]
    hidden = next(t for t in new["tables"] if t not in new["shortlist"])
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.table_id == hidden["id"]).values(source_table_cn="最新来源"))
    refreshed = rules._analysis_inputs(user(), _request(request_text="项目信息的单位净值与归档凭据"))
    assert refreshed["context"] != new["context"]


@pytest.mark.parametrize("updated", [
    "评级报送的风险敞口一般不超过10，而且不能为空",
    "评级报送：风险敞口务必非空；同时通常不大于10",
    "在评级报送中，风险敞口一般不超过10，并且一定不能为空",
    "评级报送：风险敞口一般不超过10，务必非空",
    "评级报送：风险敞口不得为空、通常不超过10",
])
def test_category_prefix_and_conjunction_apply_to_both_predicates_at_every_gate(updated):
    from tests.modules.data_validation.support import SequenceModel, service
    from tests.modules.data_validation.test_document_category_options import Categories, Sources, _document
    selection = {"target": {"table": "rating_projects"}, "report_category": "rating"}
    old = {"rule_type": "field_compare", "expression": {"logic": "any", "conditions": [
        {"left": "metric", "op": "is_null"}, {"left": "metric", "op": "gt", "right_type": "value", "right": 0}]}}
    revised = deepcopy(old)
    revised["expression"]["conditions"][1]["right"] = 10
    model = SequenceModel([selection, old, {**selection, "reuse_decision": "adapt", "memory_index": 0, "draft": revised}])
    _, rules = service(metadata=Sources(), model=model, report_navigation=Categories())
    _document(rules, 1, [("rating_projects", "评级报送", "评级范围", "")], "风险敞口")
    initial = analyze(rules, user(), "评级报送的风险敞口不得为空且一般不超过0")
    assert initial["result"]["preview"]
    candidate = analyze(rules, user(), updated, revision_of=initial["analysis_id"])["result"]
    assert candidate.get("memory_decision") == "adapt" and len(model.calls) == 3
    assert candidate["preview"] and not candidate["questions"] and not candidate["uncertainties"]
    definition = candidate["preview"]["definition"]
    assert rules.preview_candidate(user(), definition)["sql_params"] == candidate["preview"]["sql_params"]
    for change in [old["expression"], revised["expression"]["conditions"][0], revised["expression"]["conditions"][1]]:
        partial = {**definition, "expression": change}
        assert not rules.preview_candidate(user(), partial, return_questions=True).get("sql_preview")
    mixed_fields = deepcopy(definition)
    mixed_fields["expression"]["conditions"][0]["left"] = "day"
    assert not rules.preview_candidate(user(), mixed_fields, return_questions=True).get("sql_preview")
    wider_request = {**definition, "description": updated + "，同时只检查未清算的项目"}
    assert not rules.preview_candidate(user(), wider_request, return_questions=True).get("sql_preview")
