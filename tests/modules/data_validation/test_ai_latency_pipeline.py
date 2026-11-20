"""Cold semantic analysis against compact authorized document evidence."""
from copy import deepcopy
import json

import pytest
from sqlalchemy import update

from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.storage import DOC_FIELDS
from tests.modules.data_validation.support import user
from tests.modules.data_validation.test_ai_service import _request, _rules_with_doc, _select_payload
from tests.modules.data_validation.test_semantic_generation import FIELDS, draft


def run(rules, text):
    return rules.parse_rule_request(user(), _request(request_text=text, analysis_protocol=2))


def combined(proposal):
    return {**_select_payload(), "draft": proposal}


def test_semantic_calls_use_low_reasoning_with_a_bounded_complete_result(monkeypatch):
    rules, model = _rules_with_doc([combined(draft())], fields=FIELDS)
    received = []

    def detailed(model_id, messages, *, options, **kwargs):
        received.append(dict(options))
        return {"content": model.complete(model_id, messages, **kwargs), "finish_reason": "stop"}

    monkeypatch.setattr(model, "complete_with_options", detailed, raising=False)
    result = rules.parse_rule_request(user(), _request(request_text="份额低于19要复核", analysis_protocol=2, reasoning_enabled=True))

    assert result["preview"] and result["expression"] == {"left": "amount", "op": "lt", "right_type": "value", "right": 19}
    assert received == [{"reasoning_effort": "low", "max_tokens": 3072, "temperature": 0}]


@pytest.mark.parametrize("mode", [None, False, True])
def test_reasoning_switch_controls_calls_and_analysis_context(mode):
    rules, model = _rules_with_doc([combined(draft())], fields=FIELDS)
    payload = _request(request_text="份额低于19要复核", analysis_protocol=2)
    if mode is not None:
        payload["reasoning_enabled"] = mode
    result = rules.parse_rule_request(user(), payload)
    assert result["preview"]
    assert result["reasoning_enabled"] is (mode is True)
    assert model.calls[-1]["options"] == {
        "reasoning_effort": "low" if mode is True else "none", "max_tokens": 3072, "temperature": 0,
    }
    opposite = rules.parse_rule_request(user(), {**payload, "reasoning_enabled": mode is not True})
    assert opposite["analysis_context"] != result["analysis_context"]
    assert not opposite.get("analysis_reused")
    assert model.calls[-1]["options"]["reasoning_effort"] == ("none" if mode is True else "low")


@pytest.mark.parametrize("mode", ["false", 0, None, [], {}])
def test_reasoning_switch_rejects_non_boolean_values(mode):
    rules, model = _rules_with_doc([combined(draft())], fields=FIELDS)
    with pytest.raises(AppError) as exc:
        rules.parse_rule_request(user(), _request(analysis_protocol=2, reasoning_enabled=mode))
    assert exc.value.code == "VALIDATION_ERROR"
    assert not model.calls


@pytest.mark.parametrize("mode", [False, True])
def test_preview_keeps_the_analysis_reasoning_mode(monkeypatch, mode):
    rules, model = _rules_with_doc([combined(draft())], fields=FIELDS)
    request = _request(request_text="份额低于19要复核", analysis_protocol=2, reasoning_enabled=mode)
    original = rules.parse_rule_request(user(), request)
    monkeypatch.setattr(rules.analyses, "completed_result", lambda *_: original)
    payload = {"definition": original, "analysis_id": "completed", "analysis_context": original["analysis_context"],
               "model_id": request["model_id"], "analysis_request_text": request["request_text"], "reasoning_enabled": mode}
    preview = rules.preview_candidate(user(), payload, return_questions=True)
    assert preview["sql_preview"]
    with pytest.raises(AppError, match="ANALYSIS_CONTEXT_CHANGED"):
        rules.preview_candidate(user(), {**payload, "reasoning_enabled": not mode}, return_questions=True)
    assert len(model.calls) == 1


def test_call_policy_change_invalidates_a_reusable_analysis(monkeypatch):
    from auto_check.modules.data_validation import prompt_defaults

    rules, model = _rules_with_doc([combined(draft())], fields=FIELDS)
    first = run(rules, "份额低于19要复核")
    assert first["preview"] and len(model.calls) == 1

    monkeypatch.setitem(prompt_defaults.SEMANTIC_CALL_OPTIONS, "max_tokens", 4096)
    repeated = run(rules, "份额低于19要复核")

    assert repeated["preview"] and len(model.calls) == 2
    assert not repeated.get("analysis_reused")


def test_invalid_json_has_a_traceable_safe_failure_category(caplog):
    rules, model = _rules_with_doc(['private invalid response'], fields=FIELDS)
    with pytest.raises(AppError) as error:
        run(rules, '份额低于19要复核')
    assert error.value.code == 'MODEL_RESPONSE_INVALID'
    assert error.value.reference in caplog.text
    assert 'category=invalid_json_object' in caplog.text
    assert 'analysis=' in caplog.text and 'round=1' in caplog.text
    assert 'private invalid response' not in caplog.text


def test_initial_broken_json_gets_one_bounded_fresh_retry_before_rule_publication(monkeypatch):
    malformed = '{"target":{"{"table":"test_table"}'
    proposal = draft()
    rules, model = _rules_with_doc([malformed, combined(proposal)], fields=FIELDS)
    def raw_response(_model_id, messages, **_kwargs):
        model.calls.append({'messages': messages})
        return malformed if len(model.calls) == 1 else json.dumps(combined(proposal), ensure_ascii=False)
    monkeypatch.setattr(model, 'complete', raw_response)

    result = run(rules, '份额低于19要复核')

    assert len(model.calls) == 2
    assert result['preview'] and result['expression'] == proposal['expression']
    assert malformed not in model.calls[1]['messages'][0]['content']


def test_initial_broken_json_retry_is_not_an_unbounded_repair_loop():
    rules, model = _rules_with_doc(['broken json', 'broken again', combined(draft())], fields=FIELDS)
    with pytest.raises(AppError, match='MODEL_RESPONSE_INVALID'):
        run(rules, '份额低于19要复核')
    assert len(model.calls) == 2


@pytest.mark.parametrize('container', ['array_tail', 'second_object_tail', 'prefix_text', 'duplicate_key'])
def test_incomplete_json_containers_cannot_publish_a_cropped_rule(monkeypatch, container):
    body = json.dumps(combined(draft()), ensure_ascii=False)
    invalid = {'array_tail': '[' + body + ',', 'second_object_tail': body + ' {"target":',
               'prefix_text': 'partial reply ' + body,
               'duplicate_key': body[:-1] + ',"draft":' + json.dumps(draft('balance')) + '}'}[container]
    rules, model = _rules_with_doc([], fields=FIELDS)
    def response(_model_id, messages, **_kwargs):
        model.calls.append({'messages': messages})
        return invalid
    monkeypatch.setattr(model, 'complete', response)
    with pytest.raises(AppError, match='MODEL_RESPONSE_INVALID'):
        run(rules, '份额低于19要复核')
    assert len(model.calls) == 2


def test_a_single_complete_json_fence_keeps_the_normal_one_call_path(monkeypatch):
    rules, model = _rules_with_doc([], fields=FIELDS)
    def response(_model_id, messages, **_kwargs):
        model.calls.append({'messages': messages})
        return '```json\n' + json.dumps(combined(draft())) + '\n```'
    monkeypatch.setattr(model, 'complete', response)
    assert run(rules, '份额低于19要复核')['preview']
    assert len(model.calls) == 1


def test_combined_cold_analysis_keeps_documented_tail_and_scope_and_exact_replay():
    noise = [(f"noise_{i}", f"备注{i}", "varchar", "") for i in range(24)]
    fields = [*FIELDS, *noise, ("original", "原始交付状态", "varchar", ""), ("current", "当前交付状态", "varchar", "")]
    proposal = draft("balance")
    partition = {"include": ["23"], "exclude": [str(i) for i in range(23)]}
    proposal["semantic_intent"]["scopes"] = [{
        "category": "延期", "fields": ["original", "current"],
        "memberships": {"original": partition, "current": partition},
    }]
    rules, model = _rules_with_doc([combined(proposal)], fields=fields)
    with rules.storage.database.begin() as conn:
        dictionary = "\n".join([*(f"{i}-类别{i}" for i in range(23)), "23-延期"])
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name.in_(("original", "current"))).values(dictionary=dictionary))
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name.like("noise%")).values(logic="未命中的无关完整取数描述"))
    request = "交付状态为延期时，余额低于19要复核"
    result = run(rules, request)
    assert len(model.calls) == 1
    prompt = model.calls[0]["messages"][0]["content"]
    assert prompt.count(dictionary.replace("\n", "\\n")) == 1
    assert "备注23" in prompt and "未命中的无关完整取数描述" not in prompt
    assert {o["selection"]["field"] for o in result["questions"][0]["options"]} == {"original", "current"}
    assert result["expression"] == {"left": "balance", "op": "lt", "right": 19, "right_type": "value"}
    assert run(rules, request)["memory_decision"] == "exact" and len(model.calls) == 1


def test_unexpanded_paraphrase_field_requires_a_full_document_turn_before_publication():
    fields = [*FIELDS, *((f"padding{i}", f"备注{i}", "varchar", "") for i in range(24)),
              ("tail", "历史余额", "numeric", "")]
    proposal = draft("tail")
    rules, model = _rules_with_doc([combined(proposal), proposal], fields=fields)
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "tail").values(logic="实际取数基于留存台账"))
    result = run(rules, "看看当初还剩多少，跌破19要报错")
    prompts = [item["messages"][0]["content"] for item in model.calls]
    assert len(prompts) == 2
    assert "历史余额" in prompts[0] and "实际取数基于留存台账" not in prompts[0]
    assert "实际取数基于留存台账" in prompts[1] and result["preview"]["definition"]["expression"]["left"] == "tail"


@pytest.mark.parametrize("extra", [False, True])
def test_structural_repair_only_fills_missing_intent_and_never_changes_scope(extra):
    base = draft()
    incomplete = deepcopy(base)
    del incomplete["semantic_intent"]
    repair = {"patch": {"semantic_intent": base["semantic_intent"]}}
    if extra:
        repair["patch"]["filters"] = [{"field": "amount", "op": "gt", "value": 42}]
    rules, model = _rules_with_doc([_select_payload(), incomplete, repair], fields=FIELDS)
    if extra:
        with pytest.raises(AppError, match="MODEL_RESPONSE_INVALID"):
            run(rules, "份额低于19要复核")
    else:
        result = run(rules, "份额低于19要复核")
        assert result["preview"] and not result["filters"] and result["expression"] == base["expression"]
    prompts = [item["messages"][0]["content"] for item in model.calls]
    assert len(prompts) == 3 and "patch" in prompts[2] and len(prompts[2]) < len(prompts[1])


def test_truncation_even_after_a_complete_json_object_cannot_publish(monkeypatch):
    rules, model = _rules_with_doc([combined(draft())], fields=FIELDS)
    attempts = []
    def detailed(model_id, messages, *, options, **kwargs):
        attempts.append(options)
        return {"content": model.complete(model_id, messages, **kwargs), "finish_reason": "length", "usage": {}}
    monkeypatch.setattr(model, "complete_with_options", detailed, raising=False)
    with pytest.raises(AppError, match="MODEL_OUTPUT_LIMIT"):
        run(rules, "份额低于19要复核")
    assert attempts

@pytest.mark.parametrize("omit_right_role", [False, True])
def test_combined_dual_table_verifies_both_keys_dates_and_aggregation(omit_right_role):
    from tests.modules.data_validation.test_followup_service_bridge import _add_table

    related = {"table": "settlements"}
    check = draft("balance")
    check.update(expression={"left": "balance", "op": "neq", "right_type": "field",
                             "right_table": "related", "right": "portion"},
                 join={"table_name": "settlements", "on": [{"left": "row_id", "right": "foreign_id"}],
                       "report_date_field": "cutoff", "right_aggregate": "sum", "unmatched_policy": "unresolved"})
    check["semantic_intent"]["metrics"].append({"side": "right", "term": "明细本金", "fields": ["portion"]})
    if omit_right_role:
        del check["expression"]["right_table"]
    rules, model = _rules_with_doc([{**combined(check), "related_target": related}], fields=FIELDS)
    _add_table(rules, name="settlements", cn="明细账", dimension="交易",
               fields=[("foreign_id", "业务编号", "varchar", "Y"), ("cutoff", "数据日期", "date", ""),
                       ("part_id", "明细序号", "varchar", "Y"), ("portion", "明细本金", "numeric", "")])
    with rules.storage.database.begin() as conn:
        for child, origin in (("foreign_id", "row_id"), ("cutoff", "business_day")):
            conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == child).values(
                source_table="test_table", source_field=origin, logic="直取"))
    result = run(rules, "按业务编号核对同数据日期的余额与明细本金之和是否一致")
    assert len(model.calls) == 1
    assert '"source_table":"test_table"' in model.calls[0]["messages"][0]["content"]
    assert result["business_key"] == "row_id" and result["report_date_field"] == "business_day"
    assert result["join"]["on"] == [{"left": "row_id", "right": "foreign_id"}]
    assert result["join"]["report_date_field"] == "cutoff" and result["join"]["right_aggregate"] == "sum"
    assert result["expression"] == {**check["expression"], "right_table": "related"}


@pytest.mark.parametrize("bad", [{"metrics": 7}, {"scopes": 7}])
def test_malformed_combined_response_does_not_crash_the_job(bad):
    complete = draft()
    malformed = deepcopy(complete)
    malformed["semantic_intent"].update(bad)
    missing_key = next(iter(bad))
    rules, model = _rules_with_doc([combined(malformed), {"patch": {
        missing_key: complete["semantic_intent"][missing_key]}}], fields=FIELDS)
    result = run(rules, "份额低于19")
    assert result["preview"] and len(model.calls) == 2


def test_invalid_dictionary_repair_cannot_silently_add_or_remove_an_existing_filter():
    fields = [*FIELDS, ("flag", "交付状态", "varchar", "")]
    incomplete = draft("balance")
    incomplete["filters"] = [{"table": "base", "field": "amount", "op": "gt", "value": 2}]
    incomplete["semantic_intent"]["scopes"] = [{"category": "延期", "fields": ["flag"],
        "memberships": {"flag": {"include": ["Y"], "exclude": []}}}]
    patched = deepcopy(incomplete)
    patched.pop("filters")
    patched["semantic_intent"]["scopes"][0]["memberships"]["flag"]["exclude"] = ["N"]
    rules, model = _rules_with_doc([_select_payload(), incomplete, patched], fields=fields)
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "flag").values(dictionary="Y-延期\nN-按期"))
    with pytest.raises(AppError, match="MODEL_RESPONSE_INVALID"):
        run(rules, "份额超过2且交付延期时余额不得低于19")
    assert len(model.calls) == 3

def test_shared_document_boilerplate_does_not_expand_irrelevant_physical_details():
    fields = [*FIELDS, *((f"notes{i}", f"交付附记{i}", "varchar", "") for i in range(40)),
              ("flag", "交付结算方式", "varchar", "")]
    check = draft("balance")
    check["semantic_intent"]["scopes"] = [{"category": "预付", "fields": ["flag"],
        "memberships": {"flag": {"include": ["1"], "exclude": ["2"]}}}]
    rules, model = _rules_with_doc([combined(check)], fields=fields)
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name.like("notes%")).values(
            logic="本交付项目的报送基础说明，已从登记簿直取", source_field="irrelevant_trace"))
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "flag").values(dictionary="1-预付\n2-后付"))
    result = run(rules, "交付结算方式为预付的余额低于19要核实")
    prompt = model.calls[0]["messages"][0]["content"]
    assert result["preview"] and len(model.calls) == 1 and "交付附记39" in prompt
    assert prompt.count("irrelevant_trace") < 5


def test_opt_in_strategy_identity_participates_in_results_and_memory_fingerprints(monkeypatch):
    from auto_check.modules.data_validation import prompt_defaults
    rules, _ = _rules_with_doc([], fields=FIELDS)
    req = _request(analysis_protocol=2)
    old = rules._analysis_inputs(user(), req)["context"]
    assert "检索策略" in prompt_defaults.SEMANTIC_SELECTION_CONTRACT
    monkeypatch.setattr(prompt_defaults, "SEMANTIC_SELECTION_CONTRACT", "不同检索和调用配置")
    assert rules._analysis_inputs(user(), req)["context"]["prompt_fingerprint"] != old["prompt_fingerprint"]

def test_compact_directory_preserves_shared_columns_and_detailed_ambiguous_report_dates():
    from auto_check.modules.data_validation.document_evidence import DocumentEvidence, compact_directory
    fields = [{"field_name": f"remark_{i}", "field_cn": f"备注{i}", "data_type": "varchar"} for i in range(13)]
    fields += [{"field_name": "period_a", "field_cn": "数据日期", "data_type": "date"},
               {"field_name": "period_b", "field_cn": "报送日期", "data_type": "date"}]
    tables = [{"id": i, "table_name": f"t{i}", "table_name_cn": label} for i, label in enumerate(["订单", "收款"], 1)]
    index = DocumentEvidence(tables, {1: fields, 2: fields}, "检查订单的份额")
    catalog = compact_directory([index.describe(t) for t in tables])
    assert {row[0] for row in catalog["tables"][0]["fields"]} >= {"period_a", "period_b"}
    assert any(indices == [1, 2] and "备注12" in names for indices, names in catalog["common_directory"])

def test_repairing_an_unknown_metric_cannot_change_the_requested_numeric_boundary():
    corrupted = draft()
    corrupted["semantic_intent"]["metrics"][0]["fields"].append("undocumented")
    changed = draft()
    changed["expression"]["right"] = 200
    rules, _ = _rules_with_doc([_select_payload(), corrupted, changed], fields=FIELDS)
    with pytest.raises(AppError, match="MODEL_RESPONSE_INVALID"):
        run(rules, "份额低于19要复核")


def test_clarification_cannot_publish_unverified_metric_or_scope():
    raw = {"rule_type": None, "expression": {}, "semantic_intent": {"metrics": [
        {"term": "结算额", "side": "left", "fields": ["fabricated"]}],
        "scopes": [], "open_questions": ["请确认选用哪一项口径。"]}}
    rules, _ = _rules_with_doc([_select_payload(), raw, raw], fields=FIELDS)
    with pytest.raises(AppError, match="MODEL_RESPONSE_INVALID"):
        run(rules, "结算额请核实")


def test_diagnostics_preserve_public_error_stage_and_exclude_provider_content(monkeypatch, caplog):
    import logging

    rules, model = _rules_with_doc([], fields=FIELDS)
    def detailed(*args, **kwargs):
        return {"content": "PRIVATE_RESPONSE", "finish_reason": "length",
                "usage": {"completion_tokens": 28, "remote_url": "PRIVATE_ADDRESS"}}
    monkeypatch.setattr(model, "complete_with_options", detailed, raising=False)
    with caplog.at_level(logging.INFO, logger="auto_check.modules.data_validation"):
        with pytest.raises(AppError) as error:
            run(rules, "PRIVATE_REQUEST")
    assert error.value.stage == "generate_rule"
    assert "stage=select_and_generate" in caplog.text and "'completion_tokens': 28" in caplog.text
    assert "PRIVATE" not in caplog.text

def test_well_formed_unwrapped_draft_uses_the_unique_authorized_physical_binding():
    from tests.modules.data_validation.test_followup_service_bridge import _add_table
    check = draft()
    rules, model = _rules_with_doc([check], fields=FIELDS)
    _add_table(rules, name="other", cn="日历", dimension="序号",
               fields=[("row_id", "编号", "varchar", "Y"), ("date_2", "数据日期", "date", "")])
    result = run(rules, "测试表的份额低于19")
    assert len(model.calls) == 1 and result["table_name"] == "test_table" and result["preview"]
    assert result["expression"] == check["expression"]


def test_unwrapped_draft_with_overlapping_identifiers_asks_only_for_documented_target():
    from tests.modules.data_validation.test_followup_service_bridge import _add_table
    check = draft()
    rules, model = _rules_with_doc([check, _select_payload(draft_matches=True), check], fields=FIELDS)
    _add_table(rules, name="other", cn="历史账", dimension="合同", fields=FIELDS)
    _add_table(rules, name="unrelated", cn="资料登记册", dimension="笔",
               fields=[("doc_key", "文档编号", "varchar", "Y"), ("memo", "文档备注", "varchar", "")])
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "memo").values(logic="无关长文档" * 300))
    result = run(rules, "测试表的份额低于19")
    assert len(model.calls) == 2 and result["table_name"] == "test_table"
    narrow = model.calls[1]["messages"][0]["content"]
    assert "other" in narrow and "test_table" in narrow and "draft_matches" in narrow
    assert "无关长文档" not in narrow and "unrelated" not in narrow

def test_dictionary_partition_patch_uses_only_its_documented_candidates():
    fields = [*FIELDS, ("flag", "交付状态", "varchar", ""), ("notes", "附记", "varchar", "")]
    base = draft("balance")
    base["semantic_intent"]["scopes"] = [{"category": "延期", "fields": ["flag"],
        "memberships": {"flag": {"include": ["Y"], "exclude": []}}}]
    repair = {"patch": {"memberships": {"flag": {"include": ["Y"], "exclude": ["N"]}}}}
    rules, model = _rules_with_doc([_select_payload(), base, repair], fields=fields)
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "flag").values(dictionary="Y-延期\nN-按期"))
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "notes").values(logic="无关字段的长说明" * 150))
    result = run(rules, "交付延期时余额不得低于19")
    prompt = model.calls[-1]["messages"][0]["content"]
    assert "semantic_intent.scopes.0.memberships" in prompt and "N-按期" in prompt
    assert "无关字段的长说明" not in prompt and len(model.calls) == 3
    assert result["preview"] and result["filters"][0]["value"] == "Y"

@pytest.mark.parametrize("change", ["left", "right", "right_type", "plan_mode", "metadata_patch"])
def test_review_repair_freezes_valid_operands_and_repairs_only_bad_metadata(change):
    field = "amount"
    before = draft(field)
    before["rule_name"] = []
    if change in ("right", "right_type"):
        before["expression"] = {"left": field, "right": "balance", "right_type": "field", "op": "lt"}
        before["semantic_intent"]["metrics"].append({"side": "right", "term": "余额", "fields": ["balance"]})
    after = deepcopy(before)
    after["rule_name"] = "金额核查"
    if change == "left":
        after["expression"]["left"] = "balance"
        after["semantic_intent"]["metrics"][0]["fields"] = ["balance"]
    elif change == "right":
        after["expression"]["right"] = "amount"
        after["semantic_intent"]["metrics"][1]["fields"] = ["amount"]
    elif change == "right_type":
        after["expression"].update(right=19, right_type="value")
        after["semantic_intent"]["metrics"].pop()
    elif change == "plan_mode":
        before = {"plans": [before], "plan_mode": "alternatives"}
        after = {"plans": [after], "plan_mode": "parallel"}
    else:
        after = {"patch": {"rule_name": "金额核查"}}
    rules, _ = _rules_with_doc([_select_payload(), before, after], fields=FIELDS)
    if change == "metadata_patch":
        assert run(rules, "份额低于19")["rule_name"] == "金额核查"
    else:
        with pytest.raises(AppError, match="MODEL_RESPONSE_INVALID"):
            run(rules, "份额低于19")


@pytest.mark.parametrize("response", [
    {"candidate_targets": [{"table": "calendar"}]},
    {"candidate_targets": [{"target": {"table": "test_table"}, "related_target": {"table": "calendar"}}]},
])
def test_review_table_only_correction_limits_all_candidate_only_and_related_documents(response):
    from tests.modules.data_validation.test_followup_service_bridge import _add_table
    rules, model = _rules_with_doc([draft(), response, draft("unrelated_numeric")], fields=FIELDS)
    _add_table(rules, name="other", cn="历史账", dimension="合同", fields=FIELDS)
    _add_table(rules, name="calendar", cn="日历", dimension="日期", fields=[
        ("id", "序号", "varchar", "Y"), ("day", "数据日期", "date", ""), ("unrelated_numeric", "天数", "numeric", "")])
    with pytest.raises(AppError, match="MODEL_RESPONSE_INVALID"):
        run(rules, "份额低于19")
    assert len(model.calls) == 2


def test_review_missing_target_does_not_discard_requested_evidence_expansion():
    rules, model = _rules_with_doc([{"draft": draft(), "expand_evidence": True}, draft()], fields=FIELDS)
    assert run(rules, "份额低于19")["preview"]
    assert len(model.calls) == 2


@pytest.mark.parametrize("fact_key", ["source_desc", "scope", "period"])
def test_review_table_level_meaning_selects_and_expands_the_right_table(fact_key):
    from auto_check.modules.data_validation.storage import DOC_TABLES
    from tests.modules.data_validation.test_followup_service_bridge import _add_table
    fields = [*FIELDS, *((f"note{i}", f"附记{i}", "varchar", "") for i in range(16))]
    rules, model = _rules_with_doc([{"uncertainties": ["需看表级适用范围"]}, _select_payload(target={"table": "other"}), draft()],
                                   fields=fields)
    _add_table(rules, name="other", cn="历史账", dimension="合同", fields=fields)
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_TABLES).where(DOC_TABLES.c.table_name == "other").values(
            **{fact_key: "Wholesale records only."}))
        other_id = conn.execute(DOC_TABLES.select().where(DOC_TABLES.c.table_name == "other")).mappings().one()["id"]
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.table_id == other_id, DOC_FIELDS.c.field_name == "note15")
                     .values(logic="未展开的期间条款取数说明"))
    assert run(rules, "wholesale records below 19")["preview"]
    prompts = [c["messages"][0]["content"] for c in model.calls]
    assert "Wholesale records only" in prompts[0] and "Wholesale records only" in prompts[1]
    assert "未展开的期间条款取数说明" not in prompts[0] and "未展开的期间条款取数说明" in prompts[1]


@pytest.mark.parametrize("patch_form", [True, False])
def test_review_unknown_scope_column_can_be_renamed_without_changing_the_dictionary_partition(patch_form):
    fields = [*FIELDS, ("transfer", "是否转让", "varchar", "")]
    broken = draft()
    codes = {"include": ["1"], "exclude": ["0"]}
    broken["semantic_intent"]["scopes"] = [{"category": "已转让", "fields": ["not_a_field"],
        "memberships": {"not_a_field": codes}}]
    corrected = deepcopy(broken)
    corrected["semantic_intent"]["scopes"][0].update(fields=["transfer"], memberships={"transfer": codes})
    repair = {"patch": {"field": "transfer"}} if patch_form else corrected
    rules, model = _rules_with_doc([_select_payload(), broken, repair], fields=fields)
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "transfer").values(dictionary="1-是\n0-否"))
    result = run(rules, "已转让的份额低于19")
    assert result["preview"] and result["filters"][0]["field"] == "transfer" and result["filters"][0]["value"] == "1"
    assert len(model.calls) == 3

@pytest.mark.parametrize("change_role", [False, True])
def test_full_repair_can_replace_unknown_operand_but_cannot_move_valid_peer_to_related_table(change_role):
    from tests.modules.data_validation.test_followup_service_bridge import _add_table
    raw = draft("missing")
    raw["expression"] = {"left": "missing", "op": "lt", "right": "balance", "right_type": "field"}
    raw["semantic_intent"]["metrics"].append({"term": "余额", "side": "right", "fields": ["balance"]})
    raw["join"] = {"table_name": "other", "on": [{"left": "row_id", "right": "row_id"}],
                   "report_date_field": "business_day", "unmatched_policy": "unresolved"}
    repaired = deepcopy(raw)
    repaired["expression"]["left"] = "amount"
    repaired["semantic_intent"]["metrics"][0]["fields"] = ["amount"]
    if change_role:
        repaired["expression"]["right_table"] = "related"
    rules, _ = _rules_with_doc([_select_payload(related_target={"table": "other"}), raw, repaired], fields=FIELDS)
    _add_table(rules, name="other", cn="历史账", dimension="合同", fields=FIELDS)
    if change_role:
        with pytest.raises(AppError, match="MODEL_RESPONSE_INVALID"):
            run(rules, "比较两项指标")
    else:
        result = run(rules, "比较两项指标")
        assert result["expression"]["left"] == "amount" and result["expression"]["right"] == "balance"
        assert result["expression"].get("right_table", "base") == "base"


def test_atomic_scope_rename_preserves_all_previously_valid_memberships_and_options():
    fields = [*FIELDS, ("current", "当前状态", "varchar", ""), ("origin", "原始状态", "varchar", "")]
    invalid = draft()
    codes = {"include": ["1"], "exclude": ["0"]}
    invalid["semantic_intent"]["scopes"] = [{"category": "启动", "fields": ["current", "unknown"], "recommended": "current",
        "memberships": {"current": codes, "unknown": codes}}]
    repaired = deepcopy(invalid)
    repaired["semantic_intent"]["scopes"][0].update(fields=["current", "origin"],
        memberships={"current": {"include": ["0"], "exclude": ["1"]}, "origin": codes})
    rules, _ = _rules_with_doc([_select_payload(), invalid, repaired], fields=fields)
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name.in_(["current", "origin"])).values(dictionary="1-是\n0-否"))
    with pytest.raises(AppError, match="MODEL_RESPONSE_INVALID"):
        run(rules, "核实启动的份额低于19")


@pytest.mark.parametrize("repaired_value", [19, 20])
def test_missing_constant_operand_type_can_only_be_completed_with_its_original_value(repaired_value):
    raw = draft()
    del raw["expression"]["right_type"]
    fixed = deepcopy(raw)
    fixed["expression"].update(right_type="value", right=repaired_value)
    rules, model = _rules_with_doc([_select_payload(), raw, fixed], fields=FIELDS)
    if repaired_value == 19:
        result = run(rules, "份额低于19要复核")
        assert result["preview"] and result["expression"] == fixed["expression"]
    else:
        with pytest.raises(AppError, match="MODEL_RESPONSE_INVALID"):
            run(rules, "份额低于19要复核")
    assert len(model.calls) == 3


def _scope_join_fixture(*, expanded=True):
    from auto_check.modules.data_validation.storage import DOC_TABLES
    from tests.modules.data_validation.test_followup_service_bridge import _add_table

    check = draft("balance")
    check["join"] = {"table_name": "projects", "on": [{"left": "row_id", "right": "foreign_id"}],
                     "report_date_field": "cutoff", "unmatched_policy": "unresolved"}
    check["semantic_intent"]["scopes"] = [{"table": "related", "category": "已交付", "fields": ["flag"],
        "memberships": {"flag": {"include": ["1"], "exclude": ["2"]}}}]
    selection = combined(check)
    rules, model = _rules_with_doc([selection, check], fields=FIELDS)
    related_fields = [("foreign_id", "业务编号", "varchar", "Y"), ("cutoff", "数据日期", "date", ""),
                      ("flag", "交付标识" if expanded else "归档状态", "varchar", "")]
    _add_table(rules, name="projects", cn="项目表", dimension="项目", fields=related_fields)
    with rules.storage.database.begin() as conn:
        table_id = conn.execute(DOC_TABLES.select().where(DOC_TABLES.c.table_name == "projects")).mappings().one()["id"]
        conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.table_id == table_id, DOC_FIELDS.c.field_name == "flag")
                     .values(dictionary="1-是\n2-否", logic="按已核实登记记录取值"))
        for child, origin in (("foreign_id", "row_id"), ("cutoff", "business_day")):
            conn.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.table_id == table_id, DOC_FIELDS.c.field_name == child)
                         .values(source_table="test_table", source_field=origin, logic="直取"))
    return rules, model, selection


def _scope_join_analysis(rules):
    from auto_check.modules.data_validation.document_evidence import DocumentEvidence
    from auto_check.modules.data_validation.semantic_generation import SemanticAnalysis

    request = _request(request_text="交付标识为是的余额低于19", analysis_protocol=2)
    inputs = rules._analysis_inputs(user(), request)
    analysis = SemanticAnalysis(rules, user(), inputs, request["request_text"], None, None)
    analysis.index = DocumentEvidence(analysis.tables, analysis.fields, analysis.request)
    return analysis


def test_explicit_authorized_join_supplies_omitted_related_target_without_regeneration():
    rules, model, selection = _scope_join_fixture()
    original = deepcopy(selection)
    result = run(rules, "交付标识为是的余额低于19")
    assert len(model.calls) == 1 and not result.get("preview_error")
    assert {q["id"] for q in result["questions"]} == {"join.relationship_confirmed", "join.unmatched_policy"}
    assert result["table_name"] == "test_table"
    assert result["expression"] == {"left": "balance", "op": "lt", "right_type": "value", "right": 19}
    assert result["join"]["table_name"] == "projects"
    assert result["join"]["on"] == [{"left": "row_id", "right": "foreign_id"}]
    assert result["filters"] == [{"table": "related", "field": "flag", "op": "eq", "value": "1", "confirmed": True}]
    assert selection == original
    preview = rules.preview_candidate(user(), {
        **result, "name": result["rule_name"], "questions": [],
        "join": {**result["join"], "relationship_confirmed": True, "unmatched_policy": "exclude"},
    }, return_questions=True)
    assert preview["sql_preview"] and 'o."flag" = :filter_1' in preview["sql_preview"]
    assert preview["sql_params"]["filter_1"] == "1" and preview["sql_params"]["right_value"] == 19


@pytest.mark.parametrize("problem", ["unknown", "other_source", "ambiguous", "category", "conflict", "plans", "candidates"])
def test_missing_related_target_binding_never_guesses_or_overwrites_declared_choices(problem):
    from auto_check.modules.data_validation.storage import DOC_TABLES
    from tests.modules.data_validation.test_followup_service_bridge import _add_table

    rules, _, selection = _scope_join_fixture()
    if problem == "unknown":
        selection["draft"]["join"]["table_name"] = "not_documented"
    elif problem == "other_source":
        with rules.storage.database.begin() as conn:
            conn.execute(update(DOC_TABLES).where(DOC_TABLES.c.table_name == "projects").values(data_source_name="监管报表"))
    elif problem == "ambiguous":
        _add_table(rules, name="projects", cn="另一项目表", dimension="项目", fields=FIELDS)
    elif problem == "category":
        with rules.storage.database.begin() as conn:
            conn.execute(update(DOC_TABLES).where(DOC_TABLES.c.table_name == "projects").values(sheet_name="East5报送_项目表"))
    elif problem == "conflict":
        selection["related_target"] = {"table": "different_declared_table"}
    elif problem == "plans":
        selection["draft"] = {"plans": [selection["draft"]]}
    else:
        selection["candidate_targets"] = [{"table": "test_table"}]
    before = deepcopy(selection)
    analysis = _scope_join_analysis(rules)
    assert analysis.bind_missing_related_target(selection) == before
    assert selection == before


def test_combined_readiness_requires_declared_related_document_for_related_references():
    rules, _, selection = _scope_join_fixture()
    analysis = _scope_join_analysis(rules)
    docs = analysis.documents([selection])
    assert not analysis.ready_for_combined(selection, selection["draft"], docs)


def test_inferred_join_still_expands_missing_related_field_evidence_before_publication():
    rules, model, _ = _scope_join_fixture(expanded=False)
    result = run(rules, "某类账户的余额低于19")
    assert len(model.calls) == 2 and not result.get("preview_error")
    assert {q["id"] for q in result["questions"]} == {"join.relationship_confirmed", "join.unmatched_policy"}
    prompts = [c["messages"][0]["content"] for c in model.calls]
    assert "按已核实登记记录取值" not in prompts[0] and "按已核实登记记录取值" in prompts[1]
    assert result["filters"][0]["field"] == "flag" and result["expression"]["right"] == 19


def test_independent_open_question_keeps_complete_referenced_evidence_without_regeneration():
    fields = [*FIELDS, *((f"note_{i}", f"业务附记{i}", "varchar", "") for i in range(20))]
    check = draft("balance")
    question = "按每条明细余额检查，还是按项目余额合计检查？"
    check["semantic_intent"]["open_questions"] = [question]
    rules, model = _rules_with_doc([combined(check), check], fields=fields)
    result = run(rules, "余额低于19时核查")
    assert len(model.calls) == 1
    assert result["expression"] == {"left": "balance", "op": "lt", "right_type": "value", "right": 19}
    assert result["semantic_intent"]["open_questions"] == [question]
    assert question in result["uncertainties"] and not result["preview"] and not result["can_enable"]


def test_documented_base_operand_object_keeps_two_table_questions_in_the_first_response():
    rules, model, selection = _scope_join_fixture()
    selection["related_target"] = {"table": "projects"}
    selection["draft"]["expression"]["left"] = {"table": "base", "field": "balance"}
    questions = ["余额按每条明细还是按项目合计检查？", "余额缺失是否需要独立核查？"]
    selection["draft"]["semantic_intent"]["open_questions"] = questions
    original = deepcopy(selection)
    model.payloads = [selection]
    result = run(rules, "交付标识为是的余额低于19")
    assert len(model.calls) == 1 and not result.get("preview_error")
    assert result["expression"] == {"left": "balance", "op": "lt", "right_type": "value", "right": 19}
    assert result["semantic_intent"]["open_questions"] == questions
    assert set(questions) <= set(result["uncertainties"])
    assert result["filters"][0]["field"] == "flag" and result["filters"][0]["table"] == "related"
    assert not result["preview"] and not result["can_enable"] and selection == original


@pytest.mark.parametrize("operand", [
    {"table": "related", "field": "balance"}, {"table": "base", "field": "unknown"},
    {"table": "base", "field": "balance", "extra": "ignored"}, {"field": "balance"},
])
def test_operand_object_normalization_cannot_guess_role_field_or_extra_keys(operand):
    check = draft("balance")
    check["expression"]["left"] = operand
    rules, _ = _rules_with_doc([combined(check), check], fields=FIELDS)
    with pytest.raises(AppError, match="MODEL_RESPONSE_INVALID"):
        run(rules, "余额低于19")


@pytest.mark.parametrize("expansion", ["explicit", "unsupported"])
def test_open_questions_keep_explicit_expansion_and_unsupported_evidence_gates(expansion):
    fields = [*FIELDS, *((f"note_{i}", f"业务附记{i}", "varchar", "") for i in range(20))]
    check = draft("balance")
    check["semantic_intent"]["open_questions"] = ["按每条还是合计检查？"]
    selection = combined(check)
    if expansion == "explicit":
        selection["expand_evidence"] = True
    else:
        check["unsupported_requirements"] = ["仍需核对未展开文档中的汇总口径"]
    rules, model = _rules_with_doc([selection, check], fields=fields)
    result = run(rules, "余额低于19")
    assert len(model.calls) == 2 and not result["preview"] and not result["can_enable"]


@pytest.mark.parametrize("replacement", ["balance", "amount"])
def test_full_repair_preserves_a_documented_object_operand(replacement):
    raw = draft("balance")
    raw["expression"]["left"] = {"table": "base", "field": "balance"}
    raw["semantic_intent"]["metrics"][0]["side"] = "right"
    repaired = draft(replacement)
    rules, model = _rules_with_doc([combined(raw), repaired], fields=FIELDS)
    if replacement == "balance":
        result = run(rules, "余额低于19")
        assert result["preview"] and result["expression"]["left"] == "balance"
    else:
        with pytest.raises(AppError, match="MODEL_RESPONSE_INVALID"):
            run(rules, "余额低于19")
    assert len(model.calls) == 2
    assert raw["expression"]["left"] == {"table": "base", "field": "balance"}


@pytest.mark.parametrize("replacement", ["cutoff", "business_day"])
def test_full_repair_preserves_an_implicitly_bound_related_operand(replacement):
    rules, model, selection = _scope_join_fixture()
    selection["related_target"] = {"table": "projects"}
    raw = selection["draft"]
    raw["expression"] = {"left": "unknown", "op": "lt", "right_type": "field", "right": "cutoff"}
    raw["semantic_intent"]["metrics"] = [{"side": "left", "term": "日期", "fields": ["unknown"]},
        {"side": "right", "term": "对照日", "fields": ["cutoff"]}]
    repaired = deepcopy(raw)
    repaired["expression"].update(left="business_day", right=replacement)
    repaired["semantic_intent"]["metrics"][0]["fields"] = ["business_day"]
    repaired["semantic_intent"]["metrics"][1]["fields"] = [replacement]
    model.payloads = [selection, raw, repaired]
    if replacement == "cutoff":
        result = run(rules, "交付标识为是时比较日期")
        assert result["expression"]["right"] == "cutoff" and result["expression"]["right_table"] == "related"
    else:
        with pytest.raises(AppError, match="MODEL_RESPONSE_INVALID"):
            run(rules, "交付标识为是时比较日期")


def test_nested_category_constraint_blocks_inferred_cross_category_join():
    from auto_check.modules.data_validation.storage import DOC_TABLES
    rules, model, selection = _scope_join_fixture()
    selection["target"]["report_category"] = selection.pop("report_category")
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_TABLES).where(DOC_TABLES.c.table_name == "test_table").values(sheet_name="人行_测试表"))
        conn.execute(update(DOC_TABLES).where(DOC_TABLES.c.table_name == "projects").values(sheet_name="East5报送_项目表"))
    model.payloads = [selection]
    with pytest.raises(AppError, match="MODEL_RESPONSE_INVALID"):
        run(rules, "交付标识为是的余额低于19")


def test_draft_category_is_preserved_when_binding_homonymous_related_documents():
    from auto_check.modules.data_validation.storage import DOC_TABLES
    from tests.modules.data_validation.test_followup_service_bridge import _add_table
    rules, model, selection = _scope_join_fixture()
    selection["draft"]["report_category"] = selection.pop("report_category")
    with rules.storage.database.begin() as conn:
        conn.execute(update(DOC_TABLES).values(sheet_name="人行_测试表"))
    _add_table(rules, name="projects", cn="East5项目表", dimension="项目", fields=FIELDS)
    with rules.storage.database.begin() as conn:
        rows = conn.execute(DOC_TABLES.select().where(DOC_TABLES.c.table_name == "projects")).mappings().all()
        extra = max(rows, key=lambda row: row["id"])
        conn.execute(update(DOC_TABLES).where(DOC_TABLES.c.id == extra["id"]).values(sheet_name="East5报送_项目表"))
    model.payloads = [selection]
    result = run(rules, "交付标识为是的余额低于19")
    assert len(model.calls) == 1 and result["report_category"] == "group:pbc"
    assert result["join"]["table_name"] == "projects" and result["filters"][0]["field"] == "flag"
