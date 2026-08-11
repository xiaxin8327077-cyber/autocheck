from datetime import datetime
from zoneinfo import ZoneInfo

from auto_check.app.report_navigation_platform import TodoListRequest
from auto_check.modules.report_special_processing.contracts import DIMENSION_LABELS
from auto_check.modules.report_special_processing.todos import PendingConfirmTodoProvider


TZ = ZoneInfo("Asia/Shanghai")


class FakeStorage:
    def __init__(self, records):
        self.records = list(records)

    def list_pending_for_governance_owner(self, user_id: str):
        owner = str(user_id or "").strip()
        return [
            dict(item)
            for item in self.records
            if item.get("status") == "pending"
            and str(item.get("governance_owner_user_id") or "") == owner
        ]


def _record(**overrides):
    base = {
        "id": 1,
        "status": "pending",
        "dimension": "project",
        "field_name": "余额字段",
        "governance_owner_user_id": "owner-a",
        "special_handling_at": datetime(2026, 8, 10, 9, 30, tzinfo=TZ),
        "created_at": datetime(2026, 8, 10, 9, 0, tzinfo=TZ),
    }
    base.update(overrides)
    return base


def test_provider_returns_only_current_owner_pending_records():
    storage = FakeStorage(
        [
            _record(id=1, governance_owner_user_id="owner-a", field_name="余额字段"),
            _record(id=2, governance_owner_user_id="owner-b", field_name="其他字段"),
            _record(id=3, status="completed", governance_owner_user_id="owner-a", field_name="已完成字段"),
            _record(id=4, status="draft", governance_owner_user_id="owner-a", field_name="草稿字段"),
        ]
    )
    provider = PendingConfirmTodoProvider(storage)
    items = provider.list_todos(
        TodoListRequest(
            current_user={"id": "owner-a", "role": "user"},
            now=datetime(2026, 8, 10, 12, 0, tzinfo=TZ),
        )
    )

    assert len(items) == 1
    item = items[0]
    assert item.id == "rsp-pending-1"
    assert item.title == "报表特殊处理待确认"
    assert item.summary == f"{DIMENSION_LABELS['project']} · 余额字段"
    assert item.assignee_user_id == "owner-a"
    assert item.module_id == "report_special_processing"
    assert item.created_at == datetime(2026, 8, 10, 9, 30, tzinfo=TZ)
    assert item.action.type == "navigate"
    assert item.action.route == "report-special-processing"
    assert item.action.query == {"record_id": "1", "highlight": "1", "open": "confirm"}


def test_provider_omits_record_after_confirm_status_change():
    storage = FakeStorage([_record(id=9, governance_owner_user_id="owner-a")])
    provider = PendingConfirmTodoProvider(storage)
    request = TodoListRequest(
        current_user={"id": "owner-a"},
        now=datetime(2026, 8, 10, 12, 0, tzinfo=TZ),
    )
    assert [item.id for item in provider.list_todos(request)] == ["rsp-pending-9"]

    storage.records[0]["status"] = "completed"
    assert provider.list_todos(request) == []


def test_todo_provider_sets_initiator_from_handler_snapshot():
    storage = FakeStorage([_record(
        handler_display_name_snapshot="王五",
        handler_username_snapshot="wangwu",
        creator_username_snapshot="creator_u",
    )])
    items = PendingConfirmTodoProvider(storage).list_todos(
        TodoListRequest(
            current_user={"id": "owner-a"},
            now=datetime(2026, 8, 10, 12, 0, tzinfo=TZ),
        )
    )
    assert items[0].initiator == "王五"


def test_todo_provider_initiator_falls_back_to_handler_username_snapshot():
    storage = FakeStorage([_record(
        handler_display_name_snapshot="",
        handler_username_snapshot="wangwu",
        creator_username_snapshot="creator_u",
    )])
    items = PendingConfirmTodoProvider(storage).list_todos(
        TodoListRequest(
            current_user={"id": "owner-a"},
            now=datetime(2026, 8, 10, 12, 0, tzinfo=TZ),
        )
    )
    assert items[0].initiator == "wangwu"


def test_todo_provider_initiator_falls_back_to_creator_username_snapshot():
    storage = FakeStorage([_record(
        handler_display_name_snapshot="",
        handler_username_snapshot="",
        creator_username_snapshot="creator_u",
    )])
    items = PendingConfirmTodoProvider(storage).list_todos(
        TodoListRequest(
            current_user={"id": "owner-a"},
            now=datetime(2026, 8, 10, 12, 0, tzinfo=TZ),
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
        self.todo_registration = None
        self.history_registration = None

    def list_report_processes(self):
        return ()

    def register_card_provider(self, **kwargs):
        return self.card_handle

    def register_todo_provider(self, **kwargs):
        self.todo_registration = kwargs
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


def test_module_registers_and_closes_todo_provider(monkeypatch):
    from auto_check.modules.report_special_processing import module as module_file

    class DummyStorage:
        def backfill_processes_from_records(self):
            return None

    monkeypatch.setattr(module_file, "SpecialProcessingStorage", lambda database: DummyStorage())
    module = module_file.create_module()
    context = Context()
    module.start(context)

    registration = context.services.report.todo_registration
    assert registration is not None
    assert registration["provider_id"] == "rsp_pending_confirm"
    assert registration["semantics_version"] == 1
    assert hasattr(registration["provider"], "list_todos")

    module.stop()
    assert context.services.report.todo_handle.closed
    assert context.services.report.history_handle.closed
    assert context.services.report.card_handle.closed
