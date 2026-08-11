from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from mysql_config_test_support import MemoryApplicationDatabase

from auto_check.app.report_navigation import ReportNavigationService
from auto_check.app.report_navigation_platform import (
    HistoryItem,
    TodoAction,
    TodoItem,
    create_report_navigation_service,
    todo_item_payload,
)
from auto_check.app.storage_report_navigation import ReportNavigationStore

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _service() -> ReportNavigationService:
    database = MemoryApplicationDatabase()
    return ReportNavigationService(database, store=ReportNavigationStore(database))


def test_todo_payload_includes_initiator():
    item = TodoItem(
        id="t1", title="标题", summary="摘要",
        assignee_user_id="u1", module_id="m",
        created_at=None, action=TodoAction("navigate", "r", {}),
        initiator="张三",
    )
    payload = todo_item_payload(item)
    assert payload["initiator"] == "张三"


def test_processing_history_filters_actor_sorts_and_paginates():
    service = _service()
    bound = create_report_navigation_service(service).binder("rsp")
    now = datetime(2026, 8, 11, 12, 0, tzinfo=SHANGHAI)

    class Provider:
        def list_history(self, request):
            return [
                HistoryItem(
                    id=f"h-{i}", title="报表特殊处理", summary=f"s{i}",
                    # Plan brief had `i < 12` but that yields 11 user-a rows; intent is 12
                    # (total==12, newest id h-12). Lock `i <= 12`.
                    actor_user_id="user-a" if i <= 12 else "user-b",
                    module_id="report_special_processing",
                    processed_at=datetime(2026, 8, 11, i, 0, tzinfo=SHANGHAI),
                    initiator="发起人A",
                    action=TodoAction("navigate", "report-special-processing",
                                     {"record_id": str(i), "open": "detail"}),
                )
                for i in range(1, 14)
            ]

    bound.value.register_history_provider(
        provider_id="rsp_confirmed_history", provider=Provider(), semantics_version=1,
    )
    page1 = service.processing_history(
        current_user={"id": "user-a"}, page=1, page_size=10, now=now,
    )
    assert page1["total"] == 12
    assert page1["page"] == 1
    assert page1["page_size"] == 10
    assert len(page1["items"]) == 10
    assert page1["items"][0]["id"] == "h-12"  # newest first among user-a
    assert page1["items"][0]["initiator"] == "发起人A"
    assert page1["items"][0]["processed_at"]
    page2 = service.processing_history(
        current_user={"id": "user-a"}, page=2, page_size=10, now=now,
    )
    assert len(page2["items"]) == 2


def test_processing_history_rejects_illegal_page_size():
    service = _service()
    with pytest.raises(ValueError):
        service.processing_history(
            current_user={"id": "user-a"}, page=1, page_size=20,
        )


def test_processing_history_out_of_range_page_returns_requested_page_empty():
    service = _service()
    bound = create_report_navigation_service(service).binder("rsp")
    now = datetime(2026, 8, 11, 12, 0, tzinfo=SHANGHAI)

    class Provider:
        def list_history(self, request):
            return [
                HistoryItem(
                    id="h-1",
                    title="报表特殊处理",
                    summary="s1",
                    actor_user_id="user-a",
                    module_id="report_special_processing",
                    processed_at=now,
                    initiator="发起人A",
                    action=TodoAction(
                        "navigate",
                        "report-special-processing",
                        {"record_id": "1", "open": "detail"},
                    ),
                )
            ]

    bound.value.register_history_provider(
        provider_id="rsp_confirmed_history",
        provider=Provider(),
        semantics_version=1,
    )
    page = service.processing_history(
        current_user={"id": "user-a"}, page=9, page_size=10, now=now,
    )
    assert page["total"] == 1
    assert page["page"] == 9
    assert page["page_size"] == 10
    assert page["items"] == []
