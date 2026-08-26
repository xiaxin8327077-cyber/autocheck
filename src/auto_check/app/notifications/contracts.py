"""通知平台不可变契约与纯校验。"""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Mapping, Protocol, Sequence

NotificationLevel = Literal["info", "success", "warning", "error"]
NotificationActionType = Literal["navigate"]

_EVENT_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_.\-]{0,63}$")
_SOURCE_MODULE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_ROUTE_PATTERN = re.compile(r"^[a-z][a-z0-9\-]{0,63}$")
_MAX_RECIPIENTS = 100
_MAX_DEDUPE_KEY_LEN = 191
_MAX_TITLE_LEN = 191
_MAX_CONTENT_LEN = 2000
_MAX_QUERY_KEYS = 20
_MAX_QUERY_KEY_LEN = 191
_MAX_QUERY_VALUE_LEN = 191


class NotificationValidationError(ValueError):
    """通知参数校验失败。"""


@dataclass(frozen=True)
class NotificationAction:
    type: NotificationActionType
    route: str
    query: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class NotificationPublishRequest:
    event_type: str
    dedupe_key: str
    recipient_user_ids: tuple[str, ...]
    category: str
    level: NotificationLevel
    title: str
    content: str
    action: NotificationAction | None = None


@dataclass(frozen=True)
class NotificationPublishResult:
    notification_id: str
    created: bool
    recipient_count: int


@dataclass(frozen=True)
class NotificationItem:
    id: str
    source_module: str
    event_type: str
    category: str
    level: NotificationLevel
    title: str
    content: str
    action: NotificationAction | None
    created_at: datetime
    received_at: datetime
    read_at: datetime | None
    is_read: bool


@dataclass(frozen=True)
class NotificationPage:
    items: tuple[NotificationItem, ...]
    unread_count: int
    next_cursor: str | None


@dataclass(frozen=True)
class NotificationStreamEvent:
    type: Literal["notification", "resync", "close"]
    notification: NotificationItem | None = None
    unread_count: int | None = None


class NotificationStreamPublisher(Protocol):
    def publish(self, user_id: str, event: NotificationStreamEvent) -> None:
        """将已提交的通知事件发送给当前进程内目标用户订阅。"""


def validate_source_module(value: str) -> str:
    if not isinstance(value, str) or not _SOURCE_MODULE_PATTERN.fullmatch(value):
        raise NotificationValidationError(f"invalid source module: {value!r}")
    return value


def validate_publish_request(value: NotificationPublishRequest) -> NotificationPublishRequest:
    if not isinstance(value, NotificationPublishRequest):
        raise NotificationValidationError("invalid publish request type")

    event_type = value.event_type
    if not isinstance(event_type, str) or not _EVENT_TYPE_PATTERN.fullmatch(event_type):
        raise NotificationValidationError(f"invalid event_type: {event_type!r}")

    dedupe_key = value.dedupe_key
    if not isinstance(dedupe_key, str) or not dedupe_key.strip():
        raise NotificationValidationError("dedupe_key is required")
    if len(dedupe_key.encode("utf-8")) > _MAX_DEDUPE_KEY_LEN:
        raise NotificationValidationError("dedupe_key too long")

    recipients = value.recipient_user_ids
    if not recipients or len(recipients) > _MAX_RECIPIENTS:
        raise NotificationValidationError("recipient_user_ids must have 1 to 100 entries")
    for rid in recipients:
        if not isinstance(rid, str) or not rid.strip() or len(rid) > 64:
            raise NotificationValidationError(f"invalid recipient user id: {rid!r}")
    normalized_recipients = tuple(dict.fromkeys(r.strip() for r in recipients if r.strip()))
    if not normalized_recipients:
        raise NotificationValidationError("recipient_user_ids must have 1 to 100 entries")

    title = value.title
    if not isinstance(title, str) or not title.strip():
        raise NotificationValidationError("title is required")
    if len(title.encode("utf-8")) > _MAX_TITLE_LEN:
        raise NotificationValidationError("title too long")
    normalized_title = title.strip()

    content = value.content
    if not isinstance(content, str):
        raise NotificationValidationError("content must be a string")
    if len(content.encode("utf-8")) > _MAX_CONTENT_LEN:
        raise NotificationValidationError("content too long")

    category = value.category
    if not isinstance(category, str) or not _EVENT_TYPE_PATTERN.fullmatch(category):
        raise NotificationValidationError(f"invalid category: {category!r}")

    level = value.level
    if level not in ("info", "success", "warning", "error"):
        raise NotificationValidationError(f"invalid level: {level!r}")

    action = value.action
    normalized_action = None
    if action is not None:
        if action.type != "navigate":
            raise NotificationValidationError(f"invalid action type: {action.type!r}")
        if not _ROUTE_PATTERN.fullmatch(action.route):
            raise NotificationValidationError(f"invalid route: {action.route!r}")
        if not isinstance(action.query, Mapping):
            raise NotificationValidationError("action.query must be a mapping")
        if len(action.query) > _MAX_QUERY_KEYS:
            raise NotificationValidationError("action.query has too many keys")
        for qk, qv in action.query.items():
            if not isinstance(qk, str) or len(qk) > _MAX_QUERY_KEY_LEN:
                raise NotificationValidationError(f"invalid query key: {qk!r}")
            if not isinstance(qv, str) or len(qv) > _MAX_QUERY_VALUE_LEN:
                raise NotificationValidationError(f"invalid query value: {qv!r}")
        normalized_action = NotificationAction(
            type=action.type,
            route=action.route,
            query=dict(action.query),
        )

    return NotificationPublishRequest(
        event_type=event_type,
        dedupe_key=dedupe_key,
        recipient_user_ids=normalized_recipients,
        category=category,
        level=level,
        title=normalized_title,
        content=content,
        action=normalized_action,
    )


def encode_cursor(received_at: datetime, notification_id: str) -> str:
    payload = json.dumps(
        [received_at.isoformat(), notification_id],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def decode_cursor(value: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(value.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, list) or len(payload) != 2:
            raise NotificationValidationError("invalid cursor")
        time_text, notification_id = payload
        if not isinstance(time_text, str) or not isinstance(notification_id, str):
            raise NotificationValidationError("invalid cursor")
        if len(notification_id) != 32 or not re.fullmatch(r"[0-9a-f]{32}", notification_id):
            raise NotificationValidationError("invalid cursor notification id")
        parsed_time = datetime.fromisoformat(time_text)
        return parsed_time, notification_id
    except (binascii.Error, json.JSONDecodeError, ValueError, UnicodeDecodeError) as exc:
        raise NotificationValidationError("invalid cursor") from exc


def action_to_json(value: NotificationAction | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "type": value.type,
        "route": value.route,
        "query": dict(value.query),
    }


def action_from_json(value: object) -> NotificationAction | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise NotificationValidationError("invalid action json")
    return NotificationAction(
        type=str(value.get("type", "navigate")),
        route=str(value.get("route", "")),
        query=dict(value.get("query", {})),
    )
