from concurrent.futures import Future, ThreadPoolExecutor
from functools import partial
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from auto_check.modules.data_validation.contracts import AppError
from auto_check.modules.data_validation.module import create_module
from tests.modules.data_validation.support import MemoryDatabase, Metadata, loan_definition, service, user
from tests.modules.data_validation.test_tasks import _enable


class DeferredExecutor:
    def __init__(self):
        self.future = Future()
        self.work = None
        self.reject = False

    def submit(self, fn, /, *args):
        if self.reject:
            raise RuntimeError("executor unavailable")
        self.work = partial(fn, *args)
        return self.future

    def run(self):
        if self.future.set_running_or_notify_cancel():
            try:
                self.future.set_result(self.work())
            except Exception as exc:
                self.future.set_exception(exc)
                raise


@pytest.fixture
def batch(tmp_path, request):
    executor = ThreadPoolExecutor(1) if getattr(request, "param", None) == "thread" else DeferredExecutor()
    metadata, module = Metadata(), create_module()
    ctx = SimpleNamespace(
        background_executor=executor, application_database=MemoryDatabase(),
        services=SimpleNamespace(resolve=lambda name, version: metadata if name == "platform.data_sources" else None),
        config_path=tmp_path / "application.json", logger=Mock(),
    )
    module.start(ctx)
    rules = module._require_service()
    ids = [_enable(rules, user(), loan_definition(name=name))[0]["id"] for name in ("规则甲", "规则乙")]
    metadata.calls.clear()
    try:
        yield rules, executor, metadata, {"rule_ids": ids, "source_id": "src", "report_period": "2026-09-30"}
    finally:
        module.stop()
        if isinstance(executor, ThreadPoolExecutor):
            executor.shutdown()


@pytest.mark.parametrize("batch", ["thread"], indirect=True)
def test_returns_frozen_batch_before_queries_and_exposes_running_rule(batch, monkeypatch):
    rules, executor, metadata, payload = batch
    entered, release = Event(), Event()
    query = metadata.execute_select

    def blocking_query(*args, **kwargs):
        entered.set()
        if not release.wait(10):
            raise TimeoutError
        return query(*args, **kwargs)

    monkeypatch.setattr(metadata, "execute_select", blocking_query)
    with ThreadPoolExecutor(1) as clients:
        response = clients.submit(rules.start_task, user(), payload)
        try:
            assert entered.wait(3)
            task = response.result(timeout=3)
            assert task["status"] == "queued"
            detail = rules.task_detail(user(), task["id"], {})
            assert detail["status"] == "running"
            assert [item["status"] for item in detail["rules"]] == ["running", "queued"]
            assert [item["rule_id"] for item in detail["rules"]] == payload["rule_ids"]
        finally:
            release.set()
    executor.shutdown()
    assert rules.storage.get_task(task["id"])["status"] == "completed"


def test_pending_future_cancellation_finishes_batch(batch):
    rules, executor, metadata, payload = batch
    task = rules.start_task(user(), payload)
    assert [row["status"] for row in rules.storage.task_rules(task["id"])] == ["queued", "queued"]
    executor.future.cancel()
    assert rules.storage.get_task(task["id"])["status"] == "cancelled"
    assert [row["status"] for row in rules.storage.task_rules(task["id"])] == ["CANCELLED", "CANCELLED"]
    assert not metadata.calls


def test_executor_failure_before_worker_entry_finishes_batch(batch):
    rules, executor, metadata, payload = batch
    task = rules.start_task(user(), payload)
    executor.future.set_exception(RuntimeError("worker could not start"))
    assert rules.storage.get_task(task["id"])["status"] == "failed"
    assert {row["error_code"] for row in rules.storage.task_rules(task["id"])} == {"TASK_EXECUTION_ERROR"}
    assert not metadata.calls


def test_old_future_cannot_cancel_claimed_retry(batch):
    rules, executor, _, payload = batch
    task = rules.start_task(user(), payload)
    rules.cancel_task(user(), task["id"])
    claimed = rules.storage.claim_failed_task_rules(task["id"])
    assert len(claimed) == 2
    executor.future.cancel()
    assert rules.storage.get_task(task["id"])["status"] == "running"
    assert [row["status"] for row in rules.storage.task_rules(task["id"])] == ["running", "running"]


def test_rejected_submission_persists_retryable_failed_batch(batch):
    rules, executor, metadata, payload = batch
    executor.reject = True
    with pytest.raises(AppError, match="TASK_EXECUTOR_UNAVAILABLE"):
        rules.start_task(user(), payload)
    task, = rules.storage.list_tasks("1")
    assert task["status"] == "failed"
    assert {row["error_code"] for row in rules.storage.task_rules(task["id"])} == {"TASK_EXECUTOR_UNAVAILABLE"}
    assert not metadata.calls


def test_module_stop_cancels_running_batch_and_skips_next_query(batch, monkeypatch):
    rules, executor, metadata, payload = batch
    entered, release = Event(), Event()
    task = rules.start_task(user(), payload)
    query = metadata.execute_select

    def blocking_query(*args, **kwargs):
        entered.set()
        if not release.wait(3):
            raise TimeoutError
        return query(*args, **kwargs)

    monkeypatch.setattr(metadata, "execute_select", blocking_query)
    with ThreadPoolExecutor(1) as workers:
        worker = workers.submit(executor.run)
        try:
            assert entered.wait(3)
            rules.join()
            assert rules.storage.get_task(task["id"])["status"] == "cancelled"
        finally:
            release.set()
        worker.result(timeout=3)
    assert len(metadata.calls) == 1
    assert [row["status"] for row in rules.storage.task_rules(task["id"])] == ["CANCELLED", "CANCELLED"]


def test_unexpected_worker_failure_finishes_unpublished_snapshots(batch, monkeypatch):
    rules, executor, _, payload = batch
    task = rules.start_task(user(), payload)

    def bad_version(_id):
        raise KeyError("synthetic storage failure")

    monkeypatch.setattr(rules.storage, "get_version_by_id", bad_version)
    executor.run()
    assert rules.storage.get_task(task["id"])["status"] == "failed"
    assert {row["error_code"] for row in rules.storage.task_rules(task["id"])} == {"TASK_EXECUTION_ERROR"}


def test_standalone_join_drains_existing_thread_mode():
    _, rules = service(metadata=Metadata())
    rule, _ = _enable(rules, user())
    rules.inline = False
    rules.gate = Event()
    task = rules.start_task(user(), {"rule_ids": [rule["id"]], "report_period": "2026-09-30"})
    rules.join()
    assert rules.storage.get_task(task["id"])["status"] == "completed"
