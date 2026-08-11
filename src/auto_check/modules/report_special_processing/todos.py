from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence

from auto_check.app.report_navigation_platform import TodoAction, TodoItem, TodoListRequest

from .contracts import DIMENSION_LABELS

MODULE_ID = "report_special_processing"
TODO_TITLE = "报表特殊处理待确认"
PROVIDER_ID = "rsp_pending_confirm"
SEMANTICS_VERSION = 1


class PendingConfirmTodoProvider:
    """Expose RSP pending confirms owned by the current governance user."""

    def __init__(self, storage: Any) -> None:
        self.storage = storage

    def list_todos(self, request: TodoListRequest) -> Sequence[TodoItem]:
        user_id = str((request.current_user or {}).get("id") or "").strip()
        if not user_id:
            return ()
        records = self.storage.list_pending_for_governance_owner(user_id)
        items: list[TodoItem] = []
        for record in records or ():
            item = self._to_item(record, user_id)
            if item is not None:
                items.append(item)
        return items

    def _to_item(self, record: Mapping[str, Any], user_id: str) -> TodoItem | None:
        record_id = record.get("id")
        if record_id is None:
            return None
        dimension = str(record.get("dimension") or "").strip()
        dimension_label = DIMENSION_LABELS.get(dimension, dimension or "未分维度")
        field_name = str(record.get("field_name") or "").strip() or "未填字段"
        created_at = record.get("special_handling_at") or record.get("created_at")
        if created_at is not None and not isinstance(created_at, datetime):
            created_at = None
        initiator = str(
            record.get("handler_display_name_snapshot")
            or record.get("handler_username_snapshot")
            or record.get("creator_username_snapshot")
            or ""
        ).strip()
        return TodoItem(
            id=f"rsp-pending-{record_id}",
            title=TODO_TITLE,
            summary=f"{dimension_label} · {field_name}",
            assignee_user_id=user_id,
            module_id=MODULE_ID,
            created_at=created_at,
            action=TodoAction(
                type="navigate",
                route="report-special-processing",
                query={"record_id": str(record_id), "highlight": "1", "open": "confirm"},
            ),
            initiator=initiator,
        )
