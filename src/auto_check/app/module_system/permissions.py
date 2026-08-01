from __future__ import annotations

from typing import Any, Mapping


def default_permission_evaluator(
    current_user: Mapping[str, Any] | None,
    permission: str,
) -> bool:
    """Apply the initial, role-based module permission policy."""
    if not current_user:
        return False
    if str(current_user.get("role") or "") == "admin":
        return True
    return permission.endswith(".view")
