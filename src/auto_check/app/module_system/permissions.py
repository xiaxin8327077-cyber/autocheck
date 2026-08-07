from __future__ import annotations

from typing import Any, Mapping


#: Map module-local permission names to platform capability codes.
#: This lets modules declare permissions in their own namespace while the
#: platform enforces them using the central capability registry.
_MODULE_PERMISSION_TO_CAPABILITY: dict[str, str] = {
    "report_special_processing.view": "rsp.view",
    "report_special_processing.detail": "rsp.detail",
    "report_special_processing.create": "rsp.create",
    "report_special_processing.edit": "rsp.edit",
    "report_special_processing.confirm": "rsp.confirm",
    "report_special_processing.reopen": "rsp.reopen",
    "report_special_processing.void": "rsp.void",
    "report_special_processing.delete": "rsp.delete",
}


def default_permission_evaluator(
    current_user: Mapping[str, Any] | None,
    permission: str,
) -> bool:
    """Evaluate module route/menu permission against the user's capability list.

    When ``current_user`` includes a ``capabilities`` list (populated by the
    platform), the permission is mapped to a platform capability code and must
    be present in the list. For backwards compatibility, if ``capabilities`` is
    absent, the legacy rule allows any permission ending in ``.view`` for
    non-admin users.
    """
    if not current_user:
        return False
    if str(current_user.get("role") or "") == "admin":
        return True
    capabilities = current_user.get("capabilities")
    if isinstance(capabilities, list):
        capability = _MODULE_PERMISSION_TO_CAPABILITY.get(permission, permission)
        return capability in capabilities
    return permission.endswith(".view")
