import logging

import pytest
from sqlalchemy import select, update

from auto_check.modules.data_validation.storage import DOC_FIELDS, DOC_TABLES
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request, _rules_with_doc, _select_payload
from tests.modules.data_validation.test_followup_service_bridge import _add_table
from tests.modules.data_validation.test_semantic_generation import FIELDS, draft
from tests.modules.data_validation.test_shared_analysis_reuse import analyze


def seeded_analysis(response, extra, *, table_fields=()):
    fields = [*FIELDS, *((f"noise_{i}", f"备注{i}", "varchar", "") for i in range(24)), *table_fields]
    prior = {**_select_payload(), "draft": draft("amount")}
    rules, model = _rules_with_doc([prior, response, extra], fields=fields)
    with rules.storage.database.begin() as connection:
        connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name.like("noise%"))
                           .values(logic="未命中字段的完整历史表说明"))
    previous = analyze(rules, user(), "份额低于19要核实", analysis_protocol=2)
    assert len(model.calls) == 1
    return rules, model, previous


@pytest.mark.parametrize("revision", [False, True])
@pytest.mark.parametrize("mode", [{"reuse_decision": "fresh"}, {}])
def test_history_allows_fresh_grounded_rule_in_first_compact_call(revision, mode, caplog):
    proposal = draft("balance")
    selection = {**_select_payload(), **mode, "draft": proposal}
    rules, model, previous = seeded_analysis(selection, proposal)
    owner = user() if revision else user("another")
    context = {"revision_of": previous["analysis_id"], "revised_definition": previous["result"]} if revision else {}
    with caplog.at_level(logging.INFO, logger="auto_check.modules.data_validation"):
        result = rules.parse_rule_request(owner, _request(request_text="余额低于19要复核", analysis_protocol=2, **context))
    assert len(model.calls) == 2, "another user's recent examples or a revision must allow a fresh one-call plan"
    assert "stage=select_and_generate" in caplog.text
    prompt = model.calls[1]["messages"][0]["content"]
    assert "备注23" in prompt and "未命中字段的完整历史表说明" not in prompt
    assert "current_owner_choices" in prompt and "reuse_decision" in prompt and "本次合并回复" in prompt
    assert result["memory_decision"] == "fresh" and not result["analysis_reused"]
    assert result["expression"]["left"] == "balance" and result["preview"]


@pytest.mark.parametrize("decision", ["reuse", "adapt", "fresh"])
def test_history_requires_expansion_for_unseen_field_before_accepting_draft(decision):
    proposal = draft("tail")
    selection = {**_select_payload(), "reuse_decision": decision, "memory_index": 0, "draft": proposal}
    rules, model, _ = seeded_analysis(selection, proposal, table_fields=[("tail", "历史余额", "numeric", "")])
    result = rules.parse_rule_request(user(), _request(request_text="看看当初还剩多少，跌破19要报错", analysis_protocol=2))
    prompts = [entry["messages"][0]["content"] for entry in model.calls[1:]]
    assert len(prompts) == 2 and "备注23" in prompts[0] and "未命中字段的完整历史表说明" not in prompts[0]
    assert "未命中字段的完整历史表说明" in prompts[1] and result["expression"]["left"] == "tail"
    assert not result["analysis_reused"]


def test_legacy_fresh_only_memory_reply_can_request_a_target_before_generating():
    rules, model = _rules_with_doc([{**_select_payload(), "draft": draft()}, {"reuse_decision": "fresh"},
                                    _select_payload(), draft("balance")], fields=FIELDS)
    analyze(rules, user(), "份额低于19要核实", analysis_protocol=2)
    result = rules.parse_rule_request(user(), _request(request_text="余额低于19要复核", analysis_protocol=2))
    assert len(model.calls) == 4
    assert result["memory_decision"] == "fresh" and not result["analysis_reused"] and result["preview"]


@pytest.mark.parametrize("claim", [{"reuse_decision": "adapt", "memory_index": 999},
                                   {"reuse_decision": "fresh", "memory_index": 0}])
def test_invalid_memory_claim_never_treats_its_old_comparison_as_fresh(claim):
    invalid = {**_select_payload(), **claim, "draft": draft("balance")}
    invalid["draft"]["expression"]["right"] = 888
    rules, model, _ = seeded_analysis(invalid, draft("balance"))
    result = rules.parse_rule_request(user(), _request(request_text="余额低于19要复核", analysis_protocol=2))
    assert len(model.calls) == 3 and result["expression"]["right"] == 19
    assert result["memory_decision"] == "fresh" and not result["analysis_reused"]


@pytest.mark.parametrize("claim", [{}, {"reuse_decision": "fresh"},
                                   {"reuse_decision": "adapt", "memory_index": 0},
                                   {"reuse_decision": "reuse", "memory_index": 0}])
@pytest.mark.parametrize("regenerated", [19, 73])
def test_changed_literal_requires_current_threshold_in_every_generated_draft(claim, regenerated):
    old = draft("amount")
    replacement = draft("amount")
    replacement["expression"]["right"] = regenerated
    rules, model, _ = seeded_analysis({**_select_payload(), **claim, "draft": old}, replacement)
    request = _request(request_text="份额低于73要核实", analysis_protocol=2)
    result = rules.parse_rule_request(user("other"), request)
    assert len(model.calls) == 3
    if regenerated == 73:
        assert result["expression"]["right"] == 73 and 73 in result["preview"]["sql_params"].values()
        assert not result["analysis_reused"]
    else:
        assert result["status"] == "needs_clarification" and not result.get("preview")
        assert any("73" in question for question in result["uncertainties"])
        context = rules._analysis_inputs(user("other"), request)["context"]
        assert rules.storage.cached_analysis_result(context, request["request_text"]) is None
        assert all(item["request_text"] != request["request_text"]
                   for item in rules.storage.find_analysis_memories(context, request["request_text"]))


def test_reuse_checks_document_identity_when_physical_name_exists_in_two_categories():
    proposal = draft("amount")
    first = {**_select_payload(), "draft": proposal}
    east = {**_select_payload(report_category="east5"), "reuse_decision": "reuse", "memory_index": 0, "draft": proposal}
    rules, model = _rules_with_doc([first, east, proposal], fields=FIELDS)
    _add_table(rules, name="test_table", cn="东报", dimension="车辆", fields=FIELDS)
    with rules.storage.database.begin() as connection:
        pbc_id, east_id = connection.execute(select(DOC_TABLES.c.id).order_by(DOC_TABLES.c.id)).scalars()
        connection.execute(update(DOC_TABLES).where(DOC_TABLES.c.id == pbc_id).values(sheet_name="人行_份额"))
        connection.execute(update(DOC_TABLES).where(DOC_TABLES.c.id == east_id).values(sheet_name="East5报送_份额"))
    first_result = rules.parse_rule_request(user(), _request(request_text="份额低于19要核实", analysis_protocol=2))
    assert first_result["report_category"] == "group:pbc"
    result = rules.parse_rule_request(user("other"), _request(request_text="东报车辆的份额低于19要核实", analysis_protocol=2))
    assert len(model.calls) == 3 and result["report_category"] == "east5"
    assert result["memory_decision"] == "fresh" and not result["analysis_reused"] and result["preview"]


def test_changed_threshold_in_an_unsolicited_draft_during_table_reselection_is_not_remembered():
    old = draft("amount")
    fresh = draft("amount")
    fresh["expression"]["right"] = 73
    rules, model, _ = seeded_analysis({"reuse_decision": "fresh"}, {**_select_payload(), "draft": old})
    model.payloads.append(fresh)
    result = rules.parse_rule_request(user("other"), _request(request_text="份额低于73要核实", analysis_protocol=2))
    assert len(model.calls) == 4 and result["expression"]["right"] == 73 and result["preview"]


@pytest.mark.parametrize("claim", [{"reuse_decision": "fresh"}, {"reuse_decision": "adapt", "memory_index": 0}])
@pytest.mark.parametrize("text", ["请核实份额低于73的记录", "请核实2026年份额小于73的记录，编码为206"])
def test_rephrased_explicit_numeric_comparison_cannot_inherit_an_old_threshold(claim, text):
    old = draft("amount")
    fresh = draft("amount")
    fresh["expression"]["right"] = 73
    rules, model, _ = seeded_analysis({**_select_payload(), **claim, "draft": old}, fresh)
    result = rules.parse_rule_request(user("other"), _request(request_text=text, analysis_protocol=2))
    assert len(model.calls) == 3 and result["expression"]["right"] == 73 and result["preview"]


@pytest.mark.parametrize(("before", "after", "old"), [
    ("核实2025年份额记录", "核实2026年份额记录", 2025),
    ("核实代码为19的份额记录", "核实代码为73的份额记录", 19),
])
def test_identifiers_and_years_do_not_become_comparison_thresholds(before, after, old):
    prior = draft("amount")
    prior["expression"]["right"] = old
    rules, model = _rules_with_doc([{**_select_payload(), "draft": prior},
                                   {**_select_payload(), "draft": draft("amount")}], fields=FIELDS)
    rules.parse_rule_request(user(), _request(request_text=before, analysis_protocol=2))
    result = rules.parse_rule_request(user("other"), _request(request_text=after, analysis_protocol=2))
    assert len(model.calls) == 2 and result["expression"]["right"] == 19


@pytest.mark.parametrize(("predicate", "op", "unit"), [
    ("低于", "lt", "元"), ("等于", "eq", ""), ("不等于", "neq", "万元"),
])
@pytest.mark.parametrize("replacement", [19, 73])
def test_reworded_current_amount_or_equality_threshold_must_survive_memory(predicate, op, unit, replacement):
    old, regenerated = draft("balance"), draft("balance")
    old["expression"]["op"] = regenerated["expression"]["op"] = op
    regenerated["expression"]["right"] = replacement
    first = {**_select_payload(), "draft": old}
    reuse = {**first, "reuse_decision": "adapt", "memory_index": 0}
    rules, model = _rules_with_doc([first, reuse, regenerated], fields=FIELDS)
    rules.parse_rule_request(user(), _request(request_text=f"余额{predicate}19{unit}要核实", analysis_protocol=2))
    result = rules.parse_rule_request(user("other"), _request(request_text=f"请核实余额{predicate}73{unit}的记录", analysis_protocol=2))
    assert len(model.calls) == 3
    if replacement == 73:
        assert result["expression"]["right"] == 73 and 73 in result["preview"]["sql_params"].values()
    else:
        assert result["status"] == "needs_clarification" and not result.get("preview")


def test_changed_currency_scale_without_documented_storage_unit_requires_clarification():
    old, replacement = draft("balance"), draft("balance")
    replacement["expression"]["right"] = 73
    first = {**_select_payload(), "draft": old}
    reuse = {**first, "reuse_decision": "adapt", "memory_index": 0}
    rules, _ = _rules_with_doc([first, reuse, replacement], fields=FIELDS)
    rules.parse_rule_request(user(), _request(request_text="余额低于19元要核实", analysis_protocol=2))
    result = rules.parse_rule_request(user("other"), _request(request_text="请核实余额低于73万元的记录", analysis_protocol=2))
    assert result["status"] == "needs_clarification" and not result.get("preview")
    assert any("单位" in question for question in result["uncertainties"])
