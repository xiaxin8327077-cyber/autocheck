from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence

from auto_check.app.report_navigation_platform import (
    HistoryItem,
    HistoryListRequest,
    TodoAction,
)

from .contracts import DIMENSION_LABELS

MODULE_ID = "report_special_processing"
HISTORY_PROVIDER_ID = "rsp_confirmed_history"
HISTORY_TITLE = "报表特殊处理"
HISTORY_SEMANTICS_VERSION = 1


class ConfirmedHistoryProvider:
    """Expose RSP confirms completed by the current operator."""

    def __init__(self, storage: Any) -> None:
        self.storage = storage

    def list_history(self, request: HistoryListRequest) -> Sequence[HistoryItem]:
        user_id = str((request.current_user or {}).get("id") or "").strip()
        if not user_id:
            return ()
        rows = self.storage.list_confirmed_history_for_operator(user_id)
        items: list[HistoryItem] = []
        for row in rows or ():
            item = self._to_item(row, user_id)
            if item is not None:
                items.append(item)
        return items

    def _to_item(self, row: Mapping[str, Any], user_id: str) -> HistoryItem | None:
        record_id = row.get("id")
        if record_id is None:
            return None
        dimension = str(row.get("dimension") or "").strip()
        dimension_label = DIMENSION_LABELS.get(dimension, dimension or "未分维度")
        field_name = str(row.get("field_name") or "").strip() or "未填字段"
        processed_at = row.get("confirmed_at")
        if processed_at is not None and not isinstance(processed_at, datetime):
            processed_at = None
        if processed_at is None:
            return None
        initiator = str(
            row.get("handler_display_name_snapshot")
            or row.get("handler_username_snapshot")
            or row.get("creator_username_snapshot")
            or ""
        ).strip()
        return HistoryItem(
            id=f"rsp-confirmed-{record_id}",
            title=HISTORY_TITLE,
            summary=f"{dimension_label} · {field_name}",
            actor_user_id=user_id,
            module_id=MODULE_ID,
            processed_at=processed_at,
            initiator=initiator,
            action=TodoAction(
                type="navigate",
                route="report-special-processing",
                query={"record_id": str(record_id), "open": "detail"},
            ),
        )
