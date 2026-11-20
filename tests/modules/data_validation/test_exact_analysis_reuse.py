from copy import deepcopy
from types import SimpleNamespace
import threading

import pytest
from sqlalchemy import create_engine, update

from auto_check.modules.data_validation.analysis_jobs import AnalysisCancelled
from auto_check.modules.data_validation.service import DataValidationService
from auto_check.modules.data_validation.storage import DOC_FIELDS, METADATA, RuleStorage
from tests.modules.data_validation.support import SequenceModel, user
from tests.modules.data_validation.test_ai_service import SourceOnlyMetadata, _Processes, _request, _rules_with_doc, _select_payload
from tests.modules.data_validation.test_semantic_generation import FIELDS, draft
from tests.modules.data_validation.test_shared_analysis_reuse import analyze


REQUEST = "净值型项目，净值不得为空"


def setup_rules(*, open_question=False, parallel=False):
    proposal = draft()
    proposal.update(rule_name="净值型项目净值非空校验", expression={"left": "amount", "op": "is_null"}, null_policy="violate")
    proposal["semantic_intent"] = {
        "metrics": [{"side": "left", "term": "净值", "fields": ["amount", "balance"], "recommended": "amount"}],
        "scopes": [{"category": "净值型", "fields": ["phase", "orig"], "recommended": "phase",
                    "memberships": {field: {"include": ["1"], "exclude": ["2"]} for field in ("phase", "orig")}}],
        "open_questions": ["是否沿用月末业务日期？"] if open_question else [],
    }
    raw = {"plan_mode": "parallel", "plans": [proposal, draft()]} if parallel else proposal
    rules, model = _rules_with_doc([_select_payload(), raw], fields=[*FIELDS,
        ("phase", "当前运行方式", "varchar", ""), ("orig", "原始运行方式", "varchar", "")])
    with rules.storage.database.begin() as connection:
        connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name.in_(["phase", "orig"]))
                           .values(dictionary="1-净值型\n2-非净值型"))
    return rules, model


@pytest.mark.parametrize("other_user", [False, True])
def test_exact_repeat_uses_no_model_and_keeps_unanswered_choices(other_user):
    rules, model = setup_rules()
    first = analyze(rules, user(), REQUEST, analysis_protocol=2)
    assert {q["id"] for q in first["result"]["questions"]} == {"expression.left", "filters.0"}
    model.error = AssertionError("相同请求不得调用模型")
    repeated = analyze(rules, user("other") if other_user else user(), REQUEST, analysis_protocol=2)
    result = repeated["result"]
    assert len(model.calls) == 2
    assert result["analysis_reused"] and result["memory_decision"] == "exact"
    assert result["questions"] == first["result"]["questions"]
    assert result["uncertainties"] == first["result"]["uncertainties"]
    assert result["uncertainty_resolutions"] == [""] * len(result["uncertainties"])
    assert result["preview"] is None and not result["filters"][0]["confirmed"]
    assert result["verification_status"] == "not_run"
    assert repeated["analysis_id"] != first["analysis_id"]


def test_replay_survives_a_new_service_and_retains_independent_questions_and_plans():
    rules, model = setup_rules(open_question=True, parallel=True)
    first = rules.parse_rule_request(user(), _request(request_text=REQUEST, analysis_protocol=2))
    new_model = SequenceModel([], error=AssertionError("新实例应复用应用库中的分析"))
    fresh = DataValidationService(RuleStorage(rules.storage.database), rules.metadata, new_model, rules.report_navigation)
    result = fresh.parse_rule_request(user("new"), _request(request_text=REQUEST, analysis_protocol=2))
    assert not new_model.calls and result["analysis_reused"]
    assert len(result["candidate_options"]) == 2
    assert [o["candidate"]["questions"] for o in result["candidate_options"]] == [
        o["candidate"]["questions"] for o in first["candidate_options"]]
    assert "是否沿用月末业务日期？" in result["uncertainties"]
    assert all(o["candidate"]["preview"] is None for o in result["candidate_options"])


def test_result_is_reusable_after_database_reopen(tmp_path):
    from tests.modules.data_validation.support import doc_xlsx_bytes

    url = "sqlite:///" + (tmp_path / "analysis.sqlite").as_posix()
    engine = create_engine(url)
    METADATA.create_all(engine)
    model = SequenceModel([_select_payload(), draft()])
    first = DataValidationService(RuleStorage(engine), SourceOnlyMetadata(), model, _Processes())
    first.import_document(user("admin", "admin"), "document.xlsx", doc_xlsx_bytes(fields=FIELDS))
    request = _request(request_text="份额低于19", analysis_protocol=2)
    original = first.parse_rule_request(user(), request)
    engine.dispose()
    reopened = create_engine(url)
    blocked_model = SequenceModel([], error=AssertionError("持久化结果应可直接复用"))
    second = DataValidationService(RuleStorage(reopened), SourceOnlyMetadata(), blocked_model, _Processes())
    try:
        result = second.parse_rule_request(user("other"), request)
        assert result["expression"] == original["expression"] and not blocked_model.calls
        assert result["preview"]["content_sha256"] == original["preview"]["content_sha256"]
        assert all(case["status"] == "not_run" for case in result["preview"]["cases"])
    finally:
        reopened.dispose()


def test_replay_recomputes_current_users_duplicates_and_keeps_only_model_structure():
    proposed = draft()
    proposed["sql"] = "SELECT ignored_model_sql"
    rules, model = _rules_with_doc([_select_payload(), proposed], fields=FIELDS)
    request = _request(request_text="份额低于19", analysis_protocol=2)
    first = rules.parse_rule_request(user(), request)
    saved = rules.save_draft(user(), first["preview"]["definition"])
    model.error = AssertionError("直接复用时无需调用模型")
    own = rules.parse_rule_request(user(), request)
    other = rules.parse_rule_request(user("other"), request)
    assert own["duplicate"]["kind"] == "exact" and other["duplicate"]["kind"] == "none" and len(model.calls) == 2
    response = rules.storage.cached_analysis_result(rules._analysis_inputs(user(), request)["context"], request["request_text"])
    assert "ignored_model_sql" not in str(response) and "sql_preview" not in str(response)
    assert saved["rule_code"] not in str(response)


def test_confirming_one_analysis_does_not_clear_choices_in_the_cached_original():
    rules, model = setup_rules()
    first = rules.parse_rule_request(user(), _request(request_text=REQUEST, analysis_protocol=2))
    chosen = {**deepcopy(first), "expression": {"left": "balance", "op": "is_null"},
              "questions": [], "uncertainty_resolutions": ["用户已选择"] * len(first["uncertainties"]),
              "filters": [{"table": "base", "field": "orig", "op": "eq", "value": "1", "confirmed": True}]}
    preview = rules.preview_candidate(user(), chosen, return_questions=True)
    assert preview["sql_preview"]
    model.error = AssertionError("不能重新调用模型")
    repeated = rules.parse_rule_request(user(), _request(request_text=REQUEST, analysis_protocol=2))
    assert repeated["questions"] == first["questions"] and repeated["preview"] is None
    assert not repeated["filters"][0]["confirmed"] and len(model.calls) == 2


@pytest.mark.parametrize("text", [REQUEST, REQUEST + "，例如 select amount"])
def test_explicitly_submitted_new_choices_take_precedence_without_replacing_shared_cache(text):
    rules, model = setup_rules()
    first = analyze(rules, user(), text, analysis_protocol=2)
    original = first["result"]
    context = rules._analysis_inputs(user(), _request(request_text=text, analysis_protocol=2))["context"]
    shared_before = rules.storage.find_analysis_memories(context, text)
    chosen_filter = {"table": "base", "field": "orig", "op": "eq", "value": "1", "confirmed": True}
    edited = {**deepcopy(original), "expression": {"left": "balance", "op": "is_null"}, "filters": [chosen_filter]}
    revised = draft("balance")
    revised.update(expression=edited["expression"], null_policy="violate")
    revised["semantic_intent"] = {
        "metrics": [{"side": "left", "term": "净值", "fields": ["balance"]}],
        "scopes": [{"category": "净值型", "fields": ["orig"], "excluded_fields": {"phase": "用户已明确选用原始运行方式。"},
                    "memberships": {"orig": {"include": ["1"], "exclude": ["2"]}}}], "open_questions": [],
    }
    if text == REQUEST:
        model.payloads.append({**_select_payload(), "reuse_decision": "adapt", "memory_index": 0, "draft": revised})
    else:
        model.payloads.extend([_select_payload(), revised])
    result = analyze(rules, user(), text, analysis_protocol=2, revision_of=first["analysis_id"],
                     revised_definition=edited)["result"]
    count = 3 if text == REQUEST else 4
    assert len(model.calls) == count and result["expression"]["left"] == "balance"
    assert "balance" in model.calls[-1]["messages"][0]["content"]
    assert result.get("memory_decision") != "exact"
    assert rules.storage.find_analysis_memories(context, text) == shared_before
    model.error = AssertionError("新用户仍应看到缓存中的原始选项")
    repeated = rules.parse_rule_request(user("other"), _request(request_text=text, analysis_protocol=2))
    assert repeated["questions"] == original["questions"] and len(model.calls) == count


@pytest.mark.parametrize("response", [
    {"selection": {"target": {"table": "missing"}}},
    {"selection": _select_payload(), "draft": None},
    {"selection": _select_payload(), "draft": []},
])
def test_invalid_cached_structure_falls_back_and_is_replaced_by_valid_analysis(response):
    rules, model = setup_rules()
    request = _request(request_text=REQUEST, analysis_protocol=2)
    rules.parse_rule_request(user(), request)
    context = rules._analysis_inputs(user(), request)["context"]
    rules.storage.remember_analysis_result(context, REQUEST, response)
    model.payloads.extend([_select_payload(), draft()])
    result = rules.parse_rule_request(user(), request)
    assert len(model.calls) > 2 and result.get("memory_decision") != "exact"
    count = len(model.calls)
    model.error = AssertionError("修复缓存后的重复请求无需模型")
    assert rules.parse_rule_request(user(), request)["memory_decision"] == "exact"
    assert len(model.calls) == count


@pytest.mark.parametrize("change", ["text", "spacing", "model", "model_configuration", "prompt", "dictionary", "source_rules", "category", "knowledge"])
def test_request_or_evidence_change_invalidates_the_exact_result(change):
    rules, model = setup_rules()
    public_model = SimpleNamespace(id="model-1", name="模型", model_name="model", is_default=True, configuration_fingerprint="old")
    model.list_enabled = lambda: [public_model]
    rules.parse_rule_request(user(), _request(request_text=REQUEST, analysis_protocol=2))
    payload = _request(request_text=REQUEST, analysis_protocol=2)
    if change == "text":
        payload["request_text"] = "净值型项目，净值不得为零"
    elif change == "spacing":
        payload["request_text"] = "净值型项目，净值 不得为空"
    elif change == "model":
        payload["model_id"] = "another-model"
    elif change == "model_configuration":
        public_model.configuration_fingerprint = "new"
    elif change == "prompt":
        rules.save_prompt(user("admin", "admin"), "business_scope", "统一按月末核对。")
    elif change == "dictionary":
        with rules.storage.database.begin() as connection:
            connection.execute(update(DOC_FIELDS).where(DOC_FIELDS.c.field_name == "phase").values(dictionary="1-净值型\n2-其他类型"))
    elif change == "source_rules":
        rules.list_source_rules = lambda: [{"sheet_prefix": "新增前缀", "data_source_name": "监管报表"}]
    elif change == "category":
        processes = list(rules.report_navigation.list_report_processes())
        processes.append(SimpleNamespace(code="new", name="新分类", active=True))
        rules.report_navigation = SimpleNamespace(list_report_processes=lambda: processes)
    else:
        knowledge = rules.knowledge
        entry = dict(knowledge.settings()["draft"][0], keywords=["新的非匹配主题"])
        knowledge.save(user("admin", "admin"), {"expected_revision": 0, "entries": [entry]})
        knowledge.save(user("admin", "admin"), {"expected_revision": 1, "enabled": True}, activation=True)
    model.payloads.extend([_select_payload(), draft()])
    result = rules.parse_rule_request(user(), payload)
    assert len(model.calls) > 2 and result.get("memory_decision") != "exact"


def test_cancellation_after_generation_does_not_publish_a_reusable_result(monkeypatch):
    rules, model = setup_rules()
    cancelled = threading.Event()
    original = rules._analysis_inputs
    visits = 0

    def inputs(*args):
        nonlocal visits
        visits += 1
        result = original(*args)
        if visits == 2:
            cancelled.set()
        return result

    monkeypatch.setattr(rules, "_analysis_inputs", inputs)
    with pytest.raises(AnalysisCancelled):
        rules.parse_rule_request(user(), _request(request_text=REQUEST, analysis_protocol=2), cancel_event=cancelled)
    monkeypatch.setattr(rules, "_analysis_inputs", original)
    model.payloads.extend([_select_payload(), draft()])
    result = rules.parse_rule_request(user(), _request(request_text=REQUEST, analysis_protocol=2))
    assert len(model.calls) > 2 and result.get("memory_decision") != "exact"


@pytest.mark.parametrize("action", ["fail", "cancel"])
def test_failed_or_cancelled_audit_does_not_publish_cache(monkeypatch, action):
    rules, model = setup_rules()
    cancelled = threading.Event()
    memories = []

    def audit(**_kwargs):
        if action == "fail":
            raise RuntimeError("模拟审计失败")
        cancelled.set()

    with monkeypatch.context() as probe:
        probe.setattr(rules.storage, "audit", audit)
        probe.setattr(rules.storage, "remember_analysis_memory", lambda *args: memories.append(args))
        with pytest.raises(RuntimeError if action == "fail" else AnalysisCancelled):
            rules.parse_rule_request(user(), _request(request_text=REQUEST, analysis_protocol=2), cancel_event=cancelled)
    assert not memories
    model.payloads.extend([_select_payload(), draft()])
    result = rules.parse_rule_request(user(), _request(request_text=REQUEST, analysis_protocol=2))
    assert len(model.calls) > 2 and result.get("memory_decision") != "exact"


def test_model_timeout_does_not_retry_while_configuration_changes(monkeypatch):
    from auto_check.modules.data_validation.contracts import AppError

    rules, _ = setup_rules()
    original = rules._analysis_inputs
    calls = []

    def inputs(*args):
        result = original(*args)
        result["context"]["test_revision"] = len(calls)
        return result

    def timeout(*args, **kwargs):
        calls.append(1)
        raise AppError("MODEL_TIMEOUT")

    monkeypatch.setattr(rules, "_analysis_inputs", inputs)
    monkeypatch.setattr(rules, "_analyze_request", timeout)
    with pytest.raises(AppError) as error:
        rules.parse_rule_request(user(), _request(request_text=REQUEST, analysis_protocol=2))
    assert error.value.code == "MODEL_TIMEOUT" and len(calls) == 1


def test_failed_exact_result_insert_rolls_back_shared_memory_and_exact_result():
    from sqlalchemy import event

    rules, _model = setup_rules()
    payload = _request(request_text=REQUEST, analysis_protocol=2)
    context = rules._analysis_inputs(user(), payload)["context"]
    engine = rules.storage.database.engine

    def fail_after_result_insert(conn, cursor, statement, params, execution, many):
        if statement.startswith("INSERT INTO data_validation_analysis_results"):
            raise RuntimeError("模拟精确缓存写入故障")

    event.listen(engine, "after_cursor_execute", fail_after_result_insert)
    try:
        analysis = rules.start_analysis(user(), payload)
        rules.analyses.join(3)
        finished = rules.get_analysis(user(), analysis["analysis_id"])
        assert finished["status"] == "failed" and "result" not in finished
    finally:
        event.remove(engine, "after_cursor_execute", fail_after_result_insert)
        rules.analyses.close()
    assert rules.storage.find_analysis_memories(context, REQUEST) == []
    assert rules.storage.cached_analysis_result(context, REQUEST) is None


def test_job_completion_and_cache_publication_share_the_cancellation_boundary(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor, TimeoutError

    rules, model = setup_rules()
    writing = threading.Event()
    release = threading.Event()
    cancelling = threading.Event()
    original = rules.storage.remember_analysis_result

    def remember(*args):
        writing.set()
        assert release.wait(2)
        original(*args)

    monkeypatch.setattr(rules.storage, "remember_analysis_result", remember)
    owner = user()
    job = rules.start_analysis(owner, _request(request_text=REQUEST, analysis_protocol=2))
    try:
        assert writing.wait(2)
        with ThreadPoolExecutor() as pool:
            def cancel():
                cancelling.set()
                return rules.cancel_analysis(owner, job["analysis_id"])
            future = pool.submit(cancel)
            assert cancelling.wait(1)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.05)
            release.set()
            assert future.result(timeout=2)["status"] == "completed"
        rules.analyses.join()
        assert rules.get_analysis(owner, job["analysis_id"])["status"] == "completed"
    finally:
        release.set()
        rules.analyses.join()


def test_cache_projects_unused_nested_fields_and_preserves_select_clarification():
    proposed = draft()
    proposed["ai_suggestions"] = [{"ignored": "discarded-suggestion-text"}]
    selection = _select_payload()
    selection["target"]["sql"] = "discarded-target-text"
    rules, model = _rules_with_doc([selection, proposed], fields=FIELDS)
    request = _request(request_text="份额低于19", analysis_protocol=2)
    first = rules.parse_rule_request(user(), request)
    context = rules._analysis_inputs(user(), request)["context"]
    snapshot = rules.storage.cached_analysis_result(context, request["request_text"])
    assert "discarded-" not in str(snapshot)
    model.error = AssertionError("同需求直接复用")
    result = rules.parse_rule_request(user(), request)
    assert result["ai_suggestions"] == first["ai_suggestions"]
    unclear, model = _rules_with_doc([{"table": "test_table", "uncertainties": ["需要补充具体检查要求。"]}], fields=FIELDS)
    first = unclear.parse_rule_request(user(), request)
    model.error = AssertionError("待补充要求也应直接复用")
    repeated = unclear.parse_rule_request(user(), request)
    assert repeated["model_judgments"] == first["model_judgments"]
    assert repeated["uncertainties"] == first["uncertainties"]


@pytest.mark.parametrize("clarify", [False, True])
def test_replay_preserves_plan_identity_and_hash_when_model_adds_unused_metadata(clarify):
    proposed = draft()
    proposed["semantic_intent"]["metrics"][0]["explanation"] = "模型附加的说明"
    second_plan = draft("balance")
    second_plan["semantic_intent"]["metrics"][0]["explanation"] = "另一个字段的说明"
    if clarify:
        second_plan.update(rule_type=None, expression={})
        second_plan["semantic_intent"]["open_questions"] = ["请明确本项校验要求。"]
    raw = {"plans": [proposed, second_plan], "semantic_intent": {"metrics": None}}
    rules, model = _rules_with_doc([_select_payload(), raw], fields=FIELDS)
    request = _request(request_text="份额低于19", analysis_protocol=2)
    first = rules.parse_rule_request(user(), request)
    model.error = AssertionError("同一方案直接复用")
    second = rules.parse_rule_request(user(), request)
    assert [o["id"] for o in first["candidate_options"]] == [o["id"] for o in second["candidate_options"]]
    assert [(o["candidate"]["preview"] or {}).get("content_sha256") for o in first["candidate_options"]] == [
        (o["candidate"]["preview"] or {}).get("content_sha256") for o in second["candidate_options"]]


def test_publication_does_not_block_other_users_jobs():
    from concurrent.futures import ThreadPoolExecutor
    from auto_check.modules.data_validation.analysis_jobs import AnalysisRegistry

    writing = threading.Event()
    release = threading.Event()
    registry = AnalysisRegistry()

    def worker(owner, payload, progress, cancel_event):
        result = {"name": owner["id"]}
        if owner["id"] == "writer":
            def publish():
                writing.set()
                assert release.wait(2)
            registry.publish_result(cancel_event, result, publish)
        return result

    registry.worker = worker
    registry.start(user("writer"), {})
    try:
        assert writing.wait(2)
        with ThreadPoolExecutor() as pool:
            another = pool.submit(registry.start, user("another"), {}).result(timeout=1)
            assert pool.submit(registry.get, user("another"), another["analysis_id"]).result(timeout=1)
    finally:
        release.set()
        registry.close()
