from __future__ import annotations

import threading

import pytest

from auto_check.app.config import DataSourceConfig, FlowChainConfig, FlowChainStep
from auto_check.app.flow_tool import DatabaseFlowGateway, FlowChainRunContext, FlowPlatformTask, run_flow_chain


class FakeFlowGateway:
    def __init__(self):
        self.max_task_id = 100
        self.calls: list[tuple[str, str]] = []
        self.running: dict[str, list[FlowPlatformTask | None]] = {}
        self.submitted: dict[str, list[FlowPlatformTask | None]] = {}
        self.polls: dict[int, list[FlowPlatformTask]] = {}

    def find_running_task(self, flow_id: str) -> FlowPlatformTask | None:
        self.calls.append(("running", flow_id))
        values = self.running.get(flow_id, [None])
        return values.pop(0) if values else None

    def latest_task_id(self) -> int:
        self.calls.append(("latest", ""))
        return self.max_task_id

    def submit_flow(self, execute_url: str, flow_id: str) -> None:
        self.calls.append(("submit", flow_id))

    def find_submitted_task(self, flow_id: str, after_id: int) -> FlowPlatformTask | None:
        self.calls.append(("submitted", flow_id))
        values = self.submitted.get(flow_id, [None])
        return values.pop(0) if values else None

    def get_task(self, task_id: int) -> FlowPlatformTask | None:
        self.calls.append(("task", str(task_id)))
        values = self.polls.get(task_id, [])
        return values.pop(0) if values else None


def test_database_flow_gateway_uses_data_source_schema_for_default_tables():
    gateway = DatabaseFlowGateway(
        DataSourceConfig(
            db_type="postgresql",
            host="127.0.0.1",
            port=5432,
            database="auto_check_test",
            schema="reg-report-analysis",
            username="postgres",
            password="",
        ),
        flow_table="sp_flow",
        task_table="sp_task",
    )

    assert gateway.flow_table == '"reg-report-analysis"."sp_flow"'
    assert gateway.task_table == '"reg-report-analysis"."sp_task"'


def test_run_flow_chain_waits_for_end_time_before_next_flow():
    gateway = FakeFlowGateway()
    gateway.submitted = {
        "flow-a": [FlowPlatformTask(id=101, flow_id="flow-a", begin_time="2026-06-11 16:35:10", end_time="")],
        "flow-b": [FlowPlatformTask(id=102, flow_id="flow-b", begin_time="2026-06-11 16:36:00", end_time="")],
    }
    gateway.polls = {
        101: [
            FlowPlatformTask(id=101, flow_id="flow-a", begin_time="2026-06-11 16:35:10", end_time=""),
            FlowPlatformTask(id=101, flow_id="flow-a", begin_time="2026-06-11 16:35:10", end_time="2026-06-11 16:35:30"),
        ],
        102: [
            FlowPlatformTask(id=102, flow_id="flow-b", begin_time="2026-06-11 16:36:00", end_time="2026-06-11 16:36:20"),
        ],
    }
    chain = FlowChainConfig(
        id="chain-1",
        name="资管新规1",
        steps=[
            FlowChainStep(flow_id="flow-a", name="流程A"),
            FlowChainStep(flow_id="flow-b", name="流程B"),
        ],
    )

    result = run_flow_chain(
        chain,
        FlowChainRunContext(
            trigger_type="manual",
            execute_url="http://example.test/testRun",
            poll_interval_seconds=0,
            step_timeout_seconds=30,
        ),
        gateway,
        cancel_event=threading.Event(),
        sleep=lambda _seconds: None,
    )

    assert result.status == "completed"
    assert result.trigger_type == "manual"
    assert [step.status for step in result.steps] == ["completed", "completed"]
    assert [step.sp_task_id for step in result.steps] == [101, 102]
    assert gateway.calls.index(("submit", "flow-a")) < gateway.calls.index(("task", "101"))
    assert gateway.calls.index(("task", "101")) < gateway.calls.index(("submit", "flow-b"))


def test_run_flow_chain_times_out_when_task_never_ends():
    gateway = FakeFlowGateway()
    gateway.submitted = {
        "flow-a": [FlowPlatformTask(id=101, flow_id="flow-a", begin_time="2026-06-11 16:35:10", end_time="")],
    }
    gateway.polls = {
        101: [FlowPlatformTask(id=101, flow_id="flow-a", begin_time="2026-06-11 16:35:10", end_time="")],
    }
    chain = FlowChainConfig(
        id="chain-1",
        name="资管新规1",
        steps=[FlowChainStep(flow_id="flow-a", name="流程A")],
    )
    ticks = iter([0.0, 2.0, 4.0])

    with pytest.raises(TimeoutError):
        run_flow_chain(
            chain,
            FlowChainRunContext(
                trigger_type="manual",
                execute_url="http://example.test/testRun",
                poll_interval_seconds=0,
                step_timeout_seconds=1,
            ),
            gateway,
            cancel_event=threading.Event(),
            sleep=lambda _seconds: None,
            monotonic=lambda: next(ticks),
        )
