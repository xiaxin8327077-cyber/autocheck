from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date
from pathlib import Path
from threading import Event
from time import perf_counter
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from auto_check.app.module_system.contracts import ModuleRequest
from auto_check.app.module_system.permissions import default_permission_evaluator
from auto_check.app.module_system.routing import ModuleRouter
from auto_check.app.module_system.runtime import _DaemonTaskPool, _ModuleTaskExecutor
from auto_check.modules.data_validation.api import register_routes
from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.module import MANIFEST, create_module
from auto_check.modules.data_validation.storage import RULES, TASK_RULES, VERSIONS
from tests.modules.data_validation.support import Metadata, loan_definition, service, user
from tests.modules.data_validation.test_background_execution import batch
from tests.modules.data_validation.test_tasks import _enable


@pytest.mark.parametrize("period", ["2026-02-30", "2026-13-01", "20260228", "2026-W09-1", " 2026-02-28", None])
def test_invalid_period_rejected_before_freezing_or_querying(batch, period):
    rules, _, metadata, payload = batch
    with pytest.raises(AppError, match="VALIDATION_ERROR"):
        rules.start_task(user(), {**payload, "report_period": period})
    assert not rules.storage.list_tasks("1") and not metadata.calls


@pytest.mark.parametrize("dialect", ["mysql", "postgresql"])
def test_persist_iso_and_bind_calendar_date_in_batch(dialect, monkeypatch):
    meta = Metadata(sources=[SimpleNamespace(id="src", name="监管报表", dialect=dialect)])
    _, rules = service(metadata=meta)
    rule, _ = _enable(rules, user(), loan_definition(dialect=dialect, report_date_field="report_date"))
    observed = []
    query = meta.execute_select
    def capture(source_id, sql, params, **kwargs):
        observed.append((sql, params["report_date"]))
        return query(source_id, sql, params, **kwargs)
    monkeypatch.setattr(meta, "execute_select", capture)
    task = rules.start_task(user(), {"rule_ids": [rule["id"]], "report_period": "2028-02-29"})
    assert rules.storage.get_task(task["id"])["report_period"] == "2028-02-29"
    assert len(observed) == 1 and ":report_date" in observed[0][0]
    assert observed[0][1] == date(2028, 2, 29)


def test_pause_finishes_current_query_and_resume_claims_only_remaining(batch, monkeypatch):
    rules, executor, metadata, payload = batch
    task_id = rules.start_task(user(), payload)["id"]
    entered, release = Event(), Event()
    query = metadata.execute_select

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return query(*args, **kwargs)

    monkeypatch.setattr(metadata, "execute_select", blocked)
    with ThreadPoolExecutor(1) as pool:
        worker = pool.submit(executor.run)
        try:
            assert entered.wait(3)
            assert rules.pause_task(user(), task_id)["status"] == "pausing"
        finally:
            release.set()
        worker.result(timeout=3)
    assert executor.future.done()
    assert rules.storage.get_task(task_id)["status"] == "paused"
    assert [r["status"] for r in rules.storage.task_rules(task_id)] == ["PASS", "queued"]
    executor.reject = True
    with pytest.raises(AppError, match="TASK_EXECUTOR_UNAVAILABLE"):
        rules.resume_task(user(), task_id)
    assert rules.storage.get_task(task_id)["status"] == "paused"
    executor.reject = False
    executor.future = Future()
    assert rules.resume_task(user(), task_id)["status"] == "queued"
    previous = executor.work
    assert rules.resume_task(user(), task_id)["status"] == "queued"
    assert executor.work is previous
    executor.run()
    assert len(metadata.calls) == 2
    assert rules.pause_task(user(), task_id)["status"] == "completed"


def test_pause_queued_batch_frees_slot_and_allows_owner_cancel(batch):
    rules, executor, metadata, payload = batch
    task_id = rules.start_task(user(), payload)["id"]
    for action in (rules.pause_task, rules.resume_task):
        with pytest.raises(AppError, match="FORBIDDEN"):
            action(user("other", "admin"), task_id)
    assert rules.pause_task(user(), task_id)["status"] == "paused"
    assert executor.future.cancelled()
    assert rules.cancel_task(user(), task_id)["status"] == "cancelled"
    assert rules.resume_task(user(), task_id)["status"] == "cancelled"
    assert not metadata.calls


@pytest.mark.parametrize("before_submit", [False, True])
def test_cancel_queued_batch_releases_reserved_future(batch, monkeypatch, before_submit):
    rules, executor, metadata, payload = batch
    if before_submit:
        submit = rules._executions.submit
        def cancel_then_submit(tid, *args, **kwargs):
            rules.cancel_task(user(), tid)
            return submit(tid, *args, **kwargs)
        monkeypatch.setattr(rules._executions, "submit", cancel_then_submit)
    tid = rules.start_task(user(), payload)["id"]
    if not before_submit:
        rules.cancel_task(user(), tid)
    assert executor.future.cancelled() and not metadata.calls
    assert rules.storage.get_task(tid)["status"] == "cancelled"


def test_cancel_queued_batch_frees_one_of_two_module_slots(batch):
    rules, _, metadata, payload = batch
    shared = _DaemonTaskPool(maximum_workers=1, maximum_tasks=4)
    module_executor = _ModuleTaskExecutor(shared, maximum_tasks=2)
    rules._executions.executor = module_executor
    entered, release = Event(), Event()
    def other_module_worker():
        entered.set()
        assert release.wait(10)
    busy = shared.submit(other_module_worker)
    try:
        assert entered.wait(3)
        first = rules.start_task(user(), payload)["id"]
        second = rules.start_task(user(), payload)["id"]
        with pytest.raises(AppError, match="TASK_EXECUTOR_UNAVAILABLE"):
            rules.start_task(user(), payload)
        rules.cancel_task(user(), first)
        again = rules.start_task(user(), payload)
        assert again["status"] == "queued" and not metadata.calls
        for tid in (second, again["id"]):
            rules.cancel_task(user(), tid)
    finally:
        module_executor.shutdown(cancel_pending=True)
        release.set()
        busy.result(timeout=3)
        shared.shutdown(cancel_futures=True)


def test_pause_during_final_query_finishes_completed(batch, monkeypatch):
    rules, executor, metadata, payload = batch
    task_id = rules.start_task(user(), {**payload, "rule_ids": payload["rule_ids"][:1]})["id"]
    query = metadata.execute_select
    def pause_during_query(*args, **kwargs):
        assert rules.pause_task(user(), task_id)["status"] == "pausing"
        return query(*args, **kwargs)
    monkeypatch.setattr(metadata, "execute_select", pause_during_query)
    executor.run()
    assert rules.storage.get_task(task_id)["status"] == "completed"
    assert rules.storage.task_rules(task_id)[0]["status"] == "PASS"


def test_concurrent_resume_only_dispatches_once(batch, monkeypatch):
    rules, executor, metadata, payload = batch
    task_id = rules.start_task(user(), payload)["id"]
    assert rules.pause_task(user(), task_id)["status"] == "paused"
    executor.future = Future()
    entered, release = Event(), Event()
    dispatch = rules._dispatch_execution
    calls = []
    def delayed(*args, **kwargs):
        calls.append(1)
        entered.set()
        assert release.wait(5)
        return dispatch(*args, **kwargs)
    monkeypatch.setattr(rules, "_dispatch_execution", delayed)
    with ThreadPoolExecutor(1) as pool:
        first = pool.submit(rules.resume_task, user(), task_id)
        try:
            assert entered.wait(3)
            assert rules.resume_task(user(), task_id)["status"] == "queued"
        finally:
            release.set()
        first.result(timeout=3)
    executor.run()
    assert calls == [1]
    assert len(metadata.calls) == 2


def test_execution_routes_permissions_and_owner_scope(batch):
    rules, _, _, payload = batch
    tid = rules.start_task(user(), payload)["id"]
    router = ModuleRouter(MANIFEST, default_permission_evaluator)
    register_routes(router, lambda: rules)
    def request(method, path, actor, capabilities, query=None):
        return router.dispatch(ModuleRequest(method=method, path=MANIFEST.api_prefix + path, path_params={},
                               query=query or {}, body=None, current_user={**actor, "capabilities": capabilities}))
    assert request("GET", "/rules/execution-selection", user(), ["dv.view"]).status == 403
    assert request("GET", "/rules/execution-selection", user(), ["dv.run"]).body["data"]["count"] == 2
    with rules.storage.database.begin() as connection:
        connection.execute(RULES.update().values(report_category=""))
    query = {"report_category": "__uncategorized__", "status": "enabled"}
    assert request("GET", "/rules/execution-selection", user(), ["dv.run"], query).body["data"]["count"] == 2
    assert request("GET", "/rules", user(), ["dv.view"], query).body["data"]["total"] == 2
    assert request("GET", "/tasks/progress", user(), ["dv.run"]).status == 403
    assert request("GET", "/tasks/progress", user(), ["dv.view_results"]).body["data"][0]["id"] == tid
    for action in ("pause", "resume"):
        path = f"/tasks/{tid}/{action}"
        assert request("POST", path, user(), ["dv.view_results"]).status == 403
        assert request("POST", path, user("other", "admin"), ["dv.run"]).status == 403
    with pytest.raises(AppError, match="VALIDATION_ERROR"):
        rules.task_progress(user(), {"task_ids": ",".join(str(i) for i in range(1, 22))})


def test_new_and_legacy_category_snapshots(batch):
    rules, _, _, payload = batch
    cols = {}
    create_module().register_schema(SimpleNamespace(add=cols.__setitem__))
    assert "report_category" in cols[TASK_RULES.name] and TASK_RULES.c.report_category.nullable
    assert "source_id" in cols[TASK_RULES.name] and TASK_RULES.c.source_id.nullable
    assert MANIFEST.schema_version >= 15
    migration = Path(__file__).resolve().parents[3] / "src/auto_check/modules/data_validation/migrations/015_task_rule_scope.sql"
    assert "ADD COLUMN report_category VARCHAR(64) NULL" in migration.read_text("utf-8")
    tid = rules.start_task(user(), payload)["id"]
    db = rules.storage.database
    with db.begin() as conn:
        conn.execute(TASK_RULES.update().where(TASK_RULES.c.rule_id == payload["rule_ids"][0]).values(
            report_category="frozen", source_id="second", source_name="模拟二"))
        conn.execute(TASK_RULES.update().where(TASK_RULES.c.rule_id == payload["rule_ids"][1]).values(report_category=None, source_id=None))
    task, = rules.task_progress(user(), {"report_category": "frozen"})
    assert [c["rule_count"] for c in task["categories"]] == [1, 1]
    assert task["summary"]["rule_count"] == 1
    assert task["sources"] == [{"id": "second", "name": "模拟二", "rule_count": 1}, {"id": "src", "name": "监管报表", "rule_count": 1}]
    assert rules.list_recent_tasks(user(), {"report_category": "frozen"})[0]["id"] == tid
    detail = rules.task_detail(user(), tid, {"report_category": "frozen"})
    assert detail["rules"][0]["rule_id"] == payload["rule_ids"][0]
    assert detail["sources"] == task["sources"]


def test_retry_uses_worker_and_can_pause_without_overwriting_new_generation(batch):
    rules, executor, metadata, payload = batch
    task_id = rules.start_task(user(), payload)["id"]
    original = executor.future
    rules.cancel_task(user(), task_id)
    executor.future = Future()
    assert rules.retry_failed(user(), task_id)["status"] == "queued"
    assert not metadata.calls
    original.cancel()
    assert rules.storage.get_task(task_id)["status"] == "queued"
    assert rules.pause_task(user(), task_id)["status"] == "paused"
    assert rules.retry_failed(user(), task_id)["status"] == "paused"
    executor.future = Future()
    assert rules.resume_task(user(), task_id)["status"] == "queued"
    executor.run()
    assert len(metadata.calls) == 2
    assert rules.storage.get_task(task_id)["status"] == "completed"


def test_late_old_cancellation_cannot_acknowledge_pause_of_new_generation(batch):
    rules, executor, _, payload = batch
    callbacks = []
    original = executor.future
    original.add_done_callback = callbacks.append
    tid = rules.start_task(user(), payload)["id"]
    rules.cancel_task(user(), tid)
    assert original.cancelled()
    executor.future = Future()
    rules.retry_failed(user(), tid)
    assert executor.future.set_running_or_notify_cancel()
    assert rules.pause_task(user(), tid)["status"] == "pausing"
    for callback in callbacks:
        callback(original)
    assert rules.storage.get_task(tid)["status"] == "pausing"
    assert all(r["status"] == "queued" and r["execution_generation"] == 1 for r in rules.storage.task_rules(tid))
    executor.future.set_result(None)
    rules.cancel_task(user(), tid)


def test_large_batch_admission_progress_selection_and_sql_paging(batch):
    rules, executor, metadata, payload = batch
    db = rules.storage.database
    ids = list(range(100, 10100))
    with db.begin() as conn:
        rule = dict(conn.execute(select(RULES).order_by(RULES.c.id)).mappings().first())
        version = dict(conn.execute(select(VERSIONS).where(VERSIONS.c.id == rule["current_version_id"])).mappings().one())
        conn.execute(RULES.insert(), [dict(rule, id=i, current_version_id=i, rule_code=f"DV{i}", name=f"模拟{i}",
                                           report_category="scale") for i in ids])
        conn.execute(VERSIONS.insert(), [dict(version, id=i, rule_id=i) for i in ids])
    filters = {"keyword": "模拟", "source_id": rule["source_id"], "report_category": "scale"}
    assert rules.execution_selection(user(), filters) == {"rule_ids": ids[::-1], "count": 10000}
    assert rules.execution_selection(user("other"), filters)["count"] == 0
    assert rules.execution_selection(user("other", "admin"), filters)["count"] == 10000
    db.sql.clear()
    started = perf_counter()
    response = rules.start_task(user(), {**payload, "rule_ids": ids})
    task_id = response["id"]
    elapsed = perf_counter() - started
    print(f"synthetic admission: 10000 rules in {elapsed:.3f}s, {len(db.sql)} SQL statements")
    assert len(db.sql) < 100
    assert "params_json" not in response and "rule_ids" not in response
    assert not metadata.calls
    with db.begin() as conn:
        assert conn.scalar(select(func.count()).select_from(TASK_RULES).where(TASK_RULES.c.task_id == task_id)) == 10000
        conn.execute(TASK_RULES.update().where(TASK_RULES.c.rule_id.in_(ids[-3:])).values(status="VIOLATION", violation_count=1))
    db.sql.clear()
    started = perf_counter()
    task, = rules.task_progress(user(), {})
    print(f"synthetic progress: {perf_counter() - started:.3f}s, {len(db.sql)} SQL statements")
    assert task["id"] == task_id and task["summary"]["rule_count"] == 10000
    assert task["summary"]["issue_count"] == 3 and task["summary"]["pending_count"] == 9997
    assert len(db.sql) <= 4 and "rules" not in task and "params_json" not in task
    assert rules.task_progress(user("other", "admin"), {"task_ids": str(task_id)}) == []
    db.sql.clear()
    started = perf_counter()
    detail = rules.task_detail(user(), task_id, {"page_size": "20", "page": "500"})
    print(f"synthetic rule page: {perf_counter() - started:.3f}s, {len(db.sql)} SQL statements")
    assert "params_json" not in detail and any("LIMIT" in statement for statement in db.sql)
    assert detail["rule_page"] == {"page": 500, "page_size": 20, "total": 10000}
    assert [r["rule_id"] for r in detail["rules"]] == ids[-20:]
    abnormal = rules.task_detail(user(), task_id, {"only_issues": "true"})
    assert abnormal["rule_page"] == {"page": 1, "page_size": 50, "total": 3}
    assert abnormal["summary"] == task["summary"]
    assert [r["rule_id"] for r in abnormal["rules"]] == ids[-3:]
    for rule_id in ids[-3:]:
        rules.storage.add_issue(task_id=task_id, rule_id=rule_id, version_no=1, business_key=str(rule_id), message="模拟异常")
    db.sql.clear()
    issues = rules.list_task_issues(user(), task_id, {"page": 1, "page_size": 2})
    assert issues["total"] == 3 and len(issues["items"]) == 2 and all(r["rule_name"] for r in issues["items"])
    snapshots = [sql for sql in db.sql if " AS rule_name" in sql]
    assert snapshots and all(" IN (" in sql.partition("WHERE")[-1] and "version_no" in sql.partition("WHERE")[-1] for sql in snapshots)
    scoped = rules.export_issues(user(), task_id, "csv", {"rule_id": ids[-1]})
    assert [r["business_key"] for r in scoped["issues"]] == [str(ids[-1])]
    executor.future.cancel()
    assert rules.task_progress(user(), {}) == []
    assert rules.task_progress(user(), {"task_ids": str(task_id)})[0]["status"] == "cancelled"
