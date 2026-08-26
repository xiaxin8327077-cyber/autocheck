from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from auto_check.app.report_navigation_platform import CardStatisticsRequest, ReportProcess


TZ = ZoneInfo("Asia/Shanghai")


class StatsStorage:
    def __init__(self): self.windows = []
    def count_by_handling_period(self, start, end_exclusive):
        self.windows.append((start, end_exclusive))
        return {"draft": 1, "pending": 2, "processing": 2, "completed": 3, "voided": 1} if len(self.windows) == 1 else {"completed": 2}


def test_provider_uses_platform_boundaries_and_shared_effective_status_metrics():
    from auto_check.modules.report_special_processing.statistics import SpecialHandlingStatistics, status_metrics
    storage = StatsStorage(); now = datetime(2026, 8, 2, 10, 20, tzinfo=TZ)
    provider = SpecialHandlingStatistics(storage, now=lambda: now)
    for kind in ("week", "month", "quarter", "year"):
        storage.windows.clear(); start = datetime(2026, 8, 1, tzinfo=TZ); end = start + timedelta(days=7)
        request = CardStatisticsRequest("special_governance", kind, start, end, start - timedelta(days=7), start, now)
        result = provider(request)
        assert (result.total, result.completed, result.incomplete, result.previous_completed) == (7, 3, 4, 2)
        assert storage.windows == [(start, end), (start - timedelta(days=7), start)]
    assert status_metrics({"draft": 9, "pending": 2, "processing": 2, "completed": 3, "voided": 9}) == {"total": 7, "completed": 3, "incomplete": 4}


class Handle:
    def __init__(self): self.closed = False
    def close(self): self.closed = True


class ReportFacade:
    def __init__(self):
        self.handle = Handle()
        self.registration = None
        self.refresh_calls = []

    def list_report_processes(self):
        return (ReportProcess("dynamic", "动态报送", 1, True),)

    def register_card_provider(self, **kwargs):
        self.registration = kwargs
        return self.handle

    def register_todo_provider(self, **kwargs):
        self.todo_registration = kwargs
        self.todo_handle = Handle()
        return self.todo_handle

    def register_history_provider(self, **kwargs):
        self.history_registration = kwargs
        self.history_handle = Handle()
        return self.history_handle

    def refresh_card_provider(self, *, card_code):
        self.refresh_calls.append(card_code)
        return {"ok": True, "refreshed": True}


class UserFacade:
    def list_active_users(self): return ()
    def get_user(self, user_id): return None


class Services:
    def __init__(self): self.report = ReportFacade(); self.user = UserFacade(); self.calls = []
    def resolve(self, name, version): self.calls.append((name, version)); return self.user if name == "platform.user_directory" else self.report


class Context:
    def __init__(self):
        self.application_database = object(); self.services = Services(); self.now = lambda: datetime(2026, 8, 2, tzinfo=TZ)


def test_module_binds_owner_scoped_directories_and_closes_report_provider(monkeypatch):
    from auto_check.modules.report_special_processing import module as module_file
    monkeypatch.setattr(module_file, "SpecialProcessingStorage", lambda database: StatsStorage())
    module = module_file.create_module(); context = Context(); module.start(context)
    assert context.services.calls == [("platform.user_directory", 1), ("platform.report_navigation", 1), ("platform.notification", 1)]
    registration = context.services.report.registration
    assert registration["card_code"] == "special_governance"
    assert registration["semantics_version"] == 1
    assert registration["include_in_collect"] is False
    assert registration["refresh_on_dashboard"] is True
    module.stop()
    assert context.services.report.handle.closed
    assert context.services.report.todo_handle.closed
    assert context.services.report.history_handle.closed
    assert context.services.report.todo_registration["provider_id"] == "rsp_pending_confirm"
    assert context.services.report.history_registration["provider_id"] == "rsp_confirmed_history"
