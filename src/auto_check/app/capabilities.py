"""角色与能力（权限点）注册表。

支持平台级能力矩阵：系统内建角色 + 可扩展自定义角色 + 能力码（菜单/功能）。
业务侧统一通过 :func:`has_capability` 判断，避免写死 ``role == "xxx"``。

能力码分两种 type：
- ``menu``：进入某页面/菜单的访问权
- ``function``：执行某操作的权限点

锁定不变式：
- admin 列恒为 True，不可改写（:func:`assert_admin_column_unchanged`）
- :data:`REQUIRED_CAPABILITIES` 对全部角色必选，不可设 False（:func:`assert_required_unchanged`）
- :data:`ADMIN_ONLY_CAPABILITIES` 仅 admin 可勾选，非 admin 角色设 True 拒绝（:func:`assert_admin_only_unchanged`）

报表特殊处理（RSP）的 ``rsp.*`` 能力码一期**仅注册展示**，运行时不接通 RSP
业务鉴权；二期再一次性接通状态迁移与新流程按钮。
"""

from __future__ import annotations

#: 管理员角色码；该角色在能力矩阵中锁定，UI 与后端均拒绝改写。
LOCKED_ROLE = "admin"

#: 能力类型。
TYPE_MENU = "menu"
TYPE_FUNCTION = "function"

#: 角色码 → 中文显示名。仅保留管理员与普通用户；其余角色通过「新增角色」创建。
ROLE_DEFINITIONS: dict[str, str] = {
    "admin": "管理员",
    "user": "普通用户",
}

#: 已下线的内建预留角色（历史账号读取时映射为普通用户）。
REMOVED_BUILTIN_ROLES: frozenset[str] = frozenset(
    {"governance", "regulatory_report", "data_middle", "fund_custody"}
)

#: 系统内建角色码集合（与自定义角色区分）。
SYSTEM_ROLES: frozenset[str] = frozenset(ROLE_DEFINITIONS)

#: 向后兼容：KNOWN_ROLES 仍指系统内建角色（动态角色由应用库 role_definitions 提供）。
KNOWN_ROLES: frozenset[str] = SYSTEM_ROLES

#: 「标准档」角色集合：默认能力与现网普通用户一致。
STANDARD_TIER_ROLES: frozenset[str] = frozenset({"user"})

#: 能力码 → {label, type}。新功能上线时在此追加，并在默认矩阵补默认值。
CAPABILITY_DEFINITIONS: dict[str, dict[str, str]] = {
    "menu.report_navigation": {"label": "进入报送导航页", "type": TYPE_MENU},
    "menu.home": {"label": "进入对数总览", "type": TYPE_MENU},
    "menu.auto_check": {"label": "进入对数执行", "type": TYPE_MENU},
    "menu.history": {"label": "进入对数历史", "type": TYPE_MENU},
    "menu.tools": {"label": "进入工具页", "type": TYPE_MENU},
    "sys.settings": {"label": "进入系统设置页", "type": TYPE_MENU},
    "sys.settings.admin": {"label": "系统设置页管理员专属配置", "type": TYPE_FUNCTION},
    "sys.users": {"label": "用户管理", "type": TYPE_MENU},
    "sys.role_permissions": {"label": "角色权限配置页", "type": TYPE_MENU},
    "history.delete": {"label": "删除对数历史记录", "type": TYPE_FUNCTION},
    "report_navigation.edit_schedule": {"label": "编辑报送日期", "type": TYPE_FUNCTION},
    "report_navigation.edit_stats": {"label": "编辑数据治理统计", "type": TYPE_FUNCTION},
    # 以下 rsp.* 一期仅注册展示，运行时不接通 RSP 业务鉴权。
    "rsp.view": {"label": "页面查看", "type": TYPE_MENU},
    "rsp.detail": {"label": "查看详情", "type": TYPE_FUNCTION},
    "rsp.create": {"label": "新增", "type": TYPE_FUNCTION},
    "rsp.edit": {"label": "编辑", "type": TYPE_FUNCTION},
    "rsp.confirm": {"label": "确认", "type": TYPE_FUNCTION},
    "rsp.void": {"label": "作废", "type": TYPE_FUNCTION},
    "rsp.reopen": {"label": "重开", "type": TYPE_FUNCTION},
    "rsp.delete": {"label": "删除", "type": TYPE_FUNCTION},
}

#: 旧能力码 → 新能力码（读取矩阵时自动继承旧值，落盘后为全新结构）。
LEGACY_CAPABILITY_MIGRATIONS: dict[str, tuple[str, ...]] = {
    "menu.smart_reconcile": ("menu.home", "menu.auto_check", "menu.history"),
    "report_navigation.admin": (
        "report_navigation.edit_schedule",
        "report_navigation.edit_stats",
    ),
}

#: 必选能力：全部角色必须为 True，不可取消勾选。
REQUIRED_CAPABILITIES: frozenset[str] = frozenset({"menu.report_navigation"})

#: 仅管理员可勾选的能力：非 admin 角色设为 True 将被拒绝。
ADMIN_ONLY_CAPABILITIES: frozenset[str] = frozenset(
    {
        "sys.settings.admin",
        "sys.users",
        "sys.role_permissions",
    }
)

#: 标准档默认为 True 的能力码（与现网普通用户行为一致）。
_STANDARD_TIER_TRUE: frozenset[str] = frozenset(
    {
        "menu.report_navigation",
        "menu.home",
        "menu.auto_check",
        "menu.history",
        "menu.tools",
        "sys.settings",
        "rsp.view",
        "rsp.detail",
        "rsp.create",
        "rsp.edit",
        "rsp.void",
        "rsp.reopen",
    }
)


def _standard_tier_defaults() -> dict[str, bool]:
    """标准档角色的默认能力值（与现网普通用户行为一致）。"""
    return {
        code: (code in _STANDARD_TIER_TRUE) for code in CAPABILITY_DEFINITIONS
    }


#: 默认能力矩阵：role → capability → allowed。admin 列锁定不可改。
DEFAULT_MATRIX: dict[str, dict[str, bool]] = {
    "admin": {code: True for code in CAPABILITY_DEFINITIONS},
    "user": _standard_tier_defaults(),
}

#: 自定义角色的默认矩阵：等同 user 标准档。
CUSTOM_ROLE_DEFAULT_MATRIX: dict[str, bool] = _standard_tier_defaults()


def default_matrix_for_role(role: str) -> dict[str, bool]:
    """返回某角色的默认能力矩阵（系统角色用 DEFAULT_MATRIX，自定义角色用标准档）。"""
    if role in DEFAULT_MATRIX:
        return dict(DEFAULT_MATRIX[role])
    return dict(CUSTOM_ROLE_DEFAULT_MATRIX)


def all_known_roles(custom_roles: list[str] | None = None) -> list[str]:
    """系统内建角色 + 自定义角色的有序列表（系统角色在前，admin 在首）。"""
    roles = list(ROLE_DEFINITIONS.keys())
    extras = [r for r in (custom_roles or []) if r not in ROLE_DEFINITIONS]
    return roles + extras


def merge_matrix(
    stored: dict[str, dict[str, bool]] | None,
    custom_roles: list[str] | None = None,
) -> dict[str, dict[str, bool]]:
    """将已保存矩阵与默认矩阵合并：只补缺失项，不覆盖已存值。

    - 角色集 = 系统内建 ∪ 自定义角色（``custom_roles``）；其它未知角色丢弃
    - 仅保留 ``CAPABILITY_DEFINITIONS`` 内的能力码，未知能力丢弃
    - 已存值经 ``bool()`` 归一后保留，缺失项取该角色默认矩阵值
    - 自定义角色默认等同 user 标准档
    - 旧能力码自动迁移：新码缺失且旧码存在时继承旧码值
      （:data:`LEGACY_CAPABILITY_MIGRATIONS`），落盘后为全新结构
    """
    stored = stored or {}
    roles = all_known_roles(custom_roles)
    merged: dict[str, dict[str, bool]] = {}
    for role in roles:
        stored_role = stored.get(role, {})
        defaults = default_matrix_for_role(role)
        migrated = dict(stored_role)
        for legacy_code, new_codes in LEGACY_CAPABILITY_MIGRATIONS.items():
            if legacy_code in stored_role:
                for new_code in new_codes:
                    if new_code not in migrated:
                        migrated[new_code] = bool(stored_role[legacy_code])
        merged[role] = {
            code: bool(migrated[code]) if code in migrated else bool(defaults[code])
            for code in CAPABILITY_DEFINITIONS
        }
    return merged


def sanitize_admin_only(
    stored: dict[str, dict[str, bool]] | None,
) -> dict[str, dict[str, bool]]:
    """清洗历史矩阵：管理员专属能力（``ADMIN_ONLY_CAPABILITIES``）对非 admin 角色强制为 False。

    旧版本无 admin-only 约束，历史矩阵可能把管理员专属能力授予非 admin
    角色；若不清洗，后续任何保存都会被 ``assert_admin_only_unchanged``
    拒绝。仅在读取路径使用——保存路径仍由 assert 拒绝新传入的违规值。
    """
    stored = stored or {}
    sanitized = {role: dict(caps) for role, caps in stored.items()}
    for role, caps in sanitized.items():
        if role == LOCKED_ROLE:
            continue
        for code in ADMIN_ONLY_CAPABILITIES:
            caps[code] = False
    return sanitized


def sanitize_required(
    stored: dict[str, dict[str, bool]] | None,
) -> dict[str, dict[str, bool]]:
    """清洗历史矩阵：必选能力（``REQUIRED_CAPABILITIES``）对全部角色强制为 True。

    旧版本无必选约束，历史矩阵可能把必选能力（如 ``menu.report_navigation``）
    设为 False；若不清洗，前端显示未勾选且任何保存都会被
    ``assert_required_unchanged`` 拒绝。仅在读取路径使用——保存路径仍由
    assert 拒绝新传入的违规值。
    """
    stored = stored or {}
    sanitized = {role: dict(caps) for role, caps in stored.items()}
    for role, caps in sanitized.items():
        for code in REQUIRED_CAPABILITIES:
            caps[code] = True
    return sanitized


DEFAULT_ROLE_REMARKS: dict[str, str] = {
    "admin": "系统最高权限，列锁定不可改",
    "user": "兼容现网账号",
}


def merge_remarks(
    stored: dict[str, str] | None,
    custom_role_remarks: dict[str, str] | None = None,
) -> dict[str, str]:
    """合并角色备注：已存值保留，缺失取默认。

    - 系统内建角色取 :data:`DEFAULT_ROLE_REMARKS`（可被 ``stored`` 覆盖）
    - 自定义角色以 ``custom_role_remarks``（``role_definitions.remark``）为准，
      避免 ``remarks_json`` 旧快照盖住角色定义表中的最新备注
    - 保留已存但未在两源中的角色备注（避免矩阵与备注不同步时丢数据）
    """
    stored = stored or {}
    merged: dict[str, str] = {}
    for role, default_remark in DEFAULT_ROLE_REMARKS.items():
        merged[role] = str(stored.get(role, "") or default_remark)
    for role, remark in (custom_role_remarks or {}).items():
        if role in DEFAULT_ROLE_REMARKS:
            continue
        merged[role] = str(remark or "")
    for role, value in stored.items():
        if role in REMOVED_BUILTIN_ROLES:
            continue
        if role not in merged:
            merged[role] = str(value or "")
    return merged


def _resolve_role_matrix(
    role: str, matrix: dict[str, dict[str, bool]] | None
) -> dict[str, bool]:
    """从给定矩阵取某角色的能力字典；未知角色回退到标准档。"""
    if matrix is not None:
        return matrix.get(role) or matrix.get("user") or {}
    if role in DEFAULT_MATRIX:
        return DEFAULT_MATRIX[role]
    return CUSTOM_ROLE_DEFAULT_MATRIX


def has_capability(
    role: str, capability: str, matrix: dict[str, dict[str, bool]] | None = None
) -> bool:
    """判断某角色在给定矩阵（默认为 :data:`DEFAULT_MATRIX`）下是否具备某能力。

    未知角色按标准档（``user``）处理；未知能力码一律返回 ``False``。
    """
    return bool(_resolve_role_matrix(role, matrix).get(capability, False))


def capabilities_for_role(
    role: str, matrix: dict[str, dict[str, bool]] | None = None
) -> list[str]:
    """列出某角色被允许的能力码（按注册顺序）。未知角色按标准档处理。"""
    role_matrix = _resolve_role_matrix(role, matrix)
    return [code for code in CAPABILITY_DEFINITIONS if bool(role_matrix.get(code, False))]


def is_required(code: str) -> bool:
    """该能力码是否为必选（全角色不可取消）。"""
    return code in REQUIRED_CAPABILITIES


def is_admin_only(code: str) -> bool:
    """该能力码是否仅管理员可勾选。"""
    return code in ADMIN_ONLY_CAPABILITIES


def assert_admin_column_unchanged(
    previous: dict[str, dict[str, bool]] | None,
    incoming: dict[str, dict[str, bool]] | None,
) -> None:
    """校验 admin 列未被改写；任一已注册能力值变化即抛 :class:`ValueError`。"""
    previous_admin = (previous or {}).get(LOCKED_ROLE, {})
    incoming_admin = (incoming or {}).get(LOCKED_ROLE, {})
    for code in CAPABILITY_DEFINITIONS:
        before = bool(previous_admin.get(code))
        after = bool(incoming_admin.get(code))
        if before != after:
            raise ValueError(
                f"admin column is locked: {code} cannot change from {before} to {after}"
            )


def assert_required_unchanged(
    incoming: dict[str, dict[str, bool]] | None,
) -> None:
    """校验必选能力对全部非 admin 角色保持 True。"""
    incoming = incoming or {}
    for role, caps in incoming.items():
        if role == LOCKED_ROLE:
            continue
        for code in REQUIRED_CAPABILITIES:
            if not bool(caps.get(code, True)):
                raise ValueError(
                    f"{code} is required and cannot be disabled for role {role}"
                )


def assert_admin_only_unchanged(
    incoming: dict[str, dict[str, bool]] | None,
) -> None:
    """校验仅管理员能力未被赋予非 admin 角色。"""
    incoming = incoming or {}
    for role, caps in incoming.items():
        if role == LOCKED_ROLE:
            continue
        for code in ADMIN_ONLY_CAPABILITIES:
            if bool(caps.get(code, False)):
                raise ValueError(
                    f"{code} is admin-only and cannot be granted to role {role}"
                )