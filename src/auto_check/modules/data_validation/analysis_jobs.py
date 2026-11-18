"""内存临时 AI 分析任务：不持久化、不触达业务库。

任务只保存当前进程内的候选结果与进度快照，由 ``DataValidationService`` 在
``join``/模块停止时统一取消并回收线程。上游模型 HTTP 调用无法被立即中断，
因此取消是协作式的：标记后阻止后续阶段并丢弃最终结果。
"""

from __future__ import annotations

import copy
import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .contracts import AppError

LOGGER = logging.getLogger("auto_check.modules.data_validation")

MAX_ANALYSES = 64
MAX_ANALYSES_PER_USER = 8
MAX_CONCURRENT_ANALYSES = 8
MAX_CONCURRENT_PER_USER = 2
FINISHED_TTL_SECONDS = 900.0
RUNNING_TTL_SECONDS = 1800.0

_STEP_ORDER = ("semantics", "metadata", "generation")
_STEP_STATUS = {"pending", "running", "completed", "needs_confirmation"}


class AnalysisCancelled(Exception):
    """内部协作取消信号，永不作为对外错误码泄露。"""


@dataclass
class _Step:
    id: str
    status: str = "pending"
    detail: str = ""
    table_name: str | None = None
    field_count: int | None = None
    related_table_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"id": self.id, "status": self.status, "detail": self.detail}
        if self.table_name is not None:
            payload["table_name"] = self.table_name
        if self.field_count is not None:
            payload["field_count"] = int(self.field_count)
        if self.related_table_name is not None:
            payload["related_table_name"] = self.related_table_name
        return payload


@dataclass
class _Job:
    analysis_id: str
    owner_user_id: str
    started_at: float
    steps: list[_Step]
    status: str = "running"
    result: Any = None
    error: dict[str, Any] | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    done: threading.Event = field(default_factory=threading.Event)
    worker: threading.Thread | None = None
    finished_at: float | None = None

    def step(self, step_id: str) -> _Step:
        return self.steps[_STEP_ORDER.index(step_id)]


class AnalysisRegistry:
    """有界内存分析缓存：随机 ID、owner 隔离、并发/TTL 上限、协作取消。"""

    def __init__(
        self,
        *,
        worker: Callable[[dict[str, Any], dict[str, Any], Callable[[dict[str, Any]], None]], Any] | None = None,
        max_total: int = MAX_ANALYSES,
        max_per_user: int = MAX_ANALYSES_PER_USER,
        max_concurrent: int = MAX_CONCURRENT_ANALYSES,
        max_concurrent_per_user: int = MAX_CONCURRENT_PER_USER,
        finished_ttl: float = FINISHED_TTL_SECONDS,
        running_ttl: float = RUNNING_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.worker = worker
        self._max_total = int(max_total)
        self._max_per_user = int(max_per_user)
        self._max_concurrent = int(max_concurrent)
        self._max_concurrent_per_user = int(max_concurrent_per_user)
        self._finished_ttl = float(finished_ttl)
        self._running_ttl = float(running_ttl)
        self._clock = clock
        self._lock = threading.RLock()
        self._jobs: dict[str, _Job] = {}
        self._closed = False

    # ---- 生命周期 -----------------------------------------------------

    def start(self, user: dict[str, Any], payload: dict[str, Any], *, worker=None) -> dict[str, Any]:
        runner = worker or self.worker
        owner = str(user.get("id") or "")
        if runner is None or not owner:
            raise AppError("MODEL_UNAVAILABLE" if runner is None else "FORBIDDEN")
        with self._lock:
            if self._closed:
                raise AppError("ANALYSIS_UNAVAILABLE")
            self._purge_expired()
            active = [job for job in self._jobs.values() if not job.done.is_set()]
            active_user = [job for job in active if job.owner_user_id == owner]
            if len(active) >= self._max_concurrent or len(active_user) >= self._max_concurrent_per_user:
                raise AppError("ANALYSIS_LIMIT_REACHED")
            owned = [job for job in self._jobs.values() if job.owner_user_id == owner]
            if len(self._jobs) >= self._max_total or len(owned) >= self._max_per_user:
                raise AppError("ANALYSIS_LIMIT_REACHED")
            job = _Job(
                analysis_id=secrets.token_urlsafe(24),
                owner_user_id=owner,
                started_at=self._clock(),
                steps=[
                    _Step("semantics", "running", "正在解析业务语义与选表范围"),
                    _Step("metadata"),
                    _Step("generation"),
                ],
            )
            thread = threading.Thread(
                target=self._run, args=(job, user, payload, runner),
                name=f"dv-analysis-{job.analysis_id[:8]}", daemon=True,
            )
            job.worker = thread
            self._jobs[job.analysis_id] = job
            thread.start()
            return self.snapshot(job)

    def get(self, user: dict[str, Any], analysis_id: str) -> dict[str, Any]:
        with self._lock:
            self._purge_expired()
            return self.snapshot(self._require(user, analysis_id))

    def cancel(self, user: dict[str, Any], analysis_id: str) -> dict[str, Any]:
        with self._lock:
            self._purge_expired()
            job = self._require(user, analysis_id)
            if job.status == "running":
                # 只做协作标记：无法假装已经中止正在进行的上游 HTTP 调用。
                job.cancel_event.set()
                job.status = "cancelled"
                if job.finished_at is None:
                    job.finished_at = self._clock()
            return self.snapshot(job)

    def active_count(self) -> int:
        """尚未退出的 worker 数（含已标记取消但上游调用未返回的任务）。"""
        with self._lock:
            return sum(1 for job in self._jobs.values() if not job.done.is_set())

    def join(self, timeout: float = 3.0) -> None:
        with self._lock:
            threads = [job.worker for job in self._jobs.values() if job.worker is not None]
        deadline = time.monotonic() + max(float(timeout), 0.0)
        for thread in threads:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            thread.join(remaining)

    def close(self, timeout: float = 3.0) -> None:
        with self._lock:
            self._closed = True
            for job in self._jobs.values():
                if not job.done.is_set():
                    job.cancel_event.set()
                    if job.status == "running":
                        job.status = "cancelled"
                    if job.finished_at is None:
                        job.finished_at = self._clock()
        self.join(timeout)

    # ---- 内部 ---------------------------------------------------------

    def _require(self, user: dict[str, Any], analysis_id: str) -> _Job:
        owner = str(user.get("id") or "")
        job = self._jobs.get(str(analysis_id))
        # 未知 ID 与跨用户访问返回同一错误，避免探测他人任务是否存在。
        if job is None or not owner or job.owner_user_id != owner:
            raise AppError("FORBIDDEN")
        return job

    def _observe(self, job: _Job, event: dict[str, Any]) -> None:
        with self._lock:
            # 必须先判取消：cancel() 会立刻把状态改成 cancelled；若先判状态，
            # 进行中的第二阶段回调会静默返回并继续调用上游模型。
            if job.cancel_event.is_set():
                raise AnalysisCancelled()
            if job.status != "running":
                return
            step_id = str(event.get("step") or "")
            status = str(event.get("status") or "")
            if step_id not in _STEP_ORDER or status not in _STEP_STATUS:
                raise AppError("ANALYSIS_FAILED")
            step = job.step(step_id)
            step.status = status
            step.detail = str(event.get("detail") or "")
            for key in ("table_name", "field_count", "related_table_name"):
                value = event.get(key)
                if value is not None:
                    setattr(step, key, value)

    def _run(self, job: _Job, user: dict[str, Any], payload: dict[str, Any], runner: Callable) -> None:
        result: Any = None
        try:
            result = runner(user, payload, lambda event: self._observe(job, event))
        except AnalysisCancelled:
            with self._lock:
                if job.status == "running":
                    job.status = "cancelled"
        except AppError as exc:
            with self._lock:
                if job.status == "running":
                    job.status = "failed"
                    job.error = {"code": exc.code}
                    if exc.reference:
                        job.error["reference"] = str(exc.reference)
                    # 只保留中文界面已支持的安全阶段名，避免泄漏内部阶段。
                    if str(exc.stage) in {"select_table", "generate_rule", "test_model"}:
                        job.error["stage"] = str(exc.stage)
        except BaseException as error:
            # Never log exception text: upstream errors can contain credentials or prompts.
            reference = secrets.token_hex(6)
            LOGGER.warning("AI analysis failed reference=%s type=%s", reference, type(error).__name__)
            with self._lock:
                if job.status == "running":
                    job.status = "failed"
                    job.error = {"code": "ANALYSIS_FAILED", "reference": reference}
        finally:
            with self._lock:
                if job.status == "running":
                    if job.cancel_event.is_set():
                        job.status = "cancelled"
                    else:
                        job.status = "completed"
                        job.result = result
                        # worker 正常返回但把某步留在 running：收敛为 completed；
                        # pending（如选表澄清后的后续步骤）保持 pending，不代为打勾。
                        for step in job.steps:
                            if step.status == "running":
                                step.status = "completed"
                if job.finished_at is None:
                    job.finished_at = self._clock()
                job.done.set()

    def snapshot(self, job: _Job) -> dict[str, Any]:
        with self._lock:
            ended = job.finished_at if job.finished_at is not None else self._clock()
            elapsed_ms = max(0, int((ended - job.started_at) * 1000))
            payload: dict[str, Any] = {
                "analysis_id": job.analysis_id,
                "status": job.status,
                "steps": [step.to_dict() for step in job.steps],
                "elapsed_ms": elapsed_ms,
            }
            if job.result is not None:
                payload["result"] = copy.deepcopy(job.result)
            if job.error is not None:
                payload["error"] = copy.deepcopy(job.error)
            return payload

    def _purge_expired(self) -> None:
        now = self._clock()
        for analysis_id, job in list(self._jobs.items()):
            if job.done.is_set():
                if job.finished_at is not None and now - job.finished_at > self._finished_ttl:
                    del self._jobs[analysis_id]
                continue
            if now - job.started_at > self._running_ttl:
                job.cancel_event.set()
                if job.status == "running":
                    job.status = "cancelled"
                if job.finished_at is None:
                    job.finished_at = now
