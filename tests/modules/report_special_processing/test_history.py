from datetime import datetime
from zoneinfo import ZoneInfo

from auto_check.app.report_navigation_platform import HistoryListRequest
from auto_check.modules.report_special_processing.contracts import DIMENSION_LABELS
from auto_check.modules.report_special_processing.history import ConfirmedHistoryProvider


TZ = ZoneInfo("Asia/Shanghai")


class FakeStorage:
    def __init__(self, rows):
        self.rows = list(rows)

    def list_confirmed_history_for_operator(self, user_id: str):
        operator = str(user_id or "").strip()
        return [
            dict(item)
            for item in self.rows
            if str(item.get("operator_user_id") or "") == operator
            and item.get("status") == "completed"
        ]


def _history_row(**overrides):
    base = {
        "id": 1,
        "status": "completed",
        "operator_user_id": "owner-a",
        "dimension": "project",
        "field_name": "余额字段",
        "handler_display_name_snapshot": "王五",
        "handler_username_snapshot": "wangwu",
        "creator_username_snapshot": "creator_u",
        "confirmed_at": datetime(2026, 8, 10, 15, 0, tzinfo=TZ),
    }
    base.update(overrides)
    return base


def test_history_provider_returns_only_my_completed_confirms():
    storage = FakeStorage(
        [
            _history_row(id=1, operator_user_id="owner-a", field_name="余额字段"),
            _history_row(id=2, operator_user_id="owner-b", field_name="其他字段"),
            _history_row(id=3, operator_user_id="owner-a", status="pending", field_name="未完成"),
        ]
    )
    provider = ConfirmedHistoryProvider(storage)
    items = provider.list_history(
        HistoryListRequest(
            current_user={"id": "owner-a"},
            now=datetime(2026, 8, 10, 16, 0, tzinfo=TZ),
        )
    )

    assert len(items) == 1
    item = items[0]
    assert item.id == "rsp-confirmed-1"
    assert item.title == "报表特殊处理"
    assert item.summary == f"{DIMENSION_LABELS['project']} · 余额字段"
    assert item.actor_user_id == "owner-a"
    assert item.module_id == "report_special_processing"
    assert item.processed_at == datetime(2026, 8, 10, 15, 0, tzinfo=TZ)
    assert item.initiator == "王五"
    assert item.action.type == "navigate"
    assert item.action.route == "report-special-processing"
    assert item.action.query == {"record_id": "1", "open": "detail"}
    assert "confirm" not in item.action.query.values()


def test_history_provider_initiator_falls_back_to_handler_username():
    storage = FakeStorage(
        [
            _history_row(
                handler_display_name_snapshot="",
                handler_username_snapshot="wangwu",
                creator_username_snapshot="creator_u",
            )
        ]
    )
    items = ConfirmedHistoryProvider(storage).list_history(
        HistoryListRequest(
            current_user={"id": "owner-a"},
            now=datetime(2026, 8, 10, 16, 0, tzinfo=TZ),
        )
    )
    assert items[0].initiator == "wangwu"


def test_history_provider_initiator_falls_back_to_creator_username():
    storage = FakeStorage(
        [
            _history_row(
                handler_display_name_snapshot="",
                handler_username_snapshot="",
                creator_username_snapshot="creator_u",
            )
        ]
    )
    items = ConfirmedHistoryProvider(storage).list_history(
        HistoryListRequest(
            current_user={"id": "owner-a"},
            now=datetime(2026, 8, 10, 16, 0, tzinfo=TZ),
        )
    )
    assert items[0].initiator == "creator_u"


class Handle:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class ReportFacade:
    def __init__(self):
        self.card_handle = Handle()
        self.todo_handle = Handle()
        self.history_handle = Handle()
        self.history_registration = None

    def list_report_processes(self):
        return ()

    def register_card_provider(self, **kwargs):
        return self.card_handle

    def register_todo_provider(self, **kwargs):
        return self.todo_handle

    def register_history_provider(self, **kwargs):
        self.history_registration = kwargs
        return self.history_handle

    def refresh_card_provider(self, *, card_code):
        return {"ok": True}


class UserFacade:
    def list_active_users(self):
        return ()

    def get_user(self, user_id):
        return None


class Services:
    def __init__(self):
        self.report = ReportFacade()
        self.user = UserFacade()

    def resolve(self, name, version):
        return self.user if name == "platform.user_directory" else self.report


class Context:
    def __init__(self):
        self.application_database = object()
        self.services = Services()
        self.now = lambda: datetime(2026, 8, 10, tzinfo=TZ)


def test_module_registers_and_closes_history_provider(monkeypatch):
    from auto_check.modules.report_special_processing import module as module_file

    class DummyStorage:
        def backfill_processes_from_records(self):
            return None

    monkeypatch.setattr(module_file, "SpecialProcessingStorage", lambda database: DummyStorage())
    module = module_file.create_module()
    context = Context()
    module.start(context)

    registration = context.services.report.history_registration
    assert registration is not None
    assert registration["provider_id"] == "rsp_confirmed_history"
    assert registration["semantics_version"] == 1
    assert hasattr(registration["provider"], "list_history")

    module.stop()
    assert context.services.report.history_handle.closed
    assert context.services.report.todo_handle.closed
    assert context.services.report.card_handle.closed


def test_storage_list_confirmed_history_query_constraints():
    import inspect

    from auto_check.modules.report_special_processing import storage

    source = inspect.getsource(storage.SpecialProcessingStorage.list_confirmed_history_for_operator)
    assert "to_status" in source
    assert "completed" in source
    assert "operator_user_id" in source
    assert "confirmed_at" in source
    assert "func.max" in source or "max(" in source
    assert "handler_display_name_snapshot" in source
    assert "handler_username_snapshot" in source
