"""角色能力矩阵注册表的单元测试。

菜单/功能权限细分 + 自定义角色：系统内建仅 admin/user，其余通过自定义角色扩展。
"""

import pytest

from auto_check.app.capabilities import (
    ADMIN_ONLY_CAPABILITIES,
    CAPABILITY_DEFINITIONS,
    CUSTOM_ROLE_DEFAULT_MATRIX,
    DEFAULT_MATRIX,
    DEFAULT_ROLE_REMARKS,
    KNOWN_ROLES,
    LOCKED_ROLE,
    REMOVED_BUILTIN_ROLES,
    REQUIRED_CAPABILITIES,
    ROLE_DEFINITIONS,
    SYSTEM_ROLES,
    TYPE_FUNCTION,
    TYPE_MENU,
    all_known_roles,
    assert_admin_column_unchanged,
    assert_admin_only_unchanged,
    assert_required_unchanged,
    capabilities_for_role,
    default_matrix_for_role,
    has_capability,
    is_admin_only,
    is_required,
    merge_matrix,
    merge_remarks,
    sanitize_admin_only,
    sanitize_required,
)


def test_known_roles_cover_admin_and_user_only():
    assert KNOWN_ROLES == SYSTEM_ROLES
    assert SYSTEM_ROLES == frozenset({"admin", "user"})
    assert LOCKED_ROLE == "admin"
    assert REMOVED_BUILTIN_ROLES == frozenset(
        {"governance", "regulatory_report", "data_middle", "fund_custody"}
    )
    for role in SYSTEM_ROLES:
        assert ROLE_DEFINITIONS[role]


def test_capability_definitions_cover_all_registered_codes_with_type():
    expected_codes = {
        "menu.report_navigation",
        "menu.home",
        "menu.auto_check",
        "menu.history",
        "menu.tools",
        "sys.settings",
        "sys.settings.admin",
        "sys.users",
        "sys.role_permissions",
        "history.delete",
        "report_navigation.edit_schedule",
        "report_navigation.edit_stats",
        "rsp.view",
        "rsp.detail",
        "rsp.create",
        "rsp.edit",
        "rsp.confirm",
        "rsp.void",
        "rsp.reopen",
        "rsp.delete",
    }
    assert set(CAPABILITY_DEFINITIONS) == expected_codes
    for code in expected_codes:
        entry = CAPABILITY_DEFINITIONS[code]
        assert entry["label"]
        assert entry["type"] in (TYPE_MENU, TYPE_FUNCTION)


def test_legacy_capabilities_no_longer_registered():
    assert "menu.smart_reconcile" not in CAPABILITY_DEFINITIONS
    assert "report_navigation.admin" not in CAPABILITY_DEFINITIONS


def test_required_and_admin_only_subsets_are_disjoint():
    assert REQUIRED_CAPABILITIES.issubset(set(CAPABILITY_DEFINITIONS))
    assert ADMIN_ONLY_CAPABILITIES.issubset(set(CAPABILITY_DEFINITIONS))
    assert not (REQUIRED_CAPABILITIES & ADMIN_ONLY_CAPABILITIES)


def test_is_required_and_is_admin_only():
    assert is_required("menu.report_navigation") is True
    assert is_required("sys.settings") is False
    assert is_admin_only("sys.users") is True
    assert is_admin_only("sys.role_permissions") is True
    assert is_admin_only("sys.settings.admin") is True
    assert is_admin_only("history.delete") is False
    assert is_admin_only("report_navigation.edit_schedule") is False
    assert is_admin_only("report_navigation.edit_stats") is False
    assert is_admin_only("rsp.delete") is False
    assert is_admin_only("rsp.view") is False


def test_default_user_tier_capabilities():
    assert has_capability("user", "menu.report_navigation") is True
    assert has_capability("user", "menu.home") is True
    assert has_capability("user", "menu.auto_check") is True
    assert has_capability("user", "menu.history") is True
    assert has_capability("user", "menu.tools") is True
    assert has_capability("user", "sys.settings") is True
    assert has_capability("user", "sys.settings.admin") is False
    assert has_capability("user", "sys.users") is False
    assert has_capability("user", "sys.role_permissions") is False
    assert has_capability("user", "history.delete") is False
    assert has_capability("user", "report_navigation.edit_schedule") is False
    assert has_capability("user", "report_navigation.edit_stats") is False
    assert has_capability("user", "rsp.view") is True
    assert has_capability("user", "rsp.create") is True
    assert has_capability("user", "rsp.edit") is True
    assert has_capability("user", "rsp.confirm") is False
    assert has_capability("user", "rsp.void") is True
    assert has_capability("user", "rsp.reopen") is True
    assert has_capability("user", "rsp.delete") is False


def test_removed_builtin_roles_are_dropped_from_default_matrix():
    assert "governance" not in DEFAULT_MATRIX
    assert "regulatory_report" not in DEFAULT_MATRIX
    assert "data_middle" not in DEFAULT_MATRIX
    assert "fund_custody" not in DEFAULT_MATRIX
    merged = merge_matrix(
        {
            "governance": {"rsp.confirm": True},
            "regulatory_report": {"sys.settings": False},
        }
    )
    assert "governance" not in merged
    assert "regulatory_report" not in merged


def test_admin_has_all_registered_capabilities():
    for code in CAPABILITY_DEFINITIONS:
        assert has_capability("admin", code) is True


def test_unknown_role_falls_back_to_user_tier():
    assert has_capability("unknown_role", "menu.home") is True
    assert has_capability("unknown_role", "sys.users") is False
    assert has_capability("unknown_role", "rsp.create") is True


def test_unknown_capability_returns_false():
    assert has_capability("admin", "does.not.exist") is False
    assert has_capability("user", "does.not.exist") is False


def test_merge_none_returns_full_default_matrix():
    assert merge_matrix(None) == DEFAULT_MATRIX


def test_merge_fills_missing_without_overwriting_saved():
    stored = {"user": {"sys.settings": False}}
    merged = merge_matrix(stored)
    assert merged["user"]["sys.settings"] is False
    assert "history.delete" in merged["user"]
    assert merged["user"]["history.delete"] is False
    assert merged["user"]["rsp.view"] is True
    assert merged["admin"]["history.delete"] is True


def test_merge_drops_unknown_roles_and_capabilities():
    stored = {
        "ghost_role": {"sys.settings": True},
        "user": {"sys.settings": True, "ghost.capability": True},
    }
    merged = merge_matrix(stored)
    assert "ghost_role" not in merged
    assert "ghost.capability" not in merged["user"]
    assert merged["user"]["sys.settings"] is True


def test_sanitize_admin_only_cleans_historical_grant():
    stored = {
        "user": {"sys.users": True, "sys.role_permissions": True, "sys.settings": False},
    }
    sanitized = sanitize_admin_only(stored)
    assert sanitized["user"]["sys.users"] is False
    assert sanitized["user"]["sys.role_permissions"] is False
    assert sanitized["user"]["sys.settings"] is False
    admin_row = {"sys.users": True, "sys.role_permissions": True}
    cleaned_admin = sanitize_admin_only({"admin": admin_row})
    assert cleaned_admin["admin"]["sys.users"] is True
    assert stored["user"]["sys.users"] is True


def test_merge_migrates_legacy_capability_values():
    stored = {
        "user": {"menu.smart_reconcile": False},
        "admin": {"report_navigation.admin": True},
    }
    merged = merge_matrix(stored)
    assert merged["user"]["menu.home"] is False
    assert merged["user"]["menu.auto_check"] is False
    assert merged["user"]["menu.history"] is False
    assert merged["admin"]["report_navigation.edit_schedule"] is True
    assert merged["admin"]["report_navigation.edit_stats"] is True
    stored2 = {"user": {"menu.smart_reconcile": False, "menu.home": True}}
    merged2 = merge_matrix(stored2)
    assert merged2["user"]["menu.home"] is True
    assert merged2["user"]["menu.auto_check"] is False


def test_sanitize_required_cleans_historical_disable():
    stored = {
        "user": {"menu.report_navigation": False, "sys.settings": False},
    }
    sanitized = sanitize_required(stored)
    assert sanitized["user"]["menu.report_navigation"] is True
    assert sanitized["user"]["sys.settings"] is False
    assert stored["user"]["menu.report_navigation"] is False


def test_admin_column_lock_rejects_change():
    previous = merge_matrix(None)
    incoming = merge_matrix(None)
    incoming["admin"]["history.delete"] = False
    with pytest.raises(ValueError, match="admin"):
        assert_admin_column_unchanged(previous, incoming)


def test_admin_column_lock_allows_unchanged():
    previous = merge_matrix(None)
    incoming = merge_matrix(None)
    assert_admin_column_unchanged(previous, incoming)


def test_required_unchanged_rejects_disabling_for_non_admin():
    incoming = merge_matrix(None)
    incoming["user"]["menu.report_navigation"] = False
    with pytest.raises(ValueError, match="required"):
        assert_required_unchanged(incoming)


def test_required_unchanged_allows_admin_disabling():
    incoming = merge_matrix(None)
    incoming["admin"]["menu.report_navigation"] = False
    assert_required_unchanged(incoming)


def test_admin_only_unchanged_rejects_granting_to_non_admin():
    incoming = merge_matrix(None)
    incoming["user"]["sys.users"] = True
    with pytest.raises(ValueError, match="admin-only"):
        assert_admin_only_unchanged(incoming)


def test_admin_only_unchanged_allows_admin():
    incoming = merge_matrix(None)
    assert_admin_only_unchanged(incoming)


def test_capabilities_for_role_lists_allowed_only():
    codes = capabilities_for_role("user")
    assert "menu.report_navigation" in codes
    assert "menu.home" in codes
    assert "sys.users" not in codes
    assert "history.delete" not in codes
    assert "rsp.confirm" not in codes
    assert "rsp.delete" not in codes


def test_capabilities_for_admin_lists_all_registered():
    codes = capabilities_for_role("admin")
    assert set(codes) == set(CAPABILITY_DEFINITIONS)


def test_capabilities_for_unknown_role_falls_back_to_user_tier():
    codes = capabilities_for_role("ghost")
    assert "menu.home" in codes
    assert "sys.users" not in codes


def test_has_capability_with_explicit_matrix_overrides_default():
    custom = merge_matrix({"user": {"sys.users": True}})
    assert has_capability("user", "sys.users", custom) is True
    assert has_capability("user", "sys.users") is False


def test_default_role_remarks_cover_all_builtin_roles():
    assert set(DEFAULT_ROLE_REMARKS) == SYSTEM_ROLES


def test_merge_remarks_fills_missing_with_defaults():
    merged = merge_remarks({"user": "自定义备注", "governance": "旧预留备注"})
    assert merged["user"] == "自定义备注"
    assert merged["admin"] == DEFAULT_ROLE_REMARKS["admin"]
    assert "governance" not in merged


def test_merge_remarks_none_returns_defaults():
    assert merge_remarks(None) == DEFAULT_ROLE_REMARKS


def test_all_known_roles_combines_builtin_and_custom():
    roles = all_known_roles(["custom_auditor"])
    assert roles[: len(SYSTEM_ROLES)] == list(ROLE_DEFINITIONS.keys())
    assert "custom_auditor" in roles


def test_default_matrix_for_custom_role_equals_user_tier():
    custom = default_matrix_for_role("custom_auditor")
    assert custom == CUSTOM_ROLE_DEFAULT_MATRIX
    assert custom["menu.report_navigation"] is True
    assert custom["sys.users"] is False


def test_merge_matrix_includes_custom_roles():
    merged = merge_matrix({"custom_auditor": {"sys.settings": False}}, custom_roles=["custom_auditor"])
    assert "custom_auditor" in merged
    assert merged["custom_auditor"]["sys.settings"] is False
    assert merged["custom_auditor"]["menu.report_navigation"] is True
    assert merged["custom_auditor"]["sys.users"] is False


def test_merge_matrix_strips_custom_role_not_in_list():
    stored = {"custom_orphan": {"sys.settings": True}}
    merged = merge_matrix(stored, custom_roles=[])
    assert "custom_orphan" not in merged


def test_merge_remarks_supports_custom_roles():
    custom_remarks = {"custom_auditor": "自定义审计角色"}
    # 自定义角色以 role_definitions 备注为准，不被 remarks_json 旧快照覆盖
    merged = merge_remarks({"custom_auditor": "已存备注"}, custom_role_remarks=custom_remarks)
    assert merged["custom_auditor"] == "自定义审计角色"
    merged2 = merge_remarks(None, custom_role_remarks=custom_remarks)
    assert merged2["custom_auditor"] == "自定义审计角色"


def test_admin_only_lock_rejects_custom_role_granting_admin_capability():
    incoming = merge_matrix(None, custom_roles=["custom_auditor"])
    incoming["custom_auditor"]["sys.users"] = True
    with pytest.raises(ValueError, match="admin-only"):
        assert_admin_only_unchanged(incoming)


def test_required_lock_rejects_custom_role_disabling_required():
    incoming = merge_matrix(None, custom_roles=["custom_auditor"])
    incoming["custom_auditor"]["menu.report_navigation"] = False
    with pytest.raises(ValueError, match="required"):
        assert_required_unchanged(incoming)
