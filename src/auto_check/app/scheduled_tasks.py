"""统一定时任务调度器。

职责：
- 内置任务模板注册
- 存储 CRUD（scheduled_tasks 表）
- 单一后台调度循环
- 状态记录

只允许已注册的内置 task_code，禁止通过 API 配置任意命令、模块路径、SQL 或可执行文本。
删除是物理删除计划记录，当前正在运行的调用允许完成，后续不再调度。
"""

from __future__ import annotations

import logging
import re
import threading
from collections import deque
from datetime import datetime, time as datetime_time, timedelta
from typing import Any, Callable

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    delete,
    insert,
    select,
    update,
)

from auto_check.app.app_database import ApplicationDatabase
from auto_check.app.time_utils import beijing_now


logger = logging.getLogger("auto_check.scheduled_tasks")


METADATA = MetaData()

SCHEDULED_TASKS = Table(
    "scheduled_tasks",
    METADATA,
    Column("task_code", String(64), primary_key=True),
    Column("task_name", String(191), nullable=False),
    Column("schedule_type", String(16), nullable=False),
    Column("interval_minutes", Integer, nullable=True),
    Column("daily_time", String(5), nullable=True),
    Column("enabled", Integer, nullable=False, default=1),
    Column("next_run_at", DateTime(6), nullable=True),
    Column("last_started_at", DateTime(6), nullable=True),
    Column("last_finished_at", DateTime(6), nullable=True),
    Column("last_status", String(16), nullable=True),
    Column("last_error", Text, nullable=True),
    Column("created_at", DateTime(6), nullable=False),
    Column("updated_at", DateTime(6), nullable=False),
)


# Handler functions — each takes the manager and invokes the real service.

def _handle_report_navigation_statistics(manager: "ScheduledTaskManager") -> None:
    manager._report_navigation.collect_once()


def _handle_notification_cleanup(manager: "ScheduledTaskManager") -> None:
    manager._notification_service.cleanup_expired()


def _handle_db_validation_field_mapping_refresh(manager: "ScheduledTaskManager") -> None:
    manager._api_router._refresh_db_validation_field_mapping(source="auto")


#: 内置任务模板注册表。key 为 task_code。
TASK_TEMPLATES: dict[str, dict[str, Any]] = {
    "report_navigation_statistics": {
        "task_name": "报送导航统计",
        "schedule_type": "interval",
        "interval_minutes": 30,
        "daily_time": None,
        "handler": _handle_report_navigation_statistics,
    },
    "notification_cleanup": {
        "task_name": "通知过期清理",
        "schedule_type": "interval",
        "interval_minutes": 360,
        "daily_time": None,
        "handler": _handle_notification_cleanup,
    },
    "db_validation_field_mapping_refresh": {
        "task_name": "逐笔校验字段映射刷新",
        "schedule_type": "daily",
        "interval_minutes": None,
        "daily_time": "00:00",
        "handler": _handle_db_validation_field_mapping_refresh,
    },
}

INITIAL_DELAY_REPORT_NAVIGATION_SECONDS = 30

MAX_INTERVAL_MINUTES = 10080
MIN_INTERVAL_MINUTES = 1


def _parse_daily_time(value: str) -> datetime_time:
    """解析 HH:MM 字符串为 time 对象。"""
    if not isinstance(value, str) or re.fullmatch(r"\d{2}:\d{2}", value.strip()) is None:
        raise ValueError("daily_time 必须是字符串")
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError("daily_time 格式必须为 HH:MM")
    hour = int(parts[0])
    minute = int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("daily_time 格式必须为 HH:MM")
    return datetime_time(hour, minute)


def _compute_next_run_after(
    schedule_type: str,
    interval_minutes: int | None,
    daily_time: datetime_time | None,
    after: datetime,
) -> datetime:
    """根据调度配置，计算 after 之后的下一次执行时间。"""
    if schedule_type == "interval":
        return after + timedelta(minutes=interval_minutes)
    # daily
    candidate = datetime.combine(after.date(), daily_time)
    if candidate <= after:
        candidate = candidate + timedelta(days=1)
    return candidate


def _compute_initial_next_run(
    task_code: str,
    schedule_type: str,
    interval_minutes: int | None,
    daily_time: datetime_time | None,
    now: datetime,
) -> datetime:
    """计算任务首次启动时的 next_run_at。"""
    if task_code == "report_navigation_statistics":
        return now + timedelta(seconds=INITIAL_DELAY_REPORT_NAVIGATION_SECONDS)
    if task_code == "notification_cleanup":
        return now
    return _compute_next_run_after(schedule_type, interval_minutes, daily_time, now)


class ScheduledTaskManager:
    """统一定时任务管理器。"""

    def __init__(
        self,
        database: ApplicationDatabase,
        *,
        report_navigation_service: Any = None,
        notification_service: Any = None,
        api_router: Any = None,
    ) -> None:
        self._database = database
        self._report_navigation = report_navigation_service
        self._notification_service = notification_service
        self._api_router = api_router
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._running_task_code: str | None = None
        self._manual_queue: deque[str] = deque()
        self._wake = threading.Event()

    # ------------------------------------------------------------------
    # Storage CRUD
    # ------------------------------------------------------------------

    def list_tasks(self) -> list[dict[str, Any]]:
        """列出全部定时任务，按 task_code 排序。"""
        with self._database.connect() as connection:
            result = connection.execute(
                select(SCHEDULED_TASKS).order_by(SCHEDULED_TASKS.c.task_code)
            )
            return [dict(row) for row in result.mappings().all()]

    def get_task(self, task_code: str) -> dict[str, Any] | None:
        """按 task_code 查询单个任务。未注册的 task_code 返回 None。"""
        if task_code not in TASK_TEMPLATES:
            return None
        with self._database.connect() as connection:
            result = connection.execute(
                select(SCHEDULED_TASKS).where(SCHEDULED_TASKS.c.task_code == task_code)
            )
            row = result.mappings().first()
            return dict(row) if row else None

    def missing_templates(self) -> list[str]:
        """列出已注册但数据库中缺失的 task_code。"""
        with self._database.connect() as connection:
            result = connection.execute(select(SCHEDULED_TASKS.c.task_code))
            existing = {row["task_code"] for row in result.mappings().all()}
        return sorted(code for code in TASK_TEMPLATES if code not in existing)

    def missing_template_details(self) -> list[dict[str, Any]]:
        return [
            {
                "task_code": code,
                "task_name": TASK_TEMPLATES[code]["task_name"],
            }
            for code in self.missing_templates()
        ]

    def restore_template(self, task_code: str) -> dict[str, Any]:
        """恢复一个缺失的内置任务。"""
        if task_code not in TASK_TEMPLATES:
            raise ValueError(f"未知的任务模板: {task_code}")
        template = TASK_TEMPLATES[task_code]
        now = beijing_now()
        daily_time = template.get("daily_time")
        next_run = _compute_initial_next_run(
            task_code,
            template["schedule_type"],
            template.get("interval_minutes"),
            _parse_daily_time(daily_time) if daily_time else None,
            now,
        )
        with self._database.transaction() as connection:
            existing = connection.execute(
                select(SCHEDULED_TASKS.c.task_code).where(
                    SCHEDULED_TASKS.c.task_code == task_code
                )
            ).mappings().first()
            if existing:
                raise ValueError(f"任务已存在: {task_code}")
            connection.execute(
                insert(SCHEDULED_TASKS).values(
                    task_code=task_code,
                    task_name=template["task_name"],
                    schedule_type=template["schedule_type"],
                    interval_minutes=template.get("interval_minutes"),
                    daily_time=daily_time,
                    enabled=1,
                    next_run_at=next_run,
                    created_at=now,
                    updated_at=now,
                )
            )
        return self.get_task(task_code)

    def update_task(self, task_code: str, **config: Any) -> dict[str, Any]:
        """更新任务的配置。"""
        if task_code not in TASK_TEMPLATES:
            raise ValueError(f"未知的任务码: {task_code}")

        unknown_keys = set(config) - {
            "schedule_type", "interval_minutes", "daily_time", "enabled"
        }
        if unknown_keys:
            raise ValueError(f"不支持的配置项: {', '.join(sorted(unknown_keys))}")

        schedule_type = config.get("schedule_type")
        interval_minutes = config.get("interval_minutes")
        daily_time_str = config.get("daily_time")
        enabled = config.get("enabled")

        if schedule_type is not None and schedule_type not in ("interval", "daily"):
            raise ValueError("schedule_type 必须是 interval 或 daily")
        if interval_minutes is not None:
            if not isinstance(interval_minutes, int) or isinstance(interval_minutes, bool):
                raise ValueError("interval_minutes 必须是整数")
            if not (MIN_INTERVAL_MINUTES <= interval_minutes <= MAX_INTERVAL_MINUTES):
                raise ValueError(
                    f"interval_minutes 必须在 {MIN_INTERVAL_MINUTES}..{MAX_INTERVAL_MINUTES} 范围内"
                )
        if daily_time_str is not None:
            _parse_daily_time(daily_time_str)
        if enabled is not None and not isinstance(enabled, bool):
            raise ValueError("enabled 必须是布尔值")

        with self._database.transaction() as connection:
            existing_row = connection.execute(
                select(SCHEDULED_TASKS).where(SCHEDULED_TASKS.c.task_code == task_code)
            ).mappings().first()
            if not existing_row:
                raise ValueError(f"任务不存在: {task_code}")

            current = dict(existing_row)
            target_schedule_type = schedule_type or current["schedule_type"]
            target_interval = (
                interval_minutes
                if interval_minutes is not None
                else current.get("interval_minutes")
            )
            target_daily_time = (
                daily_time_str
                if daily_time_str is not None
                else current.get("daily_time")
            )
            if target_schedule_type == "interval":
                if not isinstance(target_interval, int) or isinstance(target_interval, bool):
                    raise ValueError("间隔任务必须设置 interval_minutes")
                if not (MIN_INTERVAL_MINUTES <= target_interval <= MAX_INTERVAL_MINUTES):
                    raise ValueError(
                        f"interval_minutes 必须在 {MIN_INTERVAL_MINUTES}..{MAX_INTERVAL_MINUTES} 范围内"
                    )
                target_daily_time = None
            else:
                if not target_daily_time:
                    raise ValueError("每日任务必须设置 daily_time")
                _parse_daily_time(target_daily_time)
                target_interval = None

            updates: dict[str, Any] = {"updated_at": beijing_now()}
            updates["schedule_type"] = target_schedule_type
            updates["interval_minutes"] = target_interval
            updates["daily_time"] = target_daily_time
            if enabled is not None:
                updates["enabled"] = 1 if enabled else 0

            something_changed = (
                enabled is not None
                or schedule_type is not None
                or interval_minutes is not None
                or daily_time_str is not None
            )
            if something_changed:
                if enabled is False:
                    updates["next_run_at"] = None
                else:
                    dt = _parse_daily_time(target_daily_time) if target_daily_time else None
                    updates["next_run_at"] = _compute_next_run_after(
                        target_schedule_type, target_interval, dt, beijing_now()
                    )

            connection.execute(
                update(SCHEDULED_TASKS)
                .where(SCHEDULED_TASKS.c.task_code == task_code)
                .values(**updates)
            )

        return self.get_task(task_code)

    def delete_task(self, task_code: str) -> bool:
        """物理删除计划记录。当前正在运行的调用允许完成，后续不再调度。"""
        if task_code not in TASK_TEMPLATES:
            raise ValueError(f"未知的任务码: {task_code}")
        with self._database.transaction() as connection:
            result = connection.execute(
                delete(SCHEDULED_TASKS).where(SCHEDULED_TASKS.c.task_code == task_code)
            )
            return result.rowcount > 0

    def request_run_now(self, task_code: str) -> dict[str, Any]:
        """把一次手工执行放入统一串行队列，禁用任务也允许手工执行。"""
        if task_code not in TASK_TEMPLATES:
            raise ValueError(f"未知的任务码: {task_code}")
        task = self.get_task(task_code)
        if task is None:
            raise ValueError(f"任务不存在: {task_code}")
        with self._lock:
            if self._running_task_code == task_code or task_code in self._manual_queue:
                raise ValueError("任务正在执行，请勿重复触发")
            self._manual_queue.append(task_code)
        self._wake.set()
        return {"accepted": True, "task_code": task_code}

    # ------------------------------------------------------------------
    # Scheduler
    # ------------------------------------------------------------------

    def _ensure_initial_next_run(self) -> None:
        """为尚未设置 next_run_at 的启用任务计算初始值。"""
        now = beijing_now()
        for task in self.list_tasks():
            if task.get("next_run_at") is not None:
                continue
            if not task.get("enabled"):
                continue
            next_run = _compute_initial_next_run(
                task["task_code"],
                task["schedule_type"],
                task.get("interval_minutes"),
                _parse_daily_time(task["daily_time"]) if task.get("daily_time") else None,
                now,
            )
            with self._database.transaction() as connection:
                connection.execute(
                    update(SCHEDULED_TASKS)
                    .where(SCHEDULED_TASKS.c.task_code == task["task_code"])
                    .values(next_run_at=next_run, updated_at=now)
                )

    def _execute_task(self, task_code: str) -> None:
        """执行单个任务并记录状态。"""
        template = TASK_TEMPLATES.get(task_code)
        if template is None:
            return
        handler = template.get("handler")
        if handler is None:
            return

        now = beijing_now()
        with self._database.transaction() as connection:
            connection.execute(
                update(SCHEDULED_TASKS)
                .where(SCHEDULED_TASKS.c.task_code == task_code)
                .values(
                    last_started_at=now,
                    last_status="running",
                    last_error=None,
                    updated_at=now,
                )
            )

        error_message: str | None = None
        try:
            handler(self)
        except Exception as exc:
            detail = str(exc).strip()
            error_message = (detail or f"任务执行异常: {task_code}")[:2000]
            logger.exception("定时任务执行失败: %s", task_code)

        now = beijing_now()
        with self._database.transaction() as connection:
            if error_message:
                connection.execute(
                    update(SCHEDULED_TASKS)
                    .where(SCHEDULED_TASKS.c.task_code == task_code)
                    .values(
                        last_finished_at=now,
                        last_status="failed",
                        last_error=error_message,
                        updated_at=now,
                    )
                )
            else:
                connection.execute(
                    update(SCHEDULED_TASKS)
                    .where(SCHEDULED_TASKS.c.task_code == task_code)
                    .values(
                        last_finished_at=now,
                        last_status="success",
                        last_error=None,
                        updated_at=now,
                    )
                )

            row = connection.execute(
                select(SCHEDULED_TASKS).where(SCHEDULED_TASKS.c.task_code == task_code)
            ).mappings().first()
            if row and row["enabled"]:
                next_run = _compute_next_run_after(
                    row["schedule_type"],
                    row.get("interval_minutes"),
                    _parse_daily_time(row["daily_time"]) if row.get("daily_time") else None,
                    now,
                )
                connection.execute(
                    update(SCHEDULED_TASKS)
                    .where(SCHEDULED_TASKS.c.task_code == task_code)
                    .values(next_run_at=next_run, updated_at=now)
                )

    def _tick(self) -> None:
        """检查到期任务并顺序执行。"""
        manual_task_code: str | None = None
        with self._lock:
            if self._running_task_code is None and self._manual_queue:
                manual_task_code = self._manual_queue.popleft()
                self._running_task_code = manual_task_code
        if manual_task_code is not None:
            try:
                self._execute_task(manual_task_code)
            finally:
                with self._lock:
                    self._running_task_code = None

        now = beijing_now()
        for task in self.list_tasks():
            if not task.get("enabled"):
                continue
            if task.get("next_run_at") is None:
                continue
            if task["next_run_at"] > now:
                continue
            with self._lock:
                if self._running_task_code is not None:
                    continue
                self._running_task_code = task["task_code"]
            try:
                self._execute_task(task["task_code"])
            finally:
                with self._lock:
                    self._running_task_code = None

    def _run_loop(self) -> None:
        """调度主循环，运行在单一守护线程中。"""
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:
                logger.exception("定时任务调度循环异常")
            self._wake.wait(1.0)
            self._wake.clear()

    def start(self) -> None:
        """启动调度线程。"""
        if self._thread is not None and self._thread.is_alive():
            return
        self._ensure_initial_next_run()
        self._stop.clear()
        self._wake.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="scheduled-tasks-scheduler",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """停止调度线程并安全 join。"""
        self._stop.set()
        self._wake.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._thread = None
