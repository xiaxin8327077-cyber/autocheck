"""报送日期预生成的测试先行用例。"""

from contextlib import contextmanager
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select, text

from auto_check.app.report_navigation import ReportNavigationService
from auto_check.app.storage_report_navigation import ReportNavigationStore
from auto_check.app.notifications.service import NotificationService
from auto_check.app.notifications.storage import METADATA, NotificationStorage
from mysql_config_test_support import MemoryApplicationDatabase


def test_report_navigation_service_exposes_schedule_preparation_entrypoint():
    """服务层必须暴露启动补查和定时任务共用的预生成入口。"""
    assert callable(getattr(ReportNavigationService, "prepare_schedules", None))


def test_report_navigation_service_forwards_now_to_module_helper(monkeypatch):
    """服务层入口只编排存储辅助函数，不应启动报送统计或数据源查询。"""
    store = MagicMock()
    expected = object()
    helper = MagicMock(return_value=expected)
    monkeypatch.setattr("auto_check.app.report_navigation.prepare_schedules", helper)
    service = ReportNavigationService(None, store=store)

    assert service.prepare_schedules(now=datetime(2026, 12, 31, 15, 0)) is expected
    helper.assert_called_once_with(store, now=datetime(2026, 12, 31, 15, 0))
    store.load_configuration.assert_not_called()


def _real_store(*month_numbers):
    database = MemoryApplicationDatabase()
    tables = database.connection.tables
    tables["report_nav_processes"].append(
        {
            "process_code": "alpha",
            "process_name": "流程甲",
            "display_order": 1,
            "enabled": 1,
            "allow_manual_step_completion": 1,
        }
    )
    tables["report_nav_process_months"].extend(
        {"process_code": "alpha", "month_no": month_no} for month_no in month_numbers
    )
    return database, ReportNavigationStore(database)


def _prepare(store, now):
    from auto_check.app.report_navigation_schedule_preparation import prepare_schedules

    return prepare_schedules(store, now=now)


def test_first_day_checks_next_month_but_does_not_write_before_month_end():
    database, store = _real_store(1, 12)
    store.upsert_schedule("2026-12", "alpha", date(2026, 12, 20), source_type="manual", source_year=2026, updated_by="user", now=datetime(2026, 12, 1, 9, 0))
    store.upsert_schedule("2026-01", "alpha", date(2026, 1, 20), source_type="manual", source_year=2026, updated_by="user", now=datetime(2026, 1, 1, 9, 0))

    result = _prepare(store, datetime(2026, 12, 1, 15, 0))

    assert "2026-12" in result.months
    assert "2027-01" in result.months
    assert result.issues[0].report_month == "2027-01"
    assert result.issues[0].reason == "awaiting_maintenance"
    assert store.load_schedule("2027-01", "alpha") is None


def test_month_end_inherits_next_month_date():
    database, store = _real_store(1, 12)
    store.upsert_schedule("2026-12", "alpha", date(2026, 12, 20), source_type="manual", source_year=2026, updated_by="user", now=datetime(2026, 12, 1, 9, 0))
    store.upsert_schedule("2026-01", "alpha", date(2026, 1, 20), source_type="manual", source_year=2026, updated_by="user", now=datetime(2026, 1, 1, 9, 0))

    result = _prepare(store, datetime(2026, 12, 31, 15, 0))

    assert result.issues == ()
    assert result.ready_count == 2
    assert store.load_schedule("2027-01", "alpha").report_date == date(2027, 1, 20)


def test_first_day_catches_up_missing_current_month_but_never_overwrites_manual_date():
    database, store = _real_store(1, 2)
    store.upsert_schedule("2026-02", "alpha", date(2026, 2, 28), source_type="manual", source_year=2026, updated_by="user", now=datetime(2026, 2, 1, 9, 0))
    store.upsert_schedule("2027-01", "alpha", date(2027, 1, 17), source_type="manual", source_year=2027, updated_by="user", now=datetime(2027, 1, 1, 9, 0))

    result = _prepare(store, datetime(2027, 1, 1, 15, 0))

    assert not [issue for issue in result.issues if issue.report_month == "2027-01"]
    assert store.load_schedule("2027-01", "alpha").report_date == date(2027, 1, 17)


def test_missing_history_is_reported_without_guessing_a_date():
    database, store = _real_store(1, 12)
    store.upsert_schedule("2026-12", "alpha", date(2026, 12, 20), source_type="manual", source_year=2026, updated_by="user", now=datetime(2026, 12, 1, 9, 0))

    result = _prepare(store, datetime(2026, 12, 31, 15, 0))

    assert [(issue.report_month, issue.process_code, issue.reason) for issue in result.issues] == [
        ("2027-01", "alpha", "missing_history")
    ]
    assert store.load_schedule("2027-01", "alpha") is None


def test_configuration_and_inheritance_failures_are_isolated_from_other_processes():
    database, store = _real_store(1, 12)
    database.connection.tables["report_nav_processes"].append(
        {"process_code": "beta", "process_name": "流程乙", "display_order": 2, "enabled": 1, "allow_manual_step_completion": 1}
    )
    database.connection.tables["report_nav_process_months"].extend(
        {"process_code": "beta", "month_no": month_no} for month_no in (1, 12)
    )
    store.upsert_schedule("2026-12", "alpha", date(2026, 12, 20), source_type="manual", source_year=2026, updated_by="user", now=datetime(2026, 12, 1, 9, 0))
    store.upsert_schedule("2026-12", "beta", date(2026, 12, 21), source_type="manual", source_year=2026, updated_by="user", now=datetime(2026, 12, 1, 9, 0))
    store.upsert_schedule("2026-01", "alpha", date(2026, 1, 20), source_type="manual", source_year=2026, updated_by="user", now=datetime(2026, 1, 1, 9, 0))
    store.upsert_schedule("2026-01", "beta", date(2026, 1, 21), source_type="manual", source_year=2026, updated_by="user", now=datetime(2026, 1, 1, 9, 0))

    original_ensure = store.ensure_schedule
    def failing_ensure(report_month, process_code, *, now):
        if report_month == "2027-01" and process_code == "beta":
            raise RuntimeError("database token=secret")
        return original_ensure(report_month, process_code, now=now)
    store.ensure_schedule = failing_ensure

    result = _prepare(store, datetime(2026, 12, 31, 15, 0))

    assert result.ready_count == 3
    assert [(issue.process_code, issue.reason) for issue in result.issues] == [("beta", "inheritance_failed")]
    assert store.load_schedule("2027-01", "alpha") is not None


@pytest.mark.parametrize(
    ("now", "should_prepare"),
    [
        (datetime(2025, 2, 27, 15, 0), False),
        (datetime(2025, 2, 28, 15, 0), True),
        (datetime(2024, 2, 28, 15, 0), False),
        (datetime(2024, 2, 29, 15, 0), True),
        (datetime(2026, 4, 29, 15, 0), False),
        (datetime(2026, 4, 30, 15, 0), True),
    ],
)
def test_next_month_is_written_only_on_calendar_month_end(now, should_prepare):
    database, store = _real_store(now.month, now.month % 12 + 1)
    next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
    next_month_text = next_month.strftime("%Y-%m")
    previous_text = f"{next_month.year - 1:04d}-{next_month.month:02d}"
    current_text = now.strftime("%Y-%m")
    store.upsert_schedule(current_text, "alpha", date(now.year, now.month, 20), source_type="manual", source_year=now.year, updated_by="user", now=now)
    store.upsert_schedule(previous_text, "alpha", date(next_month.year - 1, next_month.month, 20), source_type="manual", source_year=next_month.year - 1, updated_by="user", now=now)

    _prepare(store, now)

    schedule = store.load_schedule(next_month_text, "alpha")
    assert (schedule is not None) is should_prepare


def test_first_day_catches_up_a_missing_current_month_from_last_year():
    database, store = _real_store(1, 2)
    store.upsert_schedule("2026-01", "alpha", date(2026, 1, 26), source_type="manual", source_year=2026, updated_by="user", now=datetime(2026, 1, 1, 9, 0))
    store.upsert_schedule("2026-02", "alpha", date(2026, 2, 20), source_type="manual", source_year=2026, updated_by="user", now=datetime(2026, 2, 1, 9, 0))

    result = _prepare(store, datetime(2027, 1, 1, 15, 0))

    assert not [issue for issue in result.issues if issue.report_month == "2027-01"]
    assert store.load_schedule("2027-01", "alpha").report_date == date(2027, 1, 26)


def test_invalid_previous_schedule_month_is_reported_without_guessing():
    database, store = _real_store(1, 12)
    store.upsert_schedule("2026-12", "alpha", date(2026, 12, 20), source_type="manual", source_year=2026, updated_by="user", now=datetime(2026, 12, 1, 9, 0))
    database.connection.tables["report_nav_monthly_schedules"].append(
        {
            "report_month": "2026-01",
            "process_code": "alpha",
            "report_date": date(2026, 2, 20),
            "source_type": "manual",
            "source_year": 2026,
            "owner_name": "负责人",
            "updated_by": "user",
            "updated_at": datetime(2026, 1, 1, 9, 0),
        }
    )

    result = _prepare(store, datetime(2026, 12, 31, 15, 0))

    issue = next(issue for issue in result.issues if issue.report_month == "2027-01")
    assert issue.reason == "invalid_date"
    assert store.load_schedule("2027-01", "alpha") is None


def test_only_if_missing_race_preserves_manual_date_owner_and_source():
    database, store = _real_store(1)
    store.upsert_schedule("2026-01", "alpha", date(2026, 1, 20), source_type="manual", source_year=2026, updated_by="user", now=datetime(2026, 1, 1, 9, 0))
    original_upsert = store.upsert_schedule
    raced = False

    def racing_upsert(report_month, process_code, report_date, **kwargs):
        nonlocal raced
        if kwargs.get("only_if_missing") and not raced:
            raced = True
            database.connection.tables["report_nav_monthly_schedules"].append(
                {
                    "report_month": report_month,
                    "process_code": process_code,
                    "report_date": date(2027, 1, 23),
                    "source_type": "manual",
                    "source_year": 2027,
                    "owner_name": "人工负责人",
                    "updated_by": "manual-user",
                    "updated_at": datetime(2026, 12, 31, 14, 59),
                }
            )
        return original_upsert(report_month, process_code, report_date, **kwargs)

    store.upsert_schedule = racing_upsert
    schedule = store.ensure_schedule("2027-01", "alpha", now=datetime(2026, 12, 31, 15, 0))

    assert schedule.report_date == date(2027, 1, 23)
    assert schedule.owner_name == "人工负责人"
    assert schedule.source_type == "manual"
    assert schedule.updated_by == "manual-user"


class _Users:
    def __init__(self):
        self.users = {
            "admin-1": SimpleNamespace(id="admin-1", role="admin", active=True),
            "admin-2": SimpleNamespace(id="admin-2", role="admin", active=True),
            "disabled-admin": SimpleNamespace(id="disabled-admin", role="admin", active=False),
            "user-1": SimpleNamespace(id="user-1", role="user", active=True),
        }

    def get_user(self, user_id):
        user = self.users.get(user_id)
        return {"id": user.id, "enabled": user.active} if user else None

    def list_active_users(self):
        return list(self.users.values())


class _Stream:
    def __init__(self):
        self.events = []

    def publish(self, user_id, event):
        self.events.append((user_id, event))


class _SqliteNotificationDatabase:
    def __init__(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        METADATA.create_all(self.engine)

    @contextmanager
    def connect(self):
        with self.engine.connect() as connection:
            yield connection

    @contextmanager
    def transaction(self):
        with self.engine.begin() as connection:
            yield connection


def _sqlite_rows(database, table_name):
    table = METADATA.tables[table_name]
    with database.connect() as connection:
        return [dict(row) for row in connection.execute(select(table)).mappings().all()]


def test_issue_notification_uses_real_service_dedupes_admins_and_redacts_storage_error():
    from auto_check.app.report_navigation_schedule_preparation import (
        SchedulePreparationIssue,
        SchedulePreparationResult,
        run_schedule_preparation,
    )

    now = datetime(2026, 12, 31, 15, 0)
    service = MagicMock()
    service.prepare_schedules.return_value = SchedulePreparationResult(
        months=("2026-12", "2027-01"),
        checked_count=1,
        ready_count=0,
        issues=(SchedulePreparationIssue("2027-01", "alpha", "流程甲", "missing_history"),),
    )
    users = _Users()
    database = _SqliteNotificationDatabase()
    stream = _Stream()
    notification_service = NotificationService(
        NotificationStorage(database), users, stream, now=lambda: now
    )

    with pytest.raises(RuntimeError) as exc_info:
        run_schedule_preparation(service, notification_service, users, now=now)
    assert "2027-01" in str(exc_info.value)
    assert "流程甲" in str(exc_info.value)
    assert "password" not in str(exc_info.value).lower()
    assert "internal.example" not in str(exc_info.value)

    rows = _sqlite_rows(database, "system_notifications")
    assert len(rows) == 2
    assert all("2027-01" in row["content"] for row in rows)
    assert all("secret" not in row["content"].lower() for row in rows)
    recipients = _sqlite_rows(database, "system_notification_recipients")
    assert {row["user_id"] for row in recipients} == {"admin-1", "admin-2"}
    first_ids = {row["id"] for row in rows}
    first_event_count = len(stream.events)

    with pytest.raises(RuntimeError):
        run_schedule_preparation(service, notification_service, users, now=now)
    assert len(_sqlite_rows(database, "system_notifications")) == 2
    assert {row["id"] for row in _sqlite_rows(database, "system_notifications")} == first_ids
    assert len(stream.events) == first_event_count


def test_issue_notification_cleans_expired_dedupe_rows_before_republishing():
    from auto_check.app.report_navigation_schedule_preparation import (
        SchedulePreparationIssue,
        SchedulePreparationResult,
        run_schedule_preparation,
    )

    clock = {"now": datetime(2026, 12, 1, 15, 0)}
    issue = SchedulePreparationIssue("2027-01", "alpha", "流程甲", "missing_history")
    service = MagicMock()
    service.prepare_schedules.return_value = SchedulePreparationResult(
        months=("2026-12", "2027-01"), checked_count=1, ready_count=0, issues=(issue,)
    )
    users = _Users()
    database = _SqliteNotificationDatabase()
    stream = _Stream()
    notification_service = NotificationService(
        NotificationStorage(database), users, stream, now=lambda: clock["now"]
    )

    with pytest.raises(RuntimeError):
        run_schedule_preparation(service, notification_service, users, now=clock["now"])
    assert len(_sqlite_rows(database, "system_notifications")) == 2
    with database.transaction() as connection:
        connection.execute(
            text("UPDATE system_notifications SET expires_at=:expires_at"),
            {"expires_at": datetime(2026, 12, 31, 23, 59)},
        )

    clock["now"] = datetime(2027, 1, 1, 15, 0)
    with pytest.raises(RuntimeError):
        run_schedule_preparation(service, notification_service, users, now=clock["now"])
    assert len(_sqlite_rows(database, "system_notifications")) == 2
    assert all(row["created_at"] == clock["now"] for row in _sqlite_rows(database, "system_notifications"))
    assert len(stream.events) == 4


def test_notification_cleanup_failure_still_attempts_all_admin_notifications():
    from auto_check.app.report_navigation_schedule_preparation import (
        SchedulePreparationIssue,
        SchedulePreparationResult,
        run_schedule_preparation,
    )

    now = datetime(2026, 12, 31, 15, 0)
    service = MagicMock()
    service.prepare_schedules.return_value = SchedulePreparationResult(
        months=("2026-12", "2027-01"), checked_count=1, ready_count=0,
        issues=(SchedulePreparationIssue("2027-01", "alpha", "流程甲", "missing_history"),),
    )
    users = _Users()
    notification_service = MagicMock()
    notification_service.cleanup_expired.side_effect = RuntimeError("storage password=secret")

    with pytest.raises(RuntimeError) as exc_info:
        run_schedule_preparation(service, notification_service, users, now=now)

    notification_service.cleanup_expired.assert_called_once()
    assert notification_service.publish.call_count == 2
    assert "password=secret" not in str(exc_info.value)
    assert "管理员通知发送失败" in str(exc_info.value)
