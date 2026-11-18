"""内存临时分析任务回归：真实进度、取消、隔离、边界与兼容。"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import pytest

from auto_check.app.module_system.contracts import ModuleRequest
from auto_check.app.module_system.permissions import default_permission_evaluator
from auto_check.app.module_system.routing import ModuleRouter
from auto_check.modules.data_validation.analysis_jobs import AnalysisRegistry
from auto_check.modules.data_validation.api import register_routes
from auto_check.modules.data_validation.contracts import AppError
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
    def worker(current_user, payload, progress):
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
        assert cancelled["status"] == "cancelled"
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


def test_failures_expose_only_safe_codes_and_references(caplog) -> None:
    def app_error_worker(_user, _payload, _progress):
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

    def crash_worker(_user, _payload, _progress):
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

    def worker(_user, _payload, progress):
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


def test_closed_registry_refuses_to_start_new_workers() -> None:
    registry = AnalysisRegistry(worker=lambda *_args: {"ok": True})
    registry.close(0.1)
    with pytest.raises(AppError) as closed:
        registry.start(user(), {})
    assert closed.value.code == "ANALYSIS_UNAVAILABLE"


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
    rules, _model = _rules_with_doc([_select_payload(), _generate_payload()])
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
    assert cancelled.status == 200 and cancelled.body["data"]["status"] == "cancelled"
    gate.set()
    rules.join()
