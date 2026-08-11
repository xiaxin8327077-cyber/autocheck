from datetime import datetime
from zoneinfo import ZoneInfo

from mysql_config_test_support import MemoryApplicationDatabase

from auto_check.app.report_navigation import ReportNavigationService
from auto_check.app.report_navigation_platform import (
    TodoAction,
    TodoItem,
    TodoListRequest,
    create_report_navigation_service,
)
from auto_check.app.storage_report_navigation import ReportNavigationStore

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _service() -> ReportNavigationService:
    database = MemoryApplicationDatabase()
    return ReportNavigationService(database, store=ReportNavigationStore(database))


def test_register_todo_provider_and_dashboard_filters_by_assignee():
    service = _service()
    bound = create_report_navigation_service(service).binder("rsp")
    now = datetime(2026, 8, 10, 10, 0, tzinfo=SHANGHAI)
    older = datetime(2026, 8, 10, 9, 0, tzinfo=SHANGHAI)
    newer = datetime(2026, 8, 10, 11, 0, tzinfo=SHANGHAI)

    class Provider:
        def list_todos(self, request: TodoListRequest):
            assert request.current_user["id"] == "user-a"
            assert request.now == now
            return [
                TodoItem(
                    id="todo-b",
                    title="其他用户待办",
                    summary="维度 B",
                    assignee_user_id="user-b",
                    module_id="report_special_processing",
                    created_at=newer,
                    action=TodoAction(
                        type="navigate",
                        route="report-special-processing",
                        query={"record_id": "2"},
                    ),
                ),
                TodoItem(
                    id="todo-a-old",
                    title="旧待办",
                    summary="维度 A",
                    assignee_user_id="user-a",
                    module_id="report_special_processing",
                    created_at=older,
                    action=TodoAction(
                        type="navigate",
                        route="report-special-processing",
                        query={"record_id": "1", "highlight": "1"},
                    ),
                ),
                TodoItem(
                    id="todo-a-new",
                    title="新待办",
                    summary="维度 A2",
                    assignee_user_id="user-a",
                    module_id="report_special_processing",
                    created_at=newer,
                    action=TodoAction(
                        type="navigate",
                        route="report-special-processing",
                        query={"record_id": "3"},
                    ),
                ),
            ]

    handle = bound.value.register_todo_provider(
        provider_id="rsp_pending_confirm",
        provider=Provider(),
        semantics_version=1,
    )

    payload = service.dashboard(
        period="month",
        current_user={"id": "user-a", "role": "user"},
        now=now,
    )

    assert [item["id"] for item in payload["todos"]] == ["todo-a-new", "todo-a-old"]
    assert payload["todos"][0] == {
        "id": "todo-a-new",
        "title": "新待办",
        "summary": "维度 A2",
        "module_id": "report_special_processing",
        "created_at": "2026-08-10 11:00:00",
        "action": {
            "type": "navigate",
            "route": "report-special-processing",
            "query": {"record_id": "3"},
        },
    }
    handle.close()
    empty = service.dashboard(
        period="month",
        current_user={"id": "user-a", "role": "user"},
        now=now,
    )
    assert empty["todos"] == []


def test_todo_provider_failure_does_not_block_other_providers():
    service = _service()
    bound = create_report_navigation_service(service).binder("alpha")
    now = datetime(2026, 8, 10, 12, 0, tzinfo=SHANGHAI)

    class Broken:
        def list_todos(self, request: TodoListRequest):
            raise RuntimeError("boom")

    class Ok:
        def list_todos(self, request: TodoListRequest):
            return [
                TodoItem(
                    id="ok-1",
                    title="可用待办",
                    summary="摘要",
                    assignee_user_id="user-a",
                    module_id="other_module",
                    created_at=now,
                    action=TodoAction(
                        type="navigate",
                        route="other-module",
                        query={},
                    ),
                )
            ]

    bound.value.register_todo_provider(
        provider_id="broken",
        provider=Broken(),
        semantics_version=1,
    )
    bound.value.register_todo_provider(
        provider_id="ok",
        provider=Ok(),
        semantics_version=1,
    )

    payload = service.dashboard(
        period="month",
        current_user={"id": "user-a", "role": "user"},
        now=now,
    )
    assert [item["id"] for item in payload["todos"]] == ["ok-1"]
