"""协调模块执行器的受理、暂停和停用，持久化状态由规则快照的执行代保护。"""

import logging
import threading
from concurrent.futures import Future
from typing import Callable

from auto_check.app.module_system.contracts import ModuleTaskExecutor

from .contracts import AppError
from .storage import RuleStorage


class ExecutionJobs:
    def __init__(self, storage: RuleStorage, executor: ModuleTaskExecutor | None) -> None:
        self.storage = storage
        self.executor = executor
        self.stopping = threading.Event()
        self._lock = threading.Lock()
        self._futures: dict[tuple[int, int], Future] = {}

    def submit(self, task_id: int, generation: int, run: Callable[[int, int], None], *, resume: bool) -> None:
        key = (task_id, generation)

        def execute() -> None:
            try:
                run(task_id, generation)
            except Exception as exc:
                logging.getLogger(__name__).error("校验任务执行失败 task_id=%s type=%s", task_id, type(exc).__name__)
                self.storage.finish_execution(task_id, generation, "ERROR", "TASK_EXECUTION_ERROR")

        def completed(future: Future) -> None:
            with self._lock:
                if self._futures.get(key) is future:
                    self._futures.pop(key)
            if future.cancelled():
                if not self.storage.transition_task(task_id, ("pausing",), "paused", generation=generation):
                    self.storage.finish_execution(task_id, generation, "CANCELLED")
            elif future.exception() is not None:
                self.storage.finish_execution(task_id, generation, "ERROR", "TASK_EXECUTION_ERROR")
            else:
                self.storage.transition_task(task_id, ("pausing",), "paused", generation=generation)

        try:
            with self._lock:
                if self.stopping.is_set() or self.executor is None:
                    raise RuntimeError("module execution unavailable")
                future = self.executor.submit(execute)
                self._futures[key] = future
        except Exception as exc:
            if resume:
                self.storage.transition_task(task_id, ("queued", "pausing"), "paused", generation=generation)
            elif self.stopping.is_set():
                self.storage.finish_execution(task_id, generation, "CANCELLED")
            else:
                self.storage.finish_execution(task_id, generation, "ERROR", "TASK_EXECUTOR_UNAVAILABLE")
            raise AppError("TASK_EXECUTOR_UNAVAILABLE") from exc
        future.add_done_callback(completed)
        # 批次创建到本次提交间已可被另一请求发现并暂停或停止。
        if not future.done() and not future.running():
            state = self.storage.get_task(task_id, with_params=False)["status"]
            if state in {"pausing", "cancelled"}:
                future.cancel()

    def interrupt(self, task_id: int, *, pause: bool) -> None:
        with self._lock:
            if pause:
                if not self.storage.transition_task(task_id, ("queued", "running"), "pausing"):
                    return
            else:
                self.storage.cancel_task(task_id)
            futures = [future for (tid, _), future in self._futures.items() if tid == task_id]
        for future in futures:
            future.cancel()

    def close(self) -> None:
        with self._lock:
            self.stopping.set()
            active = tuple(self._futures)
        for task_id, generation in active:
            self.storage.finish_execution(task_id, generation, "CANCELLED")
