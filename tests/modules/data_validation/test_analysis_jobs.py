"""内存临时分析任务回归：真实进度、取消、隔离、边界与兼容。"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from auto_check.app.module_system.contracts import ModuleRequest
from auto_check.app.module_system.permissions import default_permission_evaluator
from auto_check.app.module_system.routing import ModuleRouter
from auto_check.modules.data_validation.analysis_jobs import AnalysisRegistry
from auto_check.modules.data_validation.api import register_routes
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.model_calls import semantic_completion
from auto_check.modules.data_validation.module import MANIFEST
from tests.modules.data_validation.support import (
    Metadata, SequenceModel, doc_xlsx_bytes, service, user,
)
from tests.modules.data_validation.test_ai_service import (
    _generate_payload, _request, _rules_with_doc, _select_payload,
)
from tests.modules.data_validation.test_query_generation import FIELDS, make_rules


def _wait_until(predicate, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def _without_elapsed(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in snapshot.items() if key != "elapsed_ms"}


def _blocking_worker(
    gate: threading.Event, stages: list[str], terminal_event: dict[str, Any] | None = None,
    *, wait_timeout: float | None = 2.0,
):
    def worker(current_user, payload, progress, cancel_event):
        stages.append("start")
        progress({"step": "semantics", "status": "completed", "detail": "已完成初步业务对象匹配，具体条件待规则草稿确认"})
        if terminal_event is not None:
            terminal_event["semantics"] = True
        gate.wait(wait_timeout)
        progress({"step": "generation", "status": "running", "detail": "正在生成规则草稿与本地结构校验"})
        stages.append("generation")
        return {"rule_name": "不应出现的迟到结果"}

    return worker


# ---------------------------------------------------------------------------
# 真实回调推进，而不是时间推进
# ---------------------------------------------------------------------------


def test_snapshot_does_not_advance_with_time_until_worker_reports() -> None:
    gate = threading.Event()
    stages: list[str] = []
    registry = AnalysisRegistry(worker=_blocking_worker(gate, stages), max_concurrent=2)
    first = user("1")
    snapshot = registry.start(first, {})

    assert snapshot["status"] == "running"
    assert snapshot["steps"][0] == {"id": "semantics", "status": "running", "detail": "正在解析业务语义与选表范围"}
    assert _wait_until(lambda: registry.get(first, snapshot["analysis_id"])["steps"][0]["status"] == "completed")
    # 回调已经汇报第一步后，状态不再随时间自行推进（elapsed_ms 只在读取时增长）。
    reference = registry.get(first, snapshot["analysis_id"])
    time.sleep(0.05)
    again = registry.get(first, snapshot["analysis_id"])
    assert _without_elapsed(again) == _without_elapsed(reference)
    assert again["steps"][0]["status"] == "completed"

    gate.set()
    assert _wait_until(lambda: registry.get(first, snapshot["analysis_id"])["status"] == "completed")
    done = registry.get(first, snapshot["analysis_id"])
    assert [step["status"] for step in done["steps"]] == ["completed", "pending", "completed"]
    assert done["result"] == {"rule_name": "不应出现的迟到结果"}
    assert "error" not in done
    registry.join(2.0)


def test_real_parse_emits_only_observed_metadata_and_keeps_generation_terminal() -> None:
    rules, model = make_rules(related=True)
    events: list[dict[str, Any]] = []
    candidate = rules.parse_rule_request(
        user(), _request(request_text="存续项目实收信托一般不为0"), progress=events.append,
    )

    assert len(model.calls) == 2
    assert events[0]["step"] == "semantics" and events[0]["status"] == "running"

    semantics_done = [event for event in events if event["step"] == "semantics" and event["status"] == "completed"]
    assert len(semantics_done) == 1
    assert semantics_done[0]["detail"] == "已完成初步业务对象匹配，具体条件待规则草稿确认"
    # 第一次纯选表阶段不得虚构表名/字段数或判断条件。
    assert all("table_name" not in event and "field_count" not in event for event in events if event["step"] == "semantics")

    metadata_done = [event for event in events if event["step"] == "metadata" and event["status"] == "completed"]
    assert len(metadata_done) == 1
    assert metadata_done[0]["table_name"] == candidate["table_name"]
    assert metadata_done[0]["field_count"] == len(candidate["columns"])
    assert metadata_done[0]["related_table_name"] == "state_table"

    generation = [event for event in events if event["step"] == "generation"]
    assert generation[0]["status"] == "running"
    assert generation[-1]["status"] in {"completed", "needs_confirmation"}
    assert candidate["table_name"]


def test_select_clarification_finishes_with_pending_steps_and_no_second_model_call() -> None:
    selection = {"target": {"table": "test_table"}, "result_type": "clarification", "uncertainties": ["多个对象需核对"]}
    rules, model = _rules_with_doc([selection], fields=FIELDS)
    events: list[dict[str, Any]] = []

    snapshot = rules.start_analysis(user(), _request())
    assert _wait_until(lambda: rules.get_analysis(user(), snapshot["analysis_id"])["status"] != "running")
    done = rules.get_analysis(user(), snapshot["analysis_id"])

    assert len(model.calls) == 1
    assert done["status"] == "completed"
    assert done["result"]["status"] == "needs_clarification"
    assert [step["status"] for step in done["steps"]] == ["needs_confirmation", "pending", "pending"]
    assert [event["step"] for event in events] == []  # 未传 progress，不影响同步解析
    rules.analyses.join(2.0)

    direct = rules.parse_rule_request(user(), _request(), progress=events.append)
    assert direct["status"] == "needs_clarification"
    assert len(model.calls) == 2  # 直接解析仍只调用一次选表模型
    assert [event["step"] for event in events] == ["semantics", "semantics"]
    assert events[0]["status"] == "running" and events[1]["status"] == "needs_confirmation"


# ---------------------------------------------------------------------------
# 取消与失败
# ---------------------------------------------------------------------------


def test_cancel_marks_cancelled_discards_late_result_and_keeps_worker_counted() -> None:
    gate = threading.Event()
    stages: list[str] = []
    ready: dict[str, Any] = {}
    registry = AnalysisRegistry(
        worker=_blocking_worker(gate, stages, ready, wait_timeout=None),
        max_concurrent=1, max_concurrent_per_user=1,
    )
    owner = user("1")
    snapshot = registry.start(owner, {})
    try:
        # Synchronize after the first progress callback, not merely thread entry:
        # cancellation before that callback correctly lets the worker exit at once.
        assert _wait_until(lambda: ready.get("semantics"))
        cancelled = registry.cancel(owner, snapshot["analysis_id"])
        assert cancelled["status"] == "cancelling"
        assert "result" not in cancelled and "error" not in cancelled
        # The gate, not a wall-clock timeout, keeps the cancelled worker alive.
        with pytest.raises(AppError) as limited:
            registry.start(owner, {})
        assert limited.value.code == "ANALYSIS_LIMIT_REACHED"

        gate.set()
        assert _wait_until(lambda: registry.get(owner, snapshot["analysis_id"])["status"] == "cancelled")
        assert _wait_until(lambda: registry.active_count() == 0)
        final = registry.get(owner, snapshot["analysis_id"])
        assert "result" not in final and stages.count("generation") == 0
        assert final["steps"][2]["status"] == "pending"

        # 线程退出后额度释放，可以开始新任务。
        later = registry.start(owner, {})
        assert _wait_until(lambda: registry.get(owner, later["analysis_id"])["status"] == "completed")
    finally:
        gate.set()
        registry.join(2.0)


@pytest.mark.parametrize("blocked_stage", [1, 2])
def test_end_analysis_interrupts_current_model_and_releases_worker(blocked_stage, caplog):
    rules, model = _rules_with_doc([_select_payload(), _generate_payload()])
    original = model.complete
    calls = []
    blocked = threading.Event()

    def complete(model_id, messages, *, timeout_seconds, cancel_event=None):
        calls.append((timeout_seconds, cancel_event))
        if len(calls) == blocked_stage:
            blocked.set()
            assert cancel_event is not None and cancel_event.wait(3)
            raise OSError("connection closed")
        return original(model_id, messages, timeout_seconds=timeout_seconds)

    model.complete = complete
    snapshot = rules.start_analysis(user(), _request())
    analysis_id = snapshot["analysis_id"]
    assert blocked.wait(2)
    rules.cancel_analysis(user(), analysis_id)
    rules.analyses.join(2)
    done = rules.get_analysis(user(), analysis_id)
    assert done["status"] == "cancelled"
    assert "result" not in done and "error" not in done
    assert len(calls) == blocked_stage and rules.analyses.active_count() == 0
    assert calls[0][1].is_set()
    assert all(0 < timeout <= 120 and event is calls[0][1] for timeout, event in calls)
    assert "Model call failed" not in caplog.text


def test_polling_renews_wait_on_same_analysis_and_abandoned_work_expires():
    now = [0.0]
    entered = threading.Event()
    def worker(_user, _payload, _progress, cancel_event):
        entered.set()
        cancel_event.wait(3)

    registry = AnalysisRegistry(worker=worker, running_ttl=150, analysis_timeout=600, clock=lambda: now[0])
    owner = user()
    analysis_id = registry.start(owner, {})["analysis_id"]
    try:
        assert entered.wait(1)
        for elapsed in (119, 157, 250, 390):
            now[0] = elapsed
            snapshot = registry.get(owner, analysis_id)
            assert snapshot["status"] == "running" and snapshot["analysis_id"] == analysis_id
        now[0] = 550
        assert registry.get(owner, analysis_id)["status"] in {"cancelling", "cancelled"}
        registry.join(1)
        assert registry.get(owner, analysis_id)["status"] == "cancelled"
    finally:
        registry.close()


def test_generation_returns_after_157_seconds_without_restarting_analysis():
    rules, model = _rules_with_doc([_select_payload(), _generate_payload()])
    now = [0.0]
    rules.analyses = AnalysisRegistry(worker=rules._execute_analysis, clock=lambda: now[0])
    generating = threading.Event()
    finish = threading.Event()
    original = model.complete

    def complete(model_id, messages, *, timeout_seconds, cancel_event):
        assert 0 < timeout_seconds <= 120 and not cancel_event.is_set()
        if model.calls:
            generating.set()
            assert finish.wait(2)
        else:
            now[0] = 65
        return original(model_id, messages, timeout_seconds=timeout_seconds)

    model.complete = complete
    analysis_id = rules.start_analysis(user(), _request())["analysis_id"]
    try:
        assert generating.wait(2)
        now[0] = 157.0
        assert rules.get_analysis(user(), analysis_id)["status"] == "running"
        finish.set()
        rules.analyses.join(2)
        completed = rules.get_analysis(user(), analysis_id)
        assert completed["status"] == "completed" and completed["elapsed_ms"] == 157000
        assert completed["result"]["rule_type"] == "field_compare" and len(model.calls) == 2
    finally:
        finish.set()
        rules.analyses.close()


def test_abandoned_analysis_releases_worker_without_further_requests():
    stopped = threading.Event()
    def worker(_user, _payload, _progress, cancel_event):
        if cancel_event.wait(3):
            stopped.set()

    registry = AnalysisRegistry(worker=worker, running_ttl=0.1)
    try:
        registry.start(user(), {})
        assert stopped.wait(1)
        registry.join(1)
        assert registry.active_count() == 0
    finally:
        registry.close()


@pytest.mark.parametrize("poll", [True, False])
def test_total_deadline_discards_late_publication_even_with_frequent_polling(poll):
    now = [0.0]
    entered, release = threading.Event(), threading.Event()
    writes = []
    registry = AnalysisRegistry(analysis_timeout=180, clock=lambda: now[0])

    def worker(owner, payload, progress, cancel_event):
        entered.set()
        assert release.wait(2)
        registry.publish_result(cancel_event, {"late": True}, lambda: writes.append("cache"))
        return {"late": True}

    analysis_id = registry.start(user(), {}, worker=worker)["analysis_id"]
    try:
        assert entered.wait(1)
        for elapsed in (60, 120, 179):
            now[0] = elapsed
            assert registry.get(user(), analysis_id)["status"] == "running"
        now[0] = 181
        if poll:
            assert registry.get(user(), analysis_id)["error"]["code"] == "ANALYSIS_TIMEOUT"
        release.set()
        registry.join(1)
        final = registry.get(user(), analysis_id)
        assert final["status"] == "failed" and final["error"]["code"] == "ANALYSIS_TIMEOUT"
        assert "result" not in final and not writes and registry.active_count() == 0
    finally:
        release.set()
        registry.close()


@pytest.fixture
def trickling_model(monkeypatch):
    from auto_check.app.language_model_platform import create_language_model_service

    waiting, disconnected = threading.Event(), threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Length", "100000")
            self.end_headers()
            waiting.set()
            # Frequent bytes prevent a socket inactivity timeout.
            try:
                for _ in range(150):
                    self.wfile.write(b" ")
                    time.sleep(0.02)
            except OSError:
                disconnected.set()

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        model = {"id": "test", "base_url": f"http://127.0.0.1:{server.server_port}/v1",
                 "enabled": True, "api_key_encrypted": "local", "model_name": "local"}
        monkeypatch.setenv("no_proxy", "127.0.0.1")
        monkeypatch.setattr("auto_check.app.language_model_platform.load_language_model_secrets", lambda db: [model])
        monkeypatch.setattr("auto_check.app.language_model_platform.decrypt_secret", lambda _: "test")
        bound = create_language_model_service(None).binder("data_validation")
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        thread.start()
        try:
            yield bound, model["id"], waiting, disconnected
        finally:
            bound.close()
            server.shutdown()
            thread.join()


@pytest.mark.parametrize("limit,expected", [("call", "MODEL_TIMEOUT"), ("analysis", "ANALYSIS_TIMEOUT"),
                                             ("user", None)])
def test_model_socket_is_closed_and_next_round_skipped(trickling_model, monkeypatch, limit, expected):
    bound, model_id, waiting, disconnected = trickling_model
    monkeypatch.setattr("auto_check.modules.data_validation.model_calls.SYNC_GENERATION_TIMEOUT_SECONDS",
                        0.5 if limit == "call" else 120)
    registry = AnalysisRegistry(analysis_timeout=0.5 if limit == "analysis" else 180)
    returned = []

    def worker(owner, payload, progress, cancel_event):
        for number, prompt in enumerate(("body", "quick"), 1):
            returned.append(semantic_completion(
                bound.value, model_id, prompt, stage="select_and_generate", public_stage="generate_rule",
                round_number=number, analysis_id="test", options={}, cancel_event=cancel_event))

    analysis_id = registry.start(user(), {}, worker=worker)["analysis_id"]
    try:
        assert waiting.wait(2)
        snapshot = registry.get(user(), analysis_id)
        assert snapshot["activity"]["phase"] == "model_wait" and snapshot["activity"]["round_number"] == 1
        if limit == "user":
            registry.cancel(user(), analysis_id)
        assert disconnected.wait(2)
        registry.join(1)
        final = registry.get(user(), analysis_id)
        if expected:
            assert final["status"] == "failed" and final["error"]["code"] == expected
            assert len(final["error"]["reference"]) == 12
        else:
            assert final["status"] == "cancelled" and "error" not in final
        assert not returned and "result" not in final and registry.active_count() == 0
    finally:
        registry.close()


def test_one_job_model_round_limit_spans_restarted_analysis_attempts():
    model = SequenceModel([{"ok": True}])

    def worker(owner, payload, progress, cancel_event):
        for attempt in range(3):
            for number in (1, 2):
                semantic_completion(model, "m", "p", stage="select_table", public_stage="select_table",
                                    round_number=number, analysis_id=str(attempt), options={}, cancel_event=cancel_event)

    registry = AnalysisRegistry(worker=worker)
    analysis_id = registry.start(user(), {})["analysis_id"]
    registry.join(2)
    final = registry.get(user(), analysis_id)
    assert len(model.calls) == 4 and final["activity"]["round_number"] == 4
    assert final["status"] == "failed" and final["error"]["code"] == "ANALYSIS_ROUND_LIMIT"
    assert len(final["error"]["reference"]) == 12
    assert "result" not in final


def test_late_model_success_after_its_deadline_is_not_published():
    now = [0.0]
    writes = []
    registry = AnalysisRegistry(clock=lambda: now[0])

    class LateModel:
        def complete_with_options(self, *args, **kwargs):
            now[0] = 121.0
            return {"content": "late", "finish_reason": "stop"}

    def worker(owner, payload, progress, cancel_event):
        raw = semantic_completion(LateModel(), "m", "p", stage="select_table", public_stage="select_table",
                                  round_number=1, analysis_id="test", options={}, cancel_event=cancel_event)
        registry.publish_result(cancel_event, {"raw": raw}, lambda: writes.append(raw))

    analysis_id = registry.start(user(), {}, worker=worker)["analysis_id"]
    registry.join(2)
    final = registry.get(user(), analysis_id)
    assert final["status"] == "failed" and final["error"]["code"] == "MODEL_TIMEOUT"
    assert "result" not in final and not writes


def test_deadline_cannot_interrupt_accepted_publication_or_block_another_user():
    from concurrent.futures import ThreadPoolExecutor

    now = [0.0]
    writing, release = threading.Event(), threading.Event()
    registry = AnalysisRegistry(clock=lambda: now[0])

    def worker(owner, payload, progress, cancel_event):
        def publish():
            writing.set()
            assert release.wait(3)
        registry.publish_result(cancel_event, {"saved": True}, publish)

    writer = registry.start(user("writer"), {}, worker=worker)["analysis_id"]
    try:
        assert writing.wait(1)
        now[0] = 181.0
        with ThreadPoolExecutor() as pool:
            waiting = pool.submit(registry.get, user("writer"), writer).result(timeout=1)
            assert waiting["status"] == "running" and waiting["activity"]["phase"] == "publishing"
            other = pool.submit(registry.start, user("other"), {}, worker=lambda *_: {"ok": True}).result(timeout=1)
        release.set()
        registry.join(2)
        assert registry.get(user("other"), other["analysis_id"])["result"] == {"ok": True}
        assert registry.get(user("writer"), writer)["result"] == {"saved": True}
    finally:
        release.set()
        registry.close()


def test_browser_can_end_unacknowledged_creation_without_sending_to_model():
    rules, model = _rules_with_doc([_select_payload(), _generate_payload()])
    entered = threading.Event()
    original = model.complete
    def record(*args, **kwargs):
        entered.set()
        return original(*args, **kwargs)
    model.complete = record
    snapshot = rules.start_analysis(user(), _request(await_first_poll=True))
    with pytest.raises(AppError):
        rules.get_analysis(user("other"), snapshot["analysis_id"])
    assert not entered.wait(0.1)
    stopped = rules.cancel_analysis(user(), snapshot["analysis_id"])
    rules.analyses.join()
    assert stopped["status"] == "cancelled" and not model.calls

    waiting = rules.start_analysis(user(), _request(await_first_poll=True))
    assert rules.get_analysis(user(), waiting["analysis_id"])["status"] == "running"
    rules.analyses.join()
    assert rules.get_analysis(user(), waiting["analysis_id"])["status"] == "completed"
    assert len(model.calls) == 2


def test_failures_expose_only_safe_codes_and_references(caplog) -> None:
    def app_error_worker(_user, _payload, _progress, _cancel_event):
        raise AppError("MODEL_TIMEOUT", stage="select_table", reference="abc123def456")

    registry = AnalysisRegistry(worker=app_error_worker)
    snapshot = registry.start(user(), {})
    assert _wait_until(lambda: registry.get(user(), snapshot["analysis_id"])["status"] == "failed")
    failed = registry.get(user(), snapshot["analysis_id"])
    assert failed["error"] == {
        "code": "MODEL_TIMEOUT", "reference": "abc123def456", "stage": "select_table",
    }
    assert "result" not in failed
    registry.join(2.0)

    secret = "password endpoint token"

    def crash_worker(_user, _payload, _progress, _cancel_event):
        raise RuntimeError(secret)

    crashing = AnalysisRegistry(worker=crash_worker)
    snapshot = crashing.start(user(), {})
    assert _wait_until(lambda: crashing.get(user(), snapshot["analysis_id"])["status"] == "failed")
    failed = crashing.get(user(), snapshot["analysis_id"])
    assert failed["error"]["code"] == "ANALYSIS_FAILED"
    reference = failed["error"]["reference"]
    assert len(reference) == 12 and all(char in "0123456789abcdef" for char in reference)
    assert reference in caplog.text and "RuntimeError" in caplog.text
    assert secret not in caplog.text
    assert secret not in json.dumps(failed)
    crashing.join(2.0)


# ---------------------------------------------------------------------------
# owner 隔离与边界
# ---------------------------------------------------------------------------


def test_analysis_ids_are_owner_isolated_and_unknown_ids_do_not_leak() -> None:
    gate = threading.Event()
    stages: list[str] = []
    registry = AnalysisRegistry(worker=_blocking_worker(gate, stages))
    owner = user("1")
    snapshot = registry.start(owner, {})
    assert _wait_until(lambda: "start" in stages)

    for other in (user("2"), user("9")):
        with pytest.raises(AppError) as denied:
            registry.get(other, snapshot["analysis_id"])
        assert denied.value.code == "FORBIDDEN"
        with pytest.raises(AppError) as denied_cancel:
            registry.cancel(other, snapshot["analysis_id"])
        assert denied_cancel.value.code == "FORBIDDEN"

    with pytest.raises(AppError) as missing:
        registry.get(owner, "not-an-existing-id")
    assert missing.value.code == "FORBIDDEN"

    assert registry.get(owner, snapshot["analysis_id"])["analysis_id"] == snapshot["analysis_id"]
    gate.set()
    registry.join(2.0)


def test_registry_enforces_cache_ttl_and_concurrency_limits() -> None:
    now = [0.0]
    gate = threading.Event()

    def worker(_user, _payload, progress, _cancel_event):
        progress({"step": "semantics", "status": "completed", "detail": "已完成初步业务对象匹配，具体条件待规则草稿确认"})
        gate.wait(2.0)
        progress({"step": "generation", "status": "completed", "detail": "已生成规则草稿建议"})
        return {"ok": True}

    registry = AnalysisRegistry(
        worker=worker, max_total=2, max_per_user=1,
        max_concurrent=2, max_concurrent_per_user=1,
        finished_ttl=10.0, running_ttl=10.0, clock=lambda: now[0],
    )
    first = registry.start(user("1"), {})
    second = registry.start(user("2"), {})
    assert first["analysis_id"] != second["analysis_id"]
    assert len(first["analysis_id"]) >= 24

    with pytest.raises(AppError) as limited:
        registry.start(user("1"), {})
    assert limited.value.code == "ANALYSIS_LIMIT_REACHED"

    gate.set()
    registry.join(2.0)
    assert registry.get(user("1"), first["analysis_id"])["status"] == "completed"

    # 超过完成态 TTL 后缓存被清理，同一用户可再次创建。
    now[0] = 11.0
    third = registry.start(user("1"), {})
    registry.join(2.0)
    assert third["analysis_id"] != first["analysis_id"]


def test_finished_snapshots_make_room_for_the_next_analysis_and_keep_its_revision_source():
    registry = AnalysisRegistry(worker=lambda _, payload, *__: {"n": payload["n"]}, max_per_user=2)
    try:
        owner = user("1")
        first = registry.start(owner, {"n": 1})["analysis_id"]
        registry.join()
        second = registry.start(owner, {"n": 2})["analysis_id"]
        registry.join()
        assert registry.active_count() == 0
        third = registry.start(owner, {"n": 3, "revision_of": first})["analysis_id"]
        registry.join()
        assert registry.completed_result(owner, first) == {"n": 1}
        assert registry.completed_result(owner, second) is None
        assert registry.completed_result(owner, third) == {"n": 3}
    finally:
        registry.close()


def test_global_snapshot_limit_reuses_oldest_finished_slot_across_owners():
    registry = AnalysisRegistry(worker=lambda *_: {"ok": True}, max_total=2)
    try:
        ids = []
        for owner in ("1", "2", "3"):
            ids.append(registry.start(user(owner), {})["analysis_id"])
            registry.join()
        assert registry.completed_result(user("1"), ids[0]) is None
        assert registry.completed_result(user("2"), ids[1]) == {"ok": True}
        assert registry.completed_result(user("3"), ids[2]) == {"ok": True}
    finally:
        registry.close()


def test_unclaimed_browser_requests_take_no_worker_slots_and_cannot_overbook_on_first_poll():
    gate = threading.Event()
    calls = []
    def worker(_, payload, *__):
        calls.append(payload["n"])
        gate.wait(2)

    registry = AnalysisRegistry(worker=worker, max_concurrent=1, max_concurrent_per_user=1)
    try:
        owner = user("1")
        first, second = [registry.start(owner, {"n": i}, await_first_poll=True)["analysis_id"] for i in (1, 2)]
        assert registry.active_count() == 0 and not calls
        assert registry.get(owner, second)["status"] == "running"
        assert _wait_until(lambda: calls == [2])
        declined = registry.get(owner, first)
        assert declined["status"] == "failed" and declined["error"]["code"] == "ANALYSIS_LIMIT_REACHED"
        assert registry.active_count() == 1
        gate.set()
        registry.join()
        assert calls == [2] and registry.active_count() == 0
    finally:
        gate.set()
        registry.close()


def test_closed_registry_refuses_to_start_new_workers() -> None:
    registry = AnalysisRegistry(worker=lambda *_args: {"ok": True})
    registry.close(0.1)
    with pytest.raises(AppError) as closed:
        registry.start(user(), {})
    assert closed.value.code == "ANALYSIS_UNAVAILABLE"


def _sync_response(rules):
    router = ModuleRouter(MANIFEST, default_permission_evaluator)
    register_routes(router, lambda: rules)
    return _dispatch(router, "POST", "/ai/parse-rule", {**user(), "capabilities": ["dv.ai_use"]}, body=_request())


def test_sync_parse_route_counts_rounds_across_config_restarts(monkeypatch):
    rules, model = _rules_with_doc([{"ok": True}])
    attempts = []
    monkeypatch.setattr(rules, "_analysis_inputs", lambda *_: {"context": {"revision": len(attempts)}})
    def analyze(owner, payload, inputs, progress, control, **kwargs):
        attempts.append(control)
        for round_number in (1, 2):
            semantic_completion(model, "m", "p", stage="select_table", public_stage="select_table",
                                round_number=round_number, analysis_id="test", options={}, cancel_event=control)
        raise AppError("VALIDATION_ERROR")
    monkeypatch.setattr(rules, "_analyze_request", analyze)
    response = _sync_response(rules)
    assert response.body["error"]["code"] == "ANALYSIS_ROUND_LIMIT"
    assert len(response.body["error"]["reference"]) == 12 and len(model.calls) == 4
    assert len(attempts) == 3 and attempts[0] is attempts[-1]


def test_sync_parse_route_disconnects_a_trickling_socket_at_total_deadline(trickling_model, monkeypatch):
    rules, _ = _rules_with_doc([_select_payload()])
    bound, model_id, waiting, disconnected = trickling_model
    rules.analyses = AnalysisRegistry(analysis_timeout=0.5)
    def analyze(owner, payload, inputs, progress, control, **kwargs):
        semantic_completion(bound.value, model_id, "body", stage="select_table", public_stage="select_table",
                            round_number=1, analysis_id="test", options={}, cancel_event=control)
    monkeypatch.setattr(rules, "_analyze_request", analyze)
    response = _sync_response(rules)
    assert waiting.is_set() and disconnected.wait(1)
    assert response.body["error"]["code"] == "ANALYSIS_TIMEOUT"
    assert len(response.body["error"]["reference"]) == 12


def test_sync_external_cancel_interrupts_live_socket(trickling_model, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from auto_check.modules.data_validation.analysis_jobs import AnalysisCancelled

    rules, _ = _rules_with_doc([_select_payload()])
    bound, model_id, waiting, disconnected = trickling_model
    stop = threading.Event()
    def analyze(owner, payload, inputs, progress, control, **kwargs):
        semantic_completion(bound.value, model_id, "body", stage="select_table", public_stage="select_table",
                            round_number=1, analysis_id="test", options={}, cancel_event=control)
    monkeypatch.setattr(rules, "_analyze_request", analyze)
    with ThreadPoolExecutor() as pool:
        future = pool.submit(rules.parse_rule_request, user(), _request(), cancel_event=stop)
        assert waiting.wait(2)
        stop.set()
        with pytest.raises(AnalysisCancelled):
            future.result(timeout=2)
    assert disconnected.wait(1)


@pytest.mark.parametrize("slow_stage", ["inputs", "prepublish", "commit"])
def test_sync_deadline_includes_metadata_and_ends_at_accepted_publication(monkeypatch, slow_stage):
    rules, model = _rules_with_doc([_select_payload(), _generate_payload()])
    now = [0.0]
    rules.analyses = AnalysisRegistry(clock=lambda: now[0])
    calls = []
    def analyze(*args, **kwargs):
        calls.append(1)
        return {"status": "needs_clarification"}
    monkeypatch.setattr(rules, "_analyze_request", analyze)
    if slow_stage == "inputs":
        original = rules._analysis_inputs
        def slow_inputs(*args):
            now[0] = 181
            return original(*args)
        monkeypatch.setattr(rules, "_analysis_inputs", slow_inputs)
    else:
        target, method = ((rules.storage, "publish_analysis") if slow_stage == "commit"
                          else (rules, "_memory_table"))
        original = getattr(target, method)
        def advance(*args):
            now[0] = 181
            return original(*args)
        monkeypatch.setattr(target, method, advance)
    response = _sync_response(rules)
    if slow_stage == "commit":
        assert response.status == 200
    else:
        assert response.body["error"]["code"] == "ANALYSIS_TIMEOUT"
        assert len(response.body["error"]["reference"]) == 12
        if slow_stage == "inputs":
            assert not calls


def test_snapshot_returns_defensive_copies() -> None:
    registry = AnalysisRegistry(worker=lambda *_args: {"nested": {"value": 1}})
    snapshot = registry.start(user(), {})
    assert _wait_until(lambda: registry.get(user(), snapshot["analysis_id"])["status"] == "completed")
    first = registry.get(user(), snapshot["analysis_id"])
    first["result"]["nested"]["value"] = 99
    assert registry.get(user(), snapshot["analysis_id"])["result"]["nested"]["value"] == 1


def test_get_purges_expired_finished_job() -> None:
    now = [0.0]
    registry = AnalysisRegistry(
        worker=lambda *_args: {"ok": True}, finished_ttl=5.0, clock=lambda: now[0],
    )
    snapshot = registry.start(user(), {})
    assert _wait_until(lambda: registry.get(user(), snapshot["analysis_id"])["status"] == "completed")
    now[0] = 6.0
    with pytest.raises(AppError) as expired:
        registry.get(user(), snapshot["analysis_id"])
    assert expired.value.code == "FORBIDDEN"


def test_service_join_cancels_running_analysis_and_releases() -> None:
    gate = threading.Event()
    stages: list[str] = []
    _database, rules = service(metadata=Metadata(), model=SequenceModel([]))
    rules.analyses.worker = _blocking_worker(gate, stages)

    snapshot = rules.start_analysis(user(), _request())
    assert _wait_until(lambda: "start" in stages)
    rules.join()
    final = rules.get_analysis(user(), snapshot["analysis_id"])
    assert final["status"] == "cancelled"
    assert "result" not in final
    gate.set()
    rules.analyses.join(2.0)


# ---------------------------------------------------------------------------
# API 兼容与权限
# ---------------------------------------------------------------------------


def _dispatch(router, method: str, path: str, current_user, body=None, path_params=None):
    response = router.dispatch(ModuleRequest(
        method=method, path=f"{MANIFEST.api_prefix}{path}", path_params=path_params or {},
        query={}, body=body, current_user=current_user,
    ))
    assert response is not None
    return response


def test_analysis_routes_reuse_ai_use_and_keep_parse_rule_compatible() -> None:
    rules, _model = _rules_with_doc([_select_payload(), _generate_payload(
        expression={"left": "maturity_date", "op": "lt", "right": "issue_date"},
        semantic_intent={"metrics": [
            {"term": "到期日期", "side": "left", "fields": ["maturity_date"]},
            {"term": "发放日期", "side": "right", "fields": ["issue_date"]},
        ], "scopes": [], "open_questions": []},
    )])
    gate = threading.Event()
    stages: list[str] = []
    rules.analyses.worker = _blocking_worker(gate, stages)

    router = ModuleRouter(MANIFEST, default_permission_evaluator)
    register_routes(router, lambda: rules)
    owner = {**user(), "capabilities": ["dv.ai_use"]}
    other = {**user("2"), "capabilities": ["dv.ai_use"]}
    anonymous = {**user("3"), "capabilities": []}

    # 原同步入口保持可用，且仍是同一 ai_use 权限。
    legacy = _dispatch(router, "POST", "/ai/parse-rule", owner, body=_request())
    assert legacy.status == 200
    assert legacy.body["data"]["rule_type"] == "field_compare"
    assert legacy.body["data"]["analysis_protocol"] == 2

    created = _dispatch(router, "POST", "/ai/analyses", owner, body=_request())
    assert created.status == 200
    snapshot = created.body["data"]
    assert snapshot["status"] == "running"
    assert isinstance(snapshot["elapsed_ms"], int)
    analysis_id = snapshot["analysis_id"]

    fetched = _dispatch(router, "GET", f"/ai/analyses/{analysis_id}", owner, path_params={"analysis_id": analysis_id})
    assert fetched.status == 200 and fetched.body["data"]["analysis_id"] == analysis_id

    denied_get = _dispatch(router, "GET", f"/ai/analyses/{analysis_id}", other, path_params={"analysis_id": analysis_id})
    assert denied_get.status == 403 and denied_get.body["error"]["code"] == "FORBIDDEN"
    denied_delete = _dispatch(router, "DELETE", f"/ai/analyses/{analysis_id}", other, path_params={"analysis_id": analysis_id})
    assert denied_delete.status == 403 and denied_delete.body["error"]["code"] == "FORBIDDEN"
    no_permission = _dispatch(router, "POST", "/ai/analyses", anonymous, body=_request())
    assert no_permission.status == 403

    assert _wait_until(lambda: "start" in stages)
    cancelled = _dispatch(router, "DELETE", f"/ai/analyses/{analysis_id}", owner, path_params={"analysis_id": analysis_id})
    assert cancelled.status == 200 and cancelled.body["data"]["status"] == "cancelling"
    gate.set()
    rules.join()
