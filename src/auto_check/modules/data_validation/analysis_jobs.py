"""内存临时 AI 分析任务：不持久化、不触达业务库。

任务只保存当前进程内的候选结果与进度快照，由 ``DataValidationService`` 在
``join``/模块停止时统一取消并回收线程。每项任务的取消信号贯穿两个模型阶段。
"""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
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
ANALYSIS_TIMEOUT_SECONDS = 180.0
MAX_MODEL_ROUNDS = 4

_STEP_ORDER = ("semantics", "metadata", "generation")
_STEP_STATUS = {"pending", "running", "completed", "needs_confirmation"}


class AnalysisCancelled(Exception):
    """内部协作取消信号，永不作为对外错误码泄露。"""


class AnalysisControl(threading.Event):
    """One cancellation signal shared by all model rounds and the transport's socket monitor."""

    def __init__(self, clock, deadline, model_progress=None, *, analysis_id=None, external_event=None):
        super().__init__()
        self.clock = clock
        self.deadline = deadline
        self.model_progress = model_progress
        self.call_deadline = deadline
        self.analysis_id = analysis_id or secrets.token_hex(6)
        self.external_event = external_event
        self.model_round = 0
        self.output_tokens_used = 0
        self._limit_failure = None
        self._optional_call = False

    def is_set(self):
        return (super().is_set() or (self.external_event is not None and self.external_event.is_set())
                or self._limit_failure is not None or self.clock() >= self.call_deadline)

    def wait(self, timeout=None):
        if self.is_set():
            return True
        remaining = max(0, self.call_deadline - self.clock())
        event = self.external_event if self.external_event is not None else super()
        event.wait(remaining if timeout is None else min(timeout, remaining))
        return self.is_set()

    def check(self, stage=""):
        if super().is_set() or (self.external_event is not None and self.external_event.is_set()):
            raise AnalysisCancelled()
        if self._limit_failure is not None:
            code, stage, reference = self._limit_failure
            raise AppError(code, stage=stage, reference=reference)
        now = self.clock()
        if now >= self.deadline:
            raise self.limit_error("ANALYSIS_TIMEOUT", stage)
        if now >= self.call_deadline:
            if self._optional_call:
                raise AppError("MODEL_TIMEOUT", stage=stage)
            raise self.limit_error("MODEL_TIMEOUT", stage)

    def limit_error(self, code, stage):
        reference = ""
        # The registry attaches the reference when it selects an asynchronous terminal state.
        if self.model_progress is None:
            reference = secrets.token_hex(6)
            phase = "model_wait" if stage else "local_check"
            LOGGER.warning("AI analysis limit code=%s analysis=%s round=%d phase=%s reference=%s",
                           code, self.analysis_id, self.model_round, phase, reference)
        self._limit_failure = code, stage, reference
        return AppError(code, stage=stage, reference=reference)

    @contextmanager
    def model_call(self, stage, public_stage, timeout):
        self.check(public_stage)
        if self.model_round >= MAX_MODEL_ROUNDS:
            raise self.limit_error("ANALYSIS_ROUND_LIMIT", public_stage)
        self.model_round += 1
        started = self.clock()
        self._optional_call = stage == "supplement_suggestions"
        self.call_deadline = min(self.deadline, started + timeout)
        try:
            if self.model_progress:
                self.model_progress(stage, "model_wait")
            try:
                self.check(public_stage)
                yield self.call_deadline - started
            finally:
                # A transport can report an interrupted socket or even return a late
                # reply. Preserve the reason before restoring the overall deadline.
                self.check(public_stage)
            if self.model_progress:
                self.model_progress(stage, "local_check")
        finally:
            self.call_deadline = self.deadline
            self._optional_call = False


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
    last_poll_at: float
    steps: list[_Step]
    status: str = "running"
    result: Any = None
    error: dict[str, Any] | None = None
    cancel_event: AnalysisControl = field(kw_only=True)
    activity: dict[str, Any] = field(default_factory=dict)
    model_round: int = 0
    revision_of: str | None = None
    done: threading.Event = field(default_factory=threading.Event)
    worker: threading.Thread | None = None
    expiry_timer: threading.Timer | None = None
    publication_lock: Any = field(default_factory=threading.RLock)
    finished_at: float | None = None

    def step(self, step_id: str) -> _Step:
        return self.steps[_STEP_ORDER.index(step_id)]

    @property
    def executing(self) -> bool:
        return self.worker is not None and self.worker.ident is not None and not self.done.is_set()

    def finish(self, now: float) -> None:
        if self.expiry_timer is not None:
            self.expiry_timer.cancel()
            self.expiry_timer = None
        self.worker = None
        self.finished_at = now
        self.cancel_event.model_progress = None
        self.done.set()


class AnalysisRegistry:
    """有界内存分析缓存：随机 ID、owner 隔离、并发/TTL 上限、协作取消。"""

    def __init__(
        self,
        *,
        worker: Callable[[dict[str, Any], dict[str, Any], Callable[[dict[str, Any]], None], threading.Event], Any] | None = None,
        max_total: int = MAX_ANALYSES,
        max_per_user: int = MAX_ANALYSES_PER_USER,
        max_concurrent: int = MAX_CONCURRENT_ANALYSES,
        max_concurrent_per_user: int = MAX_CONCURRENT_PER_USER,
        finished_ttl: float = FINISHED_TTL_SECONDS,
        running_ttl: float = RUNNING_TTL_SECONDS,
        analysis_timeout: float = ANALYSIS_TIMEOUT_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.worker = worker
        self._max_total = int(max_total)
        self._max_per_user = int(max_per_user)
        self._max_concurrent = int(max_concurrent)
        self._max_concurrent_per_user = int(max_concurrent_per_user)
        self._finished_ttl = float(finished_ttl)
        self._running_ttl = float(running_ttl)
        self._analysis_timeout = float(analysis_timeout)
        self._clock = clock
        self._lock = threading.RLock()
        self._jobs: dict[str, _Job] = {}
        self._closed = False

    # ---- 生命周期 -----------------------------------------------------

    def request_control(self, cancel_event):
        if isinstance(cancel_event, AnalysisControl):
            return cancel_event
        return AnalysisControl(self._clock, self._clock() + self._analysis_timeout, external_event=cancel_event)

    def start(self, user: dict[str, Any], payload: dict[str, Any], *, worker=None,
              await_first_poll: bool = False) -> dict[str, Any]:
        runner = worker or self.worker
        owner = str(user.get("id") or "")
        if runner is None or not owner:
            raise AppError("MODEL_UNAVAILABLE" if runner is None else "FORBIDDEN")
        with self._lock:
            if self._closed:
                raise AppError("ANALYSIS_UNAVAILABLE")
            self._purge_expired()
            if self._at_worker_limit(owner):
                raise AppError("ANALYSIS_LIMIT_REACHED")
            revision = payload.get("revision_of")
            revision = revision if isinstance(revision, str) else None
            self._make_snapshot_room(owner, revision)
            now = self._clock()
            analysis_id = secrets.token_urlsafe(24)
            job = _Job(
                analysis_id=analysis_id,
                owner_user_id=owner,
                started_at=now,
                last_poll_at=now,
                cancel_event=AnalysisControl(self._clock, now + self._analysis_timeout,
                                             lambda stage, phase: self._model_progress(job, stage, phase),
                                             analysis_id=analysis_id),
                activity={"phase": "preparing", "detail": "分析任务已创建", "elapsed_ms": 0},
                revision_of=revision,
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
            self._schedule_expiry(job, min(self._running_ttl, self._analysis_timeout))
            if not await_first_poll:
                thread.start()
            return self.snapshot(job)

    def get(self, user: dict[str, Any], analysis_id: str) -> dict[str, Any]:
        with self._lock:
            self._purge_expired()
            job = self._require(user, analysis_id)
            if job.status == "running":
                job.last_poll_at = self._clock()
                if job.worker is not None and job.worker.ident is None:
                    if self._at_worker_limit(job.owner_user_id):
                        job.status = "failed"
                        job.error = {"code": "ANALYSIS_LIMIT_REACHED"}
                        job.finish(self._clock())
                    else:
                        job.worker.start()
            return self.snapshot(job)

    def cancel(self, user: dict[str, Any], analysis_id: str) -> dict[str, Any]:
        with self._lock:
            self._purge_expired()
            job = self._require(user, analysis_id)
        with job.publication_lock:
            with self._lock:
                self._request_cancel(job)
        # 通常断开套接字后 worker 即退出。较慢的清理通过同一任务继续报告。
        job.done.wait(0.25)
        return self.snapshot(job)

    def completed_result(self, user: dict[str, Any], analysis_id: str) -> dict[str, Any] | None:
        """Previous choices belong to the job owner even though documented memories are shared."""
        with self._lock:
            self._purge_expired()
            job = self._jobs.get(analysis_id)
            if (job and job.status == "completed" and job.owner_user_id == str(user.get("id") or "")
                    and isinstance(job.result, dict)):
                return copy.deepcopy(job.result)
        return None

    def publish_result(self, cancel_event: threading.Event | None, result: dict, publish: Callable[[], None]) -> None:
        """Commit reusable results and complete their job at one cancellation boundary."""
        with self._lock:
            job = next((job for job in self._jobs.values() if job.cancel_event is cancel_event), None)
        with job.publication_lock if job is not None else nullcontext():
            with self._lock:
                if job is not None:
                    self._expire_if_due(job)
                if isinstance(cancel_event, AnalysisControl):
                    cancel_event.check()
                elif cancel_event is not None and cancel_event.is_set():
                    raise AnalysisCancelled()
                if job is not None and job.status != "running":
                    raise AnalysisCancelled()
                if job is not None:
                    self._activity(job, "publishing", "正在保存分析结果")
            publish()
            with self._lock:
                if job is not None:
                    job.result = result
                    job.status = "completed"
                    for step in job.steps:
                        if step.status == "running":
                            step.status = "completed"

    def active_count(self) -> int:
        """尚未退出的 worker 数（含已标记取消但上游调用未返回的任务）。"""
        with self._lock:
            return sum(job.executing for job in self._jobs.values())

    def join(self, timeout: float = 3.0) -> None:
        with self._lock:
            threads = [job.worker for job in self._jobs.values() if job.executing]
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
                self._request_cancel(job)
        self.join(timeout)

    # ---- 内部 ---------------------------------------------------------

    def _at_worker_limit(self, owner: str) -> bool:
        active = [job for job in self._jobs.values() if job.executing]
        owner_active = sum(job.owner_user_id == owner for job in active)
        if len(active) >= self._max_concurrent or owner_active >= self._max_concurrent_per_user:
            LOGGER.warning("AI analysis capacity reached reason=workers active=%s owner_active=%s",
                           len(active), owner_active)
            return True
        return False

    def _make_snapshot_room(self, owner: str, revision: str | None) -> None:
        jobs = self._jobs.values()
        owner_full = sum(job.owner_user_id == owner for job in jobs) >= self._max_per_user
        if not owner_full and len(self._jobs) < self._max_total:
            return
        # Preserve revision sources that workers still need, including this new request.
        protected = {(job.owner_user_id, job.revision_of) for job in jobs if not job.done.is_set()}
        protected.add((owner, revision))
        finished = (job for job in jobs if job.done.is_set() and (not owner_full or job.owner_user_id == owner)
                    and (job.owner_user_id, job.analysis_id) not in protected)
        oldest = min(finished, key=lambda job: job.finished_at, default=None)
        if oldest is None:
            LOGGER.warning("AI analysis capacity reached reason=snapshots retained=%s owner_full=%s",
                           len(self._jobs), owner_full)
            raise AppError("ANALYSIS_LIMIT_REACHED")
        del self._jobs[oldest.analysis_id]

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
            self._activity(job, "local_check", step.detail)
            for key in ("table_name", "field_count", "related_table_name"):
                value = event.get(key)
                if value is not None:
                    setattr(step, key, value)

    def _activity(self, job, phase, detail):
        job.activity = {"phase": phase, "detail": detail, "round_number": job.model_round,
                        "elapsed_ms": max(0, int((self._clock() - job.started_at) * 1000))}

    def _model_progress(self, job, stage, phase):
        with self._lock:
            if job.status != "running":
                raise AnalysisCancelled()
            if phase == "model_wait":
                job.model_round = job.cancel_event.model_round
            purpose = {"select_table": "选择校验对象", "select_and_generate": "选择校验对象并生成草稿",
                       "repair_json": "重新请求完整的结构化回复",
                       "review_interpretations": "复核文档中的备选口径", "repair_rule": "修正规则草稿",
                       "generate_rule": "生成规则草稿", "supplement_suggestions": "生成补充建议"}.get(stage, "分析需求")
            detail = f"等待模型返回（{purpose}）" if phase == "model_wait" else "模型已返回，正在本地核对结果"
            self._activity(job, phase, detail)

    def _run(self, job: _Job, user: dict[str, Any], payload: dict[str, Any], runner: Callable) -> None:
        result: Any = None
        try:
            if job.cancel_event.is_set():
                raise AnalysisCancelled()
            result = runner(user, payload, lambda event: self._observe(job, event), job.cancel_event)
        except AnalysisCancelled:
            with self._lock:
                self._expire_if_due(job)
                if job.status == "running":
                    job.status = "cancelled"
        except AppError as exc:
            with self._lock:
                self._expire_if_due(job)
                if job.status == "running":
                    job.status = "failed"
                    job.error = (self._budget_error(job, exc.code)
                                 if not exc.reference and exc.code in {"MODEL_TIMEOUT", "ANALYSIS_ROUND_LIMIT"}
                                 else {"code": exc.code})
                    if exc.reference:
                        job.error["reference"] = str(exc.reference)
                    # 只保留中文界面已支持的安全阶段名，避免泄漏内部阶段。
                    if str(exc.stage) in {"select_table", "generate_rule", "test_model"}:
                        job.error["stage"] = str(exc.stage)
        except BaseException as error:
            # Never log exception text: upstream errors can contain credentials or prompts.
            reference = secrets.token_hex(6)
            with self._lock:
                if job.status == "running":
                    LOGGER.warning("AI analysis failed reference=%s type=%s", reference, type(error).__name__)
                    job.status = "failed"
                    job.error = {"code": "ANALYSIS_FAILED", "reference": reference}
        finally:
            with self._lock:
                self._expire_if_due(job)
                if job.status == "cancelling":
                    job.status = "cancelled"
                elif job.status == "running":
                    job.status = "completed"
                    job.result = result
                    for step in job.steps:
                        if step.status == "running":
                            step.status = "completed"
                job.finish(self._clock())

    def snapshot(self, job: _Job) -> dict[str, Any]:
        with self._lock:
            ended = job.finished_at if job.finished_at is not None else self._clock()
            elapsed_ms = max(0, int((ended - job.started_at) * 1000))
            payload: dict[str, Any] = {
                "analysis_id": job.analysis_id,
                "status": job.status,
                "steps": [step.to_dict() for step in job.steps],
                "elapsed_ms": elapsed_ms,
                "activity": job.activity.copy(),
                "timeout_ms": int(self._analysis_timeout * 1000),
            }
            if job.result is not None:
                payload["result"] = copy.deepcopy(job.result)
            if job.error is not None:
                payload["error"] = copy.deepcopy(job.error)
            return payload

    @staticmethod
    def _budget_error(job, code):
        reference = secrets.token_hex(6)
        LOGGER.warning("AI analysis limit code=%s analysis=%s round=%d phase=%s reference=%s",
                       code, job.analysis_id[:8], job.model_round, job.activity.get("phase"), reference)
        return {"code": code, "reference": reference}

    def _request_cancel(self, job: _Job, *, timed_out: bool = False) -> None:
        # Publication is the completion boundary. Never wait for its database write
        # while holding the registry lock used by other users' jobs.
        if not job.publication_lock.acquire(blocking=False):
            return
        try:
            if job.status == "running":
                if timed_out:
                    job.status = "failed"
                    job.error = AnalysisRegistry._budget_error(job, "ANALYSIS_TIMEOUT")
                else:
                    job.status = "cancelling"
                job.cancel_event.set()
                if not job.executing:
                    if job.status == "cancelling":
                        job.status = "cancelled"
                    job.finish(self._clock())
        finally:
            job.publication_lock.release()

    def _schedule_expiry(self, job: _Job, delay: float) -> None:
        timer = threading.Timer(delay, self._expire_if_abandoned, args=(job,))
        timer.daemon = True
        job.expiry_timer = timer
        timer.start()

    def _expire_if_abandoned(self, job: _Job) -> None:
        with self._lock:
            remaining = self._expire_if_due(job)
            if job.status == "running" and remaining > 0:
                self._schedule_expiry(job, remaining)

    def _expire_if_due(self, job: _Job) -> float:
        now = self._clock()
        remaining = min(job.cancel_event.deadline - now, job.last_poll_at + self._running_ttl - now)
        if job.status == "running" and remaining <= 0:
            self._request_cancel(job, timed_out=now >= job.cancel_event.deadline)
        return remaining

    def _purge_expired(self) -> None:
        now = self._clock()
        for analysis_id, job in list(self._jobs.items()):
            if job.done.is_set():
                if job.finished_at is not None and now - job.finished_at > self._finished_ttl:
                    del self._jobs[analysis_id]
                continue
            self._expire_if_due(job)
