from __future__ import annotations

from dataclasses import dataclass, field
import threading
import time
from typing import Any, Callable, Protocol
from urllib.parse import urlencode
from urllib.request import urlopen

from auto_check.app.config import DataSourceConfig, FlowChainConfig, FlowChainStep
from auto_check.app.db import DatabaseClient
from auto_check.app.pbc_import import TableRef, parse_table_ref


@dataclass(frozen=True)
class FlowDefinition:
    id: str
    name: str
    enabled: str = ""


@dataclass(frozen=True)
class FlowPlatformTask:
    id: int
    flow_id: str
    begin_time: str = ""
    end_time: str = ""


@dataclass(frozen=True)
class FlowChainRunContext:
    trigger_type: str
    execute_url: str
    poll_interval_seconds: int
    step_timeout_seconds: int


@dataclass
class FlowChainStepResult:
    flow_id: str
    flow_name: str
    status: str = "pending"
    sp_task_id: int | None = None
    begin_time: str = ""
    end_time: str = ""
    message: str = ""


@dataclass
class FlowChainRunResult:
    chain_id: str
    chain_name: str
    trigger_type: str
    status: str
    steps: list[FlowChainStepResult] = field(default_factory=list)


class FlowGateway(Protocol):
    def find_running_task(self, flow_id: str) -> FlowPlatformTask | None: ...

    def latest_task_id(self) -> int: ...

    def submit_flow(self, execute_url: str, flow_id: str) -> None: ...

    def find_submitted_task(self, flow_id: str, after_id: int) -> FlowPlatformTask | None: ...

    def get_task(self, task_id: int) -> FlowPlatformTask | None: ...


class DatabaseFlowGateway:
    def __init__(self, data_source: DataSourceConfig, *, flow_table: str, task_table: str):
        self.client = DatabaseClient(data_source)
        self.db_type = data_source.db_type
        self.flow_table = _flow_table_ref(data_source, flow_table or "sp_flow").quoted(self.db_type)
        self.task_table = _flow_table_ref(data_source, task_table or "sp_task").quoted(self.db_type)

    def list_flows(self, keyword: str = "", *, limit: int = 500) -> list[FlowDefinition]:
        keyword = str(keyword or "").strip()
        params: list[Any] = []
        where = ""
        if keyword:
            where = "WHERE id LIKE %s OR name LIKE %s"
            pattern = f"%{keyword}%"
            params.extend([pattern, pattern])
        params.append(int(limit))
        rows = self.client.fetch_all(
            f"""
            SELECT id, COALESCE(name, '') AS name, COALESCE(enabled, '') AS enabled
            FROM {self.flow_table}
            {where}
            ORDER BY name, id
            LIMIT %s
            """,
            params,
        )
        return [
            FlowDefinition(id=str(row.get("id", "")), name=str(row.get("name", "")), enabled=str(row.get("enabled", "")))
            for row in rows
        ]

    def find_running_task(self, flow_id: str) -> FlowPlatformTask | None:
        rows = self.client.fetch_all(
            f"""
            SELECT id, flow_id, begin_time, end_time
            FROM {self.task_table}
            WHERE flow_id = %s AND end_time IS NULL
            ORDER BY id DESC
            LIMIT 1
            """,
            (flow_id,),
        )
        return _task_from_row(rows[0]) if rows else None

    def latest_task_id(self) -> int:
        row = self.client.fetch_one(f"SELECT COALESCE(MAX(id), 0) AS id FROM {self.task_table}")
        return int((row or {}).get("id") or 0)

    def submit_flow(self, execute_url: str, flow_id: str) -> None:
        separator = "&" if "?" in execute_url else "?"
        url = f"{execute_url}{separator}{urlencode({'id': flow_id})}"
        with urlopen(url, timeout=30) as response:
            response.read()

    def find_submitted_task(self, flow_id: str, after_id: int) -> FlowPlatformTask | None:
        rows = self.client.fetch_all(
            f"""
            SELECT id, flow_id, begin_time, end_time
            FROM {self.task_table}
            WHERE flow_id = %s AND id > %s
            ORDER BY id ASC
            LIMIT 1
            """,
            (flow_id, after_id),
        )
        return _task_from_row(rows[0]) if rows else None

    def get_task(self, task_id: int) -> FlowPlatformTask | None:
        rows = self.client.fetch_all(
            f"""
            SELECT id, flow_id, begin_time, end_time
            FROM {self.task_table}
            WHERE id = %s
            """,
            (task_id,),
        )
        return _task_from_row(rows[0]) if rows else None


def run_flow_chain(
    chain: FlowChainConfig,
    context: FlowChainRunContext,
    gateway: FlowGateway,
    *,
    cancel_event: threading.Event,
    log: Callable[[str, int | None, str | None], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> FlowChainRunResult:
    if not chain.steps:
        raise ValueError("流程链至少需要配置一个流程")
    if not context.execute_url:
        raise ValueError("流程执行接口地址不能为空")

    results = [
        FlowChainStepResult(flow_id=step.flow_id, flow_name=step.name or step.flow_id)
        for step in chain.steps
    ]
    total = len(results)
    for index, (step, step_result) in enumerate(zip(chain.steps, results), start=1):
        _raise_if_cancelled(cancel_event)
        flow_label = step.name or step.flow_id
        progress_base = int((index - 1) / total * 100)
        _log(log, f"准备执行流程：{flow_label}", progress_base, flow_label)

        running_task = gateway.find_running_task(step.flow_id)
        if running_task is not None:
            step_result.status = "running"
            step_result.sp_task_id = running_task.id
            step_result.begin_time = running_task.begin_time
            _log(log, f"流程已有运行中任务，等待结束：{flow_label} / sp_task.id={running_task.id}", progress_base, flow_label)
            finished_task = _wait_for_task_end(
                gateway,
                running_task,
                context,
                cancel_event=cancel_event,
                sleep=sleep,
                monotonic=monotonic,
            )
        else:
            before_id = gateway.latest_task_id()
            step_result.status = "submitted"
            _log(log, f"提交流程：{flow_label}", progress_base, flow_label)
            gateway.submit_flow(context.execute_url, step.flow_id)
            submitted_task = _wait_for_submitted_task(
                gateway,
                step.flow_id,
                before_id,
                context,
                cancel_event=cancel_event,
                sleep=sleep,
                monotonic=monotonic,
            )
            step_result.sp_task_id = submitted_task.id
            step_result.begin_time = submitted_task.begin_time
            step_result.status = "running"
            _log(log, f"流程已启动：{flow_label} / sp_task.id={submitted_task.id}", min(progress_base + 5, 99), flow_label)
            finished_task = _wait_for_task_end(
                gateway,
                submitted_task,
                context,
                cancel_event=cancel_event,
                sleep=sleep,
                monotonic=monotonic,
            )

        step_result.status = "completed"
        step_result.end_time = finished_task.end_time
        step_result.message = "执行结束"
        _log(log, f"流程执行结束：{flow_label}", int(index / total * 100), flow_label)

    return FlowChainRunResult(
        chain_id=chain.id,
        chain_name=chain.name,
        trigger_type=context.trigger_type,
        status="completed",
        steps=results,
    )


def flow_chain_result_to_dict(result: FlowChainRunResult) -> dict[str, Any]:
    return {
        "chain_id": result.chain_id,
        "chain_name": result.chain_name,
        "trigger_type": result.trigger_type,
        "status": result.status,
        "steps": [
            {
                "flow_id": step.flow_id,
                "flow_name": step.flow_name,
                "status": step.status,
                "sp_task_id": step.sp_task_id,
                "begin_time": step.begin_time,
                "end_time": step.end_time,
                "message": step.message,
            }
            for step in result.steps
        ],
    }


def _wait_for_submitted_task(
    gateway: FlowGateway,
    flow_id: str,
    before_id: int,
    context: FlowChainRunContext,
    *,
    cancel_event: threading.Event,
    sleep: Callable[[float], None],
    monotonic: Callable[[], float],
) -> FlowPlatformTask:
    start = monotonic()
    while True:
        _raise_if_cancelled(cancel_event)
        task = gateway.find_submitted_task(flow_id, before_id)
        if task is not None:
            return task
        if monotonic() - start > context.step_timeout_seconds:
            raise TimeoutError(f"等待流程任务创建超时：{flow_id}")
        sleep(context.poll_interval_seconds)


def _wait_for_task_end(
    gateway: FlowGateway,
    task: FlowPlatformTask,
    context: FlowChainRunContext,
    *,
    cancel_event: threading.Event,
    sleep: Callable[[float], None],
    monotonic: Callable[[], float],
) -> FlowPlatformTask:
    start = monotonic()
    current = task
    while True:
        _raise_if_cancelled(cancel_event)
        if current.end_time:
            return current
        if monotonic() - start > context.step_timeout_seconds:
            raise TimeoutError(f"等待流程执行结束超时：{task.flow_id} / sp_task.id={task.id}")
        sleep(context.poll_interval_seconds)
        refreshed = gateway.get_task(task.id)
        if refreshed is not None:
            current = refreshed


def _task_from_row(row: dict[str, Any]) -> FlowPlatformTask:
    return FlowPlatformTask(
        id=int(row.get("id") or 0),
        flow_id=str(row.get("flow_id") or ""),
        begin_time=str(row.get("begin_time") or ""),
        end_time=str(row.get("end_time") or ""),
    )


def _flow_table_ref(data_source: DataSourceConfig, table_name: str) -> TableRef:
    table_ref = parse_table_ref(table_name)
    if len(table_ref.parts) != 1:
        return table_ref
    qualifier = _default_table_qualifier(data_source)
    if not qualifier:
        return table_ref
    return TableRef(parts=(qualifier, table_ref.parts[0]))


def _default_table_qualifier(data_source: DataSourceConfig) -> str:
    if data_source.db_type == "postgresql":
        return data_source.schema or ""
    if data_source.db_type == "mysql":
        return data_source.schema or data_source.database or ""
    return ""


def _raise_if_cancelled(cancel_event: threading.Event) -> None:
    if cancel_event.is_set():
        raise RuntimeError("流程执行已取消")


def _log(log: Callable[[str, int | None, str | None], None] | None, message: str, progress: int | None, step: str | None) -> None:
    if log is not None:
        log(message, progress, step)
