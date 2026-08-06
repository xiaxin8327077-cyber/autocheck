from __future__ import annotations

from typing import Any, Mapping


EDITABLE_STATUSES = frozenset({"draft", "pending", "processing"})
NORMAL_TRANSITIONS = frozenset(
    {
        ("draft", "pending"),
        ("pending", "processing"),
        ("pending", "completed"),
        ("processing", "pending"),
        ("processing", "completed"),
    }
)


def is_admin(user: Mapping[str, Any] | None) -> bool:
    return bool(user) and user.get("role") == "admin"


def can_edit(user: Mapping[str, Any] | None, record: Mapping[str, Any]) -> bool:
    if str(record.get("status")) not in EDITABLE_STATUSES:
        return False
    if is_admin(user):
        return True
    user_id = str((user or {}).get("id") or "")
    return bool(user_id) and user_id in {
        str(record.get("creator_user_id") or ""),
        str(record.get("handler_user_id") or ""),
    }


def can_transition(source: str, target: str) -> bool:
    return (source, target) in NORMAL_TRANSITIONS


def can_void(user: Mapping[str, Any] | None) -> bool:
    return is_admin(user)


def can_reopen(user: Mapping[str, Any] | None) -> bool:
    return is_admin(user)


def can_delete(user: Mapping[str, Any] | None) -> bool:
    return is_admin(user)
