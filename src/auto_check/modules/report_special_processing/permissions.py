from __future__ import annotations

from typing import Any, Mapping

from auto_check.app.capabilities import capabilities_for_role, has_capability

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
REOPENABLE_STATUSES = frozenset({"completed", "voided"})


def is_admin(user: Mapping[str, Any] | None) -> bool:
    return bool(user) and user.get("role") == "admin"


def user_has_capability(
    user: Mapping[str, Any] | None,
    code: str,
    matrix: Mapping[str, Mapping[str, bool]] | None = None,
) -> bool:
    """优先读用户携带的 capabilities；否则按角色矩阵判断。"""
    if not user:
        return False
    caps = user.get("capabilities")
    if isinstance(caps, (list, tuple, set, frozenset)):
        return code in caps
    return has_capability(str(user.get("role") or "user"), code, matrix)  # type: ignore[arg-type]


def with_resolved_capabilities(
    user: Mapping[str, Any] | None,
    matrix: Mapping[str, Mapping[str, bool]] | None = None,
) -> dict[str, Any]:
    """为模块请求用户补齐 capabilities（模块内解析，不改平台派发）。"""
    payload = dict(user or {})
    if isinstance(payload.get("capabilities"), (list, tuple, set, frozenset)):
        return payload
    role = str(payload.get("role") or "user")
    payload["capabilities"] = capabilities_for_role(role, matrix)  # type: ignore[arg-type]
    return payload


def is_creator(user: Mapping[str, Any] | None, record: Mapping[str, Any]) -> bool:
    user_id = str((user or {}).get("id") or "")
    return bool(user_id) and user_id == str(record.get("creator_user_id") or "")


def can_view(user: Mapping[str, Any] | None) -> bool:
    return user_has_capability(user, "rsp.view")


def can_create(user: Mapping[str, Any] | None) -> bool:
    return user_has_capability(user, "rsp.create")


def can_edit(user: Mapping[str, Any] | None, record: Mapping[str, Any]) -> bool:
    if str(record.get("status")) not in EDITABLE_STATUSES:
        return False
    if not user_has_capability(user, "rsp.edit"):
        return False
    if is_admin(user):
        return True
    return is_creator(user, record)


def can_confirm(user: Mapping[str, Any] | None) -> bool:
    return user_has_capability(user, "rsp.confirm")


def can_transition(source: str, target: str) -> bool:
    return (source, target) in NORMAL_TRANSITIONS


def can_void(user: Mapping[str, Any] | None, record: Mapping[str, Any] | None = None) -> bool:
    if not user_has_capability(user, "rsp.void"):
        return False
    if is_admin(user):
        return True
    if record is None:
        return False
    if str(record.get("status") or "") not in {"draft", "pending", "processing"}:
        return False
    return is_creator(user, record)


def can_reopen(user: Mapping[str, Any] | None, record: Mapping[str, Any] | None = None) -> bool:
    if not user_has_capability(user, "rsp.reopen"):
        return False
    if is_admin(user):
        return True
    if record is None:
        return False
    if str(record.get("status") or "") not in REOPENABLE_STATUSES:
        return False
    return is_creator(user, record)


def can_delete(user: Mapping[str, Any] | None) -> bool:
    return user_has_capability(user, "rsp.delete")
