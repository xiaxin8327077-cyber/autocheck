"""统一定时任务调度器单元测试。

覆盖：规则校验、列表/恢复/配置/删除、首次 next_run_at、成功/失败状态、
关闭不会残留线程、能力码。
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest

from auto_check.app.scheduled_tasks import (
    MAX_INTERVAL_MINUTES,
    MIN_INTERVAL_MINUTES,
    ScheduledTaskManager,
    TASK_TEMPLATES,
    _compute_initial_next_run,
    _parse_daily_time,
)
from auto_check.app.capabilities import (
    ADMIN_ONLY_CAPABILITIES,
    CAPABILITY_DEFINITIONS,
    DEFAULT_MATRIX,
    has_capability,
    is_admin_only,
)
from auto_check.app.time_utils import beijing_now
from mysql_config_test_support import MemoryApplicationDatabase


def _make_database() -> MemoryApplicationDatabase:
    """创建预置了 3 个内置任务的内存数据库。"""
    db = MemoryApplicationDatabase()
    now = beijing_now()
    db.connection.tables["scheduled_tasks"] = [
        {
            "task_code": "report_navigation_statistics",
            "task_name": "报送导航统计",
            "schedule_type": "interval",
            "interval_minutes": 30,
            "daily_time": None,
            "enabled": 1,
            "next_run_at": None,
            "last_started_at": None,
            "last_finished_at": None,
            "last_status": None,
            "last_error": None,
            "created_at": now,
            "updated_at": now,
        },
        {
            "task_code": "notification_cleanup",
            "task_name": "通知过期清理",
            "schedule_type": "interval",
            "interval_minutes": 360,
            "daily_time": None,
            "enabled": 1,
            "next_run_at": None,
            "last_started_at": None,
            "last_finished_at": None,
            "last_status": None,
            "last_error": None,
            "created_at": now,
            "updated_at": now,
        },
        {
            "task_code": "db_validation_field_mapping_refresh",
            "task_name": "逐笔校验字段映射刷新",
            "schedule_type": "daily",
            "interval_minutes": None,
            "daily_time": "00:00",
            "enabled": 1,
            "next_run_at": None,
            "last_started_at": None,
            "last_finished_at": None,
            "last_status": None,
            "last_error": None,
            "created_at": now,
            "updated_at": now,
        },
    ]
    return db


def _make_manager(
    database: MemoryApplicationDatabase | None = None,
) -> tuple[ScheduledTaskManager, MagicMock, MagicMock, MagicMock]:
    """创建带 mock 服务的 ScheduledTaskManager。"""
    db = database or _make_database()
    report_nav = MagicMock()
    notification_svc = MagicMock()
    api_router = MagicMock()
    manager = ScheduledTaskManager(
        db,
        report_navigation_service=report_nav,
        notification_service=notification_svc,
        api_router=api_router,
    )
    return manager, report_nav, notification_svc, api_router


# ------------------------------------------------------------------
# 能力码
# ------------------------------------------------------------------


def test_scheduled_tasks_capability_registered():
    assert "sys.scheduled_tasks" in CAPABILITY_DEFINITIONS
    assert CAPABILITY_DEFINITIONS["sys.scheduled_tasks"]["label"] == "定时任务管理"


def test_scheduled_tasks_is_admin_only():
    assert "sys.scheduled_tasks" in ADMIN_ONLY_CAPABILITIES
    assert is_admin_only("sys.scheduled_tasks") is True


def test_scheduled_tasks_admin_has_capability():
    assert has_capability("admin", "sys.scheduled_tasks") is True


def test_scheduled_tasks_user_has_no_capability():
    assert has_capability("user", "sys.scheduled_tasks") is False
    assert DEFAULT_MATRIX["user"]["sys.scheduled_tasks"] is False
    assert DEFAULT_MATRIX["admin"]["sys.scheduled_tasks"] is True


# ------------------------------------------------------------------
# 列表 / 缺失模板
# ------------------------------------------------------------------


def test_list_tasks_returns_all_preset_tasks():
    manager, *_ = _make_manager()
    tasks = manager.list_tasks()
    assert len(tasks) == 3
    codes = {t["task_code"] for t in tasks}
    assert codes == set(TASK_TEMPLATES)


def test_missing_templates_empty_when_all_present():
    manager, *_ = _make_manager()
    assert manager.missing_templates() == []


def test_missing_templates_detects_deleted_task():
    db = _make_database()
    # 删除一个任务
    db.connection.tables["scheduled_tasks"] = [
        t for t in db.connection.tables["scheduled_tasks"]
        if t["task_code"] != "notification_cleanup"
    ]
    manager, *_ = _make_manager(db)
    assert manager.missing_templates() == ["notification_cleanup"]


# ------------------------------------------------------------------
# 恢复内置任务
# ------------------------------------------------------------------


def test_restore_missing_template():
    db = _make_database()
    db.connection.tables["scheduled_tasks"] = [
        t for t in db.connection.tables["scheduled_tasks"]
        if t["task_code"] != "notification_cleanup"
    ]
    manager, *_ = _make_manager(db)
    restored = manager.restore_template("notification_cleanup")
    assert restored is not None
    assert restored["task_code"] == "notification_cleanup"
    assert restored["task_name"] == "通知过期清理"
    assert restored["enabled"] == 1
    assert restored["next_run_at"] is not None
    assert manager.missing_templates() == []


def test_restore_unknown_template_raises():
    manager, *_ = _make_manager()
    with pytest.raises(ValueError, match="未知的任务模板"):
        manager.restore_template("nonexistent_task")


def test_restore_existing_template_raises():
    manager, *_ = _make_manager()
    with pytest.raises(ValueError, match="任务已存在"):
        manager.restore_template("notification_cleanup")


# ------------------------------------------------------------------
# 配置校验
# ------------------------------------------------------------------


def test_update_task_invalid_schedule_type():
    manager, *_ = _make_manager()
    with pytest.raises(ValueError, match="schedule_type"):
        manager.update_task("notification_cleanup", schedule_type="weekly")


def test_update_task_interval_minutes_out_of_range():
    manager, *_ = _make_manager()
    with pytest.raises(ValueError, match="interval_minutes"):
        manager.update_task("notification_cleanup", interval_minutes=0)
    with pytest.raises(ValueError, match="interval_minutes"):
        manager.update_task("notification_cleanup", interval_minutes=MAX_INTERVAL_MINUTES + 1)


def test_update_task_interval_minutes_boundary():
    manager, *_ = _make_manager()
    result = manager.update_task("notification_cleanup", interval_minutes=MIN_INTERVAL_MINUTES)
    assert result["interval_minutes"] == MIN_INTERVAL_MINUTES
    result = manager.update_task("notification_cleanup", interval_minutes=MAX_INTERVAL_MINUTES)
    assert result["interval_minutes"] == MAX_INTERVAL_MINUTES


def test_update_task_invalid_daily_time():
    manager, *_ = _make_manager()
    with pytest.raises(ValueError, match="daily_time"):
        manager.update_task("db_validation_field_mapping_refresh", daily_time="25:00")
    with pytest.raises(ValueError, match="daily_time"):
        manager.update_task("db_validation_field_mapping_refresh", daily_time="abc")


def test_update_task_valid_daily_time():
    manager, *_ = _make_manager()
    result = manager.update_task("db_validation_field_mapping_refresh", daily_time="08:30")
    assert result["daily_time"] == "08:30"


def test_update_task_unknown_task_raises():
    manager, *_ = _make_manager()
    with pytest.raises(ValueError, match="未知的任务码"):
        manager.update_task("nonexistent_task", enabled=False)


def test_update_task_disable_clears_next_run():
    manager, *_ = _make_manager()
    # 先确保 next_run_at 有值
    manager._ensure_initial_next_run()
    task = manager.get_task("notification_cleanup")
    assert task["next_run_at"] is not None

    result = manager.update_task("notification_cleanup", enabled=False)
    assert result["enabled"] == 0
    assert result["next_run_at"] is None


def test_update_task_enable_recomputes_next_run():
    manager, *_ = _make_manager()
    manager.update_task("notification_cleanup", enabled=False)
    task = manager.get_task("notification_cleanup")
    assert task["next_run_at"] is None

    result = manager.update_task("notification_cleanup", enabled=True)
    assert result["enabled"] == 1
    assert result["next_run_at"] is not None


# ------------------------------------------------------------------
# 删除
# ------------------------------------------------------------------


def test_delete_task_physical():
    manager, *_ = _make_manager()
    deleted = manager.delete_task("notification_cleanup")
    assert deleted is True
    assert manager.get_task("notification_cleanup") is None
    tasks = manager.list_tasks()
    assert len(tasks) == 2


def test_delete_unknown_task_raises():
    manager, *_ = _make_manager()
    with pytest.raises(ValueError, match="未知的任务码"):
        manager.delete_task("nonexistent_task")


# ------------------------------------------------------------------
# 首次 next_run_at
# ------------------------------------------------------------------


def test_initial_next_run_report_navigation_delayed():
    """报送导航统计首次启动延迟 30 秒。"""
    db = _make_database()
    manager, *_ = _make_manager(db)
    manager._ensure_initial_next_run()
    task = manager.get_task("report_navigation_statistics")
    now = beijing_now()
    assert task["next_run_at"] is not None
    diff = (task["next_run_at"] - now).total_seconds()
    assert 25 <= diff <= 35  # 大约 30 秒


def test_initial_next_run_notification_immediate():
    """通知清理首次启动立即到期。"""
    db = _make_database()
    manager, *_ = _make_manager(db)
    manager._ensure_initial_next_run()
    task = manager.get_task("notification_cleanup")
    now = beijing_now()
    assert task["next_run_at"] is not None
    diff = (task["next_run_at"] - now).total_seconds()
    assert abs(diff) <= 2  # 立即到期


def test_initial_next_run_field_mapping_next_midnight():
    """字段映射刷新首次安排到下一个 00:00。"""
    db = _make_database()
    manager, *_ = _make_manager(db)
    manager._ensure_initial_next_run()
    task = manager.get_task("db_validation_field_mapping_refresh")
    now = beijing_now()
    assert task["next_run_at"] is not None
    next_run = task["next_run_at"]
    assert next_run.hour == 0
    assert next_run.minute == 0
    assert next_run > now


# ------------------------------------------------------------------
# 成功 / 失败状态
# ------------------------------------------------------------------


def test_execute_task_success_records_status():
    manager, report_nav, *_ = _make_manager()
    manager._execute_task("report_navigation_statistics")
    task = manager.get_task("report_navigation_statistics")
    assert task["last_status"] == "success"
    assert task["last_error"] is None
    assert task["last_started_at"] is not None
    assert task["last_finished_at"] is not None
    report_nav.collect_once.assert_called_once()


def test_execute_task_failure_records_error():
    manager, report_nav, *_ = _make_manager()
    report_nav.collect_once.side_effect = RuntimeError("数据库连接失败")
    manager._execute_task("report_navigation_statistics")
    task = manager.get_task("report_navigation_statistics")
    assert task["last_status"] == "failed"
    assert task["last_error"] is not None
    assert "数据库连接失败" in task["last_error"] or "异常" in task["last_error"]


def test_execute_notification_cleanup_calls_service():
    manager, _, notification_svc, _ = _make_manager()
    manager._execute_task("notification_cleanup")
    task = manager.get_task("notification_cleanup")
    assert task["last_status"] == "success"
    notification_svc.cleanup_expired.assert_called_once()


def test_execute_field_mapping_calls_router():
    manager, _, _, api_router = _make_manager()
    manager._execute_task("db_validation_field_mapping_refresh")
    task = manager.get_task("db_validation_field_mapping_refresh")
    assert task["last_status"] == "success"
    api_router._refresh_db_validation_field_mapping.assert_called_once_with(source="auto")


def test_request_run_now_executes_disabled_task_through_scheduler_queue():
    manager, _, notification_svc, _ = _make_manager()
    manager.update_task("notification_cleanup", enabled=False)

    result = manager.request_run_now("notification_cleanup")
    manager._tick()

    assert result == {"accepted": True, "task_code": "notification_cleanup"}
    notification_svc.cleanup_expired.assert_called_once()
    assert manager.get_task("notification_cleanup")["last_status"] == "success"


def test_request_run_now_rejects_duplicate_queue_entry():
    manager, *_ = _make_manager()
    manager.request_run_now("notification_cleanup")

    with pytest.raises(ValueError, match="正在执行"):
        manager.request_run_now("notification_cleanup")


# ------------------------------------------------------------------
# 关闭不会残留线程
# ------------------------------------------------------------------


def test_start_stop_no_residual_thread():
    manager, *_ = _make_manager()
    manager.start()
    assert manager._thread is not None
    assert manager._thread.is_alive()
    manager.stop()
    assert manager._thread is None
    # 确认线程已退出
    threads = [t for t in threading.enumerate() if t.name == "scheduled-tasks-scheduler"]
    assert len(threads) == 0


def test_stop_without_start_is_safe():
    manager, *_ = _make_manager()
    manager.stop()  # 不应抛出异常


def test_double_start_does_not_create_duplicate_thread():
    manager, *_ = _make_manager()
    manager.start()
    first_thread = manager._thread
    manager.start()  # 第二次调用不应创建新线程
    assert manager._thread is first_thread
    manager.stop()


# ------------------------------------------------------------------
# 调度循环：到期任务被执行
# ------------------------------------------------------------------


def test_tick_executes_due_task():
    """next_run_at 已过的任务应被立即执行。"""
    db = _make_database()
    manager, report_nav, *_ = _make_manager(db)
    # 手动设置 next_run_at 为过去
    past = beijing_now() - timedelta(minutes=1)
    db.connection.tables["scheduled_tasks"][0]["next_run_at"] = past
    manager._tick()
    report_nav.collect_once.assert_called_once()


def test_tick_does_not_execute_future_task():
    """next_run_at 在将来的任务不应被执行。"""
    db = _make_database()
    manager, report_nav, *_ = _make_manager(db)
    future = beijing_now() + timedelta(hours=1)
    db.connection.tables["scheduled_tasks"][0]["next_run_at"] = future
    manager._tick()
    report_nav.collect_once.assert_not_called()


def test_tick_does_not_execute_disabled_task():
    """已禁用的任务不应被执行。"""
    db = _make_database()
    manager, report_nav, *_ = _make_manager(db)
    past = beijing_now() - timedelta(minutes=1)
    db.connection.tables["scheduled_tasks"][0]["next_run_at"] = past
    db.connection.tables["scheduled_tasks"][0]["enabled"] = 0
    manager._tick()
    report_nav.collect_once.assert_not_called()


# ------------------------------------------------------------------
# 辅助函数
# ------------------------------------------------------------------


def test_parse_daily_time_valid():
    result = _parse_daily_time("08:30")
    assert result.hour == 8
    assert result.minute == 30


def test_parse_daily_time_invalid():
    with pytest.raises(ValueError):
        _parse_daily_time("25:00")
    with pytest.raises(ValueError):
        _parse_daily_time("abc")
    with pytest.raises(ValueError):
        _parse_daily_time("12:60")  # 分钟越界


def test_compute_initial_next_run_for_custom_type():
    """测试 _compute_initial_next_run 对未知 task_code 的默认行为。"""
    now = beijing_now()
    result = _compute_initial_next_run(
        "unknown_code", "interval", 60, None, now
    )
    assert result == now + timedelta(minutes=60)


# ------------------------------------------------------------------
# API 端点（_handle_scheduled_tasks）
# ------------------------------------------------------------------


class _FakeRouter:
    """Minimal ApiRouter mock for _handle_scheduled_tasks tests."""

    def __init__(self, manager: ScheduledTaskManager, user_role: str = "admin"):
        self._scheduled_task_manager = manager
        self._user_role = user_role

    def _user_has_capability(self, current_user, code):
        role = str((current_user or {}).get("role", "") or "user")
        return has_capability(role, code)


def _bind_handle_scheduled_tasks():
    from auto_check.app.server import ApiRouter
    _FakeRouter._handle_scheduled_tasks = ApiRouter._handle_scheduled_tasks


def test_api_get_scheduled_tasks_returns_tasks_and_missing():
    db = _make_database()
    manager, *_ = _make_manager(db)
    _bind_handle_scheduled_tasks()
    router = _FakeRouter(manager)
    status, payload = router._handle_scheduled_tasks("GET", "/api/system/scheduled-tasks", None, {"role": "admin"})
    assert status == 200
    assert "tasks" in payload
    assert "missing_templates" in payload
    assert len(payload["tasks"]) == 3
    assert payload["missing_templates"] == []


def test_api_get_scheduled_tasks_requires_capability():
    db = _make_database()
    manager, *_ = _make_manager(db)
    _bind_handle_scheduled_tasks()
    router = _FakeRouter(manager, user_role="user")
    status, payload = router._handle_scheduled_tasks("GET", "/api/system/scheduled-tasks", None, {"role": "user"})
    assert status == 403


def test_api_update_task_via_api():
    db = _make_database()
    manager, *_ = _make_manager(db)
    _bind_handle_scheduled_tasks()
    router = _FakeRouter(manager)
    status, payload = router._handle_scheduled_tasks(
        "POST", "/api/system/scheduled-tasks/notification_cleanup",
        {"enabled": False}, {"role": "admin"}
    )
    assert status == 200
    assert payload["task"]["enabled"] == 0


def test_api_delete_task_via_api():
    db = _make_database()
    manager, *_ = _make_manager(db)
    _bind_handle_scheduled_tasks()
    router = _FakeRouter(manager)
    status, payload = router._handle_scheduled_tasks(
        "DELETE", "/api/system/scheduled-tasks/notification_cleanup",
        None, {"role": "admin"}
    )
    assert status == 200
    assert payload["deleted"] is True


def test_api_restore_task_via_api():
    db = _make_database()
    # 先删除一个任务
    db.connection.tables["scheduled_tasks"] = [
        t for t in db.connection.tables["scheduled_tasks"]
        if t["task_code"] != "notification_cleanup"
    ]
    manager, *_ = _make_manager(db)
    _bind_handle_scheduled_tasks()
    router = _FakeRouter(manager)
    status, payload = router._handle_scheduled_tasks(
        "POST", "/api/system/scheduled-tasks/notification_cleanup/restore",
        None, {"role": "admin"}
    )
    assert status == 200
    assert payload["task"]["task_code"] == "notification_cleanup"


def test_api_unknown_path_returns_404():
    db = _make_database()
    manager, *_ = _make_manager(db)
    _bind_handle_scheduled_tasks()
    router = _FakeRouter(manager)
    status, payload = router._handle_scheduled_tasks(
        "GET", "/api/system/scheduled-tasks/unknown_task/unknown_action",
        None, {"role": "admin"}
    )
    assert status == 404
