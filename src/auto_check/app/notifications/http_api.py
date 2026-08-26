"""通知 HTTP 参数控制器 — 只做解析和状态码映射。"""

from __future__ import annotations

import re
from typing import Any

from auto_check.app.notifications.contracts import (
    NotificationItem,
    NotificationPage,
    NotificationValidationError,
    decode_cursor,
    encode_cursor,
)

_INVALID_FILTER = "filter must be 'all' or 'unread'"
_INVALID_LIMIT = "limit must be between 1 and 50"
_INVALID_CURSOR = "invalid cursor"
_NOT_FOUND = "notification not found"
_ERROR_ID_PATTERN = re.compile(r"^[A-Z0-9]{4,8}$")


def _error_response(message: str, status: int = 400) -> tuple[int, dict[str, Any]]:
    import uuid
    error_id = _ERROR_ID_PATTERN.fullmatch(str(uuid.uuid4()).upper().replace("-", "")[:8])
    error_id_str = error_id.group(0) if error_id else "NOTIF0000"
    return status, {"error": message, "error_id": f"NOTIF-{error_id_str}"}


class NotificationHttpApi:
    def __init__(self, service: Any, stream_hub: Any) -> None:
        self._service = service
        self._stream_hub = stream_hub

    def list_notifications(
        self,
        *,
        user_id: str,
        query: dict[str, str],
    ) -> tuple[int, dict[str, Any]]:
        filter_value = str(query.get("filter", "all")).strip().lower()
        if filter_value not in ("all", "unread", "read"):
            return _error_response(_INVALID_FILTER)
        unread_only = filter_value == "unread"
        read_only = filter_value == "read"
        try:
            limit = int(str(query.get("limit", "20")))
        except (TypeError, ValueError):
            return _error_response(_INVALID_LIMIT, status=400)
        if not 1 <= limit <= 50:
            return _error_response(_INVALID_LIMIT)
        cursor = None
        cursor_value = str(query.get("cursor", "")).strip()
        if cursor_value:
            try:
                cursor = decode_cursor(cursor_value)
            except NotificationValidationError:
                return _error_response(_INVALID_CURSOR)
        try:
            page = self._service._storage.list_for_user(
                user_id,
                unread_only=unread_only,
                limit=limit,
                cursor=cursor,
                now=self._service._now(),
                read_only=read_only,
            )
        except NotificationValidationError as exc:
            return _error_response(str(exc))
        return 200, {
            "items": [_item_to_dict(item) for item in page.items],
            "unread_count": page.unread_count,
            "next_cursor": page.next_cursor,
        }

    def mark_read(
        self,
        *,
        user_id: str,
        notification_id: str,
    ) -> tuple[int, dict[str, Any]]:
        if not notification_id or len(notification_id) != 32:
            return _error_response(_NOT_FOUND, status=404)
        try:
            item = self._service._storage.mark_read(
                user_id, notification_id, self._service._now()
            )
        except NotificationValidationError as exc:
            return _error_response(str(exc))
        if item is None:
            return _error_response(_NOT_FOUND, status=404)
        return 200, {
            "notification": _item_to_dict(item),
            "unread_count": self._service._storage.unread_count(user_id, self._service._now()),
        }

    def clear_all(self, *, user_id: str) -> tuple[int, dict[str, Any]]:
        deleted = self._service._storage.delete_all_for_user(user_id, self._service._now())
        return 200, {"deleted_count": deleted}

    def mark_all_read(
        self,
        *,
        user_id: str,
    ) -> tuple[int, dict[str, Any]]:
        updated = self._service._storage.mark_all_read(user_id, self._service._now())
        return 200, {
            "updated_count": updated,
            "unread_count": self._service._storage.unread_count(user_id, self._service._now()),
        }

    def get_unread_count(
        self,
        *,
        user_id: str,
    ) -> tuple[int, dict[str, Any]]:
        count = self._service._storage.unread_count(user_id, self._service._now())
        return 200, {"unread_count": count}


def _item_to_dict(item: NotificationItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "source_module": item.source_module,
        "event_type": item.event_type,
        "category": item.category,
        "level": item.level,
        "title": item.title,
        "content": item.content,
        "action": {
            "type": item.action.type,
            "route": item.action.route,
            "query": dict(item.action.query),
        } if item.action is not None else None,
        "created_at": item.created_at.isoformat(),
        "received_at": item.received_at.isoformat(),
        "read_at": item.read_at.isoformat() if item.read_at is not None else None,
        "is_read": item.is_read,
    }
