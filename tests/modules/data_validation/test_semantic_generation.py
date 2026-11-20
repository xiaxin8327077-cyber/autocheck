from copy import deepcopy

import pytest
from sqlalchemy import update

from auto_check.app.module_system.permissions import default_permission_evaluator
from auto_check.app.module_system.routing import ModuleRouter
from auto_check.modules.data_validation.api import register_routes
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.module import MANIFEST
from auto_check.modules.data_validation.storage import DOC_FIELDS, DOC_TABLES
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _generate_payload, _request, _rules_with_doc, _select_payload
from tests.modules.data_validation.test_analysis_jobs import _dispatch
from tests.modules.data_validation.test_followup_service_bridge import _add_table


FIELDS = [("row_id", "业务编号", "varchar", "Y"), ("amount", "份额", "numeric", ""),
          ("balance", "余额", "numeric", ""), ("business_day", "数据日期", "date", "")]


@pytest.mark.parametrize("with_proposal", [False, True])
def test_only_model_business_proposals_reach_the_ui_without_another_model_call(with_proposal):
    raw = draft()
    if with_proposal:
        raw["ai_suggestions"] = [{"category": "consistency", "kind": "review",
            "title": "核实份额与余额是否采用相同统计范围", "reason": "两个文档指标需要业务确认",
            "references": [{"table_name": "test_table", "field_name": "amount"},
                           {"table_name": "test_table", "field_name": "balance"}],
            "preconditions": ["确认统计范围与允许差额"], "limitations": []}]
    rules, model = _rules_with_doc([_select_payload(), raw], fields=FIELDS)
    request = _request(request_text="份额低于19要核实", analysis_protocol=2)
    result = rules.parse_rule_request(user(), request)
    assert len(model.calls) == 2
    assert len(result["ai_suggestions"]) == int(with_proposal)
    if with_proposal:
        assert result["ai_suggestions"][0]["provenance"] == "model"
        assert result["ai_suggestions"][0]["support_level"] == "needs_confirmation"
    assert not result.get("comparison_suggestions")
    repeated = rules.parse_rule_request(user(), request)
    assert len(model.calls) == 2 and repeated["ai_suggestions"] == result["ai_suggestions"]


@pytest.mark.parametrize("outside_draft", [False, True])
@pytest.mark.parametrize("clarification", [False, True])
def test_model_proposals_survive_combined_envelopes_clarification_and_replay(outside_draft, clarification):
    proposal = draft()
    suggestions = [{"category": "consistency", "kind": "review", "title": "核对两个指标统计范围",
                    "reason": "需业务确认相同期间的份额与余额是否可比",
                    "references": [{"table_name": "test_table", "field_name": "balance"}]}]
    if clarification:
        proposal.update(rule_type=None, expression={}, semantic_intent={"metrics": [], "scopes": [],
                        "open_questions": ["请明确本次检查的业务条件"]})
    reply = {**_select_payload(), "draft": proposal}
    (reply if outside_draft else proposal)["ai_suggestions"] = suggestions
    replies = [reply] if not clarification else [_select_payload(), {**proposal, "ai_suggestions": suggestions}]
    rules, model = _rules_with_doc(replies, fields=FIELDS)
    request = _request(request_text="请看一下份额" if clarification else "份额低于19要核实", analysis_protocol=2)
    result = rules.parse_rule_request(user(), request)
    assert len(model.calls) == (2 if clarification else 1)
    assert len(result.get("ai_suggestions", [])) == 1
    assert result["ai_suggestions"][0]["title"] == suggestions[0]["title"]
    assert bool(result.get("preview")) is not clarification
    repeated = rules.parse_rule_request(user(), request)
    assert len(model.calls) == (2 if clarification else 1) and repeated["ai_suggestions"] == result["ai_suggestions"]


@pytest.mark.parametrize("unused_plans", [None, []])
def test_optional_outer_plans_does_not_lose_a_single_draft(unused_plans):
    rules, model = _rules_with_doc([{**_select_payload(), "draft": draft(), "plans": unused_plans}], fields=FIELDS)
    result = rules.parse_rule_request(user(), _request(request_text="份额低于19要核实", analysis_protocol=2))
    assert len(model.calls) == 1 and result["preview"]


def draft(field="amount", **changes):
    return _generate_payload(
        expression={"left": field, "op": "lt", "right_type": "value", "right": 19},
        semantic_intent={"metrics": [{"side": "left", "term": "核查指标", "fields": [field]}],
                         "scopes": [], "open_questions": []}, null_policy="skip", **changes,
    )


@pytest.mark.parametrize("text", ["净值型项目", "贷款期限高低先放一边，我想知道它有没有跌破那个数"])
def test_model_decides_even_when_input_looks_like_a_scope_or_uses_a_paraphrase(text):
    rules, model = _rules_with_doc([_select_payload(), draft()], fields=FIELDS)
    result = rules.parse_rule_request(user(), _request(request_text=text, analysis_protocol=2))
    assert len(model.calls) == 2
    assert result["analysis_protocol"] == 2 and result["expression"]["right"] == 19
    assert result["semantic_intent"]["metrics"][0]["fields"] == ["amount"]
    assert result["null_policy"] == "skip"
    assert result["preview"] and not result["uncertainties"]
    assert rules.storage.visible_rules("1") == []


def test_single_candidate_carries_document_labels_through_preview_independent_of_executable_rule():
    rules, _ = _rules_with_doc([_select_payload(), draft()], fields=FIELDS)
    notes = "每次按指定报送日期写入本表，以下为配置说明。"
    with rules.storage.database.begin() as connection:
        connection.execute(update(DOC_TABLES).values(table_name_cn="业务表", scope=notes, dimension="合同"))
    result = rules.parse_rule_request(user(), _request(analysis_protocol=2))
    assert result["table_name_cn"] == "业务表" and result["grain"] == "合同级"
    assert result["scope_description"] == "业务表" and result["document_scope"] == notes
    definition = result["preview"]["definition"]
    preview = rules.preview_candidate(user(), {"definition": definition}, return_questions=True)
    assert preview["document_scope"] == notes and preview["table_name_cn"] == "业务表"
    assert "document_scope" not in definition and "table_name_cn" not in definition
    assert preview["content_sha256"] == result["preview"]["content_sha256"]


def test_incomplete_contract_is_repaired_once_and_never_replaced_by_a_chinese_rule():
    partial = draft()
    del partial["semantic_intent"]
    for repaired, expected in [(draft(), "field_compare"), (partial, None)]:
        rules, model = _rules_with_doc([_select_payload(), partial, repaired], fields=FIELDS)
        request = _request(request_text="份额不得为空", analysis_protocol=2)
        if expected is None:
            with pytest.raises(AppError) as error:
                rules.parse_rule_request(user(), request)
            assert error.value.code == "MODEL_RESPONSE_INVALID"
            assert error.value.stage == "generate_rule"
        else:
            assert rules.parse_rule_request(user(), request)["rule_type"] == expected
        assert len(model.calls) == 3
        assert "semantic_intent" in model.calls[-1]["messages"][0]["content"]


def test_three_model_plans_retain_independent_structures_and_questions(monkeypatch):
    a, b, c = draft(), draft("balance"), draft()
    c["expression"]["op"] = "gt"
    c["semantic_intent"]["open_questions"] = ["另一个业务系统是否也采用相同的截止时间？"]
    rules, model = _rules_with_doc([_select_payload(), {"plans": [a, b, c], "plan_mode": "parallel"}], fields=FIELDS)
    monkeypatch.setattr("auto_check.modules.data_validation.candidate_preview.compile_checked_definition",
                        lambda *_: pytest.fail("不能在其他方案仍待确认时编译 SQL"))
    result = rules.parse_rule_request(user(), _request(request_text="请把这几项分开看", analysis_protocol=2))
    options = result["candidate_options"]
    assert len(model.calls) == 2 and len({option["id"] for option in options}) == 3
    assert all(option["candidate"]["parallel_check"] for option in options)
    assert all(not option["candidate"].get("preview") and not option["candidate"]["can_enable"] for option in options)
    assert options[2]["candidate"]["uncertainties"] == c["semantic_intent"]["open_questions"]


def test_a_document_review_discovered_in_the_final_preflight_blocks_earlier_plans(monkeypatch):
    from auto_check.modules.data_validation import semantic_grounding

    check = semantic_grounding.semantic_coverage_issue
    pending = "活动文档中该指标的适用范围需要补充。"
    visits = []

    def review(definition, *args):
        field = definition["expression"]["left"]
        visits.append(field)
        return pending if field == "balance" else check(definition, *args)

    monkeypatch.setattr(semantic_grounding, "semantic_coverage_issue", review)
    monkeypatch.setattr("auto_check.modules.data_validation.candidate_preview.compile_checked_definition",
                        lambda *_: pytest.fail("所有方案应先完成文档复核"))
    rules, _ = _rules_with_doc([_select_payload(), {"plans": [draft(), draft("balance")]}], fields=FIELDS)
    result = rules.parse_rule_request(user(), _request(analysis_protocol=2))
    first, second = (o["candidate"] for o in result["candidate_options"])
    assert visits == ["amount", "balance"]
    assert first["uncertainties"] == [] and second["uncertainties"] == [pending]
    assert first["preview"] is None and second["preview"] is None and result["preview"] is None


@pytest.mark.parametrize("semantic", [False, True])
def test_review_only_route_rechecks_edited_definitions_without_sql_then_allows_normal_preview(semantic, monkeypatch):
    rules, _ = _rules_with_doc([_select_payload(), draft()], fields=FIELDS)
    definition = rules.parse_rule_request(user(), _request(analysis_protocol=2))["preview"]["definition"]
    if not semantic:
        definition.pop("analysis_protocol")
        definition.pop("semantic_intent")
        definition["description"] = ""
    router = ModuleRouter(MANIFEST, default_permission_evaluator)
    register_routes(router, lambda: rules)
    owner = {**user(), "capabilities": ["dv.ai_use"]}
    issue = "当前限额是否适用于本期？"
    with monkeypatch.context() as probe:
        probe.setattr("auto_check.modules.data_validation.candidate_preview.compile_checked_definition",
                      lambda *_: pytest.fail("review_only 只能核实结构"))
        invalid = _dispatch(router, "POST", "/ai/preview", owner, body={"review_only": "true", "definition": definition})
        assert invalid.status == 400
        for questions, expected in [([issue], False), ([], True)]:
            response = _dispatch(router, "POST", "/ai/preview", owner, body={
                "review_only": True, "definition": {**definition, "uncertainties": questions},
            })
            assert response.status == 200
            review = response.body["data"]
            assert review["ready"] is expected and review["status"] == ("ready" if expected else "needs_confirmation")
            assert review["uncertainties"] == questions and review["definition"]["table_name"] == "test_table"
            assert not {"sql_preview", "cases", "content_sha256", "documented_identifiers"}.intersection(review)
    final = _dispatch(router, "POST", "/ai/preview", owner, body={"definition": review["definition"]})
    assert final.status == 200 and final.body["data"]["sql_preview"]


def test_model_reads_complete_dictionaries_and_only_independent_open_questions_block_the_draft():
    fields = [*FIELDS, ("phase", "现行分类依据", "varchar", ""), ("orig", "最初分类依据", "varchar", "")]
    codebook = "\n".join(f"{i}-类别{i}的文档释义" for i in range(24))
    scope = {"category": "有条件豁免类别", "fields": ["phase", "orig"], "recommended": "phase",
             "memberships": {f: {"include": ["0", "23"], "exclude": [str(i) for i in range(1, 23)]}
                             for f in ("phase", "orig")}}
    note = "另需确认新制度的正式启用时间。"
    raw = draft(uncertainties=["请核实原始分类和现行分类物理列是否存在。"])
    raw["semantic_intent"]["metrics"][0]["fields"].append("balance")
    raw["semantic_intent"].update(scopes=[scope], open_questions=[note])
    hint = {"role": "scope", "fields": ["phase", "orig"], "term": "分类口径"}
    selection = _select_payload(uncertainties=["需要进一步核实两个分类字段。"], semantic_hints=[hint])
    rules, model = _rules_with_doc([selection, raw], fields=fields)
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name.in_(("phase", "orig"))).values(dictionary=codebook))
    result = rules.parse_rule_request(user(), _request(request_text="按前述分类核查", analysis_protocol=2))
    assert len(model.calls) == 2
    prompt = model.calls[-1]["messages"][0]["content"]
    assert "23-类别23的文档释义" in prompt and "semantic_hints" in prompt
    assert {q["id"] for q in result["questions"]} == {"filters.0", "expression.left"}
    assert note in result["uncertainties"] and len(result["uncertainties"]) == 3
    assert result["model_judgments"]["generate_rule"]["uncertainties"] == raw["uncertainties"]
    assert result["model_judgments"]["select_table"]["uncertainties"] == selection["uncertainties"]
    assert result.get("preview") is None


def test_v2_shared_analysis_memory_reuses_only_a_model_verified_structured_draft():
    initial = draft()
    adapted = draft()
    adapted["expression"]["right"] = 27
    selection = _select_payload()
    memory = {**selection, "reuse_decision": "adapt", "memory_index": 0, "draft": adapted}
    rules, model = _rules_with_doc([selection, initial, memory], fields=FIELDS)
    rules.parse_rule_request(user(), _request(request_text="份额低于19要核实", analysis_protocol=2))
    result = rules.parse_rule_request(user("2"), _request(request_text="份额低于27要核实", analysis_protocol=2))
    assert len(model.calls) == 3 and result["analysis_reused"] and result["memory_decision"] == "adapt"
    assert result["expression"]["right"] == 27 and result["preview"]
    assert "current_owner_choices" in model.calls[-1]["messages"][0]["content"]


def test_metric_options_keep_model_names_for_each_documented_field():
    names = {"amount": "当期份额不得低于19", "balance": "当期余额不得低于19"}
    supplied = draft(rule_name=names["amount"])
    supplied["semantic_intent"]["metrics"][0].update(fields=["amount", "balance"], recommended="amount", rule_names=names)
    rules, model = _rules_with_doc([_select_payload(), supplied], fields=FIELDS)
    result = rules.parse_rule_request(user(), _request(analysis_protocol=2))
    question, = result["questions"]
    assert {option["value"]: option["rule_name"] for option in question["options"]} == names
    assert result["rule_name"] == names["amount"]
    assert len(model.calls) == 2
    assert "rule_names" in model.calls[-1]["messages"][0]["content"]


@pytest.mark.parametrize("include_peer", [False, True])
def test_model_scope_candidates_do_not_require_same_dictionary_peer_explanations(include_peer):
    fields = [*FIELDS, ("chosen", "最终约定", "varchar", ""), ("other", "初始约定", "varchar", "")]
    partition = {"include": ["01"], "exclude": ["02"]}
    partial = {"category": "延期交付", "fields": ["chosen"], "memberships": {"chosen": partition}}
    supplied = draft()
    supplied["semantic_intent"]["scopes"] = [
        {**partial, "fields": ["chosen", "other"], "memberships": {"chosen": partition, "other": partition}}
        if include_peer else partial
    ]
    rules, model = _rules_with_doc([_select_payload(), supplied], fields=fields)
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name.in_(("chosen", "other")))
                     .values(dictionary="01-延期交付\n02-立即交付"))
    text = "延期交付的份额低于19" if include_peer else "最终约定延期交付的份额低于19"
    result = rules.parse_rule_request(user(), _request(request_text=text, analysis_protocol=2))
    assert len(model.calls) == 2
    prompt = model.calls[1]["messages"][0]["content"]
    assert prompt.count("01-延期交付") == 1
    assert "shared_dictionaries" in prompt and "other" in model.calls[-1]["messages"][0]["content"]
    assert any(q["id"] == "filters.0" for q in result["questions"]) == include_peer
    assert bool(result.get("preview")) != include_peer


def test_unrelated_yes_no_flags_do_not_trigger_scope_repair_or_extra_filters():
    unrelated = [(f"flag_{i}", label, "varchar", "") for i, label in enumerate(
        ("是否新增", "是否终止", "是否增信", "是否分级", "是否现金管理", "是否跨境", "是否公开", "是否展期", "是否清算"))]
    fields = [*FIELDS, ("transfer", "收益权转让标识", "varchar", ""), *unrelated]
    supplied = draft("balance")
    supplied["expression"] = {"left": "balance", "op": "eq", "right_type": "value", "right": 0}
    supplied["semantic_intent"]["scopes"] = [{
        "category": "收益权转让", "fields": ["transfer"],
        "memberships": {"transfer": {"include": ["1"], "exclude": ["2"]}},
    }]
    rules, model = _rules_with_doc([_select_payload(), supplied], fields=fields)
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name.in_(["transfer", *(f[0] for f in unrelated)]))
                     .values(dictionary="1-是\n2-否"))
    result = rules.parse_rule_request(user(), _request(request_text="收益权转让标识为是的项目，余额不能为0", analysis_protocol=2))
    assert result["expression"] == {"left": "balance", "op": "eq", "right_type": "value", "right": 0}
    assert result["filters"] == [{"table": "base", "field": "transfer", "op": "eq", "value": "1", "confirmed": True}]
    assert result["preview"] and not result["questions"] and not result["uncertainties"]
    assert len(model.calls) == 2


def test_model_can_choose_a_second_documented_target_without_inheriting_the_first_tables_fields():
    second = {"table": "other_table"}
    a, b = draft(), draft("different_field")
    b["target"] = second
    b["sql"] = "untrusted model SQL"
    rules, model = _rules_with_doc([_select_payload(candidate_targets=[second]), {"plans": [a, b]}, {"ai_suggestions": []}], fields=FIELDS)
    _add_table(rules, name="other_table", cn="第二张表", dimension="业务",
               fields=[("pk", "序号", "varchar", "Y"), ("different_field", "发生额", "numeric", ""),
                       ("date_2", "数据日期", "date", "")])
    result = rules.parse_rule_request(user(), _request(request_text="两类口径分别看看", analysis_protocol=2))
    first, other = (o["candidate"] for o in result["candidate_options"])
    assert len(model.calls) == 3 and "本轮只提出独立补充校验建议" in model.calls[-1]["messages"][0]["content"]
    assert first["business_key"] == "row_id"
    assert (other["table_name"], other["business_key"], other["report_date_field"]) == ("other_table", "pk", "date_2")
    assert "different_field" in other["preview"]["sql_preview"]
    assert "untrusted" not in other["preview"]["sql_preview"] and not rules.storage.visible_rules("1")


def test_scope_without_violation_condition_returns_the_models_own_question():
    raw = {"rule_type": None, "expression": {}, "semantic_intent": {
        "metrics": [], "scopes": [], "open_questions": ["请说明要辨别哪种异常。"]}}
    rules, model = _rules_with_doc([_select_payload(), raw], fields=FIELDS)
    result = rules.parse_rule_request(user(), _request(request_text="此类业务", analysis_protocol=2))
    assert len(model.calls) == 2 and result["rule_type"] is None
    assert result["uncertainties"] == ["请说明要辨别哪种异常。"] and not result.get("preview")


@pytest.mark.parametrize("mode", ["parallel", "alternatives"])
def test_first_round_plan_envelopes_keep_both_metrics_scopes_suggestions_and_unconfirmed_join(mode):
    source = {"table": "test_table"}
    scope = {"category": "存续", "fields": ["phase"], "memberships": {"phase": {"include": ["1"], "exclude": ["2", ""]}}}
    first, second = draft("amount"), draft("shares")
    first["semantic_intent"]["scopes"] = [{**scope, "table": "base"}]
    second["semantic_intent"]["scopes"] = [{**scope, "table": "related"}]
    second["join"] = {"table_name": "test_table", "on": [{"left": "row_id", "right": "row_id"}],
                      "report_date_field": "business_day", "unmatched_policy": "unresolved"}
    def suggestion(title):
        return {"category": "consistency", "kind": "review", "title": title, "reason": "需核实指标期间",
                "references": [{"table_name": "test_table", "field_name": "amount"}]}
    second["ai_suggestions"] = [suggestion("复核份额的统计范围")]
    reply = {"plan_mode": mode, "plans": [{"target": source, "draft": first}, {
        "target": {"table": "contracts"}, "related_target": source, "draft": second}],
        "ai_suggestions": [suggestion("复核份额的统计期间")]}
    rules, model = _rules_with_doc([reply], fields=[*FIELDS, ("phase", "存续状态", "varchar", "")])
    _add_table(rules, name="contracts", cn="合同表", dimension="合同", fields=[
        ("row_id", "业务编号", "varchar", "Y"), ("shares", "合同实收", "numeric", ""),
        ("business_day", "数据日期", "date", "")])
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "phase")
                     .values(dictionary="1-存续\n2-终止", logic="其他值及空值留空。"))
    request = _request(request_text="存续的份额和合同实收低于19", analysis_protocol=2)
    for _ in range(2):
        result = rules.parse_rule_request(user(), request)
        assert len(model.calls) == 1
        assert {s["title"] for s in result["ai_suggestions"]} == {"复核份额的统计范围", "复核份额的统计期间"}
        candidates = [o["candidate"] for o in result["candidate_options"]]
        assert [(c["table_name"], c["expression"]["left"]) for c in candidates] == [("test_table", "amount"), ("contracts", "shares")]
        assert all(c["expression"]["right"] == 19 and bool(c.get("parallel_check")) == (mode == "parallel")
                   and c["preview"] is None for c in candidates)
        assert [c["filters"] for c in candidates] == [
            [{"table": role, "field": "phase", "op": "eq", "value": "1", "confirmed": True}] for role in ("base", "related")]
        assert "join.relationship_confirmed" in {q["id"] for q in candidates[1]["questions"]}


@pytest.mark.parametrize("conflict", ["target", "related_target", "report_category"])
def test_conflicting_plan_envelope_declarations_are_rejected(conflict):
    declarations = {"target": {"table": "test_table"}, "related_target": {"table": "other"}, "report_category": "east5"}
    other = {"target": {"table": "other"}, "related_target": {"table": "test_table"}, "report_category": "pbc_central"}
    proposal = {**draft(), conflict: other[conflict]}
    rules, _ = _rules_with_doc([{"plans": [{**declarations, "draft": proposal}]}], fields=FIELDS)
    _add_table(rules, name="other", cn="另一张表", dimension="项目", fields=FIELDS)
    with pytest.raises(AppError) as error:
        rules.parse_rule_request(user(), _request(request_text="份额低于19", analysis_protocol=2))
    assert error.value.code == "MODEL_RESPONSE_INVALID"


def test_plan_envelopes_never_assign_an_ambiguous_physical_table_to_the_first_category():
    reply = {"plans": [{"target": {"table": "test_table"}, "report_category": "east5", "draft": draft()},
                       {"target": {"table": "test_table"}, "draft": draft("balance")}]}
    rules, _ = _rules_with_doc([reply], fields=FIELDS)
    _add_table(rules, name="test_table", cn="另一分类", dimension="项目", fields=FIELDS)
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_TABLES).where(DOC_TABLES.c.table_name_cn != "另一分类").values(sheet_name="人行_第一种分类"))
        conn.execute(update(DOC_TABLES).where(DOC_TABLES.c.table_name_cn == "另一分类").values(sheet_name="East5报送_第二种分类"))
    with pytest.raises(AppError) as error:
        rules.parse_rule_request(user(), _request(request_text="份额余额低于19", analysis_protocol=2))
    assert error.value.code == "MODEL_RESPONSE_INVALID"


@pytest.mark.parametrize(("included", "excluded"), [
    (["1", ""], ["2"]), (["1"], [""]), (["1"], ["2", "unknown", ""]),
    (["1"], ["2", "", ""]), (["1"], ["2", "2", ""]), (["1"], ["1", "2", ""]),
])
def test_excluded_blank_cannot_hide_unknown_duplicate_missing_or_overlapping_dictionary_members(included, excluded):
    proposed = draft()
    proposed["semantic_intent"]["scopes"] = [{"category": "存续", "fields": ["phase"],
        "memberships": {"phase": {"include": included, "exclude": excluded}}}]
    rules, _ = _rules_with_doc([{**_select_payload(), "draft": proposed}, proposed],
                               fields=[*FIELDS, ("phase", "存续状态", "varchar", "")])
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "phase")
                     .values(dictionary="1-存续\n2-终止", logic="其他值及空值留空。"))
    with pytest.raises(AppError) as error:
        rules.parse_rule_request(user(), _request(request_text="存续份额低于19", analysis_protocol=2))
    assert error.value.code == "MODEL_RESPONSE_INVALID"


@pytest.mark.parametrize("conflict", ["branches", "mode", "boolean_number", "single_expression", "shared_filter"])
def test_combined_response_cannot_choose_between_conflicting_structured_rules(conflict):
    target = {"table": "test_table"}
    first = {"target": target, "draft": draft()}
    plans = [first, {"target": target, "draft": draft("balance")}]
    if conflict == "branches":
        reply = {**first, "plan_mode": "parallel", "plans": plans}
    elif conflict == "mode":
        reply = {"target": target, "plan_mode": "parallel", "draft": {"plans": plans, "plan_mode": "alternatives"}}
    elif conflict == "boolean_number":
        first["draft"]["expression"]["right"] = True
        first["expression"] = {**first["draft"]["expression"], "right": 1}
        reply = {"plans": plans}
    elif conflict == "shared_filter":
        reply = {"plans": plans, "filters": [{"field": "row_id", "table": "base", "op": "eq", "value": "X"}]}
    else:
        reply = {**first, "expression": draft("balance")["expression"]}
    rules, model = _rules_with_doc([reply], fields=FIELDS)
    with pytest.raises(AppError) as error:
        rules.parse_rule_request(user(), _request(request_text="份额余额低于19", analysis_protocol=2))
    assert error.value.code == "MODEL_RESPONSE_INVALID" and len(model.calls) == 1


@pytest.mark.parametrize("first_mode", ["parallel", "alternatives"])
@pytest.mark.parametrize("change", ["plan_mode", "drop_plan", "drop_question", "drop_unsupported",
                                    "drop_executable_unsupported", "drop_uncertainty", "move_question"])
def test_expansion_uses_reviewed_plan_relation_and_documented_answers(first_mode, change):
    target = {"table": "test_table"}
    first, second = draft(), draft("balance")
    question = "余额统计时点尚待确认，请说明。"
    request_text = "份额和余额各自低于19时提醒" if first_mode == "parallel" else "在份额、余额两种口径中选一种检查低于19"
    if change != "plan_mode":
        second = {"rule_type": None, "expression": {}, "semantic_intent": {"metrics": [], "scopes": [], "open_questions": [question]}}
    if change == "drop_unsupported":
        second["unsupported_requirements"] = [question]
        second["semantic_intent"]["open_questions"] = []
    if change == "drop_executable_unsupported":
        second = draft("balance", unsupported_requirements=[question])
    if change == "drop_uncertainty":
        second["uncertainties"] = [question]
        second["semantic_intent"]["open_questions"] = ["请确认合同统计截止日。"]
    if change == "move_question":
        second = draft("balance")
        question = "份额是否包含当日待确认的变更？"
        second["semantic_intent"]["open_questions"] = [question]
    reply = {"expand_evidence": True, "plan_mode": first_mode,
             "plans": [{"target": target, "draft": first}, {"target": target, "draft": second}]}
    generated = {"plans": [deepcopy(first), deepcopy(second)], "plan_mode": first_mode}
    if change == "plan_mode":
        generated["plan_mode"] = "parallel" if first_mode == "alternatives" else "alternatives"
        request_text = ("份额和余额各自低于19时提醒" if generated["plan_mode"] == "parallel"
                        else "在份额、余额两种口径中选一种检查低于19")
    elif change == "drop_plan":
        request_text = "仅检查份额是否低于19"
        generated = deepcopy(first)
    elif change == "move_question":
        generated["plans"][1]["semantic_intent"]["open_questions"] = []
        generated["plans"][0]["semantic_intent"]["open_questions"] = [question]
    elif change == "drop_uncertainty":
        generated["plans"][1].pop("uncertainties")
    else:
        generated["plans"][1] = draft("balance")
    rules, model = _rules_with_doc([reply, generated], fields=FIELDS)
    with rules.storage.database.begin() as connection:
        connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "balance")
                           .values(logic="记录数据日期当日终了时的余额。"))
    result = rules.parse_rule_request(user(), _request(request_text=request_text, analysis_protocol=2))
    assert len(model.calls) == 2
    if change == "drop_plan":
        assert result["preview"] and result["expression"] == first["expression"]
        assert not result.get("candidate_options")
        return
    options = [row["candidate"] for row in result["candidate_options"]]
    assert len(options) == 2
    assert all(bool(row.get("parallel_check")) == (generated["plan_mode"] == "parallel") for row in options)
    if change == "drop_uncertainty":
        assert not any(row.get("preview") for row in options)
        assert options[1]["uncertainties"] == generated["plans"][1]["semantic_intent"]["open_questions"]
    elif change == "move_question":
        assert not any(row.get("preview") for row in options)
        assert options[0]["uncertainties"] == [question] and not options[1]["uncertainties"]
    else:
        assert [row["expression"] for row in options] == [first["expression"], draft("balance")["expression"]]
        assert all(row["preview"] and not row["uncertainties"] for row in options)


def test_review_cannot_drop_a_separate_check_explicitly_requested_for_a_second_field():
    target = {"table": "test_table"}
    amount = draft()
    pending = {"rule_type": None, "expression": {}, "semantic_intent": {
        "metrics": [], "scopes": [], "open_questions": ["余额统计时点尚待确认。"]}}
    first = {"expand_evidence": True, "plan_mode": "parallel",
             "plans": [{"target": target, "draft": amount}, {"target": target, "draft": pending}]}
    rules, _ = _rules_with_doc([first, amount], fields=FIELDS)
    result = rules.parse_rule_request(user(), _request(request_text="份额和余额分别低于19时提醒", analysis_protocol=2))
    assert not result.get("preview") and result["uncertainties"]


@pytest.mark.parametrize("request_text", ["累计排放量不得为空", "排放量不得为空"])
def test_unqualified_null_check_offers_only_documented_period_variants(request_text):
    opening = draft("initial")
    opening["expression"] = {"left": "initial", "op": "is_null"}
    opening["semantic_intent"]["metrics"][0].update(term="排放量", recommended="initial")
    fields = [*FIELDS, ("initial", "累计排放量", "numeric", ""), ("current", "当期排放量", "numeric", ""),
              ("maximum", "最大排放量", "numeric", ""), ("description", "当期排放量说明", "varchar", "")]
    rules, _ = _rules_with_doc([_select_payload(), opening, opening], fields=fields)
    result = rules.parse_rule_request(user(), _request(request_text=request_text, analysis_protocol=2))
    if request_text.startswith("累计"):
        assert result["preview"] and result["expression"] == opening["expression"]
    else:
        question, = result["questions"]
        assert {o["value"] for o in question["options"]} == {"initial", "current"}
        assert not result["preview"]
