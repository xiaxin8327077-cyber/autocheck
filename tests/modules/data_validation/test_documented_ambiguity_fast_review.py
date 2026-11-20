"""A verified first model draft can expose document alternatives before another model turn."""
from copy import deepcopy

import pytest
from sqlalchemy import update

from auto_check.modules.data_validation.storage import DOC_FIELDS, DOC_TABLES
from auto_check.modules.data_validation.ai_suggestions import MAX_REFERENCES
from tests.modules.data_validation.test_ai_latency_pipeline import combined, run
from tests.modules.data_validation.test_ai_service import _rules_with_doc
from tests.modules.data_validation.test_followup_service_bridge import _add_table
from tests.modules.data_validation.test_semantic_generation import FIELDS, draft


def set_field(rules, name, **facts):
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == name).values(**facts))


def scope(field="state", term="在途"):
    return {"category": term, "fields": [field], "memberships": {field: {"include": ["Y"], "exclude": ["N"]}}}


def measure(name, term):
    plan = draft(name)
    plan["semantic_intent"]["metrics"][0]["term"] = term
    plan["semantic_intent"]["scopes"] = [scope()]
    plan["expression"].update(op="lte", right=-7)
    return plan


def test_sibling_metrics_and_two_category_fields_remain_selectable_in_one_turn():
    fields = [*FIELDS, ("unit", "单笔耗量", "numeric", ""), ("total", "累计耗量", "numeric", ""),
              ("old", "期初耗量", "numeric", ""), ("state", "当前运输状态", "varchar", ""),
              ("prior", "原始运输状态", "varchar", ""), ("unused", "封存标志", "varchar", "")]
    plans = [measure("unit", "单笔耗量"), measure("total", "累计耗量")]
    rules, model = _rules_with_doc([combined({"plans": plans, "plan_mode": "parallel"})], fields=fields)
    for name in ["state", "prior"]:
        set_field(rules, name, dictionary="Y-在途\nN-到站")
    set_field(rules, "unused", dictionary="Y-是\nN-否")
    result = run(rules, "在途的耗量不应小于等于-7")
    assert len(model.calls) == 1
    options = result["candidate_options"]
    assert {o["candidate"]["expression"]["left"] for o in options} == {"unit", "total"}
    for opt in options:
        candidate = opt["candidate"]
        assert not candidate["preview"] and not candidate["can_enable"]
        assert candidate["expression"]["op"] == "lte" and candidate["expression"]["right"] == -7
        question, = candidate["questions"]
        assert {o["selection"]["field"] for o in question["options"]} == {"state", "prior"}


def warehouse(proposals, *, proof=True, extra_fields=()):
    fields = [*FIELDS, ("state", "运输状态", "varchar", ""), ("priority", "优先级", "numeric", "")]
    rules, model = _rules_with_doc(proposals, fields=fields)
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_TABLES).values(dimension="运单", sheet_name="人行_运单"))
    _add_table(rules, name="pieces", cn="包裹清单", dimension="运单与包裹", fields=[
        ("piece_id", "包裹编号", "varchar", "Y"), ("waybill", "所属运单", "varchar", ""),
        ("account_day", "数据日期", "date", ""), ("volume", "测量容积", "numeric", ""), *extra_fields])
    set_field(rules, "balance", logic="业务别名：运单装载率。")
    set_field(rules, "volume", logic="业务别名：包裹装载率。")
    set_field(rules, "waybill", logic="直取", source_table="doc.test_table", source_field="row_id" if proof else "non_key")
    set_field(rules, "account_day", logic="直取", source_table="doc.test_table", source_field="business_day")
    set_field(rules, "state", dictionary="Y-在途\nN-到站")
    return rules, model


def warehouse_draft():
    plan = measure("balance", "装载率")
    plan["expression"]["right"] = 0
    plan["filters"] = [{"field": "priority", "op": "gt", "value": 3}]
    return plan


def test_registered_metric_on_another_grain_keeps_every_original_condition_and_blocks_preview():
    first = warehouse_draft()
    suggestion = {"category": "consistency", "kind": "review", "title": "核对运单与包裹的汇总装载口径",
                  "reason": "运单和包裹按不同粒度统计", "references": [
                      {"table_name": "test_table", "field_name": "balance"},
                      {"table_name": "pieces", "field_name": "volume"}]}
    reviewed = {"ai_suggestions": [suggestion]}
    rules, model = warehouse([combined(first), reviewed])
    result = run(rules, "在途且优先级高于3的装载率应大于0")
    assert len(model.calls) == 2
    prompt = model.calls[1]["messages"][0]["content"]
    assert '"ai_suggestions"' in prompt and '"table_name":"pieces"' in prompt
    assert '"volume"' in prompt and '"waybill"' in prompt and '"account_day"' in prompt
    assert "只生成本句委托的主校验" not in prompt
    assert model.calls[1]["options"]["max_tokens"] <= 3072
    assert [s["title"] for s in result["ai_suggestions"]] == [suggestion["title"]]
    options = {o["candidate"]["table_name"]: o["candidate"] for o in result["candidate_options"]}
    assert set(options) == {"test_table", "pieces"}
    a, b = options["test_table"], options["pieces"]
    assert not a["preview"] and not b["preview"]
    assert a["expression"] == first["expression"] and b["expression"] == {**first["expression"], "left": "volume"}
    assert b["null_policy"] == a["null_policy"] == "skip"
    assert b["report_date_field"] == "account_day"
    assert b["join"] == {"table_name": "test_table", "on": [{"left": "waybill", "right": "row_id"}],
                         "report_date_field": "business_day", "relationship_confirmed": False, "unmatched_policy": "unresolved"}
    assert b["filters"] == [{**f, "table": "related"} for f in a["filters"]]
    assert {q["id"] for q in b["questions"]} >= {"join.relationship_confirmed", "join.unmatched_policy"}
    assert not any(p.get("parallel_check") for p in options.values())
    again = run(rules, "在途且优先级高于3的装载率应大于0")
    assert again["memory_decision"] == "exact" and len(again["candidate_options"]) == 2


@pytest.mark.parametrize("bad", ["key", "date", "crossed", "category", "unit"])
def test_incomplete_scope_join_evidence_never_yields_an_unscoped_alternative(bad):
    first = warehouse_draft()
    if bad == "unit":
        first["expression"]["right"] = 81
    wrong = measure("volume", "装载率")
    wrong.update(target={"table": "pieces"}, filters=[])
    wrong["semantic_intent"]["scopes"] = []
    rules, _ = warehouse([combined(first), {"plans": [first, wrong]}], proof=bad != "key")
    if bad == "date":
        set_field(rules, "account_day", source_field="settlement_date")
    elif bad == "crossed":
        set_field(rules, "waybill", source_field="other_id\nrow_id", source_table="doc.test_table\nexternal.not_the_owner")
    elif bad == "category":
        with rules.storage.database.begin() as conn:
            conn.execute(update(DOC_TABLES).where(DOC_TABLES.c.table_name == "pieces").values(sheet_name="East5报送_包裹"))
    result = run(rules, "在途且优先级高于3的装载率应大于" + str(first["expression"]["right"]))
    assert not result.get("preview") and not result.get("candidate_options")
    assert result["uncertainties"]


def test_different_dictionary_requires_model_review_even_when_codes_and_positive_category_match():
    first = measure("balance", "耗量")
    reviewed = deepcopy(first)
    reviewed["semantic_intent"]["scopes"][0].update(fields=["state", "prior"], memberships={
        "state": {"include": ["Y"], "exclude": ["N"]}, "prior": {"include": ["Y"], "exclude": ["N"]}})
    fields = [*FIELDS, ("state", "当前运输状态", "varchar", ""), ("prior", "原始运输状态", "varchar", "")]
    rules, model = _rules_with_doc([combined(first), reviewed], fields=fields)
    set_field(rules, "state", dictionary="Y-在途\nN-到站")
    set_field(rules, "prior", dictionary="Y-在途\nN-撤销")
    result = run(rules, "在途的耗量不应小于等于-7")
    assert len(model.calls) == 2
    assert not result["preview"] and result["questions"]


def test_incomplete_original_partition_is_never_propagated_to_a_peer():
    first = measure("balance", "耗量")
    first["semantic_intent"]["scopes"][0]["memberships"]["state"]["exclude"] = []
    repaired = deepcopy(first)
    partitions = {name: {"include": ["Y"], "exclude": ["N"]} for name in ("state", "prior")}
    repaired["semantic_intent"]["scopes"][0].update(fields=["state", "prior"], memberships=partitions)
    fields = [*FIELDS, ("state", "当前运输状态", "varchar", ""), ("prior", "原始运输状态", "varchar", "")]
    rules, model = _rules_with_doc([combined(first), repaired], fields=fields)
    for name in partitions:
        set_field(rules, name, dictionary="Y-在途\nN-到站")
    result = run(rules, "在途的耗量低于标准需核实")
    assert len(model.calls) == 2
    assert not result["preview"]
    assert len(result["questions"][0]["options"]) == 2


def test_selection_only_then_documented_second_grain_is_reviewed_once_without_requiring_suggestions():
    first = warehouse_draft()
    reviewed = {"plans": [first, valid_alternative(first)]}
    rules, model = warehouse([{"target": {"table": "test_table"}}, first, reviewed])
    result = run(rules, "在途且优先级高于3的装载率应大于0")
    assert len(model.calls) == 3 and not result["ai_suggestions"]
    assert {x["candidate"]["table_name"] for x in result["candidate_options"]} == {"test_table", "pieces"}
    assert not any(x["candidate"].get("preview") for x in result["candidate_options"])


@pytest.mark.parametrize("irrelevant", [False, True])
def test_supplemental_reply_cannot_replace_or_remove_verified_primary_plans(irrelevant):
    first = warehouse_draft()
    other = valid_alternative(first)
    other["expression"]["right"] = 800
    rules, model = warehouse([combined(first), {"plans": [other]} if irrelevant else {"ai_suggestions": []}])
    result = run(rules, "在途且优先级高于3的装载率应大于0")
    assert len(model.calls) == 2 and not result.get("preview")
    assert {o["candidate"]["table_name"] for o in result["candidate_options"]} == {"test_table", "pieces"}
    assert all(o["candidate"]["expression"]["right"] == 0 for o in result["candidate_options"])
    assert result["ai_suggestions"] == []


@pytest.mark.parametrize("end", ["single_round", "total", "cancel"])
def test_supplement_deadline_only_degrades_its_own_result(end):
    from auto_check.modules.data_validation.analysis_jobs import AnalysisCancelled, AnalysisControl
    from auto_check.modules.data_validation.contracts import AppError
    from tests.modules.data_validation.support import user
    from tests.modules.data_validation.test_ai_service import _request

    rules, model = warehouse([combined(warehouse_draft()), {"ai_suggestions": []}])
    now = [0.0]
    control = AnalysisControl(lambda: now[0], 15 if end == "total" else 160)
    complete = model.complete_with_options
    def delayed(*args, **kwargs):
        response = complete(*args, **kwargs)
        if len(model.calls) == 2:
            assert kwargs["timeout_seconds"] == (15 if end == "total" else 20)
            if end == "cancel":
                control.set()
            else:
                now[0] += kwargs["timeout_seconds"]
        return response

    model.complete_with_options = delayed
    def run_with_deadline():
        return rules.parse_rule_request(user(), _request(request_text="在途且优先级高于3的装载率应大于0",
                                                         analysis_protocol=2), cancel_event=control)
    if end == "single_round":
        result = run_with_deadline()
        assert len(result["candidate_options"]) == 2 and result["ai_suggestions_status"] == "incomplete"
        assert any("补充建议" in note for note in result["notices"])
        control.check()
    elif end == "total":
        with pytest.raises(AppError, match="ANALYSIS_TIMEOUT"):
            run_with_deadline()
    else:
        with pytest.raises(AnalysisCancelled):
            run_with_deadline()
    assert control.model_round == 2 and control.output_tokens_used == 2 * 3072


@pytest.mark.parametrize("initial", ["valid", "invalid", "empty"])
def test_all_declared_cross_table_plans_request_only_missing_valid_suggestions(initial):
    first = {**warehouse_draft(), "target": {"table": "test_table"}}
    suggestion = {"category": "consistency", "kind": "review", "title": "核对运单和包裹的汇总口径",
                  "reason": "比较两类记录的装载率", "references": [
                      {"table_name": "test_table", "field_name": "balance"}, {"table_name": "pieces", "field_name": "volume"}]}
    before = [] if initial == "empty" else [suggestion if initial == "valid" else {**suggestion, "references": []}]
    second = valid_alternative(first)
    first["business_key"], second["business_key"] = "row_id", "piece_id"
    second["join"].update(relationship_confirmed=True, unmatched_policy="exclude")
    proposal = {"plans": [first, second], "ai_suggestions": before}
    rules, model = warehouse([combined(proposal), proposal])
    complete = model.complete_with_options
    def respond(model_id, messages, **kwargs):
        if "本轮只提出独立补充校验建议" in messages[0]["content"]:
            model.payloads[len(model.calls):] = [{"ai_suggestions": [suggestion]}]
        return complete(model_id, messages, **kwargs)
    model.complete_with_options = respond
    result = run(rules, "在途且优先级高于3的装载率应大于0")
    assert sum("本轮只提出独立补充校验建议" in c["messages"][0]["content"] for c in model.calls) == (initial != "valid")
    assert [item["title"] for item in result["ai_suggestions"]] == [suggestion["title"]]
    assert {o["candidate"]["table_name"] for o in result["candidate_options"]} == {"test_table", "pieces"}


@pytest.mark.parametrize("malformed", [True, False])
def test_supplement_contract_covers_aggregates_reference_limit_and_text_preconditions(malformed):
    refs = [{"table_name": t, "field_name": f} for t, f in [
        ("test_table", "balance"), ("pieces", "volume"), ("test_table", "state"),
        ("pieces", "waybill"), ("pieces", "account_day")]]
    proposal = {"category": "consistency", "kind": "aggregate_consistency", "operations": ["sum"],
                "title": "运单总量与当日包裹合计不一致", "reason": "按运单及日期汇总，差额不为零时提示",
                "references": refs[:2], "preconditions": [], "limitations": []}
    if malformed:
        proposal.update(category="cross_grain", kind="supplement", references=refs,
                        preconditions=[{"field": "state", "op": "eq", "value": "Y"}])
        del proposal["operations"]
    rules, model = warehouse([combined(warehouse_draft()), {"ai_suggestions": [proposal]}])
    result = run(rules, "在途且优先级高于3的装载率应大于0")
    prompt = model.calls[-1]["messages"][0]["content"]
    for text in ('"aggregate_consistency"', '"consistency"', '"operations":["sum"]', f"至多{MAX_REFERENCES}", "字符串数组"):
        assert text in prompt
    assert len(result["candidate_options"]) == 2 and len(model.calls) == 2
    if malformed:
        assert result["ai_suggestions_status"] == "incomplete" and not result["ai_suggestions"]
    else:
        assert [s["kind"] for s in result["ai_suggestions"]] == ["aggregate_consistency"]


def test_registered_but_generic_short_word_alone_cannot_construct_a_new_grain():
    first = warehouse_draft()
    first["semantic_intent"]["metrics"][0]["term"] = "余额"
    rules, model = warehouse([combined(first), first])
    set_field(rules, "balance", logic="业务别名：订单应收余额。")
    set_field(rules, "volume", logic="业务别名：包裹体积余额。", field_cn="余额")
    result = run(rules, "在途且优先级高于3的余额应大于0")
    assert len(model.calls) == 2
    assert "包裹体积余额" in model.calls[1]["messages"][0]["content"]
    assert result["preview"] and not result.get("candidate_options")
    assert result["table_name"] == "test_table" and result["expression"] == first["expression"]
    assert {(row["field"], row["op"], row["value"]) for row in result["filters"]} == {
        ("state", "eq", "Y"), ("priority", "gt", 3)}


def test_explicit_period_keeps_normal_evidence_review():
    fields = [*FIELDS, ("unit", "单笔耗量", "numeric", ""), ("total", "累计耗量", "numeric", ""),
              ("old", "期初耗量", "numeric", ""), ("state", "当前运输状态", "varchar", ""),
              ("prior", "原始运输状态", "varchar", "")]
    plans = [measure("unit", "单笔耗量"), measure("total", "累计耗量")]
    proposal = {"plans": plans, "plan_mode": "parallel"}
    rules, model = _rules_with_doc([combined(proposal), proposal, proposal], fields=fields)
    for name in ("state", "prior"):
        set_field(rules, name, dictionary="Y-在途\nN-到站")
    result = run(rules, "在途的耗量和期初耗量不应小于等于-7")
    assert len(model.calls) > 1
    assert result["uncertainties"] and not result.get("preview")


def valid_alternative(first):
    alt = deepcopy(first)
    alt.update(target={"table": "pieces"}, related_target={"table": "test_table"},
               join={"table_name": "test_table", "on": [{"left": "waybill", "right": "row_id"}],
                     "report_date_field": "business_day"})
    alt["expression"]["left"] = "volume"
    alt["semantic_intent"]["metrics"][0]["fields"] = ["volume"]
    for row in [*alt["semantic_intent"]["scopes"], *alt["filters"]]:
        row["table"] = "related"
    return alt


@pytest.mark.parametrize("date_key", ["account_day", "other_day"])
def test_same_period_join_key_is_redundant_but_another_date_is_a_real_condition(date_key):
    first = warehouse_draft()
    first["target"] = {"table": "test_table"}
    alt = valid_alternative(first)
    alt["join"]["on"].append({"left": date_key, "right": "business_day"})
    alt["join"].update(relationship_confirmed=True, unmatched_policy="exclude")
    first["business_key"], alt["business_key"] = "row_id", "piece_id"
    proposal = {"plans": [first, alt]}
    rules, model = warehouse([combined(proposal), proposal, {"ai_suggestions": []}],
                             extra_fields=[("other_day", "另一日期", "date", "")] if date_key == "other_day" else [])
    result = run(rules, "在途且优先级高于3的装载率应大于0")
    if date_key == "account_day":
        assert {option["candidate"]["table_name"] for option in result.get("candidate_options", [])} == {"test_table", "pieces"}
        assert all(option["candidate"]["preview"] and not option["candidate"]["questions"]
                   for option in result["candidate_options"])
        assert len(model.calls) <= 3 and "本轮只提出独立补充校验建议" in model.calls[-1]["messages"][0]["content"]
    else:
        assert not result.get("candidate_options") and result["uncertainties"]


@pytest.mark.parametrize("route", ["combined", "declared_targets", "selection_only", "reverse"])
@pytest.mark.parametrize("invalid", ["missing_scope", "wrong_key", "wrong_date", "nonzero", "unknown_category", "wrong_schema"])
def test_every_model_authored_grain_requires_its_own_scope_and_lineage(route, invalid):
    first = warehouse_draft()
    first["target"] = {"table": "test_table"}
    if invalid == "nonzero":
        first["expression"]["right"] = 9
    alt = valid_alternative(first)
    if invalid == "missing_scope":
        alt.pop("join")
        alt.pop("related_target")
        alt["filters"] = []
        alt["semantic_intent"]["scopes"] = []
    proposal = {"plans": [alt, first] if route == "reverse" else [first, alt]}
    selected = combined(proposal)
    if route in ("declared_targets", "selection_only"):
        selected["candidate_targets"] = [{"target": {"table": "pieces"}}]
    if route == "selection_only":
        selected.pop("draft")
    rules, _ = warehouse([selected, proposal], proof=invalid != "wrong_key")
    if invalid == "wrong_date":
        set_field(rules, "account_day", source_field="event_day")
    if invalid == "wrong_schema":
        set_field(rules, "waybill", source_table="foreign.test_table")
    if invalid == "unknown_category":
        with rules.storage.database.begin() as conn:
            conn.execute(update(DOC_TABLES).where(DOC_TABLES.c.table_name == "test_table").values(sheet_name="自营_运量"))
            conn.execute(update(DOC_TABLES).where(DOC_TABLES.c.table_name == "pieces").values(sheet_name="外派_件数"))
    result = run(rules, "在途且优先级高于3的装载率应大于" + str(first["expression"]["right"]))
    assert not result.get("preview") and not result.get("candidate_options") and result["uncertainties"]


@pytest.mark.parametrize("add_in_review", [False, True])
@pytest.mark.parametrize("date_key", ["account_day", "other_day"])
def test_document_expansion_preserves_equivalent_period_join_and_rejects_other_date(add_in_review, date_key):
    first = warehouse_draft()
    first["target"] = {"table": "test_table"}
    alt = valid_alternative(first)
    alt["join"].update(relationship_confirmed=True, unmatched_policy="exclude")
    first["business_key"], alt["business_key"] = "row_id", "piece_id"
    before = {"plans": [first, alt]}
    after = deepcopy(before)
    changed = after if add_in_review else before
    changed["plans"][1]["join"]["on"].insert(0, {"left": date_key, "right": "business_day"})
    original = deepcopy(after)
    rules, model = warehouse([{**combined(before), "expand_evidence": True}, after, {"ai_suggestions": []}],
                             extra_fields=[("other_day", "另一日期", "date", "")])
    result = run(rules, "在途且优先级高于3的装载率应大于0")
    assert after == original
    if date_key == "account_day" or not add_in_review:
        assert len(model.calls) == 3 and "本轮只提出独立补充校验建议" in model.calls[-1]["messages"][0]["content"]
        options = result.get("candidate_options", [])
        assert {option["candidate"]["table_name"] for option in options} == {"test_table", "pieces"}
        assert all(option["candidate"]["preview"] and not option["candidate"]["questions"] for option in options)
        detail = next(o["candidate"] for o in options if o["candidate"]["table_name"] == "pieces")
        assert detail["join"]["report_date_field"] == "business_day"
        assert detail["report_date_field"] == "account_day"
        assert all(key["left"] != "other_day" for key in detail["join"]["on"])
    else:
        assert len(model.calls) == 2
        assert not result.get("candidate_options") and result["uncertainties"]


@pytest.mark.parametrize("changed", ["filter", "extra_filter", "partition", "threshold", "null_policy"])
def test_review_preserves_user_conditions_and_can_revisit_unspecified_null_handling(changed):
    first = warehouse_draft()
    second = deepcopy(first)
    if changed == "filter":
        second["filters"] = []
    elif changed == "extra_filter":
        second["filters"].append({"field": "priority", "op": "lte", "value": 3})
    elif changed == "partition":
        second["semantic_intent"]["scopes"][0]["memberships"]["state"] = {"include": ["N"], "exclude": ["Y"]}
    elif changed == "threshold":
        second["expression"].update(op="gt", right=567)
    else:
        second["null_policy"] = "review"
    first_response = {**combined(first), "expand_evidence": True}
    fields = [*FIELDS, ("state", "运输状态", "varchar", ""), ("priority", "优先级", "numeric", "")]
    replies = [first_response, second, first] if changed == "partition" else [first_response, second]
    rules, model = _rules_with_doc(replies, fields=fields)
    set_field(rules, "state", dictionary="Y-在途\nN-到站")
    set_field(rules, "balance", logic="业务别名：装载率。")
    result = run(rules, "在途且优先级高于3的装载率应大于0")
    if not result.get("preview"):
        assert changed not in ("partition", "null_policy")
        assert result.get("uncertainties") or result.get("questions")
        return
    if changed == "partition":
        assert len(model.calls) == 3
    elif changed == "null_policy":
        assert result["null_policy"] == "review"
    assert result["expression"] == first["expression"]
    assert {(f["field"], f["op"], f["value"]) for f in result["filters"]} == {
        ("state", "eq", "Y"), ("priority", "gt", 3)}


@pytest.mark.parametrize("case", ["repair", "unregistered", "unit", "interval"])
def test_review_accepts_supported_threshold_interpretations(case):
    first = warehouse_draft()
    second = deepcopy(first)
    fields = [*FIELDS, ("state", "运输状态", "varchar", ""), ("priority", "优先级", "numeric", "")]
    request = "在途且优先级高于3的装载率应大于0"
    if case == "unit":
        request = "在途且优先级高于3的装载量应大于2万吨"
        first["expression"]["right"], second["expression"]["right"] = 2, 20000
        for plan in (first, second):
            plan["semantic_intent"]["metrics"][0]["term"] = "装载量"
    elif case == "interval":
        request = "在途且优先级高于3且低于8的装载率应大于0"
        second["filters"].append({"field": "priority", "op": "lt", "value": 8})
    elif case == "unregistered":
        # The model can correct a convenient label after reading the actual field definition.
        second["expression"]["right"] = 1
        request = "在途且优先级高于3的装载率应大于0（以修正值为准）"
    else:
        second["filters"] = []
    replies = [{**combined(first), "expand_evidence": True}, second]
    if case == "repair":
        replies.append(first)
    rules, model = _rules_with_doc(replies, fields=fields)
    set_field(rules, "state", dictionary="Y-在途\nN-到站")
    set_field(rules, "balance", logic=({"unit": "业务别名：装载量。单位：吨。", "unregistered": "按修正值减一记为装载率。"}
                                       .get(case, "业务别名：装载率。")))
    result = run(rules, request)
    assert bool(result["preview"]) and len(model.calls) == (3 if case == "repair" else 2)
    final = first if case == "repair" else second
    assert result["expression"] == final["expression"]
    assert ("priority", "gt", 3) in {(f["field"], f["op"], f["value"]) for f in result["filters"]}


@pytest.mark.parametrize("quote", ["numeric", "业务", "模拟余额", "仅建议使用原余额"])
def test_a_generic_exclusion_cannot_remove_a_user_named_metric_choice(quote):
    first = draft("balance")
    first["semantic_intent"]["metrics"][0]["term"] = "余额"
    first["semantic_intent"]["metrics"][0]["fields"] = ["balance", "sim"]
    reviewed = deepcopy(first)
    reviewed["semantic_intent"]["metrics"][0]["fields"] = ["balance"]
    reviewed["interpretation_exclusions"] = [{"id": "I2", "reason": "推荐使用原余额",
        "evidence": {"source": "document", "quote": quote}}]
    rules, _ = _rules_with_doc([{**combined(first), "expand_evidence": True}, reviewed],
                               fields=[*FIELDS, ("sim", "模拟余额", "numeric", "")])
    set_field(rules, "sim", logic="此列用于业务。仅建议使用原余额。")
    result = run(rules, "余额和模拟余额两种口径低于19都要核实")
    assert not result.get("preview") and "sim" in str(result["uncertainties"])


@pytest.mark.parametrize("shape", ["single", "combined_and", "later_and"])
def test_same_operand_name_on_another_table_does_not_inherit_a_previous_metric_choice(shape):
    from tests.modules.data_validation.support import user
    from tests.modules.data_validation.test_ai_service import _request, _select_payload
    from tests.modules.data_validation.test_exact_analysis_reuse import setup_rules, REQUEST
    from tests.modules.data_validation.test_shared_analysis_reuse import analyze

    rules, model = setup_rules()
    _add_table(rules, name="vehicles", cn="运输效率", dimension="车辆",
               fields=[("row_id", "记录编号", "varchar", "Y"), ("business_day", "数据日期", "date", ""),
                       ("amount", "燃油效率", "numeric", ""), ("spare", "机械效率", "numeric", "")])
    first = analyze(rules, user(), REQUEST, analysis_protocol=2)
    edited = {"table_name": "test_table", "expression": {"left": "amount", "op": "is_null"}, "filters": []}
    second = draft("amount")
    second["semantic_intent"]["metrics"][0]["term"] = "效率"
    selection = _select_payload(target={"table": "vehicles"}, reuse_decision="fresh")
    request = "运输效率低于19要核实"
    if shape != "single":
        request = "运输效率不得为空"
        second["expression"] = {"logic": "and", "conditions": [{"left": name, "op": "is_null"} for name in ("amount", "spare")]}
        second["semantic_intent"]["metrics"] = [{"side": "left", "term": term, "fields": [name]}
                                               for name, term in (("amount", "燃油效率"), ("spare", "机械效率"))]
        if shape == "combined_and":
            selection["draft"] = second
    reviewed = deepcopy(second)
    if shape == "single":
        reviewed["semantic_intent"]["metrics"][0]["fields"] = ["amount", "spare"]
    model.payloads.extend([selection, second, reviewed])
    result = rules.parse_rule_request(user(), _request(request_text=request, analysis_protocol=2,
                                                      revision_of=first["analysis_id"], revised_definition=edited))
    assert not result.get("preview")
    question, = result["questions"]
    assert {option["value"] for option in question["options"]} == {"amount", "spare"}
    assert result["table_name"] == "vehicles"


@pytest.mark.parametrize("typed", [
    "single_choice", "implicit_or", "explicit_or", "implicit_and", "implicit_all", "explicit_and",
    "uppercase_and", "op_all", "explicit_op_all", "wrapped_all", "explicit_wrapped_all",
])
def test_documented_peer_metrics_never_force_an_unrequested_combination(typed):
    names = ["unit", "total"]
    first = measure("unit", "耗量")
    first.update(expression={"left": "unit", "op": "is_null"}, null_policy="violate")
    metrics = first["semantic_intent"]["metrics"]
    if typed == "single_choice":
        metrics[0]["fields"] = names
    else:
        logic = "and" if typed.endswith("and") else "all" if typed.endswith("all") else "any"
        key = "op" if typed.endswith("op_all") else "logic"
        first["expression"] = {key: logic.upper() if typed == "uppercase_and" else logic,
                               "conditions": [{"left": f, "op": "is_null"} for f in names]}
        first["semantic_intent"]["open_questions"] = ["是否要求两项都非空，还是其中一项非空即可？"]
        first["semantic_intent"]["metrics"] = [{"side": "left", "fields": [f], "term": label}
                                              for f, label in zip(names, ["单笔耗量", "累计耗量"])]
    original = deepcopy(first)
    fields = [*FIELDS, ("unit", "单笔耗量", "numeric", ""), ("total", "累计耗量", "numeric", ""),
              ("old", "期初耗量", "numeric", ""), ("state", "当前运输状态", "varchar", ""),
              ("prior", "原始运输状态", "varchar", "")]
    reviewed = deepcopy(first)
    reviewed["semantic_intent"]["scopes"][0].update(fields=["state", "prior"], memberships={
        "state": {"include": ["Y"], "exclude": ["N"]}, "prior": {"include": ["Y"], "exclude": ["N"]}})
    wrapped = "wrapped" in typed
    rules, model = _rules_with_doc([combined({"plans": [first]} if wrapped else first),
                                    {"plans": [reviewed]} if wrapped else reviewed], fields=fields)
    for name in ("state", "prior"):
        set_field(rules, name, dictionary="Y-在途\nN-到站")
    text = {"explicit_or": "在途的单笔耗量或累计耗量任一项为空则提示",
            "explicit_and": "在途的单笔耗量和累计耗量全部为空才提示",
            "explicit_op_all": "在途的单笔耗量和累计耗量全部为空才提示",
            "explicit_wrapped_all": "在途的单笔耗量和累计耗量全部为空才提示"}.get(typed, "在途的耗量不得为空")
    result = run(rules, text)
    if typed.startswith("explicit"):
        normalized = {"conditions": original["expression"]["conditions"], "logic": "any" if typed == "explicit_or" else "all"}
        assert result["expression"] == normalized
    else:
        assert len(model.calls) == 1 and not result["preview"]
        assert result["expression"].get("op") == "is_null"
        ask = {q["id"]: q["options"] for q in result["questions"]}
        assert {o["selection"]["field"] for o in ask["filters.0"]} == {"state", "prior"}
        assert {o["value"] for o in ask["expression.left"]} == set(names)
    assert result["semantic_intent"]["open_questions"] == original["semantic_intent"]["open_questions"]
    assert set(original["semantic_intent"]["open_questions"]) <= set(result["uncertainties"])


@pytest.mark.parametrize("peers", [False, True])
def test_exact_positive_and_negative_category_labels_cannot_have_reversed_membership(peers):
    first = measure("balance", "耗量")
    first["semantic_intent"]["scopes"] = [scope(term="温控型")]
    repaired = deepcopy(first)
    repaired["semantic_intent"]["scopes"][0]["memberships"]["state"] = {"include": ["N"], "exclude": ["Y"]}
    fields = [*FIELDS, ("state", "当前运输方式", "varchar", "")]
    if peers:
        fields.append(("prior", "原始运输方式", "varchar", ""))
    rules, _ = _rules_with_doc([combined(first), repaired], fields=fields)
    for name in ("state", "prior"):
        set_field(rules, name, dictionary="Y-非温控型\nN-温控型")
    try:
        result = run(rules, "温控型的耗量不应小于等于-7")
    except Exception as exc:
        assert getattr(exc, "code", None) == "MODEL_RESPONSE_INVALID"
        return
    assert all(f["value"] != "Y" for f in result.get("filters", []))
    for q in result.get("questions", []):
        assert all(o.get("selection", {}).get("value") != "Y" for o in q["options"] if isinstance(o.get("selection"), dict))


def test_independent_request_on_same_table_cannot_mask_another_known_grain():
    first = warehouse_draft()
    second = draft("priority")
    second["semantic_intent"]["metrics"][0]["term"] = "优先级"
    rules, _ = warehouse([combined({"plan_mode": "parallel", "plans": [first, second]})])
    result = run(rules, "在途且优先级高于3的装载率应大于0，同时核实优先级低于2的记录")
    assert not result.get("preview") and not result.get("candidate_options")
    assert "pieces.volume" in str(result["uncertainties"])


@pytest.mark.parametrize(("dictionary", "category", "included", "valid"), [
    ("1-温控型\n2-非温控型", "温控型", ["1", "2"], False),
    ("1-温控型\n2-其他", "温控型", ["2"], False),
    ("1-温控型\n2-非温控型", "温控型或非温控型", ["1", "2"], True),
])
def test_dictionary_binding_preserves_exact_and_compound_category_meanings(dictionary, category, included, valid):
    from auto_check.modules.data_validation.semantic_grounding import _roles, _scope_options, _Unbound

    field = {"field_name": "state", "field_cn": "运输状态", "data_type": "varchar", "dictionary": dictionary}
    classification = {"category": category, "fields": ["state"], "memberships": {"state": {
        "include": included, "exclude": list({"1", "2"} - set(included))}}}
    if valid:
        assert _scope_options(classification, _roles([field], []), {})[0]["selection"]["value"] == included
    else:
        with pytest.raises(_Unbound):
            _scope_options(classification, _roles([field], []), {})
